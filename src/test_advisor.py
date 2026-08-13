"""
test_advisor.py — unit tests for position_status().

Each test builds a fresh in-memory DB with exactly the synthetic
backtest_curves/backtest_trades data needed to isolate one rule. No
database file or network needed.

Run with:   python test_advisor.py
"""

from __future__ import annotations

from datetime import date, timedelta

import duckdb

import advisor as adv
from db import init_schema

PASS, FAIL = 0, 0
ALL_REASONS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def fresh_db():
    con = duckdb.connect(":memory:")
    init_schema(con)
    con.execute("""
        INSERT INTO instruments (isin, symbol, name, series)
        VALUES ('TEST01', 'TESTSYM', 'Test Co', 'EQ')
    """)
    return con


def seed_bars(con, start: date, bars: list[tuple[int, float, float, float, float]]):
    """bars: (day_offset, open, high, low, close)"""
    for off, o, h, l, c in bars:
        con.execute("""
            INSERT INTO bars_1d (isin, symbol, date, open, high, low, close, volume)
            VALUES ('TEST01', 'TESTSYM', ?, ?, ?, ?, ?, 100000)
        """, [start + timedelta(days=off), o, h, l, c])


def open_trade(con, preset_name: str, entry_date: date, entry_price: float) -> int:
    tid = con.execute("SELECT nextval('trade_id_seq')").fetchone()[0]
    con.execute("""
        INSERT INTO trades (trade_id, isin, symbol, preset_name, entry_date,
                            entry_price, qty, stop_price, status)
        VALUES (?, 'TEST01', 'TESTSYM', ?, ?, ?, 100, ?, 'open')
    """, [tid, preset_name, entry_date, entry_price, entry_price * 0.95])
    return tid


def seed_backtest_run(con, run_id: str, preset_name: str, median_hold_days=None):
    con.execute("""
        INSERT INTO backtest_runs (run_id, run_ts, preset_name, sample)
        VALUES (?, now(), ?, 'in')
    """, [run_id, preset_name])
    if median_hold_days is not None:
        con.execute("""
            INSERT INTO backtest_metrics (run_id, median_hold_days)
            VALUES (?, ?)
        """, [run_id, median_hold_days])


def seed_curve(con, run_id: str, trades: list[tuple[int, bool]],
              points: list[tuple[int, int, float, float]]):
    """
    trades: [(trade_seq, is_winner), ...]
    points: [(trade_seq, day_n, mfe_pct, mae_pct), ...]
    """
    for seq, win in trades:
        con.execute("""
            INSERT INTO backtest_trades (run_id, trade_seq, isin, symbol, net_pnl)
            VALUES (?, ?, 'TESTX', 'X', ?)
        """, [run_id, seq, 1000.0 if win else -1000.0])
    for seq, day_n, mfe, mae in points:
        con.execute("""
            INSERT INTO backtest_curves (run_id, trade_seq, day_n, mfe_pct, mae_pct)
            VALUES (?, ?, ?, ?, ?)
        """, [run_id, seq, day_n, mfe, mae])


def run_case(con, trade_id):
    r = adv.position_status(con, trade_id)
    ALL_REASONS.extend(r["reasons"])
    return r


# =====================================================================
print("\n[1] No backtest run for the preset -> WATCH, no-basis message, no prediction")

con = fresh_db()
start = date(2025, 1, 1)
seed_bars(con, start, [(0, 100, 101, 99, 100), (5, 100, 106, 98, 103)])
tid = open_trade(con, "no_backtest_preset", start, 100.0)
r = run_case(con, tid)
check("Status is WATCH", r["status"] == "WATCH", r)
check("Reason states no basis for timing guidance",
      any("no basis for timing guidance" in x for x in r["reasons"]), r["reasons"])
check("Metrics dict still populated (days_held/pnl known)",
      r["metrics"]["days_held"] == 5)


# =====================================================================
print("\n[2] days_held > backtest median winning hold -> REVIEW")

con = fresh_db()
start = date(2025, 1, 1)
end = start + timedelta(days=11)
seed_bars(con, start, [(i, 100, 102, 99, 100 + i * 0.2) for i in range(12)])
tid = open_trade(con, "preset_a", start, 100.0)
seed_backtest_run(con, "run_a", "preset_a", median_hold_days=8)
r = run_case(con, tid)
check("Status is REVIEW", r["status"] == "REVIEW", r)
check("Reason cites day 11 and the median peak of day 8",
      any("Day 11" in x and "day 8" in x for x in r["reasons"]), r["reasons"])


# =====================================================================
print("\n[3] Marginal MFE turned negative at the current day -> REVIEW")

