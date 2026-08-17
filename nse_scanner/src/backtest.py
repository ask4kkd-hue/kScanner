"""
backtest.py — W-pattern backtest with entry/exit variants and forward curves.

THE RULE THAT MATTERS MOST
--------------------------
The backtest calls the SAME pattern code as the live scanner (patterns.py).
The only difference is that it replays history bar by bar. If you write a
separate backtest implementation you end up testing logic you do not trade
and trading logic you never tested, and the two will never reconcile.

THREE HONESTY RULES BAKED IN
----------------------------
1. Entry is at the NEXT bar's OPEN. The signal is computed after the close,
   so entering at the signal-day close is look-ahead.

2. When stop and target are both touched on the same day, we assume the STOP
   was hit. Daily bars cannot resolve intraday order. Assuming target-first
   is the single most common way backtests inflate results — typically by
   20-40%.

3. Costs are applied. Indian delivery round-trip is roughly 0.25-0.35% plus
   slippage. On a 5% target that is about 6% of the gross gain; on a 2%
   winner, about 15%. A backtest without costs shows an edge that does not
   survive contact with reality.

HOLDING PERIOD IS MEASURED, NOT ASSUMED
---------------------------------------
For every signal we record forward returns, MFE and MAE for N days. The point
where the median MFE curve flattens IS your holding period. The MAE
distribution of eventual WINNERS is where your stop belongs (set it just past
the 85th percentile). See analyse_curves().
"""

from __future__ import annotations

import argparse
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import indicators as ind
import patterns as pat
from config import CFG, config_hash, resolve_preset
from db import connect, init_schema

log = logging.getLogger("backtest")

BT = CFG["backtest"]
COSTS = CFG["costs"]
PAT = CFG["pattern"]

# A pattern triggering on day 1 of a "last N days" report window can have its
# L1 bottom formed max_separation + entry_max_wait (~90) bars earlier, plus
# whatever warm-up the stop/target's own ATR needs. This is how far back
# recent_signals_report() loads data so patterns near the start of the
# window are still structurally detectable -- the report window itself
# (days_back) is a separate, much shorter filter applied AFTER the run.
RECENT_REPORT_LOOKBACK_DAYS = 730


def _pyfloat(x) -> float | None:
    """None/NaN-safe cast to a native python float (never a numpy scalar)."""
    return None if x is None else float(x)


# =====================================================================
# COSTS
# =====================================================================

def round_trip_costs(entry_price: float, exit_price: float, qty: int) -> float:
    """Brokerage + STT + exchange charges + stamp duty + DP, plus slippage."""
    buy_val = entry_price * qty
    sell_val = exit_price * qty
    c = 0.0
    c += (buy_val + sell_val) * COSTS["brokerage_pct"] / 100.0
    c += buy_val * COSTS["stt_buy_pct"] / 100.0
    c += sell_val * COSTS["stt_sell_pct"] / 100.0
    c += (buy_val + sell_val) * COSTS["other_charges_pct"] / 100.0
    c += COSTS["dp_charge_flat"]
    return c


def apply_slippage(price: float, side: str) -> float:
    s = COSTS["slippage_pct"] / 100.0
    return price * (1.0 + s) if side == "buy" else price * (1.0 - s)


# =====================================================================
# EXIT SIMULATION
# =====================================================================

@dataclass
class TradeResult:
    entry_pos: int
    entry_price: float
    exit_pos: int
    exit_price: float
    exit_reason: str
    holding_days: int
    mae_pct: float
    mfe_pct: float


