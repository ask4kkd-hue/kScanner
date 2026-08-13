"""
web/components.py — shared building blocks for every v2 screen.
"""

from __future__ import annotations

from typing import Any, Callable

from nicegui import run, ui

import theme


async def run_bg(func: Callable, *args: Any, **kwargs: Any) -> Any:
    """
    Run a blocking call off the event loop (global rule 1). Thin wrapper
    over nicegui.run.io_bound so every screen calls long work the same way.
    """
    return await run.io_bound(func, *args, **kwargs)


def section(title: str, *, collapsed: bool = False) -> ui.expansion:
    """A collapsible panel styled with the shared theme tokens."""
    exp = ui.expansion(title, value=not collapsed).classes("w-full")
    exp.props("dense expand-separator")
    exp.style(f"border:1px solid {theme.BORDER}; border-radius:6px; "
             f"background:{theme.SURFACE};")
    return exp


def page_title(text: str, subtitle: str = "") -> None:
    with ui.column().classes("gap-0 mb-2"):
        ui.label(text).classes("text-lg font-semibold")
        if subtitle:
            ui.label(subtitle).classes("text-sm").style(f"color:{theme.TEXT_MUTED}")


def status_badge(status: str) -> ui.html:
    return ui.html(f'<span class="{theme.status_class(status)}">{status}</span>')
