"""
api/services/today.py — port of web/pages/today.py's render() into one aggregate call.

Must stay fast (<2s — v2_instructions.md's original requirement, still true here): reads
the already-persisted signals_1d table, never runs a live scan.scan() (that's the Scan
screen's manual "Run scan" button, ~1-2 minutes).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

import journal as jr
import scoring
import watchlist as wl
from config import CFG
from db import table_counts
from scan import regime_state
from validate import data_is_stale

from api.services.holdings import list_open_positions


def _tracked_symbols(con) -> set[str]:
    held = con.execute("SELECT DISTINCT symbol FROM trades WHERE status = 'open'") \
        .df()["symbol"].tolist()
    watched = con.execute("SELECT DISTINCT symbol FROM watchlist").df()["symbol"].tolist()
    return set(held) | set(watched)


def _num(v) -> float | None:
    return float(v) if v is not None and v == v else None  # NaN != NaN


def _latest_signals(con, timeframe: str, as_of_date: date | None = None):
    # signals_1d's key is (scan_date, isin, preset_name, timeframe) -- a symbol
    # matching more than one preset on the same day gets one row per preset.
    # "New Opportunities" cares whether a symbol has a fresh signal at all, not
    # how many presets happened to flag it, so this collapses to one row per
    # symbol (trigger/L1/L2/stop/target/etc are identical across presets for
    # the same symbol+date since they come from the same underlying pattern,
    # so ANY_VALUE is exact, not an approximation).
    #
    # as_of_date, when given, pins the scan_date instead of always taking the
    # latest -- this is what lets New Opportunity browse T-1/T-2/... history.
    # A date with no stored rows for this timeframe just returns empty, never
    # silently substitutes a different date under that label.
    #
    # Resolved in Python first, then always passed as a concrete date -- a
    # bare None bound into a parameterized query has already bitten this
    # codebase once (journal.update_open_trades' NULL-isin bug: DuckDB
    # infers a DOUBLE parameter type from a lone None with no other type
    # context and the query throws), so the same shape isn't repeated here.
    if as_of_date is None:
        row = con.execute(
            "SELECT MAX(scan_date) FROM signals_1d WHERE timeframe = ?", [timeframe]
        ).fetchone()
        as_of_date = row[0] if row else None
    if as_of_date is None:
        return pd.DataFrame()

    return con.execute("""
        SELECT s.symbol,
              ANY_VALUE(s.isin) AS isin,
              ANY_VALUE(s.scan_date) AS scan_date,
              ANY_VALUE(s.trigger_price) AS trigger_price,
              ANY_VALUE(s.l1_price) AS l1_price,
              ANY_VALUE(s.l2_price) AS l2_price,
              ANY_VALUE(s.neckline) AS neckline,
              ANY_VALUE(s.depth_pct) AS depth_pct,
              ANY_VALUE(s.stop_suggested) AS stop_suggested,
              ANY_VALUE(s.target_suggested) AS target_suggested,
              ANY_VALUE(s.bottom_at_sma) AS bottom_at_sma,
              ANY_VALUE(s.sma_stack) AS sma_stack,
              ANY_VALUE(f.rs_rank_pct) AS rs_rank_pct,
              ANY_VALUE(f.adr_pct20) AS adr_pct
        FROM signals_1d s
        LEFT JOIN features_1d f ON f.isin = s.isin AND f.date = s.scan_date
        WHERE s.timeframe = ? AND s.scan_date = ?
        GROUP BY s.symbol
        ORDER BY rs_rank_pct DESC NULLS LAST
    """, [timeframe, as_of_date]).df()


def _signal_outcomes(con, sig: pd.DataFrame) -> pd.DataFrame:
    """
    Descriptive-only forward outcome of each signal: did price hit the
    suggested stop or target AFTER the signal's own scan_date, using bars
    actually stored since then? Reports what already happened, never a
    forecast -- same spirit as advisor.py's "descriptive, never predictive"
    rule. For the latest/today's signal there is no bar after scan_date yet,
    so this naturally comes back all-None, no special-casing required.

    One bulk bars_1d query for the whole signal set (bounded by isin IN (...)
    and typically ~10-30 rows) rather than one query per symbol -- same
    bulk-over-per-symbol reasoning as features.py's _bulk_fetch_all_bars.
    """
    if sig.empty:
        return sig.assign(outcome_status=None, outcome_date=None, pct_since_signal=None)

    scan_date = sig["scan_date"].iloc[0]
    isins = sig["isin"].dropna().tolist()
    if not isins:
        return sig.assign(outcome_status=None, outcome_date=None, pct_since_signal=None)

    con.register("tmp_outcome_isins", pd.DataFrame({"isin": isins}))
    bars = con.execute("""
        SELECT b.isin, b.date, b.high, b.low, b.close
        FROM bars_1d b JOIN tmp_outcome_isins t ON t.isin = b.isin
        WHERE b.date > ?
        ORDER BY b.isin, b.date
    """, [scan_date]).df()
    con.unregister("tmp_outcome_isins")

    by_isin = {isin: g for isin, g in bars.groupby("isin", sort=False)}
    # Daily bars can't resolve intraday order when both stop and target are
    # touched the same day -- resolve the same way backtest.py's
    # simulate_exit does (config.backtest.same_day_stop_and_target), so a
    # signal's reported outcome always agrees with how the backtest itself
    # would have scored it.
    favor_stop = CFG["backtest"]["same_day_stop_and_target"] == "stop"

    statuses, hit_dates, pcts = [], [], []
    for _, r in sig.iterrows():
        fwd = by_isin.get(r["isin"])
        trigger = float(r["trigger_price"])
        stop = _num(r["stop_suggested"])
        target = _num(r["target_suggested"])

        if fwd is None or fwd.empty:
            statuses.append(None)
            hit_dates.append(None)
            pcts.append(None)
            continue

        status, hit_date = None, None
        for _, b in fwd.iterrows():
            hit_stop = stop is not None and b["low"] <= stop
            hit_target = target is not None and b["high"] >= target
            if hit_stop or hit_target:
                if hit_stop and hit_target:
                    status = "SL hit" if favor_stop else "Target hit"
                else:
                    status = "SL hit" if hit_stop else "Target hit"
                hit_date = str(b["date"])
                break

        latest_close = float(fwd["close"].iloc[-1])
        if status is None:
            status = "Towards target" if latest_close > trigger else "Open for trade"
        pct = (latest_close - trigger) / trigger * 100.0 if trigger else None

        statuses.append(status)
        hit_dates.append(hit_date)
        pcts.append(pct)

    return sig.assign(outcome_status=statuses, outcome_date=hit_dates, pct_since_signal=pcts)


def available_scan_dates(con, timeframe: str) -> list[str]:
    """Distinct scan dates actually stored for this timeframe, newest first --
    drives the New Opportunity screen's T-1/T-2/T-3/T-4 quick-select (which
    means "the previous scanned date", not a raw calendar-day subtraction)
    and bounds the date-picker to dates that actually have data."""
    df = con.execute("""
        SELECT DISTINCT scan_date FROM signals_1d
        WHERE timeframe = ? ORDER BY scan_date DESC LIMIT 30
    """, [timeframe]).df()
    return [str(d) for d in df["scan_date"]]


def _status(con) -> dict:
    stale, latest_bar, latest_cal = data_is_stale(con)
    fails = con.execute("""
        SELECT COUNT(*) FROM validation_log
        WHERE passed = FALSE AND date >= CURRENT_DATE - INTERVAL 7 DAY
    """).fetchone()[0]
    regime = regime_state(con, date.today())

    sessions_behind = None
    if stale and latest_bar and latest_cal:
        sessions_behind = con.execute("""
            SELECT COUNT(*) FROM trading_calendar
            WHERE bhavcopy_available AND date > ? AND date <= ?
        """, [latest_bar, latest_cal]).fetchone()[0]

    return {
        "stale": stale, "latest_bar": latest_bar, "latest_cal": latest_cal,
        "validation_fails_7d": fails, "regime": regime, "sessions_behind": sessions_behind,
    }


def _score_fields(r, calibration: dict | None) -> dict:
    """1D-only (see scoring.py docstring): backtest.py has no timeframe
    parameter, so 1W/1M signals have no comparable historical ground truth
    to score against yet -- calibration is None for those, and every field
    here comes back None rather than a fabricated number."""
    empty = {
        "quality_score": None, "quality_score_max": None, "quality_checklist": None,
        "historical_hit_rate_pct": None, "historical_sample_size": None, "historical_thin": None,
    }
    if calibration is None:
        return empty
    result = scoring.score_signal(
        {"rs_rank_pct": r.get("rs_rank_pct"), "depth_pct": r.get("depth_pct"), "adr_pct": r.get("adr_pct")},
        calibration,
    )
    if result is None:
        return empty
    return {
        "quality_score": result["score"],
        "quality_score_max": result["max_score"],
        "quality_checklist": result["checklist"],
        "historical_hit_rate_pct": result["historical_hit_rate_pct"],
        "historical_sample_size": result["historical_sample_size"],
        "historical_thin": result["historical_thin"],
    }


def _opportunities(con, tracked: set[str], as_of_date: date | None = None) -> list[dict]:
    blocks = []
    # Computed once, reused for every 1D signal below -- cheap (tens of
    # thousands of backtest_trades rows, not millions), so no caching needed.
    calibration = scoring.calibrate(con, CFG["backtest"]["min_trades_for_conclusion"])
    for timeframe, features_table in (("1d", "features_1d"), ("1w", "features_1w"), ("1m", "features_1m")):
        built = True
        if timeframe != "1d":
            n = con.execute(f"SELECT COUNT(*) FROM {features_table}").fetchone()[0]
            built = bool(n)
        if not built:
            blocks.append({
                "timeframe": timeframe, "built": False, "total_signals": 0,
                "new_signals": [], "already_tracked_count": 0,
            })
            continue

        sig = _latest_signals(con, timeframe, as_of_date)
        sig = _signal_outcomes(con, sig)
        new_sig = sig[~sig["symbol"].isin(tracked)] if not sig.empty else sig
        already = sig[sig["symbol"].isin(tracked)] if not sig.empty else sig
        blocks.append({
            "timeframe": timeframe, "built": True, "total_signals": len(sig),
            "already_tracked_count": len(already),
            # Full list, uncapped -- the New Opportunity screen needs all of
            # it; Dashboard's own condensed preview slices client-side.
            "new_signals": [
                {
                    "symbol": r["symbol"],
                    "trigger_price": float(r["trigger_price"]),
                    "l1_price": _num(r["l1_price"]),
                    "l2_price": _num(r["l2_price"]),
                    # (L1-L2)/L1 % -- how deep the second bottom undercut the
                    # first, as a percentage of L1's own price.
                    "l1_l2_distance_pct": (
                        (float(r["l1_price"]) - float(r["l2_price"])) / float(r["l1_price"]) * 100.0
                        if r["l1_price"] == r["l1_price"] and r["l2_price"] == r["l2_price"]
                        and r["l1_price"] != 0 else None
                    ),
                    "neckline": _num(r["neckline"]),
                    "depth_pct": _num(r["depth_pct"]),
                    "stop_suggested": _num(r["stop_suggested"]),
                    "target_suggested": _num(r["target_suggested"]),
                    "bottom_at_sma": r["bottom_at_sma"] if r["bottom_at_sma"] == r["bottom_at_sma"] else None,
                    "sma_stack": r["sma_stack"] if r["sma_stack"] == r["sma_stack"] else None,
                    "rs_rank_pct": _num(r["rs_rank_pct"]),
                    # iterrows() returns each row as one mixed-dtype Series --
                    # combined with the float64 columns in the same row, a
                    # real None in these object columns silently becomes NaN,
                    # same reason bottom_at_sma/sma_stack above need the same
                    # self-inequality check.
                    "outcome_status": r["outcome_status"] if r["outcome_status"] == r["outcome_status"] else None,
                    "outcome_date": r["outcome_date"] if r["outcome_date"] == r["outcome_date"] else None,
                    "pct_since_signal": _num(r["pct_since_signal"]),
                    **_score_fields(r, calibration if timeframe == "1d" else None),
                }
                for _, r in new_sig.iterrows()
            ],
        })
    return blocks


def _pnl(con, positions: list[dict]) -> dict:
    closed = con.execute("SELECT exit_date, net_pnl FROM trades WHERE status = 'closed'").df()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    def realised_since(cutoff) -> float:
        if closed.empty:
            return 0.0
        # closed["exit_date"] comes back from DuckDB as datetime64[us]; pandas
        # now rejects comparing that dtype directly against a plain
        # datetime.date (TypeError), so cutoff needs to be a Timestamp too.
        m = closed["exit_date"] >= pd.Timestamp(cutoff)
        return float(closed.loc[m, "net_pnl"].sum())

    unrealised = sum(
        (p["_close"] - p["entry_price"]) * p["qty"] for p in positions if p["_close"] is not None
    )

    return {
        "today": realised_since(today),
        "this_week": realised_since(week_start),
        "this_month": realised_since(month_start),
        "all_time": float(closed["net_pnl"].sum()) if not closed.empty else 0.0,
        "unrealised": unrealised,
    }


def get_opportunities(con, as_of_date: date | None = None) -> list[dict]:
    """
    Dedicated entry point for New Opportunity's own date browsing (T-1/T-2/...
    and the free date-picker) -- deliberately separate from get_today(), which
    also drives Dashboard's live positions/P&L/equity-curve that should never
    be date-shifted. New Opportunity has only ever read the `opportunities`
    block off get_today() anyway, so this is a narrower, focused fetch of
    exactly that, with the one extra as_of_date parameter Dashboard has no use
    for.
    """
    tracked = _tracked_symbols(con)
    return _opportunities(con, tracked, as_of_date)


def get_today(con) -> dict:
    tracked = _tracked_symbols(con)
    positions = list_open_positions(con)

    total_open_pnl = sum(
        (p["_close"] or p["entry_price"]) * p["qty"] - p["entry_price"] * p["qty"] for p in positions
    )
    at_risk = sum(1 for p in positions if p["status"] in ("WATCH", "REVIEW"))

    curve = jr.equity_curve(con)
    equity_curve = (
        [{"exit_date": str(d), "cum_pnl": float(v)}
         for d, v in zip(curve["exit_date"], curve["cum_pnl"])]
        if not curve.empty else []
    )

    near = wl.list_with_status(con)
    near = near[near.get("near_trigger", False) == True] if not near.empty else near  # noqa: E712

    return {
        "status": _status(con),
        "positions": [{k: v for k, v in p.items() if k != "_close"} for p in positions],
        "total_open_pnl": total_open_pnl,
        "at_risk_count": at_risk,
        "opportunities": _opportunities(con, tracked),
        "pnl": _pnl(con, positions),
        "equity_curve": equity_curve,
        "watchlist_near_trigger": [
            {"symbol": r["symbol"], "close": r.get("close"),
             "target_price": r.get("target_price"), "neckline": r.get("neckline")}
            for _, r in near.iterrows()
        ] if not near.empty else [],
    }
