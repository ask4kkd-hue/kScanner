"""api/schemas/backtest.py — request models for the three run modes."""

from __future__ import annotations

from pydantic import BaseModel


class RunSingleRequest(BaseModel):
    preset_name: str
    entry_variant: str = "E2"
    exit_variant: str = "X1"
    sample: str = "in"  # in | out
    limit_symbols: int | None = None
    label: str = ""


class RunSweepRequest(BaseModel):
    preset_name: str
    sample: str = "in"
    limit_symbols: int | None = None


class RunMarginalRequest(BaseModel):
    entry_variant: str = "E2"
    exit_variant: str = "X1"
    limit_symbols: int | None = None
