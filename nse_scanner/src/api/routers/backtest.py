"""api/routers/backtest.py — single run / sweep / marginal contribution."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_cursor
from api.schemas.backtest import (
    RunMarginalRequest, RunRecentRequest, RunSingleRequest, RunSweepRequest,
)
from api.services import backtest as bt_service

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("/config")
def get_config() -> dict:
    return bt_service.config()


@router.post("/run")
def post_run(body: RunSingleRequest, cur=Depends(get_cursor)) -> dict:
    try:
        run_id = bt_service.run_single(
            cur, body.preset_name, body.entry_variant, body.exit_variant,
            body.sample, body.limit_symbols, body.label,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Backtest failed: {e}") from e
    return {"run_id": run_id}


@router.get("/{run_id}")
def get_run(run_id: str, cur=Depends(get_cursor)) -> dict:
    return bt_service.get_run(cur, run_id)


@router.post("/sweep")
def post_sweep(body: RunSweepRequest, cur=Depends(get_cursor)) -> list[dict]:
    try:
        return bt_service.run_sweep(cur, body.preset_name, body.sample, body.limit_symbols)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Sweep failed: {e}") from e


@router.post("/marginal")
def post_marginal(body: RunMarginalRequest, cur=Depends(get_cursor)) -> list[dict]:
    try:
        return bt_service.run_marginal(cur, body.entry_variant, body.exit_variant, body.limit_symbols)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Marginal contribution failed: {e}") from e


@router.post("/recent")
def post_recent(body: RunRecentRequest, cur=Depends(get_cursor)) -> dict:
    try:
        return bt_service.run_recent(
            cur, body.preset_name, body.entry_variant, body.exit_variant,
            body.days_back, body.limit_symbols,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Recent signals report failed: {e}") from e
