"""web/pages/data.py — ported from app.py's (v1) Data tab. Behaviour unchanged."""

from __future__ import annotations

import pandas as pd
from nicegui import ui

import components as comp
import theme
from db import table_counts


def render(con, state: dict) -> None:
    comp.page_title("Data")

    with comp.section("Table sizes", collapsed=False):
        comp.dataframe_grid(pd.DataFrame(table_counts(con).items(), columns=["table", "rows"]))

    with comp.section("Validation failures (last 30 days)", collapsed=False):
        v = con.execute("""
            SELECT date, symbol, yf_close, bhav_close, pct_diff
            FROM validation_log
            WHERE passed = FALSE AND date >= CURRENT_DATE - INTERVAL 30 DAY
            ORDER BY ABS(pct_diff) DESC LIMIT 200
        """).df()
        if v.empty:
            ui.label("No mismatches against the official bhavcopy.").style(
                f"color:{theme.ACCENT}")
        else:
            comp.dataframe_grid(v)
            big = v[v["pct_diff"].abs() >= 15]
            if not big.empty:
                ui.label(f"{len(big)} rows differ by 15%+ — these are almost "
                        f"certainly corporate actions yfinance missed. They "
                        f"manufacture fake W-bottoms. Investigate before "
                        f"trading those symbols.").classes("text-sm mt-2").style(
                    f"color:{theme.CRITICAL}")

    with comp.section("Recent ingest runs", collapsed=True):
        comp.dataframe_grid(con.execute(
            "SELECT * FROM ingest_log ORDER BY run_ts DESC LIMIT 20").df())

    with comp.section("Symbols with residual gaps", collapsed=True):
        ui.label("These failed to fill even after the anti-join retried them.") \
            .classes("text-xs").style(f"color:{theme.TEXT_MUTED}")
        comp.dataframe_grid(con.execute("""
            SELECT i.symbol, s.status, s.consecutive_misses, s.last_success
            FROM symbol_status s JOIN instruments i ON i.isin = s.isin
            WHERE s.consecutive_misses > 0
            ORDER BY s.consecutive_misses DESC LIMIT 100
        """).df())
