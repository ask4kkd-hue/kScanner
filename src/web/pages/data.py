"""web/pages/data.py — ported from app.py's Data tab. Stub for now."""

from nicegui import ui

import components as comp


def render(con, state: dict) -> None:
    comp.page_title("Data")
    ui.label("Not yet ported from app.py.").classes("text-sm")
