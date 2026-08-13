"""
web/main.py — v2 UI entry point.

Run with:   python web/main.py
Opens at http://localhost:8080.

One master DuckDB connection, shared across the process; each connecting
client gets its own con.cursor() (independent cursor over the same
connection — safe for concurrent use, unlike sharing one raw connection
object across threads/clients, which corrupts cursor state).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
_WEB = Path(__file__).resolve().parent
for p in (_SRC, _WEB):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from nicegui import ui  # noqa: E402

from db import connect, init_schema  # noqa: E402
import shell  # noqa: E402

_master_con = None


def _master() -> "duckdb.DuckDBPyConnection":
    global _master_con
    if _master_con is None:
        _master_con = connect()
        init_schema(_master_con)
    return _master_con


@ui.page("/")
def index() -> None:
    shell.build(_master().cursor())


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="kSCANNER", host="127.0.0.1", port=8080,
          dark=True, reload=False, show=False)
