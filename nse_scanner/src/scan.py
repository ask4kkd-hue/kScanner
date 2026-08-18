"""
scan.py — the live scanner.

Calls the SAME pattern code as backtest.py. The only difference is that this
runs with as_of = the latest bar. If the two ever diverge, every backtest
conclusion becomes untransferable to live trading.

Before scanning it refuses to run on stale data. Manual operation means one
day you WILL open the app four days after your last ingest and act on a signal
that is no longer true. The guard is the thing that prevents that.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

import indicators as ind
import patterns as pat
import resample as rs
from backtest import _passes_conditions, load_symbol_frame
from config import CFG, config_hash, resolve_preset
from db import connect, init_schema
from universe import active_universe
from validate import data_is_stale

log = logging.getLogger("scan")

PAT = CFG["pattern"]
BT = CFG["backtest"]

FEATURES_TABLE = {"1d": "features_1d", "1w": "features_1w", "1m": "features_1m"}

# W-pattern needs max_separation+buffer bars just to be structurally
# possible; sma200/sma100 warm-up on top of that assumes daily-scale
# history most symbols don't have at weekly/monthly granularity (200
# monthly bars is ~17 years). Lower thresholds here are not a
# looser pattern rule — find_w_patterns/PAT are unchanged — they just
# stop discarding every weekly/monthly symbol before it's even tried.
# A preset that references sma200 will still legitimately find nothing
# on 1m for a young symbol; that is an honest result, not a bug.
MIN_BARS = {"1d": 260, "1w": 80, "1m": 40}


def load_symbol_frame_tf(con, isin: str, date_to: date, timeframe: str = "1d",
                         lookback_days: int | None = None) -> pd.DataFrame:
    """
    Timeframe-aware bars+features loader.

    "1d" is a straight passthrough to backtest.load_symbol_frame (byte-
    identical behavior, nothing about the daily path changes). "1w"/"1m"
    resample the SAME bars_1d history via resample.py — never a separate
    bars_1w/1m table, matching every other place this project handles
    weekly/monthly — then join the result against features_1w/features_1m
    by date. That join is safe because features.py computes those tables
    on the exact same resample-labelled dates (see resample.py's
    _resample_by_session: each bar is dated by its last real session).
    """
    if timeframe == "1d":
        date_from = date_to - timedelta(days=lookback_days or 700)
        return load_symbol_frame(con, isin, date_from, date_to)

    # Weekly/monthly patterns need years of raw daily history to have
    # enough resampled bars to be structurally possible (see chart.py's
    # docstring) -- reuse the same lookback the Chart screen relies on
    # for exactly this reason, rather than inventing a second constant.
    date_from = date_to - timedelta(days=int(CFG["chart"]["pattern_lookback_bars"] * 1.6))
    daily = con.execute("""
        SELECT date, open, high, low, close, volume, vwap
        FROM bars_1d WHERE isin = ? AND date BETWEEN ? AND ?
        ORDER BY date
    """, [isin, date_from, date_to]).df()
    if daily.empty:
        return daily

    bars_df = rs.to_weekly(daily) if timeframe == "1w" else rs.to_monthly(daily)
    if bars_df.empty:
        return bars_df

    feats = con.execute(f"""
        SELECT date, sma10, sma20, sma50, sma100, sma200,
               sma50_slope, sma200_slope, sma_stack, sma_compression,
               atr14, adr_pct20, adx14, rsi14,
               turnover_sma20, deliv_pct_sma20, rvol,
               dist_sma200_pct, rs_rank_pct, bars_available
        FROM {FEATURES_TABLE[timeframe]} WHERE isin = ? AND date BETWEEN ? AND ?
    """, [isin, date_from, date_to]).df()

    return bars_df.merge(feats, on="date", how="left").sort_values("date").reset_index(drop=True)


def _bulk_fetch_tf_frames(con, isins: list[str], as_of: date, timeframe: str) -> dict:
    """
    Bulk equivalent of load_symbol_frame_tf's "1w"/"1m" branch for the WHOLE
    universe, in two queries total instead of two queries PER SYMBOL -- same
    bulk-over-per-symbol fix features.py's _bulk_fetch_all_bars already
    applied to feature-building (there: ~2000 symbols x 1 query -> 1 query),
    now applied here to scanning (there: ~2000 symbols x 2 queries -> 2
    queries), which is what made a full-universe 1w/1m scan impractically
    slow. Only used for timeframe != "1d" -- the daily path keeps its own
    per-symbol windowed fetch in load_symbol_frame_tf, unchanged, since its
    "never re-touch an already-stored date" reasoning is specific to that
    narrow window.

    Returns {isin: DataFrame} with the SAME shape load_symbol_frame_tf
    returns per symbol (resampled bars merged with that timeframe's
    features), so the per-symbol scan loop below doesn't need two code
    paths for how a frame is built, only for how it's fetched.
    """
    date_from = as_of - timedelta(days=int(CFG["chart"]["pattern_lookback_bars"] * 1.6))

    con.register("tmp_scan_isins", pd.DataFrame({"isin": isins}))
    daily = con.execute("""
        SELECT b.isin, b.date, b.open, b.high, b.low, b.close, b.volume, b.vwap
        FROM bars_1d b JOIN tmp_scan_isins t ON t.isin = b.isin
        WHERE b.date BETWEEN ? AND ?
        ORDER BY b.isin, b.date
    """, [date_from, as_of]).df()
    feats = con.execute(f"""
        SELECT f.isin, f.date, f.sma10, f.sma20, f.sma50, f.sma100, f.sma200,
               f.sma50_slope, f.sma200_slope, f.sma_stack, f.sma_compression,
               f.atr14, f.adr_pct20, f.adx14, f.rsi14,
               f.turnover_sma20, f.deliv_pct_sma20, f.rvol,
               f.dist_sma200_pct, f.rs_rank_pct, f.bars_available
        FROM {FEATURES_TABLE[timeframe]} f JOIN tmp_scan_isins t ON t.isin = f.isin
        WHERE f.date BETWEEN ? AND ?
    """, [date_from, as_of]).df()
    con.unregister("tmp_scan_isins")

    daily_by_isin = {isin: g.drop(columns="isin") for isin, g in daily.groupby("isin", sort=False)}
    feats_by_isin = {isin: g.drop(columns="isin") for isin, g in feats.groupby("isin", sort=False)}
    # A symbol with zero rows in the whole bulk features fetch never gets a
    # groupby entry -- fall back to an empty frame with the FULL feature
    # column set (not just "date"), so the merge below still produces every
    # column load_symbol_frame_tf's per-symbol query would (NaN-filled,
    # same as a genuinely empty per-symbol SQL result preserves its
    # SELECT-clause columns).
    empty_feats = pd.DataFrame(columns=[c for c in feats.columns if c != "isin"])

    out = {}
    for isin in isins:
        d = daily_by_isin.get(isin)
        if d is None or d.empty:
            out[isin] = d if d is not None else pd.DataFrame()
            continue
        bars_df = rs.to_weekly(d) if timeframe == "1w" else rs.to_monthly(d)
        if bars_df.empty:
            out[isin] = bars_df
            continue
        f = feats_by_isin.get(isin, empty_feats)
        out[isin] = bars_df.merge(f, on="date", how="left").sort_values("date").reset_index(drop=True)
    return out


def current_as_of(con) -> date:
    """The same date scan()'s own `as_of = as_of or MAX(bars_1d.date)` resolves to,
    exposed so callers (the scan-result cache) can key on it without duplicating
    that resolution logic and risking the two drifting apart."""
    d = con.execute("SELECT MAX(date) FROM bars_1d").fetchone()[0]
    return pd.to_datetime(d).date() if isinstance(d, str) else d


def regime_state(con, as_of: date) -> str:
    """
    Index vs its 200 DMA. Applied only when filters.use_regime_filter is on —
    but always COMPUTED, because you cannot A/B test a filter you have no
    data for.
    """
    idx = CFG["filters"]["regime_index"]
    df = con.execute("""
        SELECT date, close FROM index_bars
        WHERE index_name = ? AND date <= ? ORDER BY date
    """, [idx, as_of]).df()
    if len(df) < 220:
        return "unknown"
    sma200 = df["close"].rolling(200).mean()
    sma50 = df["close"].rolling(50).mean()
    c, s200, s50 = df["close"].iloc[-1], sma200.iloc[-1], sma50.iloc[-1]
    if np.isnan(s200):
        return "unknown"
    if c > s200 and c > s50:
        return "bull"
    if c < s200 and c < s50:
        return "bear"
    return "neutral"


def scan(con, preset_name: str, as_of: date | None = None,
         lookback_bars: int = 400, ignore_stale: bool = False,
         apply_preset: bool = True, timeframe: str = "1d",
         limit_symbols: int | None = None) -> pd.DataFrame:
    """
    Find W-patterns whose entry trigger fires on (or just before) as_of.

    apply_preset=True (default, unchanged behaviour): also apply the
    preset's own conditions and the relative-strength filter — this is
    what backtest.py and the CLI keep using.

    apply_preset=False: apply ONLY the pattern rules and the hard
    tradability filters already baked into active_universe() (EQ series,
    ASM/GSM exclusion, minimum liquidity) — skip the preset's conditions
    and the RS filter, and return every features_1d column for the
    signal bar attached to each row, so a caller (the v2 scan screen) can
    filter the superset in-memory with filter chips instead of re-scanning.

    timeframe="1d" (default) is unchanged behaviour end to end. "1w"/"1m"
    run the SAME pattern code and the SAME preset conditions against
    resampled weekly/monthly bars (load_symbol_frame_tf, or in bulk via
    _bulk_fetch_tf_frames for the whole universe at once) instead of daily
    ones — universe membership, staleness, and regime stay daily-derived,
    since weekly/monthly bars are themselves derived from bars_1d and a
    stale daily feed makes every timeframe stale.

    limit_symbols: cap the universe to a quick trial subset (same purpose
    as backtest.py's --limit) -- useful for trying a 1m scan against, say,
    50 symbols before committing to the full universe.
    """
    if CFG["validation"]["abort_scan_if_stale"] and not ignore_stale:
        stale, latest_bar, latest_cal = data_is_stale(con)
        if stale:
            raise RuntimeError(
                f"STALE DATA — latest stored bar is {latest_bar} but the last "
                f"trading day is {latest_cal}. Run ingest.py before scanning. "
                f"(Override with --ignore-stale if you know what you are doing.)"
            )

    preset = resolve_preset(CFG, preset_name)
    conditions = preset.get("conditions", [])
    as_of = as_of or con.execute("SELECT MAX(date) FROM bars_1d").fetchone()[0]
    if isinstance(as_of, str):
        as_of = pd.to_datetime(as_of).date()

    regime = regime_state(con, as_of)
    log.info("Scanning preset '%s' as of %s | regime=%s", preset_name, as_of, regime)

    if CFG["filters"]["use_regime_filter"] and \
       CFG["filters"]["regime_mode"] == "block" and regime == "bear":
        log.warning("Regime filter is set to BLOCK and the market is bearish — "
                    "no signals will be emitted.")
        return pd.DataFrame()

    uni = active_universe(con, as_of)
    if limit_symbols:
        uni = uni.head(limit_symbols)
    log.info("Universe after liquidity/series/surveillance filters: %d", len(uni))

    bulk_frames = (_bulk_fetch_tf_frames(con, uni["isin"].tolist(), as_of, timeframe)
                  if timeframe != "1d" else None)

    rows = []

    for _, s in uni.iterrows():
        if bulk_frames is not None:
            df = bulk_frames.get(s["isin"], pd.DataFrame())
        else:
            df = load_symbol_frame_tf(con, s["isin"], as_of, timeframe,
                                      lookback_days=int(lookback_bars * 1.6))
        if len(df) < MIN_BARS[timeframe]:
            continue

        atr_series = df["atr14"]
        if atr_series.isna().all():
            atr_series = ind.atr(df["high"], df["low"], df["close"])

        found = pat.find_w_patterns(
            df, atr_series,
            zigzag_pct=PAT["zigzag_pct"],
            min_separation=PAT["min_separation"],
            max_separation=PAT["max_separation"],
            require_undercut=PAT["require_undercut"],
            min_depth_pct=PAT["min_depth_pct"],
            exclude_locked_bars=PAT["exclude_locked_bars"],
            confirm_max_wait=PAT["entry_max_wait"],
        )
        if not found:
            continue

        # One row per symbol: the single most-recent pattern with a fresh,
        # real entry trigger — never "whichever candidate came last in the
        # raw list." Same selection rule the chart uses, so the signal list
        # and the chart markup always agree on why a symbol is here.
        picked = pat.select_active_pattern(
            df, found, entry_variant="E2", max_wait=PAT["entry_max_wait"],
            max_bars_since_trigger=2,
        )
        if picked is None:
            continue
        p, sig_pos = picked

        row = df.iloc[sig_pos]
        if apply_preset:
            if not _passes_conditions(row, conditions):
                continue
            if CFG["filters"]["use_relative_strength"]:
                rs = row.get("rs_rank_pct")
                if rs is None or np.isnan(rs) or rs < CFG["filters"]["rs_rank_min_pct"]:
                    continue

        atr_at = float(atr_series.iloc[p.l2_pos])
        stop = p.l2_price - BT["stop_atr_mult"] * (atr_at if not np.isnan(atr_at) else 0)

        out_row = {
            "scan_date": as_of,
            "isin": s["isin"], "symbol": s["symbol"],
            "preset_name": preset_name, "timeframe": timeframe,
            "signal_type": "w_double_bottom",
            "trigger_price": float(row["close"]),
            "l1_date": df["date"].iloc[p.l1_pos], "l1_price": p.l1_price,
            "l2_date": df["date"].iloc[p.l2_pos], "l2_price": p.l2_price,
            "neckline": p.neckline, "depth_pct": p.depth_pct,
            "separation": p.separation,
            "stop_suggested": stop,
            "target_suggested": p.neckline + (p.neckline - p.l2_price),
            "bottom_at_sma": pat.classify_bottom_vs_sma(
                df, p, {k: df[k] for k in
                        ("sma20", "sma50", "sma100", "sma200") if k in df},
                atr_series),
            "sma_stack": row.get("sma_stack"),
            "feature_version": None,
            "config_hash": config_hash(preset),
        }

        if not apply_preset:
            fdf = con.execute(f"""
                SELECT * FROM {FEATURES_TABLE[timeframe]} WHERE isin = ? AND date = ?
            """, [s["isin"], df["date"].iloc[sig_pos]]).df()
            if not fdf.empty:
                extra = fdf.iloc[0].to_dict()
                extra.pop("isin", None)
                extra.pop("date", None)
                out_row.update(extra)

        rows.append(out_row)

    out = pd.DataFrame(rows)
    log.info("Signals: %d", len(out))
    return out


def filter_to_preset(df: pd.DataFrame, preset_name: str) -> pd.DataFrame:
    """
    Given an apply_preset=False scan() result (the pattern + hard-filter
    superset, every feature column attached), derive exactly what an
    apply_preset=True scan of the same preset would have found — without
    re-scanning. Reuses the SAME _passes_conditions/RS-filter logic scan()
    applies inline, so this can never drift from what a live scan finds;
    it is a filter over already-computed rows, not a second implementation.
    """
    if df.empty:
        return df
    preset = resolve_preset(CFG, preset_name)
    conditions = preset.get("conditions", [])
    mask = df.apply(lambda row: _passes_conditions(row, conditions), axis=1)
    out = df[mask]
    if CFG["filters"]["use_relative_strength"] and "rs_rank_pct" in out.columns:
        rs_min = CFG["filters"]["rs_rank_min_pct"]
        out = out[out["rs_rank_pct"].apply(lambda v: v is not None and v == v and v >= rs_min)]
    return out


def store_signals(con, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    cols = con.execute("PRAGMA table_info('signals_1d')").df()["name"].tolist()
    for c in cols:
        if c not in df.columns:
            df[c] = None
    con.register("tmp_sig", df[cols])
    con.execute("""
        INSERT INTO signals_1d SELECT * FROM tmp_sig
        ON CONFLICT (scan_date, isin, preset_name, timeframe) DO NOTHING
    """)
    con.unregister("tmp_sig")
    return len(df)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the live W-pattern scan.")
    ap.add_argument("--preset", default="w_baseline")
    ap.add_argument("--timeframe", default="1d", choices=["1d", "1w", "1m"])
    ap.add_argument("--export", action="store_true", help="write an xlsx to exports/")
    ap.add_argument("--ignore-stale", action="store_true")
    ap.add_argument("--limit", type=int, help="limit symbols (for a quick trial)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    con = connect()
    init_schema(con)

    df = scan(con, args.preset, ignore_stale=args.ignore_stale, timeframe=args.timeframe,
              limit_symbols=args.limit)
    store_signals(con, df)

    if df.empty:
        print("No signals.")
    else:
        print(df[["symbol", "trigger_price", "l2_price", "neckline",
                  "stop_suggested", "bottom_at_sma", "sma_stack"]].to_string(index=False))
        if args.export:
            from pathlib import Path
            out = Path(CFG["paths"]["exports"])
            out.mkdir(parents=True, exist_ok=True)
            f = out / f"signals_{args.preset}_{date.today():%Y%m%d}.xlsx"
            df.to_excel(f, index=False)
            print(f"\nExported -> {f}")

    con.close()


if __name__ == "__main__":
    main()
