"""api/schemas/today.py — response shape for GET /api/today (one aggregate call, see routers/today.py)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class StatusInfo(BaseModel):
    stale: bool
    latest_bar: date | None
    latest_cal: date | None
    validation_fails_7d: int
    regime: str
    sessions_behind: int | None = None


class PositionRow(BaseModel):
    trade_id: int
    symbol: str
    entry_date: date
    entry_price: float
    qty: int
    stop_price: float
    close: float | None
    days_held: int | None
    pnl_pct: float | None
    pnl_rupees: float | None
    r_multiple: float | None
    mae_pct: float | None
    mfe_pct: float | None
    status: str  # HOLD | WATCH | REVIEW -- advisor guidance, not position lifecycle
    reasons: list[str]
    lifecycle_status: str  # OPEN | PARTIAL_PROFIT | PARTIAL_LOSS | CLOSED
    remaining_qty: int
    partial_pnl_rupees: float | None


class OpportunitySignal(BaseModel):
    symbol: str
    trigger_price: float
    l1_price: float | None
    l2_price: float | None
    l1_l2_distance_pct: float | None
    neckline: float | None
    depth_pct: float | None
    stop_suggested: float | None
    target_suggested: float | None
    bottom_at_sma: str | None
    sma_stack: str | None
    rs_rank_pct: float | None


class OpportunityBlock(BaseModel):
    timeframe: str  # 1d | 1w | 1m
    built: bool  # False only for 1w/1m when that features table has zero rows
    total_signals: int
    new_signals: list[OpportunitySignal]  # full list, untracked (not already held/watched)
    already_tracked_count: int


class WatchlistNearRow(BaseModel):
    symbol: str
    close: float | None
    target_price: float | None
    neckline: float | None


class PnlSummary(BaseModel):
    today: float
    this_week: float
    this_month: float
    all_time: float
    unrealised: float


class EquityPoint(BaseModel):
    exit_date: str
    cum_pnl: float


class TodayResponse(BaseModel):
    status: StatusInfo
    positions: list[PositionRow]
    total_open_pnl: float
    at_risk_count: int
    opportunities: list[OpportunityBlock]
    pnl: PnlSummary
    equity_curve: list[EquityPoint]
    watchlist_near_trigger: list[WatchlistNearRow]
