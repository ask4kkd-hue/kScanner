"""api/routers/analytics.py — the Analytics screen: config + run."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_cursor
from api.schemas.analytics import RunAnalysisRequest
from api.services import analytics as analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/config")
def get_config() -> dict:
    return analytics_service.config()


@router.post("/run")
def post_run(body: RunAnalysisRequest, cur=Depends(get_cursor)) -> list[dict]:
    try:
        return analytics_service.run(cur, body.analysis_type, body.min_pct, body.max_pct)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