con = fresh_db()
start = date(2025, 1, 1)
end = start + timedelta(days=9)
seed_bars(con, start, [(i, 100, 102, 99, 101) for i in range(10)])
tid = open_trade(con, "preset_b", start, 100.0)
seed_backtest_run(con, "run_b", "preset_b", median_hold_days=30)  # keep rule 1 off
seed_curve(con, "run_b", [(1, True), (2, True)], [
    (1, 8, 5.0, -1.0), (2, 8, 5.5, -1.5),   # median mfe day 8 = 5.25
    (1, 9, 5.0, -1.2), (2, 9, 5.0, -1.5),   # median mfe day 9 = 5.00  (marginal < 0)
])
r = run_case(con, tid)
check("Status is REVIEW", r["status"] == "REVIEW", r)
check("Reason cites marginal MFE turning negative at day 9",
      any("Marginal MFE turned negative at day 9" in x for x in r["reasons"]), r["reasons"])


# =====================================================================
print("\n[4] Drawdown approaching the 85th-percentile winner MAE -> WATCH")

con = fresh_db()
start = date(2025, 1, 1)
end = start + timedelta(days=5)
# low of 97.8 on day 3 -> mae = (97.8/100 - 1)*100 = -2.2%
seed_bars(con, start, [
    (0, 100, 101, 100, 100), (1, 100, 101, 99, 100), (2, 100, 101, 98, 100),
    (3, 100, 101, 97.8, 100), (4, 100, 102, 98, 101), (5, 101, 103, 99, 102),
])
tid = open_trade(con, "preset_c", start, 100.0)
seed_backtest_run(con, "run_c", "preset_c", median_hold_days=30)
# ABS(mae) = [1.0, 2.0, 3.0] at day 5 among 3 winners -> P85 = 2.7
seed_curve(con, "run_c", [(1, True), (2, True), (3, True)], [
    (1, 5, 4.0, -1.0), (2, 5, 4.0, -2.0), (3, 5, 4.0, -3.0),
])
r = run_case(con, tid)
check("Status is WATCH", r["status"] == "WATCH", r)
check("Reason cites the 85th-percentile winner MAE (2.7%)",
      any("85% of your winners never drew down more than 2.7%" in x
          for x in r["reasons"]), r["reasons"])
check("p85_mae metric matches hand-computed 2.7",
      abs(r["metrics"]["backtest_p85_mae"] - 2.7) < 0.01)


# =====================================================================
print("\n[5] Running MFE behind the backtest's median path -> WATCH")

con = fresh_db()
start = date(2025, 1, 1)
end = start + timedelta(days=6)
# high never exceeds 101.5 -> mfe = 1.5%; low stays tight -> mae small
seed_bars(con, start, [(i, 100, 100.5 + i * 0.1, 99.5, 100 + i * 0.1)
                       for i in range(6)] + [(6, 100.5, 101.5, 100, 101)])
tid = open_trade(con, "preset_d", start, 100.0)
seed_backtest_run(con, "run_d", "preset_d", median_hold_days=30)
# median mfe at day 6 = 4.0; mae kept modest so rule 4 (MAE) does not also fire
seed_curve(con, "run_d", [(1, True), (2, True)], [
    (1, 6, 3.0, -1.0), (2, 6, 5.0, -1.5),
])
r = run_case(con, tid)
check("Status is WATCH", r["status"] == "WATCH", r)
check("Reason compares running MFE to the backtest median at day 6",
      any("Backtest median at day 6 was 4.0%" in x for x in r["reasons"]), r["reasons"])


# =====================================================================
print("\n[6] Running MFE ahead of the 75th-percentile path -> HOLD (no downgrade)")

con = fresh_db()
start = date(2025, 1, 1)
end = start + timedelta(days=5)
# high reaches 107.2 -> mfe = 7.2%
seed_bars(con, start, [(i, 100, 101 + i, 99, 100 + i) for i in range(5)]
         + [(5, 105, 107.2, 104, 107)])
tid = open_trade(con, "preset_e", start, 100.0)
seed_backtest_run(con, "run_e", "preset_e", median_hold_days=30)
# p75 mfe at day 5 (of [3,4,5]) = 4.5; median = 4.0 (well below actual 7.2%).
# mae kept loose (p85=2.0, approach floor 1.6%) so it clears the real -1.0%
# drawdown in this bar data and rule 3 does not also fire here.
seed_curve(con, "run_e", [(1, True), (2, True), (3, True)], [
    (1, 5, 3.0, -2.0), (2, 5, 4.0, -2.0), (3, 5, 5.0, -2.0),
])
r = run_case(con, tid)
check("Status is HOLD", r["status"] == "HOLD", r)
check("Reason cites being above the 75th-percentile path",
      any("above your 75th-percentile path" in x for x in r["reasons"]), r["reasons"])


# =====================================================================
print("\n[7] No prediction language anywhere in any reason produced above")

banned = ["will ", "expect", "likely", "should buy", "should sell", "going to"]
violations = [(reason, word) for reason in ALL_REASONS for word in banned
             if word in reason.lower()]
check("Zero banned prediction words across all reasons generated in this run",
      len(violations) == 0, violations)


# =====================================================================
print("\n" + "=" * 52)
print(f"  {PASS} passed, {FAIL} failed")
print("=" * 52)

if FAIL:
    raise SystemExit(1)
