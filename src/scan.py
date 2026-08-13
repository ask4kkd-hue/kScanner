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
from backtest import _passes_conditions, load_symbol_frame
from config import CFG, config_hash, resolve_preset
from db import connect, init_schema
from universe import active_universe
from validate import data_is_stale

log = logging.getLogger("scan")

PAT = CFG["pattern"]
BT = CFG["backtest"]


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
         apply_preset: bool = True) -> pd.DataFrame:
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
    log.info("Universe after liquidity/series/surveillance filters: %d", len(uni))

    start = as_of - timedelta(days=int(lookback_bars * 1.6))
    rows = []

    for _, s in uni.iterrows():
        df = load_symbol_frame(con, s["isin"], start, as_of)
        if len(df) < 260:
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
            "preset_name": preset_name, "timeframe": "1d",
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
            fdf = con.execute("""
                SELECT * FROM features_1d WHERE isin = ? AND date = ?
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
    ap.add_argument("--export", action="store_true", help="write an xlsx to exports/")
    ap.add_argument("--ignore-stale", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    con = connect()
    init_schema(con)

    df = scan(con, args.preset, ignore_stale=args.ignore_stale)
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
