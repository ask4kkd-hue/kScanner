"""web/pages/backtest.py — ported from app.py's (v1) Backtest tab. Behaviour unchanged."""

from __future__ import annotations

from nicegui import ui

import components as comp
import theme
from backtest import analyse_curves, marginal_contribution, run_backtest, sweep
from config import CFG


def render(con, state: dict) -> None:
    comp.page_title("Backtest", "W-pattern study")
    ui.label("Run the unfiltered control first. Without a baseline number "
            "you cannot tell whether a filter helped, hurt, or did nothing.") \
        .classes("text-sm").style(f"color:{theme.TEXT_MUTED}")

    preset_names = list(CFG["presets"].keys())
    entry_variants = CFG["backtest"]["entry_variants"]
    exit_variants = CFG["backtest"]["exit_variants"]
    minimum = CFG["backtest"]["min_trades_for_conclusion"]

    with ui.row().classes("gap-3 items-end w-full flex-wrap"):
        mode_sel = ui.toggle(["Single run", "Entry x exit sweep", "Marginal contribution"],
                             value="Single run").props("dense no-caps")
        preset_sel = ui.select(preset_names, value=preset_names[0], label="Preset").classes("w-40")
        entry_sel = ui.select(entry_variants, value=entry_variants[1] if len(entry_variants) > 1
                              else entry_variants[0], label="Entry").classes("w-24")
        exit_sel = ui.select(exit_variants, value=exit_variants[0], label="Exit").classes("w-24")
        sample_sel = ui.select(["in", "out"], value="in", label="Sample").classes("w-20")
        limit_in = ui.number("Limit symbols (0 = all)", value=0, min=0).classes("w-32")

    results_box = ui.column().classes("w-full gap-3 mt-2")
    run_btn = ui.button("Run backtest", icon="play_arrow").props("unelevated no-caps")

    async def do_run() -> None:
        run_btn.props("loading")
        lim = int(limit_in.value) or None
        try:
            if mode_sel.value == "Single run":
                rid = await comp.run_bg(run_backtest, con, preset_sel.value,
                                        entry_sel.value, exit_sel.value,
                                        sample=sample_sel.value, limit_symbols=lim)
                render_single_run(rid)
            elif mode_sel.value == "Entry x exit sweep":
                s = await comp.run_bg(sweep, con, preset_sel.value, sample_sel.value, lim)
                render_sweep(s)
            else:
                m = await comp.run_bg(
                    marginal_contribution, con, "w_baseline",
                    ["w_sma200_trend", "w_sma200_rising", "w_sma50_trend",
                     "w_golden", "w_stacked", "w_delivery", "w_full"],
                    entry_sel.value, exit_sel.value, lim)
                render_marginal(m)
        except Exception as exc:
            ui.notify(f"Backtest failed: {exc}", type="negative", multi_line=True)
        finally:
            run_btn.props(remove="loading")

    def render_marginal(m) -> None:
        results_box.clear()
        with results_box:
            ui.label("Does each filter actually add anything?").classes(
                "text-sm font-semibold")
            comp.dataframe_grid(m[["preset", "trades", "win_rate", "expectancy_r",
                    "delta_expectancy", "trade_retention_pct", "enough_trades"]])
            ui.label(f"A filter that lifts expectancy but cuts trades below "
                    f"{minimum} has found a coincidence, not an edge.").classes(
                "text-xs italic mt-1").style(f"color:{theme.TEXT_MUTED}")

    def render_sweep(s) -> None:
        results_box.clear()
        with results_box:
            ui.label("Entry x exit grid").classes("text-sm font-semibold")
            comp.dataframe_grid(s[["entry", "exit", "trades", "win_rate", "expectancy_r",
                    "profit_factor", "median_hold_days", "max_dd_pct"]])
            ui.label("Sorted by expectancy — check the trade count before "
                    "believing the top row.").classes("text-xs italic mt-1").style(
                f"color:{theme.TEXT_MUTED}")

    def render_single_run(rid: str) -> None:
        results_box.clear()
        with results_box:
            m = con.execute("SELECT * FROM backtest_metrics WHERE run_id = ?", [rid]).df()
            if not m.empty:
                r = m.iloc[0]
                with ui.row().classes("gap-6 text-sm"):
                    ui.label(f"Trades: {int(r['trades'])}")
                    ui.label(f"Win rate: {r['win_rate']:.1f}%")
                    ui.label(f"Expectancy: {r['expectancy_r']:.3f} R")
                    ui.label(f"Profit factor: {r['profit_factor']:.2f}")
                    ui.label(f"Max DD: {r['max_dd_pct']:.1f}%")
                    ui.label(f"Median hold: {r['median_hold_days']:.0f} d")
                if r["trades"] < minimum:
                    ui.label(f"Only {int(r['trades'])} trades — below the "
                            f"{minimum} threshold. This is noise, not a result.") \
                        .classes("text-sm mt-1").style(f"color:{theme.WARNING}")

            curves = analyse_curves(con, rid)
            if not curves.empty:
                ui.label("Holding period, measured").classes(
                    "text-sm font-semibold mt-3")
                ui.label("Median MFE by day — where this flattens is your "
                        "natural holding period").classes("text-xs").style(
                    f"color:{theme.TEXT_MUTED}")
                ui.echart({
                    "backgroundColor": "transparent",
                    "grid": {"left": 40, "right": 20, "top": 10, "bottom": 24},
                    "xAxis": {"type": "category", "data": curves["day_n"].tolist(),
                             "axisLabel": {"color": theme.TEXT_MUTED}},
                    "yAxis": {"type": "value", "axisLabel": {"color": theme.TEXT_MUTED}},
                    "series": [
                        {"type": "line", "name": "median MFE", "showSymbol": False,
                         "data": curves["median_mfe"].round(2).tolist(),
                         "lineStyle": {"color": theme.ACCENT}},
                        {"type": "line", "name": "p75 MFE", "showSymbol": False,
                         "data": curves["p75_mfe"].round(2).tolist(),
                         "lineStyle": {"color": theme.SMA_COLORS["sma200"]}},
                    ],
                    "legend": {"textStyle": {"color": theme.TEXT_MUTED}},
                }).classes("w-full").style("height:200px;")

                if "p85_mae_win" in curves.columns:
                    ui.label("Stop candidate: the drawdown 85% of eventual "
                            "winners never exceeded").classes("text-xs mt-2").style(
                        f"color:{theme.TEXT_MUTED}")
                    ui.echart({
                        "backgroundColor": "transparent",
                        "grid": {"left": 40, "right": 20, "top": 10, "bottom": 24},
                        "xAxis": {"type": "category", "data": curves["day_n"].tolist(),
                                 "axisLabel": {"color": theme.TEXT_MUTED}},
                        "yAxis": {"type": "value", "axisLabel": {"color": theme.TEXT_MUTED}},
                        "series": [{"type": "line", "showSymbol": False,
                                  "data": curves["p85_mae_win"].round(2).tolist(),
                                  "lineStyle": {"color": theme.CRITICAL}}],
                    }).classes("w-full").style("height:160px;")

                comp.dataframe_grid(curves)

    run_btn.on_click(do_run)
