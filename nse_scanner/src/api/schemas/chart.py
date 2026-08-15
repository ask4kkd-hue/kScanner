"""api/schemas/chart.py — response shape for GET /api/chart/{symbol}."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChartBar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class ChartMetrics(BaseModel):
    close: float
    adr_pct: str
    adx: str
    rsi: str
    delivery_pct: str
    rs_rank: str
    pattern_found: bool


class ChartResponse(BaseModel):
    bars: list[ChartBar]
    chart_style: str  # "area" | "candle_solid"
    indicators: list[str]
    metrics: ChartMetrics
    # Overlay payloads are forwarded verbatim to klinecharts on the client —
    # their shape is klinecharts' own overlay schema (name/points/styles/
    # extendData/lock), not something this API should re-model field by
    # field; the OUTER response benefits from a real schema, these don't.
    server_overlays: list[dict[str, Any]]
    user_drawings: list[dict[str, Any]]
