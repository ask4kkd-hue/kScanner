"""
resample.py — timeframe and chart-type transforms.

These are pure data transforms. The chart draws exactly what these return —
no indicator or transform maths belongs in JavaScript (v2 global rule 3).

to_weekly/to_monthly group by the trading SESSIONS actually present in the
input, not synthetic calendar periods, so a holiday-shortened week does not
manufacture a wrong weekly low: a missing session simply does not
contribute to the aggregate, rather than being filled in as a fake gap.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import indicators as ind


def _resample_by_session(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """
    Group real trading sessions by calendar period (freq='W' or 'M'), label
    each group with the LAST actual session in it, and drop the final group
    unconditionally — it is always the still-forming current period.
    """
    if df.empty:
        return df.copy()

    d = df.sort_values("date").reset_index(drop=True).copy()
    d["date"] = pd.to_datetime(d["date"])
    period = d["date"].dt.to_period(freq)
    d["_period_end"] = d.groupby(period)["date"].transform("max")

    grouped = d.groupby("_period_end", sort=True)
    out = grouped.agg(open=("open", "first"), high=("high", "max"),
                      low=("low", "min"), close=("close", "last"))
    out["sessions"] = grouped.size()
    out["thin"] = out["sessions"] < 3

    if "volume" in d.columns:
        out["volume"] = grouped["volume"].sum()

    if "vwap" in d.columns and "volume" in d.columns:
        pv = (d["vwap"].fillna(d["close"]) * d["volume"].fillna(0))
        pv_sum = pv.groupby(d["_period_end"]).sum()
        vol_sum = d.groupby("_period_end")["volume"].sum().replace(0, np.nan)
        out["vwap"] = pv_sum / vol_sum

    out = out.reset_index().rename(columns={"_period_end": "date"})
    out = out.sort_values("date").reset_index(drop=True)

    # Always drop the current, still-forming period (see module docstring).
    return out.iloc[:-1].reset_index(drop=True) if len(out) else out


def to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    return _resample_by_session(df, "W")


def to_monthly(df: pd.DataFrame) -> pd.DataFrame:
    return _resample_by_session(df, "M")


def to_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """
    ha_close = (o+h+l+c)/4
    ha_open  = (prev_ha_open + prev_ha_close)/2, seeded with (o+c)/2
    ha_high  = max(h, ha_open, ha_close)
    ha_low   = min(l, ha_open, ha_close)
    """
    if df.empty:
        return df.copy()

    d = df.sort_values("date").reset_index(drop=True).copy()
    o = d["open"].to_numpy(dtype=float)
    h = d["high"].to_numpy(dtype=float)
    l = d["low"].to_numpy(dtype=float)
    c = d["close"].to_numpy(dtype=float)

    ha_close = (o + h + l + c) / 4.0
    ha_open = np.empty(len(d), dtype=float)
    ha_open[0] = (o[0] + c[0]) / 2.0
    for i in range(1, len(d)):
        ha_open[i] = (ha_open[i - 1] + ha_close[i - 1]) / 2.0

    ha_high = np.maximum.reduce([h, ha_open, ha_close])
    ha_low = np.minimum.reduce([l, ha_open, ha_close])

    out = d.copy()
    out["open"], out["high"], out["low"], out["close"] = (
        ha_open, ha_high, ha_low, ha_close)
    return out


def to_renko(
    df: pd.DataFrame,
    brick_mode: str = "atr",
    brick_atr_mult: float = 1.0,
    brick_pct: float | None = None,
) -> pd.DataFrame:
    """
    Brick size fixed from ATR14 at the first bar (or a flat percentage of
    the first close). A new brick forms each time close moves a full brick
    from the last brick's close; reversing direction needs TWO bricks worth
    of move (the standard Renko rule), not one.

    The x-axis is not time-linear — each row is a brick, not a session.
    Callers should treat the returned frame's `date` as a tooltip label
    only, never as an evenly-spaced axis.
    """
    if df.empty:
        return df.copy()

    d = df.sort_values("date").reset_index(drop=True).copy()
    first_close = float(d["close"].iloc[0])

    if brick_mode == "pct" and brick_pct:
        brick = first_close * brick_pct / 100.0
    else:
        atr_s = ind.atr(d["high"], d["low"], d["close"], 14)
        fv = atr_s.first_valid_index()
        brick = (float(atr_s.loc[fv]) * brick_atr_mult
                 if fv is not None and not np.isnan(atr_s.loc[fv]) else np.nan)
    if not brick or np.isnan(brick) or brick <= 0:
        brick = first_close * 0.01  # 1% fallback if ATR/pct is unusable

    bricks: list[dict] = []
    anchor = first_close
    direction = 0  # 0 = undecided, 1 = up, -1 = down

    for _, row in d.iterrows():
        c = float(row["close"])
        moved = True
        while moved:
            moved = False
            if direction >= 0 and c >= anchor + brick:
                new_anchor = anchor + brick
                bricks.append({"date": row["date"], "open": anchor,
                               "high": new_anchor, "low": anchor,
                               "close": new_anchor})
                anchor, direction, moved = new_anchor, 1, True
            elif direction <= 0 and c <= anchor - brick:
                new_anchor = anchor - brick
                bricks.append({"date": row["date"], "open": anchor,
                               "high": anchor, "low": new_anchor,
                               "close": new_anchor})
                anchor, direction, moved = new_anchor, -1, True
            elif direction == 1 and c <= anchor - 2 * brick:
                new_anchor = anchor - brick
                bricks.append({"date": row["date"], "open": anchor,
                               "high": anchor, "low": new_anchor,
                               "close": new_anchor})
                anchor, direction, moved = new_anchor, -1, True
            elif direction == -1 and c >= anchor + 2 * brick:
                new_anchor = anchor + brick
                bricks.append({"date": row["date"], "open": anchor,
                               "high": new_anchor, "low": anchor,
                               "close": new_anchor})
                anchor, direction, moved = new_anchor, 1, True

    out = pd.DataFrame(bricks, columns=["date", "open", "high", "low", "close"])
    out.attrs["x_axis_time_linear"] = False
    out.attrs["brick_size"] = brick
    return out