def simulate_exit(
    df: pd.DataFrame,
    entry_pos: int,
    entry_price: float,
    stop: float,
    variant: str,
    extra: Optional[dict] = None,
) -> Optional[TradeResult]:
    """
    Walk forward from entry until an exit rule fires.

    Variants:
      X1 fixed % target        X4 trail below SMA(n)
      X2 R-multiple target     X5 ATR chandelier trail
      X3 measured move         X6 pure time stop, no target
    """
    extra = extra or {}
    n = len(df)
    if entry_pos >= n - 1:
        return None

    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    op = df["open"].to_numpy(dtype=float)

    risk = entry_price - stop
    if risk <= 0:
        return None

    time_stop = BT["time_stop_bars"]

    target = None
    if variant == "X1":
        target = entry_price * (1.0 + BT["target_pct"] / 100.0)
    elif variant == "X2":
        target = entry_price + BT["target_r"] * risk
    elif variant == "X3":
        target = extra.get("measured_move")

    trail_series = extra.get("trail")       # for X4
    atr_series = extra.get("atr")           # for X5

    running_high = entry_price
    mae, mfe = 0.0, 0.0
    cur_stop = stop

    max_pos = min(n - 1, entry_pos + max(time_stop, 1) * 4)

    for i in range(entry_pos, max_pos + 1):
        held = i - entry_pos

        mae = min(mae, (low[i] / entry_price - 1.0) * 100.0)
        mfe = max(mfe, (high[i] / entry_price - 1.0) * 100.0)
        running_high = max(running_high, high[i])

        # trailing stops tighten using YESTERDAY's value (no look-ahead)
        if variant == "X4" and trail_series is not None and i > entry_pos:
            t = np.asarray(trail_series, dtype=float)[i - 1]
            if not np.isnan(t):
                cur_stop = max(cur_stop, t)
        if variant == "X5" and atr_series is not None and i > entry_pos:
            a = np.asarray(atr_series, dtype=float)[i - 1]
            if not np.isnan(a):
                cur_stop = max(cur_stop, running_high - BT["chandelier_atr_mult"] * a)

        hit_stop = low[i] <= cur_stop
        hit_target = (target is not None) and (high[i] >= target)

        if hit_stop and hit_target:
            # HONESTY RULE 2 — daily bars cannot resolve intraday order
            if BT["same_day_stop_and_target"] == "stop":
                px = min(cur_stop, op[i]) if op[i] < cur_stop else cur_stop
                return TradeResult(entry_pos, entry_price, i, px,
                                   "stop_hit_ambiguous", held, mae, mfe)
            return TradeResult(entry_pos, entry_price, i, target,
                               "target_hit_ambiguous", held, mae, mfe)

        if hit_stop:
            # gap through the stop fills at the open, not the stop price
            px = op[i] if op[i] < cur_stop else cur_stop
            return TradeResult(entry_pos, entry_price, i, px, "stop_hit", held, mae, mfe)

        if hit_target:
            px = op[i] if op[i] > target else target
            return TradeResult(entry_pos, entry_price, i, px, "target_hit", held, mae, mfe)

        if held >= time_stop:
            return TradeResult(entry_pos, entry_price, i, close[i],
                               "time_stop", held, mae, mfe)

    last = max_pos
    return TradeResult(entry_pos, entry_price, last, close[last],
                       "end_of_data", last - entry_pos, mae, mfe)


# =====================================================================
# FORWARD CURVES
# =====================================================================

def forward_curve(df: pd.DataFrame, entry_pos: int, entry_price: float,
                  days: int) -> pd.DataFrame:
    """
    Return / MFE / MAE at day 1..N after entry, regardless of exit rule.

    This is the raw material for deriving the holding period. It deliberately
    ignores stops and targets — you want to see what the move DOES, not what
    your current rules capture.
    """
    n = len(df)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)

    rows = []
    run_mfe, run_mae = 0.0, 0.0
    for k in range(1, days + 1):
        i = entry_pos + k
        if i >= n:
            break
        run_mfe = max(run_mfe, (high[i] / entry_price - 1.0) * 100.0)
        run_mae = min(run_mae, (low[i] / entry_price - 1.0) * 100.0)
        rows.append({
            "day_n": k,
            "ret_pct": (close[i] / entry_price - 1.0) * 100.0,
            "mfe_pct": run_mfe,
            "mae_pct": run_mae,
        })
    return pd.DataFrame(rows)


