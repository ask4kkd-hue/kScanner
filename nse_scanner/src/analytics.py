"""
analytics.py — ad-hoc analysis screens, distinct from the W-pattern scanner.

Not a signal generator: these are one-off "show me stocks that..." queries
over the stored price history, deliberately NOT filtered through
universe.active_universe()'s liquidity/tradability rules the way every
scan/backtest path is. This is a research tool, not a "what can I trade
today" list — a deeply crashed stock is exactly the kind of thing that
often falls out of the liquidity filter, and that's the point of it.

ANALYSIS_TYPES is a small registry (same spirit as features.py's
REGISTRY) so the frontend's dropdown is data-driven rather than
hardcoded, and adding a new analysis type later is "add a function +
a registry entry," not a framework change. Only one param shape exists
today (a min/max % range), so run_analysis() takes it directly rather
than a generic kwargs bag — that generalizes when a second analysis
type actually needs something different, not before.
"""

from __future__ import annotations

import pandas as pd

ANALYSIS_TYPES = {
    "down_from_ath": {
        "label": "Down X% from All-Time High",
        "param_label": "% down from ATH",
        "min_default": 70.0,
        "max_default": 100.0,
    },
}


def down_from_ath(con, min_pct: float, max_pct: float) -> pd.DataFrame:
    """
    Stocks currently down between min_pct% and max_pct% (inclusive) from
    their all-time high — a range, not just a floor, so you can isolate a
    band (e.g. 70-85% down) instead of always pulling in the -99% names too.

    ATH = MAX(high) over the symbol's full history (the intraday high, not
    close — the conventional meaning of "all-time high"). Current price =
    latest close, matching how the rest of the app treats close as the
    reference price. Only excludes delisted/suspended instruments
    (symbol_status != 'active') — no turnover/price/ASM-GSM filter, by
    deliberate choice for this screen.
    """
    if min_pct > max_pct:
        raise ValueError(f"min_pct ({min_pct}) must be <= max_pct ({max_pct}).")
    return con.execute("""
        WITH history AS (
            SELECT isin, MAX(high) AS ath, ARG_MAX(date, high) AS ath_date
            FROM bars_1d GROUP BY isin
        ),
        latest AS (
            SELECT isin, close AS last_close, date AS last_date,
                   ROW_NUMBER() OVER (PARTITION BY isin ORDER BY date DESC) AS rn
            FROM bars_1d
        )
        SELECT i.symbol, i.name, i.sector, h.ath, h.ath_date,
               l.last_close, l.last_date,
               (h.ath - l.last_close) / h.ath * 100.0 AS pct_down_from_ath
        FROM instruments i
        JOIN symbol_status ss ON ss.isin = i.isin AND ss.status = 'active'
        JOIN history h ON h.isin = i.isin
        JOIN latest l ON l.isin = i.isin AND l.rn = 1
        WHERE h.ath > 0
          AND (h.ath - l.last_close) / h.ath * 100.0 BETWEEN ? AND ?
        ORDER BY pct_down_from_ath DESC
    """, [min_pct, max_pct]).df()


def run_analysis(con, analysis_type: str, **params) -> pd.DataFrame:
    if analysis_type not in ANALYSIS_TYPES:
        raise ValueError(f"Unknown analysis_type '{analysis_type}'. "
                         f"Available: {sorted(ANALYSIS_TYPES)}")
    if analysis_type == "down_from_ath":
        return down_from_ath(con, params["min_pct"], params["max_pct"])
    raise ValueError(f"Analysis type '{analysis_type}' has no handler wired up.")
