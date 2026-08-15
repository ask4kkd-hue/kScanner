"""
patterns.py — pivot detection and W-pattern (double bottom) identification.

THE LOOK-AHEAD RULE
-------------------
A pivot low with right-window R is only KNOWABLE R bars after it forms.
Every pattern this module returns carries `confirm_pos` — the earliest bar at
which you could have known about it. Backtests and live scans must both use
confirm_pos, never the pivot's own date.

Getting this wrong makes a backtest look excellent and a live scanner look
broken, and the two will never reconcile.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------- pivots

def pivot_lows(low: pd.Series, left: int = 3, right: int = 3) -> np.ndarray:
    """
    Positions of pivot lows: a bar whose Low is strictly lower than `left`
    bars before and `right` bars after.

    Returns integer positions (not dates).
    """
    v = low.to_numpy(dtype=float)
    n = len(v)
    out = []
    for i in range(left, n - right):
        window_l = v[i - left:i]
        window_r = v[i + 1:i + right + 1]
        if np.isnan(v[i]) or np.isnan(window_l).any() or np.isnan(window_r).any():
            continue
        if v[i] < window_l.min() and v[i] < window_r.min():
            out.append(i)
    return np.array(out, dtype=int)


def pivot_highs(high: pd.Series, left: int = 3, right: int = 3) -> np.ndarray:
    """Positions of pivot highs. Mirror of pivot_lows."""
    v = high.to_numpy(dtype=float)
    n = len(v)
    out = []
    for i in range(left, n - right):
        wl = v[i - left:i]
        wr = v[i + 1:i + right + 1]
        if np.isnan(v[i]) or np.isnan(wl).any() or np.isnan(wr).any():
            continue
        if v[i] > wl.max() and v[i] > wr.max():
            out.append(i)
    return np.array(out, dtype=int)


def last_n_pivot_lows(low: pd.Series, n: int = 3, left: int = 3, right: int = 3):
    """The most recent n confirmed pivot lows, newest first."""
    piv = pivot_lows(low, left, right)
    return piv[-n:][::-1] if len(piv) else np.array([], dtype=int)


# ---------------------------------------------------------------- zigzag

def zigzag(close: pd.Series, reversal_pct: float = 5.0) -> List[dict]:
    """
    Alternating confirmed swing points on CLOSE (not high/low). A swing is
    only confirmed once price has reversed reversal_pct% away from it — that
    reversal IS the look-ahead guard for the swing itself: you could not have
    known bar i was the bottom until price closed reversal_pct% above it.

    Returns [{'kind': 'low'|'high', 'pos': int, 'price': float,
    'confirm_pos': int}, ...] in chronological order. NaNs (e.g. masked
    locked bars) are skipped, not treated as a move.
    """
    c = close.to_numpy(dtype=float)
    n = len(c)
    pivots: List[dict] = []
    if n < 2 or np.isnan(c[0]):
        return pivots

    trend = 0  # 0 = undecided yet, +1 = tracking a high, -1 = tracking a low
    anchor_price = c[0]
    extreme_pos, extreme_price = 0, c[0]

    for i in range(1, n):
        price = c[i]
        if np.isnan(price):
            continue

        if trend == 0:
            move = (price - anchor_price) / anchor_price * 100.0
            if move >= reversal_pct:
                trend, extreme_pos, extreme_price = 1, i, price
            elif move <= -reversal_pct:
                trend, extreme_pos, extreme_price = -1, i, price
            continue

        if trend == 1:
            if price > extreme_price:
                extreme_pos, extreme_price = i, price
                continue
            retrace = (extreme_price - price) / extreme_price * 100.0
            if retrace >= reversal_pct:
                pivots.append({"kind": "high", "pos": extreme_pos,
                               "price": extreme_price, "confirm_pos": i})
                trend, extreme_pos, extreme_price = -1, i, price
        else:
            if price < extreme_price:
                extreme_pos, extreme_price = i, price
                continue
            rally = (price - extreme_price) / extreme_price * 100.0
            if rally >= reversal_pct:
                pivots.append({"kind": "low", "pos": extreme_pos,
                               "price": extreme_price, "confirm_pos": i})
                trend, extreme_pos, extreme_price = 1, i, price

    return pivots


# ---------------------------------------------------------------- w-pattern

@dataclass
class WPattern:
    """One detected double bottom. All positions are integer bar offsets."""
    l1_pos: int
    l1_price: float
    l2_pos: int
    l2_price: float
    neckline_pos: int
    neckline: float
    confirm_pos: int          # bar close first reclaimed L1 after L2 — the pattern does not exist before this
    depth_pct: float          # neckline to L2, as % of neckline
    separation: int           # bars between the two bottoms
    tolerance_atr: float      # |L2-L1| expressed in ATR units (informational only)
    undercut: bool            # did L2 dip below L1

    def to_dict(self) -> dict:
        return asdict(self)


def find_w_patterns(
    df: pd.DataFrame,
    atr_series: pd.Series,
    zigzag_pct: float = 5.0,
    min_separation: int = 10,
    max_separation: int = 60,
    require_undercut: bool = True,
    min_depth_pct: float = 3.0,
    exclude_locked_bars: bool = True,
    confirm_max_wait: int = 30,
) -> List[WPattern]:
    """
    Find double bottoms with a percentage zigzag on CLOSE.

    Rules:
      - A bottom is only a candidate once price has rallied zigzag_pct% off
        it — the zigzag's own confirmation, not a fixed left/right bar window.
      - L1 and L2 are ADJACENT confirmed swing lows (the two most recent
        bottoms), not any combinatorial pair of lows in the window.
      - The pattern DOES NOT EXIST until price closes back above L1 after L2
        — this is the confirmation, not a separate later "entry trigger" on
        top of an already-real pattern. If that reclaim never happens within
        confirm_max_wait bars, this L1/L2 pair is not returned at all.
      - Neckline = highest high strictly between the two bottoms.
      - Depth (neckline to L2) >= min_depth_pct, so we skip flat noise.

    df needs columns: high, low, close.
    """
    required = {"high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"find_w_patterns: df missing columns {sorted(missing)}")

    close = df["close"]
    high = df["high"]

    # Circuit-locked bars (high == low == close) create fake swings. Blank
    # the high (kills the neckline) and hold the close flat through them
    # (a repeated close is a zero-length move, never a swing) rather than
    # leaving a NaN, since the zigzag walks the series bar by bar.
    if exclude_locked_bars:
        locked = (high == df["low"]) & (df["low"] == close)
        close = close.mask(locked).ffill().bfill()
        high = high.mask(locked)

    pivots = zigzag(close, zigzag_pct)
    lows = [p for p in pivots if p["kind"] == "low"]
    if len(lows) < 2:
        return []

    close_arr = close.to_numpy(dtype=float)
    highs_arr = high.to_numpy(dtype=float)
    atr_arr = atr_series.to_numpy(dtype=float)
    n = len(close_arr)

    results: List[WPattern] = []

    for k in range(1, len(lows)):
        l1, l2 = lows[k - 1], lows[k]
        i1, i2 = l1["pos"], l2["pos"]
        sep = i2 - i1
        if sep < min_separation or sep > max_separation:
            continue

        p1, p2 = l1["price"], l2["price"]
        if require_undercut and not (p2 < p1):
            continue

        # the pattern only exists once close reclaims L1 after L2
        confirm_pos = None
        for i in range(i2, min(n, i2 + confirm_max_wait + 1)):
            if close_arr[i] > p1:
                confirm_pos = i
                break
        if confirm_pos is None:
            continue

        between = highs_arr[i1 + 1:i2]
        if len(between) == 0:
            continue
        neck_rel = int(np.nanargmax(between))
        neck_pos = i1 + 1 + neck_rel
        neckline = float(between[neck_rel])
        if np.isnan(neckline) or neckline <= 0:
            continue

        depth_pct = (neckline - p2) / neckline * 100.0
        if depth_pct < min_depth_pct:
            continue

        atr_at_l2 = atr_arr[i2]
        tol_atr = (abs(p2 - p1) / atr_at_l2
                  if not np.isnan(atr_at_l2) and atr_at_l2 > 0 else float("nan"))

        results.append(
            WPattern(
                l1_pos=i1,
                l1_price=float(p1),
                l2_pos=i2,
                l2_price=float(p2),
                neckline_pos=neck_pos,
                neckline=neckline,
                confirm_pos=confirm_pos,   # <-- the look-ahead guard: L1 reclaimed here
                depth_pct=float(depth_pct),
                separation=int(sep),
                tolerance_atr=float(tol_atr),
                undercut=bool(p2 < p1),
            )
        )

    return results


# ---------------------------------------------------------------- entry triggers

def find_entry_trigger(
    df: pd.DataFrame,
    pattern: WPattern,
    variant: str,
    extra: Optional[dict] = None,
    max_wait: int = 30,
) -> Optional[int]:
    """
    Find the bar position where a given entry rule first fires, searching
    forward from pattern.confirm_pos.

    Variants (see the design doc, Backtest section):
      E1  next bar after confirmation   -- earliest, most trades, most failures
      E2  close above L1                -- the "reclaim" rule; shakeout confirmed
      E3  close above neckline          -- latest, best win rate, worst R:R
      E4  close above SMA20             -- momentum confirmation
      E5  close above AVWAP anchored at L1

    Returns the SIGNAL bar position, or None if the rule never fires within
    max_wait bars. Entry itself happens at the NEXT bar's open — see backtest.py.
    """
    extra = extra or {}
    n = len(df)
    start = pattern.confirm_pos
    if start >= n:
        return None

    stop_at = min(n, start + max_wait + 1)
    close = df["close"].to_numpy(dtype=float)

    if variant == "E1":
        return start if start < n else None

    if variant == "E2":
        level = pattern.l1_price
        for i in range(start, stop_at):
            if close[i] > level:
                return i
        return None

    if variant == "E3":
        level = pattern.neckline
        for i in range(start, stop_at):
            if close[i] > level:
                return i
        return None

    if variant == "E4":
        sma20 = extra.get("sma20")
        if sma20 is None:
            return None
        s = np.asarray(sma20, dtype=float)
        for i in range(start, stop_at):
            if not np.isnan(s[i]) and close[i] > s[i]:
                return i
        return None

    if variant == "E5":
        av = extra.get("avwap_l1")
        if av is None:
            return None
        a = np.asarray(av, dtype=float)
        for i in range(start, stop_at):
            if not np.isnan(a[i]) and close[i] > a[i]:
                return i
        return None

    raise ValueError(f"Unknown entry variant: {variant}")


def select_active_pattern(
    df: pd.DataFrame,
    patterns: List[WPattern],
    entry_variant: str = "E2",
    extra: Optional[dict] = None,
    max_wait: int = 30,
    max_bars_since_trigger: Optional[int] = None,
) -> Optional[tuple[WPattern, int]]:
    """
    Pick the ONE pattern that matters, out of every candidate double bottom
    `find_w_patterns` found in the window.

    A symbol can have several valid W-patterns stacked up over a year of
    history. Taking "whichever came last in the raw list" is not the same as
    "the one a trader would act on": it can be a pattern price has already
    blown straight through without ever confirming, while an earlier, real,
    triggered pattern sits ignored. This is the one selection rule shared by
    the live scan and the chart markup, so what gets drawn is always exactly
    why (or why not) a symbol is in the signal list.

    Rule: keep only patterns whose entry trigger actually fired, then take
    the one with the most recent trigger.
      - scan.py passes max_bars_since_trigger so only fresh triggers count.
      - The chart screen (api/services/chart.py's _active_pattern()) doesn't
        call this function at all — it just takes the most recent confirmed
        candidate from find_w_patterns() regardless of entry-trigger status,
        since the chart's job is showing the last real setup on the symbol,
        triggered or not. Same behavior the original NiceGUI chart.py had.

    Returns (pattern, signal_bar_pos), or None if nothing ever triggered.
    """
    best: Optional[tuple[WPattern, int]] = None
    for p in patterns:
        sig_pos = find_entry_trigger(df, p, entry_variant, extra, max_wait)
        if sig_pos is None:
            continue
        if best is None or sig_pos > best[1]:
            best = (p, sig_pos)

    if best is None:
        return None
    if max_bars_since_trigger is not None:
        bars_since = (len(df) - 1) - best[1]
        if bars_since > max_bars_since_trigger:
            return None
    return best


# ---------------------------------------------------------------- classification

def classify_bottom_vs_sma(
    df: pd.DataFrame,
    pattern: WPattern,
    sma_cols: dict,
    atr_series: pd.Series,
    within_atr: float = 1.0,
) -> str:
    """
    Which moving average did the second bottom form on?

    Returns 'at_sma20' | 'at_sma50' | 'at_sma100' | 'at_sma200' | 'none'.

    This is a CLASSIFIER, not a filter. A W bottoming at the 200 DMA is a
    different animal from one forming in mid-air, and slicing results this way
    is likely the most informative cut in the whole study.

    sma_cols: {'sma20': Series, 'sma50': Series, ...}
    """
    i = pattern.l2_pos
    price = pattern.l2_price
    a = atr_series.to_numpy(dtype=float)[i]
    if np.isnan(a) or a <= 0:
        return "none"

    best_name, best_dist = "none", np.inf
    for name in ("sma20", "sma50", "sma100", "sma200"):
        s = sma_cols.get(name)
        if s is None:
            continue
        val = np.asarray(s, dtype=float)[i]
        if np.isnan(val):
            continue
        d = abs(price - val) / a
        if d <= within_atr and d < best_dist:
            best_name, best_dist = f"at_{name}", d
    return best_name


def sma_stack_state(row: pd.Series) -> str:
    """
    Moving-average alignment at the signal bar.
      'stacked_up'   10>20>50>100>200  (clean uptrend)
      'stacked_down' 10<20<50<100<200  (clean downtrend)
      'mixed'        anything else
    """
    keys = ["sma10", "sma20", "sma50", "sma100", "sma200"]
    vals = [row.get(k) for k in keys]
    if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in vals):
        return "unknown"
    if all(vals[i] > vals[i + 1] for i in range(len(vals) - 1)):
        return "stacked_up"
    if all(vals[i] < vals[i + 1] for i in range(len(vals) - 1)):
        return "stacked_down"
    return "mixed"


def sma_compression_pct(row: pd.Series) -> float:
    """
    How tightly the moving averages are clustered, as % of price.
    Low values mean a coiled spring; breakouts from compression tend to run.
    """
    keys = ["sma10", "sma20", "sma50", "sma100", "sma200"]
    vals = [row.get(k) for k in keys]
    vals = [v for v in vals if v is not None and not (isinstance(v, float) and np.isnan(v))]
    if len(vals) < 2 or not row.get("close"):
        return float("nan")
    return (max(vals) - min(vals)) / row["close"] * 100.0
