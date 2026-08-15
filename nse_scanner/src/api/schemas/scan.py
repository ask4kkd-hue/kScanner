"""api/schemas/scan.py — request/response shapes for the Scan screen."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChipState(BaseModel):
    active: bool
    value: float | str | None = None


class ScanRunResponse(BaseModel):
    scan_id: str
    total_count: int
    preselected_chip_ids: list[str]


class ScanFilterRequest(BaseModel):
    chips: dict[str, ChipState]


class ScanFilterResponse(BaseModel):
    count: int
    total: int
    rows: list[dict[str, Any]]  # symbol/trigger_price/l1_price/... — same free-form
                                # shape render_grid() picked, not worth a rigid model
    bottom_at_sma_distribution: dict[str, int]
