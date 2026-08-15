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

import yaml
from fastapi.testclient import TestClient

sys.path.insert(0, ".")
from api.main import app  # noqa: E402
from api.services import scan as scan_service  # noqa: E402

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
print("\n[5] Scan router")

r = client.get("/api/scan/filter-chips")
check("GET /api/scan/filter-chips -> 200", r.status_code == 200, r.text)
chips = r.json()
check("returns the config.yaml filter_chips list", isinstance(chips, list) and len(chips) > 0, str(len(chips)))
check("each chip has id/label/expr", all({"id", "label", "expr"} <= set(c.keys()) for c in chips), str(chips[:1]))

r = client.get("/api/scan/presets")
check("GET /api/scan/presets -> 200", r.status_code == 200, r.text)
presets = r.json()
check("returns a non-empty preset name list", isinstance(presets, list) and len(presets) > 0, str(presets))
test_preset = presets[0]

r = client.get(f"/api/scan/presets/{test_preset}/preselect")
check(f"GET /api/scan/presets/{test_preset}/preselect -> 200", r.status_code == 200, r.text)
check("returns a list of chip ids", isinstance(r.json(), list), r.text)

r = client.post("/api/scan/run", json={"preset_name": test_preset})
check("POST /api/scan/run -> 200", r.status_code == 200, r.text)
run_body = r.json()
check("has scan_id/total_count/preselected_chip_ids", set(run_body.keys()) == {
    "scan_id", "total_count", "preselected_chip_ids"
}, str(run_body.keys()))
scan_id = run_body["scan_id"]

# Filter with everything OFF first -> should equal the unfiltered total.
r = client.post(f"/api/scan/{scan_id}/filter", json={
    "chips": {c["id"]: {"active": False, "value": c.get("default")} for c in chips}
})
check("POST filter (all chips off) -> 200", r.status_code == 200, r.text)
filter_body = r.json()
check("count with nothing active equals total", filter_body["count"] == filter_body["total"], str(filter_body))
check("rows length matches count", len(filter_body["rows"]) == filter_body["count"], str(len(filter_body["rows"])))

# Now actually turn ONE chip on and confirm the count can only shrink or stay the same.
first_chip = chips[0]
r = client.post(f"/api/scan/{scan_id}/filter", json={
    "chips": {first_chip["id"]: {"active": True, "value": first_chip.get("default")}}
})
check("POST filter (one chip on) -> 200", r.status_code == 200, r.text)
filtered_body = r.json()
check("filtering can only narrow the result, never widen it",
     filtered_body["count"] <= filter_body["count"],
     f"{filtered_body['count']} vs {filter_body['count']}")

r = client.post("/api/scan/does-not-exist/filter", json={"chips": {}})
check("unknown scan_id -> 404", r.status_code == 404, r.text)

# Validation happens at the API boundary (Pydantic Field pattern), BEFORE
# config.save_preset() (a surgical text insert into config.yaml, not a
# schema-validated writer) ever runs — these must never reach the real
# file. Confirmed the hard way: an earlier version of this test expected
# save_preset() itself to reject a bad name, it doesn't, and the request
# went through and wrote an empty-named preset into the real config.yaml.
for bad_name in ["", "123starts_with_digit", "has spaces", "has-dash"]:
    r = client.post("/api/scan/save-preset", json={"name": bad_name, "conditions": ["close > sma200"]})
    check(f"save-preset rejects invalid name {bad_name!r} -> 422 (before touching config.yaml)",
         r.status_code == 422, r.text)

with open("config.yaml", encoding="utf-8") as f:
    preset_count_after = yaml.safe_load(f)["presets"].keys()
check("config.yaml's real preset list is unchanged after the rejected attempts",
     set(preset_count_after) == set(scan_service.presets()), str(preset_count_after))

# =====================================================================
print("\n[6] Watchlist router")

