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

import io
import time
import uuid
from datetime import date, timedelta

import pandas as pd

_CACHE: dict[str, tuple[pd.DataFrame, float]] = {}
_TTL_SECONDS = 2 * 60 * 60
_MAX_ENTRIES = 20

# How long a persisted (preset, timeframe, scan_date) row is kept around.
# A new trading day already makes the key stop matching on its own — this
# is just housekeeping so the table doesn't grow forever.
_PERSIST_KEEP_DAYS = 30


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


# =====================================================================
# PERSISTED CACHE — survives app restarts, keyed by (preset, timeframe, day)
# =====================================================================

def get_persisted(con, preset_name: str, timeframe: str, scan_date: date) -> pd.DataFrame | None:
    row = con.execute("""
        SELECT payload FROM scan_result_cache
        WHERE preset_name = ? AND timeframe = ? AND scan_date = ?
    """, [preset_name, timeframe, scan_date]).fetchone()
    if not row:
        return None
    return pd.read_json(io.StringIO(row[0]), orient="records")


def store_persisted(con, preset_name: str, timeframe: str, scan_date: date, df: pd.DataFrame) -> None:
    payload = df.to_json(orient="records", date_format="iso")
    con.execute("""
        INSERT INTO scan_result_cache (preset_name, timeframe, scan_date, payload, row_count, created_at)
        VALUES (?, ?, ?, ?, ?, now())
        ON CONFLICT (preset_name, timeframe, scan_date) DO UPDATE SET
            payload = excluded.payload, row_count = excluded.row_count,
            created_at = excluded.created_at
    """, [preset_name, timeframe, scan_date, payload, len(df)])
    con.execute("DELETE FROM scan_result_cache WHERE scan_date < ?",
               [scan_date - timedelta(days=_PERSIST_KEEP_DAYS)])
