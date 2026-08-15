"""api/routers/refresh.py — SSE stream for the daily refresh pipeline (Universe -> Ingest -> Validate -> Features)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse

from api.deps import get_cursor
from api.services.refresh import refresh_steps

router = APIRouter(prefix="/refresh", tags=["refresh"])


@router.get("/stream")
async def stream(cur=Depends(get_cursor)) -> StreamingResponse:
    async def gen():
        for label, fn in refresh_steps(cur):
            yield f"data: {json.dumps({'step': label, 'status': 'running'})}\n\n"
            try:
                await run_in_threadpool(fn)
            except Exception as e:
                tail = str(e).strip().splitlines()[-15:]
                yield f"data: {json.dumps({'step': label, 'status': 'error', 'detail': chr(10).join(tail)})}\n\n"
                return
            yield f"data: {json.dumps({'step': label, 'status': 'done'})}\n\n"
        yield f"data: {json.dumps({'step': None, 'status': 'complete'})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