# =====================================================================
# RUN
# =====================================================================

def load_symbol_frame(con, isin: str, date_from: date, date_to: date) -> pd.DataFrame:
    """Bars joined to features for one symbol."""
    return con.execute("""
        SELECT b.date, b.open, b.high, b.low, b.close, b.volume,
               b.vwap, b.deliv_pct,
               f.sma10, f.sma20, f.sma50, f.sma100, f.sma200,
               f.sma50_slope, f.sma200_slope, f.sma_stack, f.sma_compression,
               f.atr14, f.adr_pct20, f.adx14, f.rsi14,
               f.turnover_sma20, f.deliv_pct_sma20, f.rvol,
               f.dist_sma200_pct, f.rs_rank_pct, f.bars_available
        FROM bars_1d b
        LEFT JOIN features_1d f ON f.isin = b.isin AND f.date = b.date
        WHERE b.isin = ? AND b.date BETWEEN ? AND ?
        ORDER BY b.date
    """, [isin, date_from, date_to]).df()


def _passes_conditions(row: pd.Series, conditions: List[str]) -> bool:
    """
    Evaluate preset conditions against a signal-bar row.

    Conditions are simple `column op value` strings from config.yaml, so you
    add combinations by editing YAML and never touching Python.
    """
    for cond in conditions:
        try:
            if not _eval_condition(row, cond):
                return False
        except Exception:
            return False
    return True


_OPS = [">=", "<=", "!=", "=", ">", "<"]


def _eval_condition(row: pd.Series, cond: str) -> bool:
    for op in _OPS:
        if op in cond:
            lhs, rhs = cond.split(op, 1)
            lhs, rhs = lhs.strip(), rhs.strip().strip("'\"")
            left = row.get(lhs)
            if left is None or (isinstance(left, float) and np.isnan(left)):
                return False
            right = row.get(rhs)
            if right is None:
                try:
                    right = float(rhs)
                except ValueError:
                    right = rhs
            if op == ">=":  return left >= right
            if op == "<=":  return left <= right
            if op == ">":   return left > right
            if op == "<":   return left < right
            if op == "=":   return left == right
            if op == "!=":  return left != right
    raise ValueError(f"Cannot parse condition: {cond}")


def _resolve_date_range(sample: str, date_from: str | None = None,
                        date_to: str | None = None) -> tuple[date, date]:
    """Same in/out-of-sample resolution used by every backtest entry point."""
    d_from = pd.to_datetime(date_from or BT["date_from"]).date()
    if sample == "in":
        d_to = pd.to_datetime(date_to or BT["in_sample_end"]).date()
    else:
        d_from = pd.to_datetime(BT["out_sample_start"]).date()
        d_to = pd.to_datetime(date_to or date.today()).date()
    return d_from, d_to


