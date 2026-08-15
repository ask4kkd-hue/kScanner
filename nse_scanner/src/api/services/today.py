"""
api/services/today.py — port of web/pages/today.py's render() into one aggregate call.

Must stay fast (<2s — v2_instructions.md's original requirement, still true here): reads
the already-persisted signals_1d table, never runs a live scan.scan() (that's the Scan
screen's manual "Run scan" button, ~1-2 minutes).
"""

from __future__ import annotations

from datetime import date, timedelta

import journal as jr
import watchlist as wl
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


def _latest_signals(con, timeframe: str):
    # signals_1d's key is (scan_date, isin, preset_name, timeframe) -- a symbol
    # matching more than one preset on the same day gets one row per preset.
    # "New Opportunities" cares whether a symbol has a fresh signal at all, not
    # how many presets happened to flag it, so this collapses to one row per
    # symbol (trigger/L1/L2/stop/target/etc are identical across presets for
    # the same symbol+date since they come from the same underlying pattern,
    # so ANY_VALUE is exact, not an approximation).
    return con.execute("""
        WITH latest AS (SELECT MAX(scan_date) AS d FROM signals_1d WHERE timeframe = ?)
        SELECT s.symbol,
              ANY_VALUE(s.trigger_price) AS trigger_price,
              ANY_VALUE(s.l1_price) AS l1_price,
              ANY_VALUE(s.l2_price) AS l2_price,
              ANY_VALUE(s.neckline) AS neckline,
              ANY_VALUE(s.depth_pct) AS depth_pct,
              ANY_VALUE(s.stop_suggested) AS stop_suggested,
              ANY_VALUE(s.target_suggested) AS target_suggested,
              ANY_VALUE(s.bottom_at_sma) AS bottom_at_sma,
              ANY_VALUE(s.sma_stack) AS sma_stack,
              ANY_VALUE(f.rs_rank_pct) AS rs_rank_pct
        FROM signals_1d s
        JOIN latest ON s.scan_date = latest.d
        LEFT JOIN features_1d f ON f.isin = s.isin AND f.date = s.scan_date
        WHERE s.timeframe = ?
        GROUP BY s.symbol
        ORDER BY rs_rank_pct DESC NULLS LAST
    """, [timeframe, timeframe]).df()


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


def _opportunities(con, tracked: set[str]) -> list[dict]:
    blocks = []
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

        sig = _latest_signals(con, timeframe)
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
                    "l1_l2_distance": (
                        float(r["l1_price"]) - float(r["l2_price"])
                        if r["l1_price"] == r["l1_price"] and r["l2_price"] == r["l2_price"] else None
                    ),
                    "neckline": _num(r["neckline"]),
                    "depth_pct": _num(r["depth_pct"]),
                    "stop_suggested": _num(r["stop_suggested"]),
                    "target_suggested": _num(r["target_suggested"]),
                    "bottom_at_sma": r["bottom_at_sma"] if r["bottom_at_sma"] == r["bottom_at_sma"] else None,
                    "sma_stack": r["sma_stack"] if r["sma_stack"] == r["sma_stack"] else None,
                    "rs_rank_pct": _num(r["rs_rank_pct"]),
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
        m = closed["exit_date"] >= cutoff
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
