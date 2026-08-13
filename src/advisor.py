"""
advisor.py — position status. DESCRIPTIVE ONLY.

Every statement cites a real number from this user's own backtest_curves /
backtest_metrics / bars_1d. Never "will", "expect", "likely", "should buy",
"should sell", and never a price prediction. If no backtest exists for a
preset, the response says exactly that instead of guessing.

MAE/MFE for the open position are computed FRESH here (via journal's own
compute_mae_mfe), not read from the trades table — that keeps the advisor
correct even if nobody has run journal.update_open_trades() recently.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from journal import compute_mae_mfe

# "Approaching" the 85th-percentile MAE threshold means the current
# drawdown has already reached this fraction of it — named here so it is
# a documented choice, not a buried magic number.
MAE_APPROACH_FRACTION = 0.8


def _latest_backtest_run(con, preset_name: str) -> Optional[str]:
    row = con.execute("""
        SELECT run_id FROM backtest_runs
        WHERE preset_name = ? ORDER BY run_ts DESC LIMIT 1
    """, [preset_name]).fetchone()
    return row[0] if row else None


def position_status(con, trade_id: int) -> dict:
    """
    Returns {'status': 'HOLD'|'WATCH'|'REVIEW', 'reasons': [str, ...],
    'metrics': {...}}.
    """
    t = con.execute("SELECT * FROM trades WHERE trade_id = ?", [trade_id]).df()
    if t.empty:
        raise ValueError(f"No trade {trade_id}")
    t = t.iloc[0]

    last = con.execute("""
        SELECT date, close FROM bars_1d WHERE isin = ?
        ORDER BY date DESC LIMIT 1
    """, [t["isin"]]).df()
    if last.empty:
        return {"status": "WATCH",
                "reasons": ["No price data for this symbol."],
                "metrics": {}}

    as_of = last["date"].iloc[0]
    close = float(last["close"].iloc[0])
    entry = float(t["entry_price"])
    days_held = (pd.to_datetime(as_of) - pd.to_datetime(t["entry_date"])).days
    current_pnl_pct = (close / entry - 1.0) * 100.0
    mae_pct, mfe_pct = compute_mae_mfe(con, t["isin"], t["entry_date"], as_of, entry)

    metrics = {
        "days_held": days_held, "current_pnl_pct": current_pnl_pct,
        "mae_pct": mae_pct, "mfe_pct": mfe_pct,
        "backtest_median_hold": None, "backtest_median_mfe_at_day": None,
        "backtest_p85_mae": None,
    }

    run_id = _latest_backtest_run(con, t["preset_name"])
    if run_id is None:
        return {
            "status": "WATCH",
            "reasons": [f"No backtest run for preset '{t['preset_name']}' — "
                       f"no basis for timing guidance."],
            "metrics": metrics,
        }

    bm = con.execute("""
        SELECT median_hold_days FROM backtest_metrics WHERE run_id = ?
    """, [run_id]).df()
    median_hold = (float(bm["median_hold_days"].iloc[0])
                   if not bm.empty and bm["median_hold_days"].iloc[0] is not None
                   else None)
    metrics["backtest_median_hold"] = median_hold

    # Per-day curve stats across this run's trades. p85_mae_win is the 85th
    # percentile of drawdown MAGNITUDE among WINNING trades only — "85% of
    # your winners never drew down more than X%".
    curve = con.execute("""
        SELECT c.day_n,
               MEDIAN(c.mfe_pct) AS median_mfe,
               PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY c.mfe_pct) AS p75_mfe,
               PERCENTILE_CONT(0.85) WITHIN GROUP (ORDER BY ABS(c.mae_pct))
                   FILTER (WHERE bt.net_pnl > 0) AS p85_mae_win
        FROM backtest_curves c
        JOIN backtest_trades bt
          ON bt.run_id = c.run_id AND bt.trade_seq = c.trade_seq
        WHERE c.run_id = ?
        GROUP BY c.day_n ORDER BY c.day_n
    """, [run_id]).df()

    def _at_day(n: int, col: str) -> Optional[float]:
        row = curve[curve["day_n"] == n]
        if row.empty or pd.isna(row[col].iloc[0]):
            return None
        return float(row[col].iloc[0])

    median_mfe_today = _at_day(days_held, "median_mfe")
    p75_mfe_today = _at_day(days_held, "p75_mfe")
    p85_mae_win = _at_day(days_held, "p85_mae_win")
    median_mfe_prev = _at_day(days_held - 1, "median_mfe") if days_held > 0 else None
    marginal_mfe = (median_mfe_today - median_mfe_prev
                    if median_mfe_today is not None and median_mfe_prev is not None
                    else None)

    metrics["backtest_median_mfe_at_day"] = median_mfe_today
    metrics["backtest_p85_mae"] = p85_mae_win

    status = "HOLD"
    reasons: list[str] = []

    # Rule: held past the backtest's median winning holding period.
    if median_hold is not None and days_held > median_hold:
        status = "REVIEW"
        reasons.append(f"Day {days_held}. Your backtest median winner peaked "
                       f"at day {median_hold:.0f}.")

    # Rule: the edge (marginal MFE) has turned negative for this many days held.
    if marginal_mfe is not None and marginal_mfe <= 0:
        status = "REVIEW"
        reasons.append(f"Marginal MFE turned negative at day {days_held} "
                       f"in your backtest.")

    # Rule: drawdown is approaching (or past) the 85th-percentile winner MAE.
    if p85_mae_win is not None and not np.isnan(mae_pct):
        drawdown = abs(mae_pct)
        if drawdown >= MAE_APPROACH_FRACTION * p85_mae_win:
            if status != "REVIEW":
                status = "WATCH"
            reasons.append(f"Down {drawdown:.1f}%. 85% of your winners never "
                           f"drew down more than {p85_mae_win:.1f}%.")

    # Rule: running MFE is behind the backtest's typical path at this day.
    if median_mfe_today is not None and not np.isnan(mfe_pct) \
            and mfe_pct < median_mfe_today:
        if status == "HOLD":
            status = "WATCH"
        reasons.append(f"Up {mfe_pct:.1f}% at day {days_held}. Backtest "
                       f"median at day {days_held} was {median_mfe_today:.1f}%.")

    # Rule: running MFE is ahead of the 75th-percentile path — a good sign,
    # never downgrades status set by the rules above.
    if p75_mfe_today is not None and not np.isnan(mfe_pct) \
            and mfe_pct > p75_mfe_today:
        reasons.append(f"Up {mfe_pct:.1f}% at day {days_held}, above your "
                       f"75th-percentile path.")

    if not reasons:
        reasons.append(f"Day {days_held}, up {current_pnl_pct:.1f}%. "
                       f"No backtest threshold crossed yet.")

    return {"status": status, "reasons": reasons, "metrics": metrics}
