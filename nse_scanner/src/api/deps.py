"""
api/deps.py — the DB connection dependency.

Same rule web/main.py already proves works: ONE master DuckDB connection
for the whole process lifetime, and every request gets its own con.cursor()
(an independent cursor over that same connection, not a new connection —
DuckDB is single-writer, a second connect() to the same file fails
outright). Route handlers declared as plain `def` (not `async def`) run in
FastAPI's threadpool automatically; the cursor crossing from the request
thread into that pool is the same pattern NiceGUI's run.io_bound already
uses successfully with con.cursor() today.
"""

from __future__ import annotations

import duckdb

from db import connect, init_schema

_master_con: duckdb.DuckDBPyConnection | None = None


def get_master() -> duckdb.DuckDBPyConnection:
    global _master_con
    if _master_con is None:
        _master_con = connect()
        init_schema(_master_con)
    return _master_con


def get_cursor() -> duckdb.DuckDBPyConnection:
    """FastAPI dependency: `cur: duckdb.DuckDBPyConnection = Depends(get_cursor)`."""
    return get_master().cursor()
