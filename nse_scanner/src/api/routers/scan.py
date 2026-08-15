"""api/routers/scan.py — run-once, filter-in-memory via chips."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_cursor
from api.schemas.scan import ScanFilterRequest, ScanFilterResponse, ScanRunResponse
from api.services import scan as scan_service

router = APIRouter(prefix="/scan", tags=["scan"])


@router.get("/filter-chips")
def get_filter_chips() -> list[dict]:
    return scan_service.CHIPS


@router.get("/presets")
def get_presets() -> list[str]:
    return scan_service.presets()


@router.get("/presets/{name}/preselect")
def get_preselect(name: str) -> list[str]:
    try:
        return scan_service.preselected_chip_ids(name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


class RunScanRequest(BaseModel):
    preset_name: str


@router.post("/run", response_model=ScanRunResponse)
def post_run(body: RunScanRequest, cur=Depends(get_cursor)) -> dict:
    try:
        scan_id, total = scan_service.run_scan(cur, body.preset_name)
    except RuntimeError as e:
        # The stale-data guard, or an unknown preset — both are the caller's
        # problem to fix (refresh the data, or pick a real preset), not a
        # server error.
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {
        "scan_id": scan_id, "total_count": total,
        "preselected_chip_ids": scan_service.preselected_chip_ids(body.preset_name),
    }


@router.post("/{scan_id}/filter", response_model=ScanFilterResponse)
def post_filter(scan_id: str, body: ScanFilterRequest) -> dict:
    chips = {k: v.model_dump() for k, v in body.chips.items()}
    result = scan_service.filter_scan(scan_id, chips)
    if result is None:
        raise HTTPException(status_code=404, detail="Scan not found or expired — run scan again.")
    return result


class SavePresetRequest(BaseModel):
    # web/pages/scan.py validated this in the UI layer before ever calling
    # config.save_preset() — that function itself only checks "does this
    # name already exist," nothing about the name's shape. An empty or
    # punctuation-laden name reaching save_preset() gets written straight
    # into config.yaml's presets: block verbatim (it's a surgical text
    # insert, not a schema-validated writer), so this validation has to
    # happen here, at the API boundary, not be assumed from the service.
    name: str = Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    conditions: list[str]


@router.post("/save-preset")
def post_save_preset(body: SavePresetRequest) -> dict:
    try:
        scan_service.save_preset(body.name, body.conditions)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"saved": body.name}