def _prepare_universe(con, d_from: date, d_to: date,
                      limit_symbols: int | None = None) -> dict:
    """
    Load every symbol's bars+features for [d_from, d_to] in ONE bulk query
    and run W-pattern detection ONCE per symbol, instead of once per symbol
    PER CELL. Pattern detection depends only on price history + the fixed
    `pattern:` config block -- never on entry/exit variant or preset -- so
    a sweep's 30 cells (or marginal_contribution's 8 presets) can all share
    this single pass. Returns {isin: {symbol, df, atr_series, patterns}}.
    """
    syms = con.execute("""
        SELECT DISTINCT i.isin, i.symbol
        FROM instruments i JOIN bars_1d b ON b.isin = i.isin
        ORDER BY i.symbol
    """).df()
    if limit_symbols:
        syms = syms.head(limit_symbols)

    con.register("tmp_universe_syms", syms)
    bulk = con.execute("""
        SELECT b.isin, b.date, b.open, b.high, b.low, b.close, b.volume,
               b.vwap, b.deliv_pct,
               f.sma10, f.sma20, f.sma50, f.sma100, f.sma200,
               f.sma50_slope, f.sma200_slope, f.sma_stack, f.sma_compression,
               f.atr14, f.adr_pct20, f.adx14, f.rsi14,
               f.turnover_sma20, f.deliv_pct_sma20, f.rvol,
               f.dist_sma200_pct, f.rs_rank_pct, f.bars_available
        FROM bars_1d b
        JOIN tmp_universe_syms s ON s.isin = b.isin
        LEFT JOIN features_1d f ON f.isin = b.isin AND f.date = b.date
        WHERE b.date BETWEEN ? AND ?
        ORDER BY b.isin, b.date
    """, [d_from, d_to]).df()
    con.unregister("tmp_universe_syms")

    # groupby, not a per-symbol boolean filter -- filtering `bulk` once per
    # symbol would silently reintroduce an O(n_symbols * n_rows) scan.
    grouped = bulk.groupby("isin", sort=False)

    universe = {}
    for isin, symbol in zip(syms["isin"], syms["symbol"]):
        if isin not in grouped.groups:
            continue
        df = grouped.get_group(isin).drop(columns="isin").reset_index(drop=True)
        if len(df) < 260:
            continue

        atr_series = df["atr14"]
        if atr_series.isna().all():
            atr_series = ind.atr(df["high"], df["low"], df["close"])

        patterns = pat.find_w_patterns(
            df, atr_series,
            zigzag_pct=PAT["zigzag_pct"],
            min_separation=PAT["min_separation"],
            max_separation=PAT["max_separation"],
            require_undercut=PAT["require_undercut"],
            min_depth_pct=PAT["min_depth_pct"],
            exclude_locked_bars=PAT["exclude_locked_bars"],
            confirm_max_wait=PAT["entry_max_wait"],
        )
        universe[isin] = {"symbol": symbol, "df": df,
                          "atr_series": atr_series, "patterns": patterns}
    return universe