r = client.get("/api/watchlist")
check("GET /api/watchlist -> 200", r.status_code == 200, r.text)
check("returns a list", isinstance(r.json(), list), r.text)

r = client.post("/api/watchlist", json={"symbol": "__NOT_A_REAL_SYMBOL__"})
check("adding an unknown symbol -> 404", r.status_code == 404, r.text)

# =====================================================================
print("\n[7] Holdings router")

r = client.get("/api/trades/open")
check("GET /api/trades/open -> 200", r.status_code == 200, r.text)
check("returns a list", isinstance(r.json(), list), r.text)

r = client.post("/api/trades", json={
    "symbol": "__NOT_A_REAL_SYMBOL__", "entry_date": "2024-01-01",
    "entry_price": 100.0, "qty": 1, "stop_price": 95.0,
})
check("opening a trade for an unknown symbol -> 404 (rejected, nothing written)", r.status_code == 404, r.text)

# Full open -> appears in /open -> close lifecycle, against a REAL symbol
# (open_trade needs a real isin to snapshot features against) — this
# writes real rows to trades/trade_snapshot, so it is EXPLICITLY cleaned
# up afterward via direct SQL, the same pattern already used for the
# drawings and config.yaml tests above. Never left in the user's real
# trade journal.
r = client.post("/api/trades", json={
    "symbol": test_symbol, "entry_date": "2024-01-02",
    "entry_price": 1.0, "qty": 1, "stop_price": 0.5, "preset_name": "__test_api_fixture__",
})
check("POST /api/trades (real symbol) -> 200", r.status_code == 200, r.text)
test_trade_id = r.json().get("trade_id")
check("returns a trade_id", isinstance(test_trade_id, int), r.text)

r = client.get("/api/trades/open")
check("newly-opened test trade appears in /api/trades/open",
     any(p["trade_id"] == test_trade_id for p in r.json()), r.text)

r = client.post(f"/api/trades/{test_trade_id}/close", json={
    "exit_date": "2024-01-03", "exit_price": 1.1, "exit_reason": "discretionary", "tags": ["oversized"],
})
check(f"POST /api/trades/{test_trade_id}/close -> 200", r.status_code == 200, r.text)

r = client.get("/api/trades/open")
check("closed test trade no longer appears in /api/trades/open",
     not any(p["trade_id"] == test_trade_id for p in r.json()), r.text)

get_master().execute("DELETE FROM trade_tags WHERE trade_id = ?", [test_trade_id])
get_master().execute("DELETE FROM trade_snapshot WHERE trade_id = ?", [test_trade_id])
get_master().execute("DELETE FROM trades WHERE trade_id = ?", [test_trade_id])
still_there = get_master().execute(
    "SELECT COUNT(*) FROM trades WHERE trade_id = ?", [test_trade_id]).fetchone()[0]
check("test trade fully removed from the real trades table after cleanup", still_there == 0)

# =====================================================================
print("\n[8] Performance router")

r = client.get("/api/performance/summary")
check("GET /api/performance/summary -> 200", r.status_code == 200, r.text)
check("has min_trades_for_conclusion", "min_trades_for_conclusion" in r.json(), r.text)

r = client.get("/api/performance/equity-curve")
check("GET /api/performance/equity-curve -> 200", r.status_code == 200, r.text)
check("returns a list", isinstance(r.json(), list), r.text)

r = client.get("/api/performance/attribution")
check("GET /api/performance/attribution -> 200", r.status_code == 200, r.text)
attr = r.json()
check("has by_preset/by_timeframe/by_sector/bottom_at_sma_note", set(attr.keys()) == {
    "by_preset", "by_timeframe", "by_sector", "bottom_at_sma_note",
}, str(attr.keys()))
check("bottom_at_sma_note explains why, doesn't fake the cut",
     "not" in attr["bottom_at_sma_note"].lower(), attr["bottom_at_sma_note"])

