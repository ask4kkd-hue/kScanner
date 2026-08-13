"""web/pages/backtest.py — ported from app.py's Backtest tab. Stub for now."""

from nicegui import ui

import components as comp


def render(con, state: dict) -> None:
    comp.page_title("Backtest")
    ui.label("Not yet ported from app.py.").classes("text-sm")
