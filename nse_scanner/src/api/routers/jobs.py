"""api/routers/jobs.py — the full-rebuild background job (start + poll)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api import jobs as job_store
from api.deps import get_master
from api.services.refresh import full_rebuild_steps

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/full-rebuild")
def post_full_rebuild() -> dict:
    cur = get_master().cursor()
    job_id = job_store.start(full_rebuild_steps(cur))
    return {"job_id": job_id}


@router.get("/{job_id}")
def get_job(job_id: str) -> dict:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return job
