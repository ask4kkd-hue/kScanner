"""api/routers/data.py — port of web/pages/data.py. Same queries, unchanged."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from db import table_counts

from api.deps import get_cursor
from api.util import jsonable_df, jsonable_dict

router = APIRouter(prefix="/data", tags=["data"])


@router.get("/table-counts")
def get_table_counts(cur=Depends(get_cursor)) -> dict:
    return jsonable_dict(table_counts(cur))


@router.get("/validation-failures")
def get_validation_failures(days: int = 30, cur=Depends(get_cursor)) -> dict:
    v = cur.execute(f"""
        SELECT date, symbol, yf_close, bhav_close, pct_diff
        FROM validation_log
        WHERE passed = FALSE AND date >= CURRENT_DATE - INTERVAL {days} DAY
        ORDER BY ABS(pct_diff) DESC LIMIT 200
    """).df()
    rows = jsonable_df(v)
    flagged = sum(1 for r in rows if r["pct_diff"] is not None and abs(r["pct_diff"]) >= 15)
    return {"rows": rows, "flagged_15pct": flagged}


@router.get("/ingest-log")
def get_ingest_log(limit: int = 20, cur=Depends(get_cursor)) -> list[dict]:
    return jsonable_df(cur.execute(
        "SELECT * FROM ingest_log ORDER BY run_ts DESC LIMIT ?", [limit]).df())


@router.get("/symbol-gaps")
def get_symbol_gaps(cur=Depends(get_cursor)) -> list[dict]:
    return jsonable_df(cur.execute("""
        SELECT i.symbol, s.status, s.consecutive_misses, s.last_success
        FROM symbol_status s JOIN instruments i ON i.isin = s.isin
        WHERE s.consecutive_misses > 0
        ORDER BY s.consecutive_misses DESC LIMIT 100
    """).df())
