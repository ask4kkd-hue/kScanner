"""api/routers/today.py — one aggregate GET, mirrors web/pages/today.py's five sections."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends

from api.deps import get_cursor
from api.schemas.today import OpportunityBlock, TodayResponse
from api.services.today import available_scan_dates, get_opportunities, get_today

router = APIRouter(prefix="/today", tags=["today"])


@router.get("", response_model=TodayResponse)
def today(cur=Depends(get_cursor)) -> dict:
    return get_today(cur)


@router.get("/opportunities", response_model=list[OpportunityBlock])
def opportunities(as_of_date: date | None = None, cur=Depends(get_cursor)) -> list[dict]:
    """Same shape as TodayResponse.opportunities, fetched on its own so New
    Opportunity can browse a past scan date without touching Dashboard's
    live positions/P&L (get_today() covers those, unaffected by as_of_date)."""
    return get_opportunities(cur, as_of_date)


@router.get("/opportunity-dates")
def opportunity_dates(timeframe: str = "1d", cur=Depends(get_cursor)) -> dict:
    return {"dates": available_scan_dates(cur, timeframe)}
