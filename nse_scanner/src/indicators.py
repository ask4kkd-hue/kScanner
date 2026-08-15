"""
indicators.py — hand-coded technical indicators.

Why hand-coded and not pandas-ta:
  Three specific conventions decide whether your numbers match TradingView.
  Library versions drift on all three. Since accuracy is the top priority for
  this project, the five indicators we actually depend on are implemented here
  and unit-tested.

  1. ATR uses Wilder's RMA, not SMA and not EMA.
     RMA(n) = prev * (n-1)/n + current/n
     Get this wrong and Supertrend flips on different days.

  2. Bollinger uses POPULATION stdev (ddof=0).
     Pandas defaults to sample stdev (ddof=1). TradingView uses population.

  3. Supertrend uses LOCKED bands.
     The final upper band only ratchets DOWN while price is below it.
     Unlocked implementations produce noticeably more flips.

Every function takes and returns pandas Series aligned to the input index.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------- moving avgs

def sma(series: pd.Series, length: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(length, min_periods=length).mean()


def ema(series: pd.Series, length: int) -> pd.Series:
    """Exponential moving average (standard 2/(n+1) smoothing)."""
    return series.ewm(span=length, adjust=False, min_periods=length).mean()


def wma(series: pd.Series, length: int) -> pd.Series:
    """Weighted moving average — linear weights 1..n."""
    weights = np.arange(1, length + 1, dtype=float)
    denom = weights.sum()
    return series.rolling(length, min_periods=length).apply(
        lambda w: np.dot(w, weights) / denom, raw=True
    )


def hma(series: pd.Series, length: int) -> pd.Series:
    """
    Hull moving average.
        HMA(n) = WMA( 2*WMA(n/2) - WMA(n), sqrt(n) )
    Used by the existing Chartink screener (HMA 10 and HMA 50).
    """
    half = max(1, int(length / 2))
    root = max(1, int(np.sqrt(length)))
    raw = 2.0 * wma(series, half) - wma(series, length)
    return wma(raw, root)


def rma(series: pd.Series, length: int) -> pd.Series:
    """
    Wilder's smoothing (a.k.a. RMA / SMMA).

        RMA_t = RMA_{t-1} * (n-1)/n + x_t / n

    Seeded with a simple mean of the first n values, which is what
    TradingView and Wilder's original formulation do.
    """
    arr = series.to_numpy(dtype=float)
    out = np.full(arr.shape, np.nan)
    n = length
    if len(arr) < n:
        return pd.Series(out, index=series.index)

    # seed: simple average of the first n non-nan values
    first_valid = np.argmax(~np.isnan(arr))
    seed_end = first_valid + n
    if seed_end > len(arr):
        return pd.Series(out, index=series.index)

    out[seed_end - 1] = np.nanmean(arr[first_valid:seed_end])
    alpha = 1.0 / n
    for i in range(seed_end, len(arr)):
        prev = out[i - 1]
        out[i] = prev + alpha * (arr[i] - prev) if not np.isnan(arr[i]) else prev
    return pd.Series(out, index=series.index)


# ---------------------------------------------------------------- volatility

def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """max(H-L, |H-prevC|, |L-prevC|)."""
    prev_close = close.shift(1)
    a = high - low
    b = (high - prev_close).abs()
    c = (low - prev_close).abs()
    return pd.concat([a, b, c], axis=1).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """Average True Range using Wilder's RMA. See module docstring, point 1."""
    return rma(true_range(high, low, close), length)


def adr_pct(high: pd.Series, low: pd.Series, length: int = 20) -> pd.Series:
    """
    Average Daily Range as a percentage.

        mean( (High - Low) / Low ) over `length` bars * 100

    Directly determines whether a 5% target in 5-10 days is even reachable.
    A stock with 1.2% ADR structurally cannot get there without a gap.
    """
    daily = (high - low) / low
    return daily.rolling(length, min_periods=length).mean() * 100.0


def bollinger(close: pd.Series, length: int = 20, mult: float = 2.0):
    """
    Bollinger Bands with POPULATION stdev (ddof=0). See module docstring, point 2.
    Returns (mid, upper, lower, width_pct).
    """
    mid = sma(close, length)
    sd = close.rolling(length, min_periods=length).std(ddof=0)
    upper = mid + mult * sd
    lower = mid - mult * sd
    width = (upper - lower) / mid * 100.0
    return mid, upper, lower, width


# ---------------------------------------------------------------- momentum

def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    """Wilder's RSI — uses RMA smoothing, not SMA."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = rma(gain, length)
    avg_loss = rma(loss, length)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # when avg_loss == 0 the series is all gains -> RSI 100
    out[avg_loss == 0] = 100.0
    return out


def adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14):
    """
    Wilder's ADX / DMI. Returns (adx, di_plus, di_minus).

    WARNING: ADX is double-smoothed. It needs roughly 150 bars before the
    values are trustworthy — not the 14 you might expect. features.py gates
    this with min_bars.
    """
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index
    )

    tr_rma = rma(true_range(high, low, close), length)
    di_plus = 100.0 * rma(plus_dm, length) / tr_rma
    di_minus = 100.0 * rma(minus_dm, length) / tr_rma

    denom = (di_plus + di_minus).replace(0.0, np.nan)
    dx = 100.0 * (di_plus - di_minus).abs() / denom
    return rma(dx, length), di_plus, di_minus


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line, histogram)."""
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return line, sig, line - sig


