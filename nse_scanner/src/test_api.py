"""
test_api.py — FastAPI router tests via TestClient (in-process, no real server/browser —
the successor to this project's "direct Python calls bypassing the UI" verification habit).

Run with:   python test_api.py
Needs the real DB (reads db/market.duckdb) — same as the other test_*.py files' reliance
on the project's actual data where relevant, but this one specifically exercises the
HTTP layer, not just business logic.
"""

from __future__ import annotations

import sys

from fastapi.testclient import TestClient

sys.path.insert(0, ".")
from api.main import app  # noqa: E402

PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


client = TestClient(app)

# =====================================================================
print("\n[1] Health check")
r = client.get("/api/health")
check("GET /api/health -> 200", r.status_code == 200, r.text)
check("body is {status: ok}", r.json() == {"status": "ok"})

# =====================================================================
print("\n[2] Data router")

r = client.get("/api/data/table-counts")
check("GET /api/data/table-counts -> 200", r.status_code == 200, r.text)
body = r.json()
check("has bars_1d key", "bars_1d" in body, str(body.keys()))
check("bars_1d is JSON-safe (int or null)", body.get("bars_1d") is None or isinstance(body["bars_1d"], int))

r = client.get("/api/data/validation-failures?days=30")
check("GET /api/data/validation-failures -> 200", r.status_code == 200, r.text)
body = r.json()
check("has rows + flagged_15pct keys", "rows" in body and "flagged_15pct" in body, str(body.keys()))
check("rows is a list", isinstance(body["rows"], list))
if body["rows"]:
    row = body["rows"][0]
    check("date field is a plain string (not a raw Timestamp object)",
         isinstance(row.get("date"), (str, type(None))), str(row))

r = client.get("/api/data/ingest-log?limit=5")
check("GET /api/data/ingest-log -> 200", r.status_code == 200, r.text)
check("respects limit param", len(r.json()) <= 5, str(len(r.json())))

r = client.get("/api/data/symbol-gaps")
check("GET /api/data/symbol-gaps -> 200", r.status_code == 200, r.text)
check("returns a list", isinstance(r.json(), list))

# =====================================================================
print("\n[3] CORS is configured for the Vite dev server")
r = client.options("/api/data/table-counts", headers={
    "Origin": "http://localhost:5173",
    "Access-Control-Request-Method": "GET",
})
check("CORS preflight allows the Vite dev origin",
     r.headers.get("access-control-allow-origin") == "http://localhost:5173", dict(r.headers))

# =====================================================================
print("\n" + "=" * 52)
print(f"  {PASS} passed, {FAIL} failed")
print("=" * 52)

if FAIL:
    raise SystemExit(1)
