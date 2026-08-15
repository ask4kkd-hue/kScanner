"""
web/kline.py — Python wrapper for the vendored KLineChart component.

Event-argument unwrapping verified against NiceGUI's own CodeMirror element
(elements/codemirror/line_anchors.py): a JS `$emit('name', payload)` arrives
as `e.args == payload` directly — no extra wrapping.
"""

from __future__ import annotations

from typing import Callable

from nicegui import ui
from nicegui.events import GenericEventArguments


class KLineChart(ui.element,
                 component="components/klinechart.js",
                 esm={"klinecharts": "static/vendor/klinecharts"}):
    """
    set_bars/set_indicators/set_style/load_overlays/clear_overlays go to JS.
    on_overlays_changed/on_crosshair come back from JS.
    """

    def __init__(self, *, chart_type: str = "candle_solid") -> None:
        super().__init__()
        self._props["initialType"] = chart_type
        self.classes("w-full").style("height:520px;")

    def set_bars(self, bars: list[dict]) -> None:
        """bars: [{date, open, high, low, close, volume}, ...]. date may be
        an ISO string or epoch milliseconds."""
        self.run_method("set_bars", bars)

    def set_indicators(self, indicators: list[str]) -> None:
        """e.g. ['MA:10,20,50', 'VOL']."""
        self.run_method("set_indicators", indicators)

    def set_style(self, chart_type: str) -> None:
        """'candle_solid' | 'area'."""
        self.run_method("set_style", chart_type)

    def load_overlays(self, user_drawings: list[dict], server_overlays: list[dict] | None = None) -> None:
        """user_drawings: loaded from the drawings table, persisted on edit.
        server_overlays: informational (W-pattern lines, AVWAP), recomputed
        every refresh, never saved back as if the user drew them."""
        self.run_method("load_overlays", user_drawings, server_overlays or [])

    def clear_overlays(self) -> None:
        self.run_method("clear_overlays")

    def clear_user_overlays(self) -> None:
        """The 'Clear all' drawing-tool action: removes user drawings only,
        leaves server-computed pattern/AVWAP lines in place."""
        self.run_method("clear_user_overlays")

    def start_drawing(self, tool: str) -> None:
        """tool: horizontal_line | trend_line | ray | rectangle |
        fibonacci_retracement | text_note."""
        self.run_method("start_drawing", tool)

    def resize(self) -> None:
        self.run_method("resize")

    def on_overlays_changed(self, handler: Callable[[list[dict]], None]) -> "KLineChart":
        self.on("overlays-changed", lambda e: handler(e.args))
        return self

    def on_crosshair(self, handler: Callable[[int], None]) -> "KLineChart":
        self.on("crosshair", lambda e: handler(e.args))
        return self
