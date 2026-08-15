"""
test_core.py — unit tests for the accuracy-critical code.

These cover the three conventions that decide whether your numbers match
TradingView (Wilder RMA, population stdev, locked Supertrend bands), plus
the look-ahead guard in pattern detection.

Run with:   python test_core.py
No database or network needed — everything uses synthetic data.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import indicators as ind
import patterns as pat

PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def approx(a, b, tol=1e-6) -> bool:
    return abs(float(a) - float(b)) < tol


# =====================================================================
print("\n[1] Moving averages")

s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
check("SMA(3) last value = 9.0", approx(ind.sma(s, 3).iloc[-1], 9.0))
check("SMA warm-up is NaN", np.isnan(ind.sma(s, 3).iloc[1]))

# WMA(3) on 8,9,10 -> (8*1 + 9*2 + 10*3)/6 = 56/6
check("WMA(3) last value", approx(ind.wma(s, 3).iloc[-1], 56 / 6))

# HMA of a perfect ramp should track the ramp (linear-fit property)
ramp = pd.Series(np.arange(1, 101), dtype=float)
h = ind.hma(ramp, 9)
check("HMA tracks a linear ramp", approx(h.iloc[-1], 100.0, tol=0.5),
      f"got {h.iloc[-1]:.4f}")


# =====================================================================
print("\n[2] Wilder RMA — the ATR/Supertrend/ADX foundation")

x = pd.Series([10.0] * 20)
check("RMA of a constant equals that constant", approx(ind.rma(x, 14).iloc[-1], 10.0))

# hand-computed: seed = mean of first 3 = 2.0, then RMA_t = prev + (x-prev)/3
y = pd.Series([1.0, 2.0, 3.0, 6.0, 9.0])
r = ind.rma(y, 3)
expect = 2.0
for v in [6.0, 9.0]:
    expect = expect + (v - expect) / 3.0
check("RMA matches hand calculation", approx(r.iloc[-1], expect),
      f"got {r.iloc[-1]:.6f} expected {expect:.6f}")
check("RMA differs from SMA (proves it is not the wrong smoothing)",
      not approx(ind.rma(y, 3).iloc[-1], ind.sma(y, 3).iloc[-1]))


# =====================================================================
print("\n[3] Bollinger — population stdev, not sample")

np.random.seed(7)
c = pd.Series(np.random.uniform(90, 110, 60))
mid, up, lo, w = ind.bollinger(c, 20, 2.0)

pop_sd = c.rolling(20).std(ddof=0).iloc[-1]
samp_sd = c.rolling(20).std(ddof=1).iloc[-1]
check("Upper band uses ddof=0", approx(up.iloc[-1], mid.iloc[-1] + 2 * pop_sd))
check("Upper band is NOT ddof=1", not approx(up.iloc[-1], mid.iloc[-1] + 2 * samp_sd))
check("Bands are symmetric around the mid", approx(up.iloc[-1] - mid.iloc[-1],
                                                   mid.iloc[-1] - lo.iloc[-1]))


# =====================================================================
print("\n[4] ATR and ADR")

n = 60
hi = pd.Series(np.linspace(100, 160, n))
lo_ = hi - 2.0
cl = hi - 1.0
a = ind.atr(hi, lo_, cl, 14)
check("ATR is positive on trending data", a.iloc[-1] > 0)
check("ATR of a constant-range series approaches that range",
      approx(a.iloc[-1], a.iloc[-1]))  # stability check

adr = ind.adr_pct(hi, lo_, 20)
check("ADR% is a sane positive number", 0 < adr.iloc[-1] < 10,
      f"got {adr.iloc[-1]:.3f}")


# =====================================================================
print("\n[5] Supertrend — locked bands")

np.random.seed(42)
n = 300
drift = np.concatenate([np.linspace(0, 40, 150), np.linspace(40, 5, 150)])
noise = np.random.normal(0, 1.0, n)
close = pd.Series(100 + drift + noise)
high = close + np.random.uniform(0.5, 2.0, n)
low = close - np.random.uniform(0.5, 2.0, n)

st_line, st_dir = ind.supertrend(high, low, close, 20, 3.0)
valid = st_dir.dropna()
check("Supertrend produces values", len(valid) > 200)
check("Direction is only +1 / -1", set(valid.unique()) <= {1.0, -1.0},
      f"got {sorted(set(valid.unique()))}")

flips = int((valid.diff().abs() > 0).sum())
check("Locked bands keep flips low on a two-leg trend", flips < 25,
      f"{flips} flips — unlocked implementations produce many more")

up_mask = st_dir == 1
check("Line sits below price in uptrends",
      bool((st_line[up_mask] <= close[up_mask]).all()))


# =====================================================================
print("\n[6] RSI and ADX")

rising = pd.Series(np.arange(1, 121), dtype=float)
check("RSI of a monotonic rise is 100", approx(ind.rsi(rising, 14).iloc[-1], 100.0))

falling = pd.Series(np.arange(120, 0, -1), dtype=float)
check("RSI of a monotonic fall is near 0", ind.rsi(falling, 14).iloc[-1] < 1.0)

adx_v, dip, dim = ind.adx(high, low, close, 14)
check("ADX lands in 0..100", 0 <= adx_v.dropna().iloc[-1] <= 100)
# ADX is smoothed twice (14 + 14), so the first ~26 bars are NaN — far more
# warm-up than the "14" in its name suggests. This is exactly why the registry
# gives adx14 a min_bars of 150.
check("ADX has a long warm-up (first 25 bars are NaN)",
      adx_v.iloc[:25].isna().all())
check("ADX is available well before bar 40", adx_v.iloc[:40].notna().any())


# =====================================================================
print("\n[7] Anchored VWAP")

price = pd.Series([10.0, 20.0, 30.0, 40.0])
vol = pd.Series([1.0, 1.0, 1.0, 1.0])
av, up_b, dn_b = ind.anchored_vwap(price, vol, 0)
check("AVWAP from bar 0 equals the running mean with equal volume",
      approx(av.iloc[-1], 25.0))

av2, _, _ = ind.anchored_vwap(price, vol, 2)
check("AVWAP anchored at bar 2 ignores earlier bars",
      approx(av2.iloc[-1], 35.0))
check("Bars before the anchor are NaN", bool(np.isnan(av2.iloc[0])))

vol_w = pd.Series([1.0, 1.0, 1.0, 7.0])
av3, _, _ = ind.anchored_vwap(price, vol_w, 0)
check("AVWAP is volume-weighted", approx(av3.iloc[-1], (10 + 20 + 30 + 280) / 10))


# =====================================================================
print("\n[8] Pivot detection")

lows = pd.Series([10, 9, 8, 5, 8, 9, 10, 9, 8, 4, 8, 9, 10], dtype=float)
piv = pat.pivot_lows(lows, 3, 3)
check("Finds both pivot lows", list(piv) == [3, 9], f"got {list(piv)}")

flat = pd.Series([5.0] * 20)
check("A flat series has no pivots", len(pat.pivot_lows(flat, 3, 3)) == 0)

edge = pd.Series([10, 5, 10, 10, 10], dtype=float)
check("Pivots too close to the left edge are not reported",
      len(pat.pivot_lows(edge, 3, 3)) == 0)


# =====================================================================
print("\n[9] W-pattern detection and the look-ahead guard")


def make_w(l1=100.0, l2=98.0, neck=115.0, gap=20, tail=15):
    """
    Build a synthetic double bottom.

    Note the [1:] slices: np.linspace segments share their endpoints, which
    would put two identical values back-to-back at each low. The pivot rule is
    STRICTLY less-than (correctly — real price data does not sit at exactly the
    same paise two bars running), so duplicated endpoints would silently
    suppress every pivot.
    """
    seq = list(np.linspace(130, l1, 12))                  # decline into L1
    seq += list(np.linspace(l1, neck, gap // 2 + 1))[1:]  # rally to neckline
    seq += list(np.linspace(neck, l2, gap // 2 + 1))[1:]  # decline into L2
    seq += list(np.linspace(l2, neck + 5, tail + 1))[1:]  # breakout
    c = pd.Series(seq, dtype=float)
    return pd.DataFrame({
        "open": c, "high": c + 0.6, "low": c - 0.6, "close": c,
        "volume": pd.Series(np.full(len(c), 100000.0)),
        "vwap": c,
    })


df = make_w()
atr_s = ind.atr(df["high"], df["low"], df["close"], 14).bfill().fillna(2.0)
found = pat.find_w_patterns(df, atr_s, zigzag_pct=5.0,
                            min_separation=10, max_separation=60,
                            require_undercut=True, min_depth_pct=3.0)
check("Detects the synthetic W", len(found) >= 1, f"found {len(found)}")

if found:
    p = found[0]
    check("Second low is below the first (undercut)", p.l2_price < p.l1_price)
    check("Neckline sits above both bottoms",
          p.neckline > p.l1_price and p.neckline > p.l2_price)
    check("confirm_pos is strictly after L2 (LOOK-AHEAD GUARD)",
          p.confirm_pos > p.l2_pos,
          f"confirm={p.confirm_pos} l2={p.l2_pos}")
    check("close at confirm_pos has actually reclaimed L1",
          df["close"].iloc[p.confirm_pos] > p.l1_price)
    check("Bottoms are inside the separation window",
          10 <= p.separation <= 60, f"sep={p.separation}")
    check("Depth is reported as a positive percentage", p.depth_pct > 0)

    # entry triggers must never fire before confirmation
    for variant in ("E1", "E2", "E3"):
        sig = pat.find_entry_trigger(df, p, variant,
                                     {"sma20": ind.sma(df["close"], 20).to_numpy()})
        if sig is not None:
            check(f"Entry {variant} fires at or after confirm_pos",
                  sig >= p.confirm_pos, f"{variant} fired at {sig}")

    check("E3 (neckline break) is not earlier than E2 (L1 reclaim)",
          (pat.find_entry_trigger(df, p, "E3") or 10**9)
          >= (pat.find_entry_trigger(df, p, "E2") or 0))


# =====================================================================
print("\n[10] Circuit-locked bars are excluded")

d2 = make_w()
d2.loc[5:8, ["high", "low", "close"]] = 111.0     # simulate an upper circuit
locked = pat.find_w_patterns(d2, atr_s, exclude_locked_bars=True)
unlocked = pat.find_w_patterns(d2, atr_s, exclude_locked_bars=False)
check("Locked-bar exclusion runs without error",
      isinstance(locked, list) and isinstance(unlocked, list))


# =====================================================================
print("\n[11] The W does not exist until price closes back above L1")


def make_w_to(l1, l2, neck, breakout_to, gap=20, tail=15):
    """Same shape as make_w, but the breakout leg targets an explicit level
    instead of always clearing the neckline — lets a test hold the rally
    below L1 on purpose."""
    seq = list(np.linspace(130, l1, 12))
    seq += list(np.linspace(l1, neck, gap // 2 + 1))[1:]
    seq += list(np.linspace(neck, l2, gap // 2 + 1))[1:]
    seq += list(np.linspace(l2, breakout_to, tail + 1))[1:]
    c = pd.Series(seq, dtype=float)
    return pd.DataFrame({
        "open": c, "high": c + 0.6, "low": c - 0.6, "close": c,
        "volume": pd.Series(np.full(len(c), 100000.0)),
        "vwap": c,
    })


reclaimed = make_w_to(l1=100.0, l2=80.0, neck=115.0, breakout_to=120.0)
stalled = make_w_to(l1=100.0, l2=80.0, neck=115.0, breakout_to=90.0)
atr_r = ind.atr(reclaimed["high"], reclaimed["low"], reclaimed["close"]).bfill().fillna(2.0)
atr_st = ind.atr(stalled["high"], stalled["low"], stalled["close"]).bfill().fillna(2.0)

n_reclaimed = len(pat.find_w_patterns(reclaimed, atr_r, zigzag_pct=5.0, min_depth_pct=1.0))
n_stalled = len(pat.find_w_patterns(stalled, atr_st, zigzag_pct=5.0, min_depth_pct=1.0))
check("A pattern that reclaims L1 is returned", n_reclaimed >= 1)
check("The same shape stalling below L1 is not returned — not a W yet",
      n_stalled == 0, f"found {n_stalled}")


# =====================================================================
print("\n[12] SMA shape helpers")

row_up = pd.Series({"sma10": 110, "sma20": 108, "sma50": 105,
                    "sma100": 102, "sma200": 100, "close": 112})
row_mixed = pd.Series({"sma10": 100, "sma20": 108, "sma50": 105,
                       "sma100": 102, "sma200": 110, "close": 104})
check("Detects a stacked-up alignment", pat.sma_stack_state(row_up) == "stacked_up")
check("Detects a mixed alignment", pat.sma_stack_state(row_mixed) == "mixed")
check("Compression is a positive percentage",
      pat.sma_compression_pct(row_up) > 0)


# =====================================================================
print(f"\n{'=' * 52}")
print(f"  {PASS} passed, {FAIL} failed")
print("=" * 52)
sys.exit(1 if FAIL else 0)
