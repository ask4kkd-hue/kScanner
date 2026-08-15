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
print("\n[3] Today router (aggregate endpoint)")

r = client.get("/api/today")
check("GET /api/today -> 200", r.status_code == 200, r.text)
body = r.json()
check("has all top-level sections", set(body.keys()) == {
    "status", "positions", "total_open_pnl", "at_risk_count", "opportunities",
    "pnl", "equity_curve", "watchlist_near_trigger",
}, str(body.keys()))
check("status has a regime string", isinstance(body["status"]["regime"], str), str(body["status"]))
check("opportunities has all three timeframes in order", [o["timeframe"] for o in body["opportunities"]] == ["1d", "1w", "1m"], str(body["opportunities"]))
check("positions is a list", isinstance(body["positions"], list))
if body["positions"]:
    p = body["positions"][0]
    check("position row has status in {HOLD,WATCH,REVIEW}", p["status"] in ("HOLD", "WATCH", "REVIEW"), str(p))
    check("no leaked internal _close field", "_close" not in p, str(p))
check("pnl has all five keys", set(body["pnl"].keys()) == {
    "today", "this_week", "this_month", "all_time", "unrealised"
}, str(body["pnl"]))

# =====================================================================
print("\n[4] Chart router")

r = client.get("/api/instruments/symbols")
check("GET /api/instruments/symbols -> 200", r.status_code == 200, r.text)
symbols = r.json()
check("returns a non-empty list of symbols", isinstance(symbols, list) and len(symbols) > 0, str(len(symbols)))

# Find a symbol with enough history for a real chart (avoids the very
# newest listings, which legitimately have too little history yet).
test_symbol = "RELIANCE" if "RELIANCE" in symbols else symbols[0]

r = client.get(f"/api/chart/{test_symbol}")
check(f"GET /api/chart/{test_symbol} -> 200", r.status_code == 200, r.text)
body = r.json()
check("has bars", len(body.get("bars", [])) > 0, str(len(body.get("bars", []))))
check("bar has OHLCV fields", set(body["bars"][0].keys()) >= {"date", "open", "high", "low", "close", "volume"},
     str(body["bars"][0]))
check("has metrics.pattern_found (bool)", isinstance(body["metrics"]["pattern_found"], bool), str(body["metrics"]))
check("server_overlays is a list", isinstance(body["server_overlays"], list))
check("user_drawings is a list", isinstance(body["user_drawings"], list))

r = client.get("/api/chart/__NOT_A_REAL_SYMBOL__")
check("unknown symbol -> 404", r.status_code == 404, r.text)

r = client.get(f"/api/chart/{test_symbol}", params={"timeframe": "M"})
check(f"GET /api/chart/{test_symbol}?timeframe=M -> 200", r.status_code == 200, r.text)

# Drawings round trip: PUT then GET then DELETE, on a harmless test timeframe
# key so it never collides with a symbol/timeframe the user might actually
# be viewing (drawings are keyed per isin+timeframe, "9999w" isn't a real one).
test_tf = "9999w"
sample_overlay = [{"name": "horizontalStraightLine", "points": [{"value": 123.45}], "lock": False}]
r = client.put(f"/api/chart/{test_symbol}/drawings", params={"timeframe": test_tf}, json=sample_overlay)
check("PUT drawings -> 200", r.status_code == 200, r.text)
r = client.get(f"/api/chart/{test_symbol}/drawings", params={"timeframe": test_tf})
check("GET drawings round-trips what was saved", r.json() == sample_overlay, r.text)
r = client.delete(f"/api/chart/{test_symbol}/drawings", params={"timeframe": test_tf})
check("DELETE drawings -> 200", r.status_code == 200, r.text)
r = client.get(f"/api/chart/{test_symbol}/drawings", params={"timeframe": test_tf})
check("drawings are empty after delete", r.json() == [], r.text)

# DELETE-via-service only ever sets payload to "[]" (matches the NiceGUI
# original's "reset" semantics) — it never removes the row, so the sentinel
# test_tf row would otherwise sit in the real drawings table forever.
# Since this test runs in-process against the app's own master connection,
# clean it up directly rather than leaving test fixture data in production.
from api.deps import get_master  # noqa: E402
get_master().execute("DELETE FROM drawings WHERE timeframe = ?", [test_tf])

# =====================================================================
print("\n[5] CORS is configured for the Vite dev server")
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
