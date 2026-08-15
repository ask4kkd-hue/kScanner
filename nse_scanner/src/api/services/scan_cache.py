"""
api/services/scan_cache.py — the server-side replacement for NiceGUI's state["scan_df"].

"Run scan" is expensive (pattern detection across the whole universe, apply_preset=False
so every features_1d column comes along); chips then filter that cached DataFrame
in-memory via the SAME backtest._eval_condition function the CLI/backtest engine uses —
never a reimplementation of chip evaluation in TypeScript.

In-memory, single-process dict — matches this project's "one local user, no Redis needed"
scale (same reasoning as api/jobs.py's job registry). Entries expire after 2 hours or once
more than 20 accumulate, whichever comes first.
"""

from __future__ import annotations

import time
import uuid

import pandas as pd

_CACHE: dict[str, tuple[pd.DataFrame, float]] = {}
_TTL_SECONDS = 2 * 60 * 60
_MAX_ENTRIES = 20


def _evict_stale() -> None:
    now = time.time()
    stale = [k for k, (_, ts) in _CACHE.items() if now - ts > _TTL_SECONDS]
    for k in stale:
        del _CACHE[k]
    if len(_CACHE) > _MAX_ENTRIES:
        oldest = sorted(_CACHE.items(), key=lambda kv: kv[1][1])[: len(_CACHE) - _MAX_ENTRIES]
        for k, _ in oldest:
            del _CACHE[k]


def store(df: pd.DataFrame) -> str:
    _evict_stale()
    scan_id = uuid.uuid4().hex
    _CACHE[scan_id] = (df, time.time())
    return scan_id


def get(scan_id: str) -> pd.DataFrame | None:
    entry = _CACHE.get(scan_id)
    return entry[0] if entry else None
