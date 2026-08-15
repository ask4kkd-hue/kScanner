"""api/routers/exports.py — reveal the exports folder in Explorer. Only makes sense because frontend and backend run on the same machine, same assumption web/shell.py's open_exports() made."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/exports", tags=["exports"])

_EXPORTS_DIR = Path(__file__).resolve().parents[3] / "exports"


@router.post("/reveal")
def reveal() -> dict:
    try:
        subprocess.Popen(["explorer", str(_EXPORTS_DIR)])
        opened = True
    except Exception:
        opened = False
    return {"path": str(_EXPORTS_DIR), "opened": opened}
