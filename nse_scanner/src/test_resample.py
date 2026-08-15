"""
test_resample.py — unit tests for the timeframe/chart-type transforms.

No database or network needed — everything uses synthetic data.
Run with:   python test_resample.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import resample as rs

PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def bar(d, o, h, l, c, v=1000.0):
    return {"date": pd.Timestamp(d), "open": o, "high": h, "low": l,
            "close": c, "volume": v}


# =====================================================================
print("\n[1] Weekly resample: known 3-week series, one with a holiday gap")

rows = [
    # Week 1: Mon 2025-01-06 .. Fri 2025-01-10, full week
    bar("2025-01-06", 100, 105, 99, 102),
    bar("2025-01-07", 102, 106, 101, 104),
    bar("2025-01-08", 104, 108, 103, 106),
    bar("2025-01-09", 106, 110, 105, 108),
    bar("2025-01-10", 108, 112, 107, 110),
    # Week 2: Mon 2025-01-13 .. Fri 2025-01-17, Wed 15th is a HOLIDAY (absent)
    bar("2025-01-13", 110, 115, 109, 113),
    bar("2025-01-14", 113, 117, 112, 115),
    bar("2025-01-16", 115, 119, 95, 117),   # deliberately the week's low
    bar("2025-01-17", 117, 121, 116, 119),
    # Week 3: Mon 2025-01-20 .. Fri 2025-01-24, full week
    bar("2025-01-20", 119, 123, 118, 121),
    bar("2025-01-21", 121, 125, 120, 123),
    bar("2025-01-22", 123, 127, 122, 125),
    bar("2025-01-23", 125, 129, 124, 127),
    bar("2025-01-24", 127, 131, 126, 129),
    # Week 4: Mon-Tue only, 2025-01-27/28 — the CURRENT, incomplete week
    bar("2025-01-27", 129, 133, 128, 131),
    bar("2025-01-28", 131, 135, 130, 133),
]
daily = pd.DataFrame(rows)
weekly = rs.to_weekly(daily)

check("Incomplete current week excluded", len(weekly) == 3,
      f"got {len(weekly)} rows")

if len(weekly) == 3:
    w1, w2, w3 = weekly.iloc[0], weekly.iloc[1], weekly.iloc[2]
    check("Week 1 aggregates correctly",
          (w1["open"], w1["high"], w1["low"], w1["close"], w1["sessions"])
          == (100, 112, 99, 110, 5))
    check("Week 1 labeled with its last trading day",
          w1["date"] == pd.Timestamp("2025-01-10"))
    check("Holiday week (missing Wed) still finds the correct low",
          w2["low"] == 95, f"got {w2['low']}")
    check("Holiday week aggregates correctly despite only 4 sessions",
          (w2["open"], w2["high"], w2["close"], w2["sessions"])
          == (110, 121, 119, 4))
    check("Week 3 aggregates correctly",
          (w3["open"], w3["high"], w3["low"], w3["close"], w3["sessions"])
          == (119, 131, 118, 129, 5))
    check("volume summed per week", w1["volume"] == 5000, f"got {w1['volume']}")


# =====================================================================
print("\n[2] Heikin Ashi matches a hand-worked 5-bar example")

ha_in = pd.DataFrame([
    bar("2025-02-01", 10, 12, 9, 11),
    bar("2025-02-02", 11, 13, 10, 12),
    bar("2025-02-03", 12, 11, 9, 10),
    bar("2025-02-04", 10, 14, 9, 13),
    bar("2025-02-05", 13, 15, 12, 14),
])
ha = rs.to_heikin_ashi(ha_in)

expected = [
    (10.5, 12.0, 9.0, 10.5),
    (10.5, 13.0, 10.0, 11.5),
    (11.0, 11.0, 9.0, 10.5),
    (10.75, 14.0, 9.0, 11.5),
    (11.125, 15.0, 11.125, 13.5),
]
ok = True
for i, (eo, eh, el, ec) in enumerate(expected):
    row = ha.iloc[i]
    if not (np.isclose(row["open"], eo) and np.isclose(row["high"], eh)
            and np.isclose(row["low"], el) and np.isclose(row["close"], ec)):
        ok = False
        print(f"    mismatch at bar {i}: got "
              f"({row['open']},{row['high']},{row['low']},{row['close']}) "
              f"expected ({eo},{eh},{el},{ec})")
check("All 5 Heikin Ashi bars match hand-worked values", ok)


# =====================================================================
print("\n[3] Renko: brick count for a clean trend; reversal needs 2 bricks")

# Clean uptrend: 100 -> 160 with a 10% (=10) brick, exact multiples of
# brick size, so the brick count is unambiguous: 60 / 10 = 6.
clean = pd.DataFrame([
    bar("2025-03-01", 100, 100, 100, 100),
    bar("2025-03-02", 115, 115, 115, 115),
    bar("2025-03-03", 130, 130, 130, 130),
    bar("2025-03-04", 145, 145, 145, 145),
    bar("2025-03-05", 160, 160, 160, 160),
])
bricks_clean = rs.to_renko(clean, brick_mode="pct", brick_pct=10.0)
check("Clean trend produces exactly 6 bricks (60 / brick-of-10)",
      len(bricks_clean) == 6, f"got {len(bricks_clean)}")
check("Renko output is flagged as not time-linear",
      bricks_clean.attrs.get("x_axis_time_linear") is False)

# A pullback smaller than 2 bricks must NOT reverse the trend.
no_reversal = pd.DataFrame([
    bar("2025-03-01", 100, 100, 100, 100),
    bar("2025-03-02", 130, 130, 130, 130),   # 3 up-bricks: 100->110->120->130
    bar("2025-03-03", 115, 115, 115, 115),   # only a 15 pullback (<2*brick=20)
])
bricks_pullback = rs.to_renko(no_reversal, brick_mode="pct", brick_pct=10.0)
check("A sub-2-brick pullback adds no new bricks",
      len(bricks_pullback) == 3, f"got {len(bricks_pullback)}")

# The same series continued past a 2-brick move down must reverse.
reversal = pd.DataFrame([
    bar("2025-03-01", 100, 100, 100, 100),
    bar("2025-03-02", 130, 130, 130, 130),
    bar("2025-03-03", 115, 115, 115, 115),
    bar("2025-03-04", 108, 108, 108, 108),   # 130 - 108 = 22 >= 2*brick=20
])
bricks_reversed = rs.to_renko(reversal, brick_mode="pct", brick_pct=10.0)
check("A full 2-brick move down adds exactly 2 new bricks (reversal + continuation)",
      len(bricks_reversed) == 5, f"got {len(bricks_reversed)}")
if len(bricks_reversed) == 5:
    last_two = bricks_reversed.iloc[3:5]
    check("Both new bricks after the reversal point down",
          bool((last_two["close"] < last_two["open"]).all()))


# =====================================================================
print("\n" + "=" * 52)
print(f"  {PASS} passed, {FAIL} failed")
print("=" * 52)

if FAIL:
    raise SystemExit(1)
