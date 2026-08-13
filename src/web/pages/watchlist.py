"""
web/pages/watchlist.py — symbols tracked but not yet traded.

"Promote to holding" reuses holdings.open_entry_dialog() rather than
duplicating the position-entry form.
"""

from __future__ import annotations

from nicegui import ui

import components as comp
import theme
import watchlist as wl
from pages.holdings import open_entry_dialog


def _symbols(con) -> list[str]:
    return con.execute(
        "SELECT DISTINCT symbol FROM instruments ORDER BY symbol"
    ).df()["symbol"].tolist()


def render(con, state: dict) -> None:
    comp.page_title("Watchlist")

    body = ui.column().classes("w-full gap-2")

    def refresh() -> None:
        body.clear()
        with body:
            with ui.row().classes("w-full gap-2 items-end"):
                symbols = _symbols(con)
                sym_sel = ui.select(symbols, with_input=True, label="Symbol").classes("w-48")
                note_in = ui.input("Note").classes("w-48")
                target_in = ui.number("Target price", min=0, step=0.05).classes("w-32")
                tags_in = ui.input("Tags").classes("w-32")

                def add():
                    if not sym_sel.value:
                        ui.notify("Pick a symbol.", type="warning")
                        return
                    wl.add(con, sym_sel.value, note=note_in.value or "",
                          target_price=target_in.value or None, tags=tags_in.value or "")
                    ui.notify(f"Added {sym_sel.value} to watchlist.", type="positive")
                    refresh()

                ui.button("Add", on_click=add).props("unelevated no-caps")

            df = wl.list_with_status(con)
            if df.empty:
                ui.label("Watchlist is empty.").classes("text-sm mt-2")
                return

            for _, row in df.iterrows():
                near = bool(row.get("near_trigger"))
                with ui.card().classes("w-full").style(
                        f"background:{theme.SURFACE}; "
                        f"border:1px solid {theme.WARNING if near else theme.BORDER};"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.row().classes("items-center gap-3"):
                            ui.label(row["symbol"]).classes("text-base font-bold")
                            if near:
                                ui.html(f'<span class="{theme.status_class("WATCH")}">NEAR TRIGGER</span>')
                        with ui.row().classes("items-center gap-2"):
                            ui.button("Promote to holding",
                                     on_click=lambda sym=row["symbol"]: open_entry_dialog(
                                         con, refresh, prefill_symbol=sym)) \
                                .props("dense no-caps outline")
                            ui.button(icon="delete_outline",
                                     on_click=lambda isin=row["isin"]: (wl.remove(con, isin),
                                                                        ui.notify("Removed."), refresh())) \
                                .props("flat dense round size=sm")

                    close = row.get("close")
                    target = row.get("target_price")
                    pct_from_target = (abs(close - target) / target * 100.0
                                       if close is not None and target else None)
                    with ui.row().classes("w-full gap-6 text-xs mt-1").style(
                            f"color:{theme.TEXT_MUTED}"):
                        ui.label(f"close {close:.2f}" if close is not None else "close —")
                        ui.label(f"target {target:.2f}" if target else "target —")
                        ui.label(f"{pct_from_target:.1f}% from target"
                                 if pct_from_target is not None else "")
                        if row.get("note"):
                            ui.label(f"note: {row['note']}")
                        if row.get("tags"):
                            ui.label(f"tags: {row['tags']}")

    refresh()