def run_backtest(
    con,
    preset_name: str,
    entry_variant: str = "E2",
    exit_variant: str = "X1",
    date_from: str | None = None,
    date_to: str | None = None,
    sample: str = "in",
    label: str = "",
    limit_symbols: int | None = None,
    _universe: dict | None = None,
) -> str:
    """Run one (preset x entry x exit) cell. Returns run_id."""
    preset = resolve_preset(CFG, preset_name)
    conditions = preset.get("conditions", [])

    d_from, d_to = _resolve_date_range(sample, date_from, date_to)

    run_id = uuid.uuid4().hex[:12]
    fv = con.execute(
        "SELECT feature_version FROM features_1d LIMIT 1").fetchone()
    fv = fv[0] if fv else "unknown"

    con.execute("INSERT INTO backtest_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
        run_id, datetime.now(), label or f"{preset_name}/{entry_variant}/{exit_variant}",
        preset_name, entry_variant, exit_variant,
        "; ".join(conditions), config_hash(preset), fv, d_from, d_to, sample,
    ])

    universe = _universe if _universe is not None else _prepare_universe(
        con, d_from, d_to, limit_symbols)

    log.info("[%s] %s | %s/%s | %s..%s | %d symbols",
             run_id, preset_name, entry_variant, exit_variant, d_from, d_to, len(universe))

    trades, curves = [], []
    seq = 0

    for isin, u in universe.items():
        symbol, df = u["symbol"], u["df"]
        atr_series, found = u["atr_series"], u["patterns"]

        for p in found:
            extra_entry = {"sma20": df["sma20"].to_numpy()}
            if entry_variant == "E5":
                av, _, _ = ind.anchored_vwap(
                    df["vwap"].fillna(df["close"]), df["volume"], p.l1_pos)
                extra_entry["avwap_l1"] = av.to_numpy()

            sig_pos = pat.find_entry_trigger(
                df, p, entry_variant, extra_entry, PAT["entry_max_wait"])
            if sig_pos is None or sig_pos + 1 >= len(df):
                continue

            row = df.iloc[sig_pos]
            if not _passes_conditions(row, conditions):
                continue

            # HONESTY RULE 1 — enter at the NEXT bar's open
            entry_pos = sig_pos + 1
            entry_price = apply_slippage(float(df["open"].iloc[entry_pos]), "buy")

            atr_at = float(atr_series.iloc[p.l2_pos]) if not np.isnan(
                atr_series.iloc[p.l2_pos]) else 0.0
            stop = p.l2_price - BT["stop_atr_mult"] * atr_at
            if stop <= 0 or stop >= entry_price:
                continue

            extra_exit = {
                "measured_move": p.neckline + (p.neckline - p.l2_price),
                "trail": df[f"sma{BT['trail_sma']}"].to_numpy()
                         if f"sma{BT['trail_sma']}" in df else None,
                "atr": atr_series.to_numpy(),
            }
            res = simulate_exit(df, entry_pos, entry_price, stop,
                                exit_variant, extra_exit)
            if res is None:
                continue

            exit_price = apply_slippage(res.exit_price, "sell")
            risk_per_share = entry_price - stop
            qty = max(1, int((BT["capital"] * BT["risk_per_trade_pct"] / 100.0)
                             / risk_per_share))
            gross = (exit_price - entry_price) * qty
            cost = round_trip_costs(entry_price, exit_price, qty)
            net = gross - cost

            seq += 1
            trades.append({
                "run_id": run_id, "trade_seq": seq,
                "isin": isin, "symbol": symbol,
                "signal_date": df["date"].iloc[sig_pos],
                "entry_date": df["date"].iloc[entry_pos],
                "entry_price": entry_price, "qty": qty,
                "stop_price": stop,
                "target_price": extra_exit["measured_move"],
                "exit_date": df["date"].iloc[res.exit_pos],
                "exit_price": exit_price, "exit_reason": res.exit_reason,
                "gross_pnl": gross, "costs": cost, "net_pnl": net,
                "r_multiple": (exit_price - entry_price) / risk_per_share,
                "holding_days": res.holding_days,
                "mae_pct": res.mae_pct, "mfe_pct": res.mfe_pct,
                # feature snapshot — lets you slice results afterwards
                "bottom_at_sma": pat.classify_bottom_vs_sma(
                    df, p, {k: df[k] for k in
                            ("sma20", "sma50", "sma100", "sma200") if k in df},
                    atr_series),
                "sma_stack": row.get("sma_stack"),
                "regime_state": None,
                # cast off numpy.float32 -- DuckDB's pandas scan can't convert
                # numpy scalar objects sitting in an object-dtype column
                "rs_rank_pct": _pyfloat(row.get("rs_rank_pct")),
                "adr_pct": _pyfloat(row.get("adr_pct20")),
                "deliv_pct": _pyfloat(row.get("deliv_pct_sma20")),
                "dist_sma200_pct": _pyfloat(row.get("dist_sma200_pct")),
                "depth_pct": p.depth_pct,
                "separation": p.separation,
            })

            fc = forward_curve(df, entry_pos, entry_price, BT["forward_curve_days"])
            if not fc.empty:
                fc["run_id"] = run_id
                fc["trade_seq"] = seq
                curves.append(fc)

    if trades:
        tdf = pd.DataFrame(trades)
        con.register("tmp_bt", tdf)
        con.execute("INSERT INTO backtest_trades SELECT * FROM tmp_bt")
        con.unregister("tmp_bt")
    if curves:
        cdf = pd.concat(curves, ignore_index=True)[
            ["run_id", "trade_seq", "day_n", "ret_pct", "mfe_pct", "mae_pct"]]
        con.register("tmp_cv", cdf)
        con.execute("INSERT INTO backtest_curves SELECT * FROM tmp_cv")
        con.unregister("tmp_cv")

    compute_metrics(con, run_id)
    log.info("[%s] %d trades", run_id, len(trades))
    return run_id


# =====================================================================
# METRICS
# =====================================================================

