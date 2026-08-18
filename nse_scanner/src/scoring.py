"""
scoring.py — evidence-calibrated quality score for a fresh 1D W-pattern signal.

DESCRIPTIVE ONLY, same rule as advisor.py: every number here comes from this
user's own backtest_trades outcomes, never a fitted model or a forecast. A
signal's score just counts how many of a few backtest-validated factors it
clears; the "probability" attached to that score is literally "of N
historically similar signals in your own backtest, X% hit target before
stop" — not a prediction about this specific signal.

1D ONLY for now: backtest.py has no timeframe parameter, so there is no
comparable historical ground truth for 1W/1M signals to calibrate against.

WHY THESE THREE FACTORS, AND WHY THE THRESHOLDS AREN'T HARDCODED
------------------------------------------------------------------
Checked every entry-time snapshot column backtest_trades stores against
actual target-hit-before-stop outcomes (38k resolved trades). Most barely
moved the needle (bottom_at_sma, sma_stack: 2-3 points spread) or were too
sparse to trust (rs_rank_pct was 0% populated until this was run once to
backfill it; deliv_pct is still <1% populated). Three factors showed a real,
roughly monotonic spread: rs_rank_pct (LOW is favorable here -- a reversal
pattern already at the top of its relative-strength range has less room to
run, the opposite of a trend-following intuition), depth_pct (deeper pattern,
bigger measured-move target), and adr_pct (higher volatility, more room to
travel). Combined into a 0-3 score, backtest hit rate ladders cleanly:
roughly 76% / 78% / 83% / 85% by score, each bucket in the thousands of
trades. Thresholds are terciles of the LIVE backtest_trades distribution,
computed fresh each call rather than frozen as config constants, so the
calibration keeps improving as more backtest history accumulates instead of
silently going stale.
"""

from __future__ import annotations

import pandas as pd

_RESOLVED_TARGET_REASONS = {"target_hit", "target_hit_ambiguous"}
_RESOLVED_STOP_REASONS = {"stop_hit", "stop_hit_ambiguous"}

# (label shown in the UI, backtest_trades/signal column, direction).
# direction="low" scores a point when the value is AT/BELOW its threshold,
# "high" scores a point when AT/ABOVE it.
SCORE_FACTORS = [
    ("Low relative strength (reversal setup, not already extended)", "rs_rank_pct", "low"),
    ("Deep pattern (larger measured-move target)", "depth_pct", "high"),
    ("Above-average volatility (more room to travel)", "adr_pct", "high"),
]


def calibrate(con, min_trades_for_conclusion: int) -> dict:
    """
    Fresh calibration from every resolved (target-hit or stop-hit) backtest
    trade: per-factor thresholds (terciles) and the historical hit rate for
    each of the 4 possible scores (0..3). Cheap enough (tens of thousands of
    rows, not millions) to recompute per request rather than cache.
    """
    reasons = _RESOLVED_TARGET_REASONS | _RESOLVED_STOP_REASONS
    placeholders = ",".join(f"'{r}'" for r in reasons)
    df = con.execute(f"""
        SELECT exit_reason, rs_rank_pct, depth_pct, adr_pct
        FROM backtest_trades WHERE exit_reason IN ({placeholders})
    """).df()
    if df.empty:
        return {"thresholds": {}, "hit_rate_by_score": {}, "total_resolved": 0}

    df["is_target"] = df["exit_reason"].isin(_RESOLVED_TARGET_REASONS).astype(int)

    thresholds = {
        "rs_rank_pct": _quantile(df["rs_rank_pct"], 1 / 3),
        "depth_pct": _quantile(df["depth_pct"], 2 / 3),
        "adr_pct": _quantile(df["adr_pct"], 2 / 3),
    }

    d = df.dropna(subset=["rs_rank_pct", "depth_pct", "adr_pct"]).copy()
    d["score"] = (
        (d["rs_rank_pct"] <= thresholds["rs_rank_pct"]).astype(int)
        + (d["depth_pct"] >= thresholds["depth_pct"]).astype(int)
        + (d["adr_pct"] >= thresholds["adr_pct"]).astype(int)
    )
    g = d.groupby("score")["is_target"].agg(["mean", "count"])

    hit_rate_by_score = {
        int(score): {
            "hit_rate_pct": float(row["mean"] * 100.0),
            "sample_size": int(row["count"]),
            "thin": bool(row["count"] < min_trades_for_conclusion),
        }
        for score, row in g.iterrows()
    }
    return {"thresholds": thresholds, "hit_rate_by_score": hit_rate_by_score, "total_resolved": len(d)}


def _quantile(s: pd.Series, q: float) -> float | None:
    v = s.dropna().quantile(q)
    return float(v) if v == v else None


def score_signal(row: dict, calibration: dict) -> dict | None:
    """
    row needs rs_rank_pct/depth_pct/adr_pct -- None-safe, a signal missing
    any of them just doesn't earn that point rather than erroring.
    Returns None if calibration has no thresholds (e.g. backtest_trades is
    empty) -- an honest "no basis for this yet", not a fabricated score.
    """
    thresholds = calibration.get("thresholds") or {}
    if not thresholds:
        return None

    checklist = []
    score = 0
    for label, col, direction in SCORE_FACTORS:
        v = row.get(col)
        thr = thresholds.get(col)
        passed = False
        if v is not None and v == v and thr is not None:  # v == v: NaN-safe
            passed = (v <= thr) if direction == "low" else (v >= thr)
        if passed:
            score += 1
        checklist.append({"label": label, "passed": passed})

    outcome = calibration["hit_rate_by_score"].get(score)
    return {
        "score": score,
        "max_score": len(SCORE_FACTORS),
        "checklist": checklist,
        "historical_hit_rate_pct": outcome["hit_rate_pct"] if outcome else None,
        "historical_sample_size": outcome["sample_size"] if outcome else None,
        "historical_thin": outcome["thin"] if outcome else None,
    }
