"""web/pages/today.py — default landing screen. Stub; built out in Part G."""

from nicegui import ui

import components as comp


def render(con, state: dict) -> None:
    comp.page_title("Today", "Everything important, without clicking.")
    ui.label("Part G not yet built.").classes("text-sm")
