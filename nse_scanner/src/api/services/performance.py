"""
api/services/performance.py — port of web/pages/performance.py's analytics.

Every attribution cut carries a "thin" flag (trades < backtest.min_trades_for_conclusion)
computed here, not left for the frontend to duplicate the threshold constant — same rule
the CLI backtest report and CLAUDE.md's methodology section apply: below that count, a
number is noise, not a finding, and every consumer must render it that way.
"""

from __future__ import annotations

import journal as jr
from config import CFG

from api.util import jsonable_df, jsonable_dict

MIN_TRADES = CFG["backtest"]["min_trades_for_conclusion"]


def _mark_thin(df) -> list[dict]:
    """DataFrame -> JSON-safe records (NaN/Timestamp sanitized the same way
    every other endpoint's DataFrame output is — pandas aggregates like
    AVG() over an edge-case group can legitimately produce NaN, which isn't
    valid JSON on its own) with a `thin` flag added per row."""
    rows = jsonable_df(df)
    for r in rows:
        r["thin"] = int(r.get("trades") or 0) < MIN_TRADES
    return rows


def summary(con) -> dict:
    s = jr.summary(con)
    s["min_trades_for_conclusion"] = MIN_TRADES
    s["thin"] = s.get("trades", 0) < MIN_TRADES
    if s.get("profit_factor") == float("inf"):
        s["profit_factor"] = None  # JSON has no Infinity; None + a UI "∞" label instead
    return jsonable_dict(s)


def equity_curve(con) -> list[dict]:
    df = jr.equity_curve(con)
    if df.empty:
        return []
    return [
        {"exit_date": str(d), "cum_pnl": float(c), "drawdown": float(dd)}
        for d, c, dd in zip(df["exit_date"], df["cum_pnl"], df["drawdown"])
    ]


def attribution(con) -> dict:
    by_preset = _mark_thin(jr.preset_attribution(con))

    tf_df = con.execute("""
        SELECT COALESCE(timeframe, '1d') AS tf_label, COUNT(*) AS trades,
              AVG(r_multiple) AS avg_r,
              AVG(CASE WHEN net_pnl > 0 THEN 1.0 ELSE 0.0 END) * 100 AS win_rate,
              SUM(net_pnl) AS net_pnl
        FROM trades WHERE status = 'closed' GROUP BY 1
    """).df()
    by_timeframe = _mark_thin(tf_df)

    sector_df = con.execute("""
        SELECT COALESCE(i.sector, 'unknown') AS sector, COUNT(*) AS trades,
              AVG(t.r_multiple) AS avg_r,
              AVG(CASE WHEN t.net_pnl > 0 THEN 1.0 ELSE 0.0 END) * 100 AS win_rate,
              SUM(t.net_pnl) AS net_pnl
        FROM trades t LEFT JOIN instruments i ON i.isin = t.isin
        WHERE t.status = 'closed' GROUP BY 1 ORDER BY trades DESC
    """).df()
    by_sector = _mark_thin(sector_df)

    return {
        "by_preset": by_preset, "by_timeframe": by_timeframe, "by_sector": by_sector,
        "bottom_at_sma_note": (
            "Not available for live trades — journal.py's entry snapshot doesn't "
            "capture bottom_at_sma (categorical fields aren't snapshotted, only "
            "numeric indicators). Present in the backtest's bottom_at_sma slicing "
            "instead."
        ),
    }


def adherence(con) -> list[dict]:
    return jsonable_df(jr.adherence_report(con))


def tags(con) -> list[dict]:
    return jsonable_df(jr.tag_analysis(con))


SNAPSHOT_METRICS = ["deliv_pct_sma20", "adr_pct20", "adx14", "rs_rank_pct", "dist_sma200_pct"]


def snapshot(con, metric: str) -> list[dict]:
    return jsonable_df(jr.snapshot_analysis(con, metric))


def presets_traded(con) -> list[str]:
    return con.execute("""
        SELECT DISTINCT preset_name FROM trades
        WHERE status = 'closed' AND preset_name != '' ORDER BY 1
    """).df()["preset_name"].tolist()


def compare(con, preset_name: str) -> list[dict]:
    return jsonable_df(jr.compare_with_backtest(con, preset_name))
