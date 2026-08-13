"""web/pages/scan.py — instant-filter scan screen. Stub; built out in Part D."""

from nicegui import ui

import components as comp


def render(con, state: dict) -> None:
    comp.page_title("Scan", "Scan once, filter instantly with chips.")
    ui.label("Part D not yet built.").classes("text-sm")
