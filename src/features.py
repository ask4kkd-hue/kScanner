"""
features.py — the declarative feature registry.

THE "EVERYTHING IS OPTIONAL" DESIGN
-----------------------------------
Features are DECLARED, not hard-coded into a pipeline. Each declaration names
its dependencies, its warm-up requirement, and which columns it produces.

You enable features in config.yaml. Enabling `supertrend` automatically pulls
in `atr14` even if you never listed it — dependencies are resolved
transitively and topologically sorted. Disabled features are neither computed
nor stored.

TWO PASSES
----------
Pass 1 is per-symbol (SMA, ATR, ADX...).
Pass 2 is cross-sectional (relative strength rank) and can only run AFTER
pass 1 has finished for the ENTIRE universe. Computing ranks against a
partial universe produces numbers that look completely plausible and are wrong.

WARM-UP
-------
Every feature declares min_bars. Indicators return values long before those
values are trustworthy — ADX(14) needs roughly 150 bars because it is
double-smoothed, not the 14 you would expect. `bars_available` is stored on
every row so scans can gate on it.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from typing import Callable, Dict, List

import numpy as np
import pandas as pd

import indicators as ind
from config import CFG, config_hash
from db import connect, init_schema

log = logging.getLogger("features")

P = CFG["features"]["params"]


# =====================================================================
# FEATURE FUNCTIONS  (each takes the symbol frame, returns a dict of Series)
# =====================================================================

def _f_sma(df, n):
    return {f"sma{n}": ind.sma(df["close"], n)}


def f_sma10(df, ctx):   return _f_sma(df, 10)
def f_sma20(df, ctx):   return _f_sma(df, 20)
def f_sma50(df, ctx):   return _f_sma(df, 50)
def f_sma100(df, ctx):  return _f_sma(df, 100)
def f_sma200(df, ctx):  return _f_sma(df, 200)


def f_sma_slope(df, ctx):
    """Direction matters as much as position. 'close > sma200 while sma200
    is falling' is a different trade from the same test in a rising trend."""
    n = P["sma_slope_length"]
    return {
        "sma50_slope": ind.slope_pct(ctx["sma50"], n),
        "sma200_slope": ind.slope_pct(ctx["sma200"], n),
    }


def f_sma_shape(df, ctx):
    """Stack alignment and compression across the whole SMA family."""
    smas = ["sma10", "sma20", "sma50", "sma100", "sma200"]
    mat = pd.concat([ctx[s] for s in smas], axis=1)
    mat.columns = smas

    up = pd.Series(True, index=df.index)
    dn = pd.Series(True, index=df.index)
    for i in range(len(smas) - 1):
        up &= mat[smas[i]] > mat[smas[i + 1]]
        dn &= mat[smas[i]] < mat[smas[i + 1]]

    stack = pd.Series("mixed", index=df.index, dtype=object)
    stack[up] = "stacked_up"
    stack[dn] = "stacked_down"
    stack[mat.isna().any(axis=1)] = "unknown"

    compression = (mat.max(axis=1) - mat.min(axis=1)) / df["close"] * 100.0
    return {"sma_stack": stack, "sma_compression": compression}


def f_ema(df, ctx):
    return {"ema10": ind.ema(df["close"], 10), "ema21": ind.ema(df["close"], 21)}


def f_hma10(df, ctx):
    return {"hma10": ind.hma(df["close"], 10)}


def f_hma50(df, ctx):
    return {"hma50": ind.hma(df["close"], 50)}


def f_atr14(df, ctx):
    return {"atr14": ind.atr(df["high"], df["low"], df["close"], P["atr_length"])}


def f_adr(df, ctx):
    """The filter most likely to matter: a 1.2% ADR stock structurally cannot
    deliver 5% in seven days without a gap."""
    return {"adr_pct20": ind.adr_pct(df["high"], df["low"], P["adr_length"])}


def f_rsi(df, ctx):
    return {"rsi14": ind.rsi(df["close"], P["rsi_length"])}


def f_adx(df, ctx):
    a, p, m = ind.adx(df["high"], df["low"], df["close"], P["adx_length"])
    return {"adx14": a, "di_plus": p, "di_minus": m}


def f_supertrend(df, ctx):
    line, direction = ind.supertrend(
        df["high"], df["low"], df["close"],
        P["supertrend_length"], P["supertrend_mult"])
    return {"supertrend": line, "st_dir": direction}


