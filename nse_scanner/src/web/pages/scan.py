"""
web/pages/scan.py — scan once, filter instantly with chips.

The expensive part (pattern detection across the universe) runs once per
"Run scan" click and is cached in `state['scan_df']` as a superset with
every features_1d column attached (scan.scan(..., apply_preset=False)).
Chips then filter that in-memory DataFrame — no re-scan as chips change.
"""

from __future__ import annotations

import re

from nicegui import ui

import components as comp
import theme
import watchlist as wl
from backtest import _eval_condition
from config import CFG, save_preset
from scan import scan as run_scan

CHIPS = CFG["filter_chips"]
CHIP_BY_ID = {c["id"]: c for c in CHIPS}


def _chip_column(expr: str) -> str:
    """The leftmost identifier in a chip's expr — used to match a chip to a
    preset condition on the same column, for pre-selecting chips."""
    m = re.match(r"\s*([a-zA-Z_][a-zA-Z0-9_]*)", expr)
    return m.group(1) if m else ""


def render(con, state: dict) -> None:
    comp.page_title("Scan", "Scan once, filter instantly with chips.")

    preset_names = list(CFG["presets"].keys())
    chip_state: dict[str, dict] = state.setdefault("scan_chip_state", {
        c["id"]: {"active": False, "value": c.get("default")} for c in CHIPS
    })

    with ui.row().classes("w-full gap-3 items-end"):
        preset_sel = ui.select(preset_names, value=preset_names[0],
                               label="Preset").classes("w-48")
        run_btn = ui.button("Run scan", icon="play_arrow").props("unelevated no-caps")
        count_label = ui.label("").classes("text-sm").style(f"color:{theme.TEXT_MUTED}")

    chip_row = ui.row().classes("w-full gap-2 flex-wrap")
    grid_box = ui.column().classes("w-full")
    dist_box = ui.column().classes("w-full")

    def preselect_chips_for_preset(name: str) -> list[str]:
        """Best-effort: a chip is pre-selected if the preset filters the
        same column, matched by name — not by exact operator/threshold,
        since chips carry their own independent default values."""
        from config import resolve_preset
        conditions = resolve_preset(CFG, name).get("conditions", [])
        cond_cols = {_chip_column(c) for c in conditions}
        turned_on = []
        for c in CHIPS:
            chip_state[c["id"]]["active"] = _chip_column(c["expr"]) in cond_cols
            if chip_state[c["id"]]["active"]:
                turned_on.append(c["label"])
        return turned_on

    def apply_filters() -> None:
        df = state.get("scan_df")
        if df is None:
            return
        filtered = df
        for chip in CHIPS:
            cs = chip_state[chip["id"]]
            if not cs["active"]:
                continue
            expr = chip["expr"]
            if "{v}" in expr:
                expr = expr.replace("{v}", str(cs["value"]))
            mask = filtered.apply(lambda row: _eval_condition(row, expr), axis=1)
            filtered = filtered[mask]

        count_label.text = f"{len(filtered)} of {len(df)} signals"
        state["scan_filtered"] = filtered
        render_grid(filtered)
        render_distribution(filtered)

    def render_chips() -> None:
        chip_row.clear()
        with chip_row:
            for chip in CHIPS:
                cs = chip_state[chip["id"]]
                active = cs["active"]

                def toggle(c=chip):
                    chip_state[c["id"]]["active"] = not chip_state[c["id"]]["active"]
                    render_chips()
                    apply_filters()

                label = chip["label"]
                if active and "{v}" in chip["expr"]:
                    label = f'{chip["label"]} {cs["value"]}'
                btn = ui.button(label, on_click=toggle).props(
                    "dense no-caps unelevated" if active else "dense no-caps outline"
                ).classes("text-xs")
                if active:
                    btn.style(f"background:{theme.ACCENT}; color:white;")
                if active and "{v}" in chip["expr"]:
                    def on_value(e, c=chip):
                        chip_state[c["id"]]["value"] = e.value
                        render_chips()
                        apply_filters()
                    ui.number(value=cs["value"], min=chip.get("min"),
                             max=chip.get("max"), step=chip.get("step", 1),
                             on_change=on_value).classes("w-20").props("dense borderless")

    def render_grid(df) -> None:
        grid_box.clear()
        with grid_box:
            if df.empty:
                ui.label("No signals match the current chips.").classes("text-sm")
                return
            cols = ["symbol", "trigger_price", "l1_price", "l2_price", "neckline",
                   "depth_pct", "stop_suggested", "target_suggested",
                   "bottom_at_sma", "sma_stack", "rs_rank_pct"]
            cols = [c for c in cols if c in df.columns]
            column_defs = [{"field": c, "sortable": True, "filter": True,
                           "resizable": True} for c in cols]
            column_defs.append({"headerName": "", "field": "_actions",
                               "sortable": False, "filter": False, "width": 90})
            row_data = df[cols].round(2).to_dict("records")

            grid = ui.aggrid({
                "columnDefs": column_defs,
                "rowData": row_data,
                "rowSelection": "single",
                "domLayout": "autoHeight",
            }).classes("w-full")

            def on_row_click(e) -> None:
                sym = e.args["data"].get("symbol")
                if sym:
                    state["chart_symbol"] = sym
                    ui.notify(f"Opening {sym} in Chart — switch tabs to view.")

            grid.on("rowClicked", on_row_click)

            with ui.row().classes("gap-2 mt-1"):
                symbol_input = ui.select(df["symbol"].tolist(), label="Add to watchlist") \
                    .classes("w-48")

                def add_watch():
                    if symbol_input.value:
                        wl.add(con, symbol_input.value)
                        ui.notify(f"Added {symbol_input.value} to watchlist.")

                ui.button("Add to Watchlist", on_click=add_watch).props("dense no-caps outline")

    def render_distribution(df) -> None:
        dist_box.clear()
        with dist_box:
            if df.empty or "bottom_at_sma" not in df.columns:
                return
            counts = df["bottom_at_sma"].value_counts()
            ui.label("Where the second bottom formed").classes("text-sm font-semibold mt-2")
            ui.echart({
                "backgroundColor": "transparent",
                "xAxis": {"type": "category", "data": counts.index.tolist(),
                         "axisLabel": {"color": theme.TEXT_MUTED}},
                "yAxis": {"type": "value", "axisLabel": {"color": theme.TEXT_MUTED}},
                "series": [{"type": "bar", "data": counts.values.tolist(),
                          "itemStyle": {"color": theme.ACCENT}}],
            }).classes("w-full").style("height:220px;")

    async def do_run_scan() -> None:
        run_btn.props("loading")
        try:
            df = await comp.run_bg(run_scan, con, preset_sel.value,
                                   ignore_stale=True, apply_preset=False)
        except RuntimeError as exc:
            ui.notify(str(exc), type="negative", multi_line=True, timeout=10000)
            return
        finally:
            run_btn.props(remove="loading")
        state["scan_df"] = df
        turned_on = preselect_chips_for_preset(preset_sel.value)
        ui.notify(f"Scan complete: {len(df)} candidates. "
                 f"Preset turned on: {', '.join(turned_on) or 'none'}.")
        render_chips()
        apply_filters()

    def on_preset_change() -> None:
        turned_on = preselect_chips_for_preset(preset_sel.value)
        render_chips()
        apply_filters()
        if turned_on:
            ui.notify(f"'{preset_sel.value}' turned on: {', '.join(turned_on)}")

    async def save_as_preset() -> None:
        active_conditions = []
        for chip in CHIPS:
            cs = chip_state[chip["id"]]
            if cs["active"]:
                expr = chip["expr"]
                if "{v}" in expr:
                    expr = expr.replace("{v}", str(cs["value"]))
                active_conditions.append(expr)
        if not active_conditions:
            ui.notify("No chips are active — nothing to save.", type="warning")
            return

        with ui.dialog() as dialog, ui.card():
            ui.label("Save active chips as a preset")
            name_input = ui.input("Preset name (letters, numbers, underscore)").classes("w-64")
            with ui.row():
                ui.button("Cancel", on_click=dialog.close).props("flat no-caps")

                def confirm():
                    name = (name_input.value or "").strip()
                    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", name or ""):
                        ui.notify("Enter a valid preset name.", type="warning")
                        return
                    try:
                        save_preset(name, active_conditions)
                    except ValueError as exc:
                        ui.notify(str(exc), type="negative")
                        return
                    dialog.close()
                    preset_names.append(name)
                    preset_sel.options = list(preset_names)
                    preset_sel.update()
                    ui.notify(f"Saved preset '{name}' to config.yaml.", type="positive")

                ui.button("Save", on_click=confirm).props("unelevated no-caps")
        dialog.open()

    run_btn.on_click(do_run_scan)
    preset_sel.on_value_change(on_preset_change)
    with ui.row().classes("gap-2"):
        ui.button("Save these chips as a preset", on_click=save_as_preset) \
            .props("dense no-caps outline")

    render_chips()
    if state.get("scan_df") is not None:
        count_label.text = f"{len(state.get('scan_filtered', state['scan_df']))} of {len(state['scan_df'])} signals"
        render_grid(state.get("scan_filtered", state["scan_df"]))
        render_distribution(state.get("scan_filtered", state["scan_df"]))
    else:
        ui.label("Click 'Run scan' to find candidates.").classes("text-sm")
