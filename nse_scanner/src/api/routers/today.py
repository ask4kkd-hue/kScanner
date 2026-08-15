"""api/routers/today.py — one aggregate GET, mirrors web/pages/today.py's five sections."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_cursor
from api.schemas.today import TodayResponse
from api.services.today import get_today

router = APIRouter(prefix="/today", tags=["today"])


@router.get("", response_model=TodayResponse)
def today(cur=Depends(get_cursor)) -> dict:
    return get_today(cur)