# ---------------------------------------------------------------- supertrend

def supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    length: int = 20,
    mult: float = 3.0,
):
    """
    Supertrend with LOCKED bands. See module docstring, point 3.

    Returns (supertrend_line, direction) where direction is +1 for uptrend
    and -1 for downtrend.

    The locking rule:
      final_upper = min(basic_upper, prev_final_upper)  while prev close <= prev_final_upper
      final_lower = max(basic_lower, prev_final_lower)  while prev close >= prev_final_lower

    Without this the bands whipsaw with every ATR wiggle and you get materially
    more flips than the chart you are looking at.
    """
    hl2 = (high + low) / 2.0
    atr_v = atr(high, low, close, length)

    basic_upper = hl2 + mult * atr_v
    basic_lower = hl2 - mult * atr_v

    n = len(close)
    f_upper = np.full(n, np.nan)
    f_lower = np.full(n, np.nan)
    direction = np.full(n, np.nan)
    line = np.full(n, np.nan)

    c = close.to_numpy(dtype=float)
    bu = basic_upper.to_numpy(dtype=float)
    bl = basic_lower.to_numpy(dtype=float)

    start = int(np.argmax(~np.isnan(atr_v.to_numpy())))
    if np.isnan(atr_v.to_numpy()).all():
        return (
            pd.Series(line, index=close.index),
            pd.Series(direction, index=close.index),
        )

    f_upper[start] = bu[start]
    f_lower[start] = bl[start]
    direction[start] = 1 if c[start] > bu[start] else -1
    line[start] = f_lower[start] if direction[start] == 1 else f_upper[start]

    for i in range(start + 1, n):
        # locked upper band: ratchets down only
        f_upper[i] = (
            min(bu[i], f_upper[i - 1]) if c[i - 1] <= f_upper[i - 1] else bu[i]
        )
        # locked lower band: ratchets up only
        f_lower[i] = (
            max(bl[i], f_lower[i - 1]) if c[i - 1] >= f_lower[i - 1] else bl[i]
        )

        if direction[i - 1] == 1:
            direction[i] = -1 if c[i] < f_lower[i] else 1
        else:
            direction[i] = 1 if c[i] > f_upper[i] else -1

        line[i] = f_lower[i] if direction[i] == 1 else f_upper[i]

    return (
        pd.Series(line, index=close.index),
        pd.Series(direction, index=close.index),
    )


# ---------------------------------------------------------------- volume

def rvol(volume: pd.Series, length: int = 20) -> pd.Series:
    """Relative volume: today vs the trailing average."""
    return volume / volume.rolling(length, min_periods=length).mean()


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-balance volume."""
    sign = np.sign(close.diff().fillna(0.0))
    return (sign * volume).cumsum()


# ---------------------------------------------------------------- anchored vwap

def anchored_vwap(
    vwap_daily: pd.Series,
    volume: pd.Series,
    anchor_pos: int,
    band_mult: float = 1.0,
):
    """
    Anchored VWAP from a bar position to the end of the series.

        AVWAP(t) = sum(vwap_i * vol_i) / sum(vol_i)   for i = anchor..t

    Uses bhavcopy's daily AVG_PRICE as vwap_i. Most daily-only scanners cannot
    do this because they have no per-day VWAP — this is a genuine edge here.

    Returns (avwap, upper_band, lower_band). Values before the anchor are NaN.
    """
    n = len(vwap_daily)
    out = np.full(n, np.nan)
    up = np.full(n, np.nan)
    dn = np.full(n, np.nan)

    if anchor_pos < 0 or anchor_pos >= n:
        idx = vwap_daily.index
        return pd.Series(out, index=idx), pd.Series(up, index=idx), pd.Series(dn, index=idx)

    p = vwap_daily.to_numpy(dtype=float)[anchor_pos:]
    v = volume.to_numpy(dtype=float)[anchor_pos:]
    p = np.nan_to_num(p, nan=0.0)
    v = np.nan_to_num(v, nan=0.0)

    cum_pv = np.cumsum(p * v)
    cum_v = np.cumsum(v)
    with np.errstate(invalid="ignore", divide="ignore"):
        av = np.where(cum_v > 0, cum_pv / cum_v, np.nan)

    # running dispersion of price around the anchored vwap
    cum_p2v = np.cumsum((p ** 2) * v)
    with np.errstate(invalid="ignore", divide="ignore"):
        var = np.where(cum_v > 0, cum_p2v / cum_v - av ** 2, np.nan)
    sd = np.sqrt(np.clip(var, 0.0, None))

    out[anchor_pos:] = av
    up[anchor_pos:] = av + band_mult * sd
    dn[anchor_pos:] = av - band_mult * sd

    idx = vwap_daily.index
    return pd.Series(out, index=idx), pd.Series(up, index=idx), pd.Series(dn, index=idx)


# ---------------------------------------------------------------- helpers

def slope_pct(series: pd.Series, length: int = 20) -> pd.Series:
    """
    Percentage change of a series over `length` bars.
    Used for SMA slope — 'close > sma200 while sma200 is falling' is a
    different trade from 'close > sma200 while it is rising'.
    """
    return (series / series.shift(length) - 1.0) * 100.0


def pct_distance(a: pd.Series, b: pd.Series) -> pd.Series:
    """Percentage distance of a from b."""
    return (a / b - 1.0) * 100.0
