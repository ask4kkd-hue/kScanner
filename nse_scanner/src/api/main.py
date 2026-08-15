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

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from api.deps import get_master  # noqa: E402
from api.routers import data  # noqa: E402


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Opens the master connection + runs init_schema once, at process start —
    # matches web/main.py's _master() lazy-init in effect (same connect()/
    # init_schema() call), just triggered eagerly here so the first request
    # isn't the one paying DB-open cost. Deliberately does this ONLY here
    # (not also lazily inside get_master(), which would risk a second
    # connect() attempt racing this one on the single-writer DB file).
    get_master()
    yield


app = FastAPI(title="kSCANNER API", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data.router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


_DIST = _SRC.parent.parent / "nse_scanner_ui" / "dist"
if _DIST.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")


if __name__ in {"__main__", "__mp_main__"}:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
