"""
web/pages/chart.py — TradingView-style chart.

D/W/M timeframes and Candle/Line/Heikin Ashi/Renko chart types all resample
server-side (resample.py) and hand the JS component plain OHLCV bars — no
indicator or transform maths in JavaScript (global rule 3). W-pattern
detection always runs on the real underlying price bars for the active
timeframe, never on the Heikin Ashi/Renko display transform, so the L1/L2/
neckline levels stay real prices regardless of how the candles are drawn.

Drawings are keyed on (isin, timeframe) and reloaded fresh on every symbol
or timeframe change, so a daily trendline never leaks onto the weekly chart.
"""

from __future__ import annotations

import json

import pandas as pd
from nicegui import ui

import components as comp
import indicators as ind
import patterns as pat
import resample as rs
import theme
from config import CFG
from kline import KLineChart

TIMEFRAMES = {"D": "1d", "W": "1w", "M": "1m"}
CHART_TYPES = ["Candle", "Line", "Heikin Ashi", "Renko"]
OVERLAY_OPTIONS = ["sma10", "sma20", "sma50", "sma100", "sma200"]
AVWAP_OPTIONS = ["(none)", "52-week low", "52-week high", "last W first low"]
DRAWING_TOOLS = [
    ("horizontal_line", "H-Line"), ("trend_line", "Trend"), ("ray", "Ray"),
    ("rectangle", "Rect"), ("fibonacci_retracement", "Fib"), ("text_note", "Text"),
]


def _symbols(con) -> list[str]:
    return con.execute(
        "SELECT DISTINCT symbol FROM instruments ORDER BY symbol"
    ).df()["symbol"].tolist()


def _isin_for(con, symbol: str) -> str | None:
    row = con.execute("SELECT isin FROM instruments WHERE symbol = ?", [symbol]).fetchone()
    return row[0] if row else None


def _load_daily(con, isin: str, bars: int) -> pd.DataFrame:
    return con.execute("""
        SELECT b.date, b.open, b.high, b.low, b.close, b.volume, b.vwap,
               f.rsi14, f.adx14, f.adr_pct20, f.deliv_pct_sma20, f.rs_rank_pct
        FROM bars_1d b
        LEFT JOIN features_1d f ON f.isin = b.isin AND f.date = b.date
        WHERE b.isin = ? ORDER BY b.date DESC LIMIT ?
    """, [isin, bars]).df().sort_values("date").reset_index(drop=True)


def _load_drawings(con, isin: str, timeframe: str) -> list[dict]:
    row = con.execute("SELECT payload FROM drawings WHERE isin = ? AND timeframe = ?",
                      [isin, timeframe]).fetchone()
    if not row:
        return []
    try:
        return json.loads(row[0])
    except Exception:
        return []


def _save_drawings(con, isin: str, timeframe: str, overlays: list[dict]) -> None:
    con.execute("""
        INSERT INTO drawings (isin, timeframe, payload, updated_at)
        VALUES (?, ?, ?, now())
        ON CONFLICT (isin, timeframe) DO UPDATE SET
            payload = excluded.payload, updated_at = excluded.updated_at
    """, [isin, timeframe, json.dumps(overlays), ])


