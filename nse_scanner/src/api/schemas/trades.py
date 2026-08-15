"""api/schemas/trades.py — request models for opening/closing a position."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class TradeOpenRequest(BaseModel):
    symbol: str
    entry_date: date
    entry_price: float
    qty: int
    stop_price: float
    target_price: float | None = None
    preset_name: str = ""
    thesis: str = ""


class TradeCloseRequest(BaseModel):
    exit_date: date
    exit_price: float
    exit_reason: str  # target | stop | time_stop | discretionary
    followed_plan: bool = True
    review_note: str = ""
    tags: list[str] = []
