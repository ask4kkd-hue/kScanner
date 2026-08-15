"""
api/jobs.py — tiny in-memory job store for the one operation that genuinely
needs background-job-with-polling: the full rebuild (30-90+ minutes). Every
other slow operation (refresh, single backtest, sweep, marginal) is a plain
synchronous call via run_in_threadpool — this is the deliberate exception,
not a pattern to reuse elsewhere. No Redis/DB table needed for one local user.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from typing import Callable

Step = tuple[str, Callable[[], None]]

_JOBS: dict[str, dict] = {}


def _run(job_id: str, steps: list[Step]) -> None:
    _JOBS[job_id]["status"] = "running"
    for label, fn in steps:
        _JOBS[job_id]["step"] = label
        try:
            fn()
        except Exception:
            tail = traceback.format_exc().strip().splitlines()[-15:]
            _JOBS[job_id]["status"] = "error"
            _JOBS[job_id]["error"] = "\n".join(tail)
            return
    _JOBS[job_id]["status"] = "done"
    _JOBS[job_id]["step"] = None


def start(steps: list[Step]) -> str:
    job_id = uuid.uuid4().hex[:12]
    _JOBS[job_id] = {"job_id": job_id, "status": "pending", "step": None, "error": None}
    threading.Thread(target=_run, args=(job_id, steps), daemon=True).start()
    return job_id


def get(job_id: str) -> dict | None:
    return _JOBS.get(job_id)
