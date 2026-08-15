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


class TradeUpdateRequest(BaseModel):
    # All optional — only the fields actually sent get updated (see
    # journal.update_trade's _EDITABLE_FIELDS allowlist; exit-side fields
    # aren't editable here on purpose, that's close_trade's job).
    entry_date: date | None = None
    entry_price: float | None = None
    qty: int | None = None
    stop_price: float | None = None
    target_price: float | None = None
    thesis: str | None = None


class TradeCloseRequest(BaseModel):
    exit_date: date
    exit_price: float
    exit_reason: str  # target | stop | time_stop | discretionary
    followed_plan: bool = True
    review_note: str = ""
    tags: list[str] = []