r = client.get("/api/performance/adherence")
check("GET /api/performance/adherence -> 200", r.status_code == 200, r.text)

r = client.get("/api/performance/tags")
check("GET /api/performance/tags -> 200", r.status_code == 200, r.text)

r = client.get("/api/performance/snapshot-metrics")
check("GET /api/performance/snapshot-metrics -> 200", r.status_code == 200, r.text)
snapshot_metrics = r.json()
check("returns the 5 known metrics", len(snapshot_metrics) == 5, str(snapshot_metrics))

r = client.get("/api/performance/snapshot", params={"metric": snapshot_metrics[0]})
check("GET /api/performance/snapshot -> 200", r.status_code == 200, r.text)

r = client.get("/api/performance/snapshot", params={"metric": "not_a_real_metric"})
check("unknown snapshot metric -> 400", r.status_code == 400, r.text)

r = client.get("/api/performance/presets-traded")
check("GET /api/performance/presets-traded -> 200", r.status_code == 200, r.text)
check("empty (no closed trades in this DB) -> []", r.json() == [], r.text)

# =====================================================================
print("\n[9] Backtest router")

r = client.get("/api/backtest/config")
check("GET /api/backtest/config -> 200", r.status_code == 200, r.text)
bt_config = r.json()
check("has presets/entry_variants/exit_variants/min_trades_for_conclusion", set(bt_config.keys()) == {
    "presets", "entry_variants", "exit_variants", "min_trades_for_conclusion",
}, str(bt_config.keys()))

# A real single run, but capped to a small symbol slice (limit_symbols) to
# keep this test suite's normal runtime reasonable — sweep/marginal (up to
# 30 and 8 full backtests respectively) are deliberately NOT exercised here
# for the same reason, verified once by hand against a live server instead.
#
# The user explicitly asked earlier in this project never to delete
# backtest results ("we will use it for comparison... evolving phase") — so
# this run is tagged with an unmistakable label and cleaned up by matching
# ONLY that exact label afterward, never a broad sweep of backtest_runs
# that could catch a real run.
BT_TEST_LABEL = "__test_api_fixture__"
r = client.post("/api/backtest/run", json={
    "preset_name": "w_naked", "entry_variant": bt_config["entry_variants"][0],
    "exit_variant": bt_config["exit_variants"][0], "sample": "in", "limit_symbols": 50,
    "label": BT_TEST_LABEL,
})
check("POST /api/backtest/run (limit_symbols=50) -> 200", r.status_code == 200, r.text)
bt_run_id = r.json().get("run_id")
check("returns a run_id", isinstance(bt_run_id, str) and len(bt_run_id) > 0, r.text)

r = client.get(f"/api/backtest/{bt_run_id}")
check(f"GET /api/backtest/{bt_run_id} -> 200", r.status_code == 200, r.text)
run_body = r.json()
check("has metrics/curves/min_trades_for_conclusion", set(run_body.keys()) == {
    "metrics", "curves", "min_trades_for_conclusion",
}, str(run_body.keys()))

r = client.get("/api/backtest/this-run-id-does-not-exist")
check("unknown run_id -> 200 with metrics=null (not an error — a run that never happened)",
     r.status_code == 200 and r.json()["metrics"] is None, r.text)

for table in ("backtest_curves", "backtest_trades", "backtest_metrics"):
    get_master().execute(f"DELETE FROM {table} WHERE run_id = ?", [bt_run_id])
get_master().execute(
    "DELETE FROM backtest_runs WHERE run_id = ? AND label = ?", [bt_run_id, BT_TEST_LABEL])
still_there = get_master().execute(
    "SELECT COUNT(*) FROM backtest_runs WHERE run_id = ?", [bt_run_id]).fetchone()[0]
check("test backtest run fully removed (matched by run_id AND its unique label only)",
     still_there == 0)

# =====================================================================
print("\n[10] CORS is configured for the Vite dev server")
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