def f_bollinger(df, ctx):
    mid, up, lo, w = ind.bollinger(df["close"], P["bb_length"], P["bb_mult"])
    return {"bb_mid": mid, "bb_upper": up, "bb_lower": lo, "bb_width": w}


def f_macd(df, ctx):
    line, sig, _ = ind.macd(df["close"])
    return {"macd": line, "macd_signal": sig}


def f_rvol(df, ctx):
    n = P["vol_length"]
    return {
        "vol_sma20": df["volume"].rolling(n, min_periods=n).mean(),
        "rvol": ind.rvol(df["volume"], n),
    }


def f_turnover(df, ctx):
    """Liquidity in RUPEES. 100,000 shares of a Rs 8 stock is nothing;
    of a Rs 3,000 stock it is enormous."""
    n = P["vol_length"]
    to = df["close"] * df["volume"]
    return {"turnover": to, "turnover_sma20": to.rolling(n, min_periods=n).mean()}


def f_delivery(df, ctx):
    """Delivery % separates accumulation from intraday churn — the single most
    useful India-specific field, and it is free in the bhavcopy."""
    n = P["vol_length"]
    dp = df.get("deliv_pct")
    if dp is None:
        return {}
    base = dp.rolling(n, min_periods=max(5, n // 2)).mean()
    trades = df.get("no_of_trades")
    ats = (df["volume"] / trades.replace(0, np.nan)) if trades is not None else None
    out = {"deliv_pct_sma20": base, "deliv_surge": dp / base.replace(0, np.nan)}
    if ats is not None:
        out["avg_trade_size"] = ats
    return out


def f_position(df, ctx):
    hi52 = df["high"].rolling(252, min_periods=100).max()
    lo52 = df["low"].rolling(252, min_periods=100).min()
    return {
        "dist_sma200_pct": ind.pct_distance(df["close"], ctx["sma200"]),
        "dist_52w_high_pct": ind.pct_distance(df["close"], hi52),
        "dist_52w_low_pct": ind.pct_distance(df["close"], lo52),
    }


def f_ret_55d(df, ctx):
    n = P["rs_lookback"]
    return {"ret_55d": (df["close"] / df["close"].shift(n) - 1.0) * 100.0}


# =====================================================================
# REGISTRY
# =====================================================================

REGISTRY: Dict[str, dict] = {
    "sma10":      {"deps": [], "min_bars": 10,  "fn": f_sma10,  "outputs": ["sma10"]},
    "sma20":      {"deps": [], "min_bars": 20,  "fn": f_sma20,  "outputs": ["sma20"]},
    "sma50":      {"deps": [], "min_bars": 50,  "fn": f_sma50,  "outputs": ["sma50"]},
    "sma100":     {"deps": [], "min_bars": 100, "fn": f_sma100, "outputs": ["sma100"]},
    "sma200":     {"deps": [], "min_bars": 200, "fn": f_sma200, "outputs": ["sma200"]},

    "sma_slope":  {"deps": ["sma50", "sma200"], "min_bars": 220,
                   "fn": f_sma_slope, "outputs": ["sma50_slope", "sma200_slope"]},
    "sma_shape":  {"deps": ["sma10", "sma20", "sma50", "sma100", "sma200"],
                   "min_bars": 200, "fn": f_sma_shape,
                   "outputs": ["sma_stack", "sma_compression"]},

    "ema":        {"deps": [], "min_bars": 30,  "fn": f_ema,   "outputs": ["ema10", "ema21"]},
    "hma10":      {"deps": [], "min_bars": 20,  "fn": f_hma10, "outputs": ["hma10"]},
    "hma50":      {"deps": [], "min_bars": 70,  "fn": f_hma50, "outputs": ["hma50"]},

    # ATR needs ~100 bars for Wilder smoothing to settle, not 14.
    "atr14":      {"deps": [], "min_bars": 100, "fn": f_atr14, "outputs": ["atr14"]},
    "adr_pct20":  {"deps": [], "min_bars": 25,  "fn": f_adr,   "outputs": ["adr_pct20"]},
    "rsi14":      {"deps": [], "min_bars": 100, "fn": f_rsi,   "outputs": ["rsi14"]},

    # ADX is DOUBLE-smoothed: ~150 bars before the values mean anything.
    "adx14":      {"deps": [], "min_bars": 150, "fn": f_adx,
                   "outputs": ["adx14", "di_plus", "di_minus"]},

    "supertrend": {"deps": ["atr14"], "min_bars": 100, "fn": f_supertrend,
                   "outputs": ["supertrend", "st_dir"]},
    "bollinger":  {"deps": [], "min_bars": 25, "fn": f_bollinger,
                   "outputs": ["bb_mid", "bb_upper", "bb_lower", "bb_width"]},
    "macd":       {"deps": [], "min_bars": 60, "fn": f_macd,
                   "outputs": ["macd", "macd_signal"]},

    "rvol":       {"deps": [], "min_bars": 25, "fn": f_rvol,
                   "outputs": ["vol_sma20", "rvol"]},
    "turnover":   {"deps": [], "min_bars": 25, "fn": f_turnover,
                   "outputs": ["turnover", "turnover_sma20"]},
    "delivery":   {"deps": [], "min_bars": 25, "fn": f_delivery,
                   "outputs": ["deliv_pct_sma20", "deliv_surge", "avg_trade_size"]},

    "position":   {"deps": ["sma200"], "min_bars": 200, "fn": f_position,
                   "outputs": ["dist_sma200_pct", "dist_52w_high_pct",
                               "dist_52w_low_pct"]},

    "ret_55d":    {"deps": [], "min_bars": 60, "fn": f_ret_55d, "outputs": ["ret_55d"]},

    # PASS 2 — cross-sectional. Needs every symbol's pass-1 output first.
    "rs_rank":    {"deps": ["ret_55d"], "min_bars": 60, "pass": 2, "fn": None,
                   "outputs": ["rs_vs_bench", "rs_rank_pct"]},
}


def resolve_enabled(enabled: List[str]) -> List[str]:
    """
    Expand the enabled list to include transitive dependencies, then
    topologically sort so each feature runs after everything it needs.
    """
    seen, order = set(), []

    def visit(name: str, stack: tuple = ()):
        if name in seen:
            return
        if name in stack:
            raise ValueError(f"Circular feature dependency: {' -> '.join(stack + (name,))}")
        spec = REGISTRY.get(name)
        if spec is None:
            raise KeyError(f"Unknown feature '{name}'. Known: {sorted(REGISTRY)}")
        for d in spec["deps"]:
            visit(d, stack + (name,))
        seen.add(name)
        order.append(name)

    for n in enabled:
        visit(n)
    return order


def feature_version(enabled: List[str]) -> str:
    """Stamped on every row. This is what lets you answer, months from now,
    'did my hit rate change because the DATA changed or because I did?'"""
    return config_hash({"features": sorted(enabled), "params": P})


# =====================================================================
# PASS 1
# =====================================================================

def compute_symbol(df: pd.DataFrame, order: List[str]) -> pd.DataFrame:
    """Run pass-1 features for one symbol. df must be sorted by date ascending."""
    df = df.sort_values("date").reset_index(drop=True)
    ctx: Dict[str, pd.Series] = {}
    out = pd.DataFrame({"date": df["date"]})

    for name in order:
        spec = REGISTRY[name]
        if spec.get("pass", 1) != 1 or spec["fn"] is None:
            continue
        produced = spec["fn"](df, ctx)
        for col, series in produced.items():
            ctx[col] = series
            out[col] = series.values

    out["bars_available"] = np.arange(1, len(df) + 1)
    return out


def build_features(con, isins: List[str] | None = None,
                   rebuild_from: date | None = None,
                   full: bool = False) -> int:
    """
    Compute and store pass-1 features.

    Incremental runs recompute the last (250 + lookback) bars per symbol —
    SMA200 needs 200 bars of context, so a shorter window would produce wrong
    values at the join. Full rebuilds drop and recreate everything.
    """
    enabled = CFG["features"]["enabled"]
    order = resolve_enabled(enabled)
    fv = feature_version(enabled)
    warm = P["warmup_discard_bars"]

    if full:
        con.execute("DELETE FROM features_1d")
        log.info("Full rebuild: features_1d cleared")

    if isins is None:
        isins = con.execute(
            "SELECT DISTINCT isin FROM bars_1d ORDER BY isin").df()["isin"].tolist()

    log.info("Computing %d features for %d symbols (version %s)",
             len(order), len(isins), fv)

    total = 0
    for i, isin in enumerate(isins, 1):
        bars = con.execute("""
            SELECT date, open, high, low, close, volume, vwap,
                   deliv_pct, no_of_trades
            FROM bars_1d WHERE isin = ? ORDER BY date
        """, [isin]).df()
        if len(bars) < 30:
            continue

        feats = compute_symbol(bars, order)
        feats["isin"] = isin
        feats["feature_version"] = fv

        # Discard the warm-up region: those rows HAVE values and the values
        # are wrong. This is the quietest failure mode in the whole system.
        feats = feats[feats["bars_available"] > warm]
        if rebuild_from is not None:
            feats = feats[pd.to_datetime(feats["date"]).dt.date >= rebuild_from]
        if feats.empty:
            continue

        _upsert_features(con, feats)
        total += len(feats)

        if i % 100 == 0:
            log.info("  %d/%d symbols, %d rows", i, len(isins), total)

    log.info("Pass 1 complete: %d rows", total)
    return total


def _upsert_features(con, feats: pd.DataFrame) -> None:
    cols = con.execute("PRAGMA table_info('features_1d')").df()["name"].tolist()
    for c in cols:
        if c not in feats.columns:
            feats[c] = None
    con.register("tmp_feat", feats[cols])
    con.execute("""
        INSERT INTO features_1d SELECT * FROM tmp_feat
        ON CONFLICT (isin, date) DO UPDATE SET
            """ + ", ".join(f"{c} = excluded.{c}" for c in cols
                            if c not in ("isin", "date")))
    con.unregister("tmp_feat")


# =====================================================================
# PASS 2 — cross-sectional
# =====================================================================

def build_rs_rank(con) -> int:
    """
    Relative strength rank across the universe, per date.

    MUST run after pass 1 has completed for every symbol. Ranking against a
    partial universe gives numbers that look right and are not.

    rs_rank_pct is a percentile within that DATE's universe — so a backtest
    reading it is ranking against the universe as it existed then, not today's.
    """
    if "rs_rank" not in CFG["features"]["enabled"]:
        log.info("rs_rank disabled; skipping pass 2")
        return 0

    bench = CFG["universe"]["benchmark"]
    n = P["rs_lookback"]

    rows = con.execute("""
        WITH bench AS (
            SELECT date, close,
                   close / LAG(close, ?) OVER (ORDER BY date) - 1.0 AS bench_ret
            FROM index_bars WHERE index_name = ?
        )
        SELECT f.isin, f.date, f.ret_55d, b.bench_ret * 100.0 AS bench_ret_pct
        FROM features_1d f
        LEFT JOIN bench b ON b.date = f.date
        WHERE f.ret_55d IS NOT NULL
    """, [n, bench]).df()

    if rows.empty:
        log.warning("No ret_55d rows; run pass 1 first")
        return 0

    rows["rs_vs_bench"] = rows["ret_55d"] - rows["bench_ret_pct"].fillna(0.0)
    rows["rs_rank_pct"] = (
        rows.groupby("date")["ret_55d"].rank(pct=True) * 100.0
    )

    con.register("tmp_rs", rows[["isin", "date", "rs_vs_bench", "rs_rank_pct"]])
    con.execute("""
        UPDATE features_1d f SET
            rs_vs_bench = t.rs_vs_bench,
            rs_rank_pct = t.rs_rank_pct
        FROM tmp_rs t
        WHERE f.isin = t.isin AND f.date = t.date
    """)
    con.unregister("tmp_rs")
    log.info("Pass 2 complete: %d rows ranked", len(rows))
    return len(rows)


# =====================================================================
# CLI
# =====================================================================

def main() -> None:
    ap = argparse.ArgumentParser(description="Build the feature layer.")
    ap.add_argument("--full", action="store_true",
                    help="full rebuild (do this weekly — see the design doc)")
    ap.add_argument("--from-date", help="rebuild from this date onward (YYYY-MM-DD)")
    ap.add_argument("--symbol", help="single symbol, for debugging")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    con = connect()
    init_schema(con)

    isins = None
    if args.symbol:
        isins = con.execute("SELECT isin FROM instruments WHERE symbol = ?",
                            [args.symbol]).df()["isin"].tolist()

    rebuild_from = pd.to_datetime(args.from_date).date() if args.from_date else None
    build_features(con, isins=isins, rebuild_from=rebuild_from, full=args.full)
    build_rs_rank(con)
    con.close()


if __name__ == "__main__":
    main()
