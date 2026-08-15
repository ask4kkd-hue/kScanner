"""
test_features.py — unit tests for the daily incremental windowing in
build_features().

This exists because of a real bug caught before it ever touched the real
DB: an early version windowed the FETCH correctly but still re-touched
every already-stored row above the warm-up threshold on every run,
re-deriving each one from a shorter, less-settled window. The newest row
always converged to the true full-history value — but rows in the middle
of that re-touched slice measurably drifted (several RSI/ADX points in
testing), silently degrading data a previous full rebuild had already
gotten right. The fix: an incremental run must never rewrite a date the
symbol already has a stored row for, full stop — not just trust that a
window converges closely enough.

In-memory DuckDB, synthetic data — no real DB or network needed.
Run with:   python test_features.py
"""

from __future__ import annotations

from datetime import date, timedelta

import duckdb
import numpy as np
import pandas as pd

import features as feat
from config import CFG
from db import init_schema

PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def seed_symbol(con, isin: str, symbol: str, n: int, start: date, seed: int) -> date:
    """Insert n synthetic weekday bars for one symbol; returns the last date."""
    con.execute(
        "INSERT INTO instruments (isin, symbol, name, series) VALUES (?, ?, ?, 'EQ')",
        [isin, symbol, symbol],
    )
    rng = np.random.default_rng(seed)
    closes = 100 + np.cumsum(rng.normal(0.05, 1.0, n))
    d, i, last = start, 0, start
    while i < n:
        if d.weekday() < 5:
            c = closes[i]
            con.execute("""
                INSERT INTO bars_1d (isin, symbol, date, open, high, low, close, volume, vwap)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [isin, symbol, d, c - 0.2, c + 0.3, c - 0.3, c, 100000, c])
            last = d
            i += 1
        d += timedelta(days=1)
    return last


con = duckdb.connect(":memory:")
init_schema(con)
last_date = seed_symbol(con, "TEST01", "TESTSYM", 1200, date(2020, 1, 1), seed=42)

# =====================================================================
print("\n[1] A no-op incremental run (zero new bars) touches nothing")

n_full = feat.build_features(con, full=True, timeframe="1d")
baseline = con.execute("SELECT * FROM features_1d ORDER BY date").df()

n_noop = feat.build_features(con, full=False, timeframe="1d")
after_noop = con.execute("SELECT * FROM features_1d ORDER BY date").df()

check("Full rebuild wrote a non-trivial number of rows", n_full > 500, f"got {n_full}")
check("No-op incremental run touched exactly zero rows", n_noop == 0, f"got {n_noop}")
check("Table is byte-for-byte identical after the no-op run",
      baseline.reset_index(drop=True).equals(after_noop.reset_index(drop=True)))

# =====================================================================
print("\n[2] Adding new bars: incremental touches ONLY the new dates, matches a full rebuild")

new_d, added = last_date, 0
rng2 = np.random.default_rng(99)
while added < 5:
    new_d = new_d + timedelta(days=1)
    if new_d.weekday() < 5:
        c = 200 + rng2.normal(0, 1.0)
        con.execute("""
            INSERT INTO bars_1d (isin, symbol, date, open, high, low, close, volume, vwap)
            VALUES ('TEST01','TESTSYM',?,?,?,?,?,?,?)
        """, [new_d, c - 0.2, c + 0.3, c - 0.3, c, 120000, c])
        added += 1

n_inc = feat.build_features(con, full=False, timeframe="1d")
after_new = con.execute("SELECT * FROM features_1d ORDER BY date").df()

check("Incremental run touched exactly the 5 new dates", n_inc == 5, f"got {n_inc}")

cutoff = pd.Timestamp(last_date)
old_before = after_noop[after_noop["date"] <= cutoff].reset_index(drop=True)
old_after = after_new[after_new["date"] <= cutoff].reset_index(drop=True)
check("Every pre-existing row is untouched byte-for-byte by the incremental run",
      old_before.equals(old_after))

n_full2 = feat.build_features(con, full=True, timeframe="1d")
full_after_new = con.execute("SELECT * FROM features_1d ORDER BY date").df()
merged = full_after_new.merge(after_new, on=["isin", "date"], suffixes=("_full", "_inc"))
worst = 0.0
for col in ["sma10", "sma50", "sma200", "rsi14", "adx14", "bars_available"]:
    worst = max(worst, (merged[f"{col}_full"].astype(float)
                        - merged[f"{col}_inc"].astype(float)).abs().max())
check("Incremental output matches a full rebuild EXACTLY (incl. bars_available)",
      worst < 1e-6, f"max abs diff {worst}")

# =====================================================================
print("\n[3] A brand-new symbol (no stored rows yet) computes its full history, not a tiny window")

# 400 daily bars seeded; warmup_discard_bars (config.yaml) rows at the start
# of ANY symbol's own history never pass the `bars_available > warm` filter,
# windowed or not — so the expected row count is fully determined by that
# arithmetic, independent of this fix.
n_seeded = 400
seed_symbol(con, "TEST02", "NEWCO", n_seeded, date(2023, 1, 1), seed=7)
warm = CFG["features"]["params"]["warmup_discard_bars"]
n_new_symbol = feat.build_features(con, isins=["TEST02"], full=False, timeframe="1d")
check("First-ever incremental run for a new symbol computes its FULL history "
     "(not a small window) — row count matches warmup arithmetic exactly",
      n_new_symbol == max(0, n_seeded - warm),
      f"got {n_new_symbol}, expected {max(0, n_seeded - warm)}")

# =====================================================================
print("\n[4] --from-date bypasses the incremental since-guard (explicit resync)")

rebuild_from = date(2023, 1, 1)
n_from_date = feat.build_features(con, isins=["TEST01"], full=False,
                                  rebuild_from=rebuild_from, timeframe="1d")
still_there = con.execute(
    "SELECT COUNT(*) FROM features_1d WHERE isin = 'TEST01' AND date >= ?", [rebuild_from]
).fetchone()[0]
check("--from-date forces a real (non-empty) recompute of already-stored rows",
      n_from_date > 0, f"got {n_from_date}")
check("Every row on/after --from-date was rewritten, not just the newest tail",
      n_from_date == still_there, f"{n_from_date} vs {still_there} stored")


# =====================================================================
print("\n" + "=" * 52)
print(f"  {PASS} passed, {FAIL} failed")
print("=" * 52)

if FAIL:
    raise SystemExit(1)
