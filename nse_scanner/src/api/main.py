"""
api/main.py — FastAPI entry point.

Run with:   python api/main.py                 (dev, matches web/main.py's convention)
       or:  uvicorn api.main:app --reload       (from src/, standard FastAPI dev workflow)
Opens at http://127.0.0.1:8000. The React dev server (nse_scanner_ui, :5173) talks to this
over CORS during development; in the built/cutover mode this same process also serves
nse_scanner_ui/dist as static files (see the mount at the bottom), so only one process
needs to run.
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from config import CFG  # noqa: E402
from api.deps import get_master  # noqa: E402
from api.routers import (  # noqa: E402
    backtest, chart, data, exports, holdings, jobs, performance, refresh, scan, today, watchlist,
)

log = logging.getLogger("api.main")


def _run_startup_warm_scans() -> None:
    """Background thread: pre-compute the configured scans into scan_result_cache
    (config.yaml's startup_warm_scans) so opening Scan for one of them is instant
    on the first try, not just the second. Runs on its own cursor, same concurrency
    pattern as every other background op in this app (api/jobs.py, refresh SSE).

    A CPU-heavy loop (pattern detection across ~2400 symbols, mostly pure-Python/
    pandas work, not I/O) sharing the GIL with uvicorn's asyncio loop measured
    ~8-10x slower here than the identical call in a standalone script (88s solo
    vs 12+ min threaded on this machine) — Python's default 5ms GIL switch
    interval starves a background thread badly against an event loop that keeps
    waking up. Lowering it fixes exactly this known pattern (CPython docs,
    threading + asyncio contention) without touching the scan code itself.
    """
    import time
    prev_interval = sys.getswitchinterval()
    sys.setswitchinterval(0.0005)
    t0 = time.monotonic()
    try:
        from api.services.scan import run_scan
        cur = get_master().cursor()
        for w in CFG.get("startup_warm_scans", []):
            preset, timeframe = w["preset"], w.get("timeframe", "1d")
            try:
                _, n = run_scan(cur, preset, timeframe)
                log.info("Startup warm-scan %s/%s -> %d signals (%.1fs)",
                         preset, timeframe, n, time.monotonic() - t0)
            except Exception:
                log.exception("Startup warm-scan failed for %s/%s", preset, timeframe)
    finally:
        sys.setswitchinterval(prev_interval)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Opens the master connection + runs init_schema once, at process start —
    # matches web/main.py's _master() lazy-init in effect (same connect()/
    # init_schema() call), just triggered eagerly here so the first request
    # isn't the one paying DB-open cost. Deliberately does this ONLY here
    # (not also lazily inside get_master(), which would risk a second
    # connect() attempt racing this one on the single-writer DB file).
    get_master()
    threading.Thread(target=_run_startup_warm_scans, daemon=True).start()
    yield


app = FastAPI(title="kSCANNER API", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data.router, prefix="/api")
app.include_router(today.router, prefix="/api")
app.include_router(chart.router, prefix="/api")
app.include_router(scan.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")
app.include_router(holdings.router, prefix="/api")
app.include_router(performance.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")
app.include_router(refresh.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(exports.router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


_DIST = _SRC.parent.parent / "nse_scanner_ui" / "dist"
if _DIST.exists():
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        # React Router owns everything under here client-side (e.g. /performance,
        # /chart/RELIANCE) — there's no server-side route for those paths, so any
        # non-API, non-asset GET falls back to index.html and the router takes it
        # from there. A stray /api/* 404 is a real 404, not a SPA route.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(_DIST / "index.html")


if __name__ in {"__main__", "__mp_main__"}:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