def compute_metrics(con, run_id: str) -> dict:
    t = con.execute("SELECT * FROM backtest_trades WHERE run_id = ?", [run_id]).df()
    if t.empty:
        con.execute("INSERT INTO backtest_metrics VALUES (?,0,0,0,0,0,0,0,0,0,0,0,0,0)",
                    [run_id])
        return {}

    wins = t[t["net_pnl"] > 0]
    losses = t[t["net_pnl"] <= 0]
    win_rate = len(wins) / len(t) * 100.0
    avg_win_r = wins["r_multiple"].mean() if len(wins) else 0.0
    avg_loss_r = losses["r_multiple"].mean() if len(losses) else 0.0
    expectancy = (win_rate / 100.0) * avg_win_r + (1 - win_rate / 100.0) * avg_loss_r
    gross_win = wins["net_pnl"].sum()
    gross_loss = abs(losses["net_pnl"].sum())
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")

    eq = t.sort_values("exit_date")["net_pnl"].cumsum()
    peak = eq.cummax()
    dd = ((eq - peak) / BT["capital"] * 100.0).min() if len(eq) else 0.0

    total_ret = t["net_pnl"].sum() / BT["capital"] * 100.0
    years = max(0.5, (pd.to_datetime(t["exit_date"]).max()
                      - pd.to_datetime(t["entry_date"]).min()).days / 365.25)
    cagr = ((1 + total_ret / 100.0) ** (1 / years) - 1) * 100.0

    # r_multiple/mae_pct/mfe_pct are FLOAT (4-byte) columns in backtest_trades,
    # so pandas reductions over them (.mean()/.median()) come back as
    # numpy.float32 scalars -- DuckDB's parameterized INSERT can't take those
    # directly, only native python floats. Cast everything on the way out.
    m = dict(
        run_id=run_id, trades=int(len(t)), win_rate=_pyfloat(win_rate),
        expectancy_r=_pyfloat(expectancy), avg_win_r=_pyfloat(avg_win_r),
        avg_loss_r=_pyfloat(avg_loss_r),
        profit_factor=_pyfloat(pf if np.isfinite(pf) else 999.0), max_dd_pct=_pyfloat(dd),
        total_return_pct=_pyfloat(total_ret), cagr_pct=_pyfloat(cagr),
        median_hold_days=_pyfloat(t["holding_days"].median()),
        median_mae=_pyfloat(t["mae_pct"].median()), median_mfe=_pyfloat(t["mfe_pct"].median()),
        benchmark_cagr_pct=None,
    )
    con.execute("DELETE FROM backtest_metrics WHERE run_id = ?", [run_id])
    con.execute("INSERT INTO backtest_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                list(m.values()))
    return m


def analyse_curves(con, run_id: str) -> pd.DataFrame:
    """
    THE HOLDING-PERIOD ANSWER.

    Returns, per day 1..N:
      median_mfe   -- where this FLATTENS is your natural holding period
      p75_mfe      -- what a good trade reaches
      median_mae   -- typical heat you must sit through
      p85_mae_win  -- stop candidate: 85th pct of WINNERS' worst drawdown
      pct_positive -- survival curve
      marginal_mfe -- gain from holding one more day; when it hits ~0, exit
    """
    c = con.execute("""
        SELECT c.day_n, c.ret_pct, c.mfe_pct, c.mae_pct,
               (t.net_pnl > 0) AS is_winner
        FROM backtest_curves c
        JOIN backtest_trades t
          ON t.run_id = c.run_id AND t.trade_seq = c.trade_seq
        WHERE c.run_id = ?
    """, [run_id]).df()
    if c.empty:
        return c

    g = c.groupby("day_n")
    out = pd.DataFrame({
        "median_mfe": g["mfe_pct"].median(),
        "p75_mfe": g["mfe_pct"].quantile(0.75),
        "median_mae": g["mae_pct"].median(),
        "median_ret": g["ret_pct"].median(),
        "pct_positive": g["ret_pct"].apply(lambda s: (s > 0).mean() * 100.0),
    }).reset_index()

    winners = c[c["is_winner"]]
    if len(winners):
        p85 = winners.groupby("day_n")["mae_pct"].quantile(0.15)  # 15th pct = deepest 85%
        out["p85_mae_win"] = out["day_n"].map(p85)

    out["marginal_mfe"] = out["median_mfe"].diff().fillna(out["median_mfe"])
    return out


def sweep(con, preset: str, sample: str = "in",
          limit_symbols: int | None = None) -> pd.DataFrame:
    """
    Run the full entry x exit grid for one preset.

    30 cells, each with a REASON — which is the test for legitimate sweeping.
    Brute-forcing thousands of combinations is how you find noise.
    """
    d_from, d_to = _resolve_date_range(sample)
    universe = _prepare_universe(con, d_from, d_to, limit_symbols)

    rows = []
    for e in BT["entry_variants"]:
        for x in BT["exit_variants"]:
            rid = run_backtest(con, preset, e, x, date_from=d_from, date_to=d_to,
                               sample=sample, limit_symbols=limit_symbols,
                               _universe=universe)
            m = con.execute(
                "SELECT * FROM backtest_metrics WHERE run_id = ?", [rid]).df()
            if not m.empty:
                r = m.iloc[0].to_dict()
                r.update({"entry": e, "exit": x, "preset": preset})
                rows.append(r)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Sort by expectancy, but the trade count column is right there so a
    # 12-trade fluke at the top is obvious.
    return df.sort_values("expectancy_r", ascending=False)


def marginal_contribution(con, base_preset: str, candidates: List[str],
                          entry: str = "E2", exit_: str = "X1",
                          limit_symbols: int | None = None) -> pd.DataFrame:
    """
    THE CONTROL-FIRST TABLE.

    Runs the baseline, then each candidate preset, and reports the delta.
    A filter that lifts expectancy but cuts trades from 800 to 40 has not
    helped you — it has found a coincidence. The trade count is shown so you
    cannot miss that.
    """
    d_from, d_to = _resolve_date_range("in")
    universe = _prepare_universe(con, d_from, d_to, limit_symbols)

    rows = []
    for name in [base_preset] + candidates:
        rid = run_backtest(con, name, entry, exit_, date_from=d_from, date_to=d_to,
                           limit_symbols=limit_symbols, _universe=universe)
        m = con.execute("SELECT * FROM backtest_metrics WHERE run_id = ?",
                        [rid]).df()
        if m.empty:
            continue
        r = m.iloc[0].to_dict()
        r["preset"] = name
        rows.append(r)

    df = pd.DataFrame(rows)
    if df.empty or len(df) < 2:
        return df
    base = df.iloc[0]
    df["delta_expectancy"] = df["expectancy_r"] - base["expectancy_r"]
    df["delta_win_rate"] = df["win_rate"] - base["win_rate"]
    df["trade_retention_pct"] = df["trades"] / base["trades"] * 100.0
    df["enough_trades"] = df["trades"] >= BT["min_trades_for_conclusion"]
    return df


_RESOLVED_STOP_REASONS = {"stop_hit", "stop_hit_ambiguous"}
_RESOLVED_TARGET_REASONS = {"target_hit", "target_hit_ambiguous"}


def recent_signals_report(
    con, preset_name: str, entry_variant: str, exit_variant: str,
    days_back: int, limit_symbols: int | None = None,
) -> dict:
    """
    "What actually happened to the last `days_back` days of signals" — per
    symbol, not just an aggregate. Runs the SAME run_backtest() used
    everywhere else over a generous fixed lookback (RECENT_REPORT_LOOKBACK_DAYS,
    long enough that a pattern triggering on day 1 of the requested window is
    still structurally detectable), then filters the resulting trades down to
    entry_date >= today - days_back for display. The backtest run itself is
    unchanged; only this reporting/filtering layer is new.

    The stored backtest_metrics row for this run reflects the WHOLE lookback
    range, not the report window, so the summary here is computed fresh over
    the filtered subset rather than reused from compute_metrics().
    """
    d_to = date.today()
    d_from = d_to - timedelta(days=RECENT_REPORT_LOOKBACK_DAYS)
    cutoff = d_to - timedelta(days=days_back)

    run_id = run_backtest(con, preset_name, entry_variant, exit_variant,
                          date_from=d_from, date_to=d_to, sample="in",
                          limit_symbols=limit_symbols)

    trades = con.execute("""
        SELECT symbol, entry_date, entry_price, exit_date, exit_price,
               exit_reason, net_pnl, r_multiple, holding_days
        FROM backtest_trades
        WHERE run_id = ? AND entry_date >= ?
        ORDER BY entry_date DESC
    """, [run_id, cutoff]).df()

    if trades.empty:
        return {
            "run_id": run_id, "days_back": days_back,
            "trades": trades,
            "summary": {
                "total_trades": 0, "resolved_trades": 0, "still_open": 0,
                "win_rate": None, "target_hits": 0, "stop_hits": 0,
                "time_stop_exits": 0, "realized_pnl": 0.0, "unrealized_pnl": 0.0,
            },
        }

    resolved = trades[trades["exit_reason"] != "end_of_data"]
    still_open = trades[trades["exit_reason"] == "end_of_data"]
    wins = resolved[resolved["net_pnl"] > 0]

    summary = {
        "total_trades": int(len(trades)),
        "resolved_trades": int(len(resolved)),
        "still_open": int(len(still_open)),
        "win_rate": _pyfloat(len(wins) / len(resolved) * 100.0) if len(resolved) else None,
        "target_hits": int(resolved["exit_reason"].isin(_RESOLVED_TARGET_REASONS).sum()),
        "stop_hits": int(resolved["exit_reason"].isin(_RESOLVED_STOP_REASONS).sum()),
        "time_stop_exits": int((resolved["exit_reason"] == "time_stop").sum()),
        "realized_pnl": _pyfloat(resolved["net_pnl"].sum()),
        "unrealized_pnl": _pyfloat(still_open["net_pnl"].sum()),
    }

    # `trades` is returned as a DataFrame, not pre-serialized -- same
    # convention as sweep()/marginal_contribution(); the API service layer
    # sanitizes Timestamp/numpy types at the boundary via jsonable_df(),
    # same as every other DataFrame-returning function here.
    return {"run_id": run_id, "days_back": days_back, "trades": trades, "summary": summary}


def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest the W-pattern.")
    ap.add_argument("--preset", default="w_naked")
    ap.add_argument("--entry", default="E2")
    ap.add_argument("--exit", dest="exit_", default="X1")
    ap.add_argument("--sample", default="in", choices=["in", "out"])
    ap.add_argument("--sweep", action="store_true", help="run the entry x exit grid")
    ap.add_argument("--marginal", action="store_true",
                    help="baseline vs each SMA filter, with deltas")
    ap.add_argument("--limit", type=int, help="limit symbols (for a quick trial)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    con = connect()
    init_schema(con)

    if args.marginal:
        cands = ["w_sma200_trend", "w_sma200_rising", "w_sma50_trend",
                 "w_golden", "w_stacked", "w_delivery", "w_full"]
        df = marginal_contribution(con, "w_baseline", cands,
                                   args.entry, args.exit_, args.limit)
        print(df.to_string(index=False))
    elif args.sweep:
        df = sweep(con, args.preset, args.sample, args.limit)
        print(df.to_string(index=False))
    else:
        rid = run_backtest(con, args.preset, args.entry, args.exit_,
                           sample=args.sample, limit_symbols=args.limit)
        print(con.execute("SELECT * FROM backtest_metrics WHERE run_id = ?",
                          [rid]).df().to_string(index=False))
        print()
        print(analyse_curves(con, rid).to_string(index=False))

    con.close()


if __name__ == "__main__":
    main()