def render(con, state: dict) -> None:
    comp.page_title("Chart")

    symbols = _symbols(con)
    if not symbols:
        ui.label("No instruments loaded yet. Run universe.py first.")
        return

    default_symbol = state.get("chart_symbol") or symbols[0]

    with ui.row().classes("w-full gap-3 items-end flex-wrap"):
        symbol_sel = ui.select(symbols, value=default_symbol, with_input=True,
                               label="Symbol").classes("w-48")
        bars_input = ui.number("Bars", value=CFG["ui"]["chart_lookback_bars"],
                               min=100, max=2000).classes("w-24")
        tf_toggle = ui.toggle(["D", "W", "M"], value="D").props("dense no-caps")
        type_sel = ui.select(CHART_TYPES, value="Candle", label="Chart type").classes("w-36")
        overlays_sel = ui.select(OVERLAY_OPTIONS, value=["sma50", "sma200"], multiple=True,
                                 label="Overlays").classes("w-56").props("use-chips dense")
        avwap_sel = ui.select(AVWAP_OPTIONS, value="(none)",
                              label="Anchor VWAP at").classes("w-44")
        show_w = ui.checkbox("Mark last W L1/L2", value=True)

    chart = KLineChart()

    with ui.row().classes("gap-1"):
        for tool_id, label in DRAWING_TOOLS:
            ui.button(label, on_click=lambda t=tool_id: chart.start_drawing(t)) \
                .props("dense flat no-caps size=sm")
        ui.button("Clear all", on_click=lambda: chart.clear_user_overlays()) \
            .props("dense flat no-caps size=sm")

    metrics_row = ui.row().classes("w-full gap-6 text-sm mt-2")

    def on_overlays_changed(overlays: list[dict]) -> None:
        isin = _isin_for(con, state.get("chart_symbol", ""))
        if isin:
            _save_drawings(con, isin, state.get("chart_timeframe", "1d"), overlays)

    chart.on_overlays_changed(on_overlays_changed)

    def refresh() -> None:
        sym = symbol_sel.value
        tf = tf_toggle.value
        state["chart_symbol"] = sym
        state["chart_timeframe"] = TIMEFRAMES[tf]

        isin = _isin_for(con, sym)
        if not isin:
            return

        daily = _load_daily(con, isin, int(bars_input.value))
        if daily.empty:
            ui.notify("No bars for this symbol yet.", type="warning")
            return

        bars_df = {"D": daily, "W": rs.to_weekly(daily),
                  "M": rs.to_monthly(daily)}[tf]
        if bars_df.empty:
            ui.notify("Not enough history for this timeframe yet.", type="warning")
            return
        bars_df = bars_df.reset_index(drop=True)

        chart_type = type_sel.value
        if chart_type == "Heikin Ashi":
            display_df = rs.to_heikin_ashi(bars_df)
        elif chart_type == "Renko":
            ccfg = CFG["chart"]
            display_df = rs.to_renko(bars_df, brick_mode=ccfg["renko_brick_mode"],
                                     brick_atr_mult=ccfg["renko_brick_atr_mult"])
        else:
            display_df = bars_df

        vol = display_df["volume"] if "volume" in display_df.columns else None
        chart.set_bars([
            {"date": pd.Timestamp(d).strftime("%Y-%m-%dT%H:%M:%S"),
             "open": float(o), "high": float(h), "low": float(l), "close": float(c),
             "volume": float(vol.iloc[i]) if vol is not None and vol.iloc[i] == vol.iloc[i] else 0}
            for i, (d, o, h, l, c) in enumerate(zip(
                display_df["date"], display_df["open"], display_df["high"],
                display_df["low"], display_df["close"]))
        ])
        chart.set_style("area" if chart_type == "Line" else "candle_solid")
        chart.set_indicators([f"MA:{','.join(o[3:] for o in overlays_sel.value)}"]
                             if overlays_sel.value else [])

        # Metrics strip — always the latest DAILY features_1d row: weekly/
        # monthly indicator tables don't exist yet (see README "Pending
        # features"), so these are today's real daily readings regardless
        # of which timeframe the candles above are drawn in.
        last = daily.iloc[-1]

        def fmt(col: str, digits: int = 1) -> str:
            v = last.get(col)
            return f"{v:.{digits}f}" if v is not None and v == v else "—"

        # W-pattern on the current timeframe's real bars (not the Heikin
        # Ashi/Renko transform) — same detection rules regardless of
        # timeframe, applied to that timeframe's own bars, per the "same
        # logic across 1D/1W/1M" instruction.
        pcfg = CFG["pattern"]
        atr_s = ind.atr(bars_df["high"], bars_df["low"], bars_df["close"])
        candidates = pat.find_w_patterns(
            bars_df, atr_s,
            zigzag_pct=pcfg["zigzag_pct"], min_separation=pcfg["min_separation"],
            max_separation=pcfg["max_separation"], require_undercut=pcfg["require_undercut"],
            min_depth_pct=pcfg["min_depth_pct"], exclude_locked_bars=pcfg["exclude_locked_bars"],
            confirm_max_wait=pcfg["entry_max_wait"],
        )
        active = candidates[-1] if candidates else None

        metrics_row.clear()
        with metrics_row:
            for label, val in [
                ("close", f"{last['close']:.2f}"), ("ADR%", fmt("adr_pct20")),
                ("ADX", fmt("adx14")), ("RSI", fmt("rsi14")),
                ("delivery%", fmt("deliv_pct_sma20")), ("RS rank", fmt("rs_rank_pct", 0)),
                ("pattern", "W found" if active else "none"),
            ]:
                with ui.column().classes("gap-0"):
                    ui.label(label).classes("text-xs").style(f"color:{theme.TEXT_MUTED}")
                    ui.label(val).classes("text-sm font-mono").style(
                        f"color:{theme.TEXT_PRIMARY}")

        server_overlays = []
        if show_w.value and active:
            for label, price in (("L1", active.l1_price), ("L2", active.l2_price),
                                 ("neckline", active.neckline)):
                server_overlays.append({
                    "name": "priceLine",
                    "points": [{"value": price}],
                    "extendData": label,
                    "lock": True,
                })

        avwap_choice = avwap_sel.value
        if avwap_choice != "(none)" and "vwap" in bars_df.columns:
            lookback = 252 if tf == "D" else 52
            if avwap_choice == "52-week low":
                pos = int(bars_df["low"].tail(lookback).idxmin())
            elif avwap_choice == "52-week high":
                pos = int(bars_df["high"].tail(lookback).idxmax())
            else:
                pos = active.l1_pos if active else 0
            av, _, _ = ind.anchored_vwap(
                bars_df["vwap"].fillna(bars_df["close"]), bars_df["volume"], pos)
            points = [{"timestamp": int(pd.Timestamp(bars_df["date"].iloc[i]).timestamp() * 1000),
                      "value": float(v)}
                     for i, v in enumerate(av) if v == v]
            if len(points) >= 2:
                server_overlays.append({"name": "path", "points": points, "lock": True})

        user_drawings = _load_drawings(con, isin, state["chart_timeframe"])
        chart.load_overlays(user_drawings, server_overlays)

    for control in (symbol_sel, bars_input, tf_toggle, type_sel,
                    overlays_sel, avwap_sel, show_w):
        control.on_value_change(refresh)

    refresh()
