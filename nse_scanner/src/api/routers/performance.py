"""api/routers/performance.py — trade-level analytics, all read-only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_cursor
from api.services import performance as perf

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("/summary")
def get_summary(cur=Depends(get_cursor)) -> dict:
    return perf.summary(cur)


@router.get("/equity-curve")
def get_equity_curve(cur=Depends(get_cursor)) -> list[dict]:
    return perf.equity_curve(cur)


@router.get("/attribution")
def get_attribution(cur=Depends(get_cursor)) -> dict:
    return perf.attribution(cur)


@router.get("/adherence")
def get_adherence(cur=Depends(get_cursor)) -> list[dict]:
    return perf.adherence(cur)


@router.get("/tags")
def get_tags(cur=Depends(get_cursor)) -> list[dict]:
    return perf.tags(cur)


@router.get("/snapshot-metrics")
def get_snapshot_metrics() -> list[str]:
    return perf.SNAPSHOT_METRICS


@router.get("/snapshot")
def get_snapshot(metric: str, cur=Depends(get_cursor)) -> list[dict]:
    if metric not in perf.SNAPSHOT_METRICS:
        raise HTTPException(status_code=400, detail=f"Unknown metric: {metric}")
    return perf.snapshot(cur, metric)


@router.get("/presets-traded")
def get_presets_traded(cur=Depends(get_cursor)) -> list[str]:
    return perf.presets_traded(cur)


@router.get("/compare")
def get_compare(preset_name: str, cur=Depends(get_cursor)) -> list[dict]:
    return perf.compare(cur, preset_name)
