"""
api/services/chart.py — port of web/pages/chart.py's refresh().

Same two-fetch design: `bars` (limited to the requested display window) feeds the candles,
`pattern_daily` (a much longer, separate fetch — config chart.pattern_lookback_bars) feeds
W-pattern detection, decoupled from the display window for the exact reason documented in
chart.py itself: a monthly pattern needs up to ~90 monthly bars (~7+ years of daily data)
just to be structurally possible, which the display window could never supply.
"""

from __future__ import annotations

import json

import pandas as pd

import indicators as ind
import patterns as pat
import resample as rs
from config import CFG

TIMEFRAMES = {"D": "1d", "W": "1w", "M": "1m"}
FEATURES_TABLE = {"D": "features_1d", "W": "features_1w", "M": "features_1m"}
PATTERN_LOOKBACK_BARS = CFG["chart"]["pattern_lookback_bars"]

TF_MARKER_COLOR = {"D": "#c3c2b7", "W": "#D9A030", "M": "#8B5CF6"}  # theme.py REF_LINE_COLOR/WARNING + violet


def symbols(con) -> list[str]:
    return con.execute("SELECT DISTINCT symbol FROM instruments ORDER BY symbol").df()["symbol"].tolist()


def isin_for(con, symbol: str) -> str | None:
    row = con.execute("SELECT isin FROM instruments WHERE symbol = ?", [symbol]).fetchone()
    return row[0] if row else None


def _load_daily(con, isin: str, bars: int) -> pd.DataFrame:
    return con.execute("""
        SELECT b.date, b.open, b.high, b.low, b.close, b.volume, b.vwap,
               f.rsi14, f.adx14, f.adr_pct20, f.deliv_pct_sma20, f.rs_rank_pct
        FROM bars_1d b
        LEFT JOIN features_1d f ON f.isin = b.isin AND f.date = b.date
        WHERE b.isin = ? ORDER BY b.date DESC LIMIT ?
    """, [isin, bars]).df().sort_values("date").reset_index(drop=True)


def load_drawings(con, isin: str, timeframe: str) -> list[dict]:
    row = con.execute("SELECT payload FROM drawings WHERE isin = ? AND timeframe = ?",
                      [isin, timeframe]).fetchone()
    if not row:
        return []
    try:
        return json.loads(row[0])
    except Exception:
        return []


def save_drawings(con, isin: str, timeframe: str, overlays: list[dict]) -> None:
    con.execute("""
        INSERT INTO drawings (isin, timeframe, payload, updated_at)
        VALUES (?, ?, ?, now())
        ON CONFLICT (isin, timeframe) DO UPDATE SET
            payload = excluded.payload, updated_at = excluded.updated_at
    """, [isin, timeframe, json.dumps(overlays)])


def _load_feature_row(con, isin: str, tf: str, as_of) -> dict:
    table = FEATURES_TABLE[tf]
    row = con.execute(
        f"SELECT * FROM {table} WHERE isin = ? AND date <= ? ORDER BY date DESC LIMIT 1",
        [isin, as_of]).df()
    return row.iloc[0].to_dict() if not row.empty else {}


def _active_pattern(bars_df: pd.DataFrame):
    pcfg = CFG["pattern"]
    atr_s = ind.atr(bars_df["high"], bars_df["low"], bars_df["close"])
    candidates = pat.find_w_patterns(
        bars_df, atr_s,
        zigzag_pct=pcfg["zigzag_pct"], min_separation=pcfg["min_separation"],
        max_separation=pcfg["max_separation"], require_undercut=pcfg["require_undercut"],
        min_depth_pct=pcfg["min_depth_pct"], exclude_locked_bars=pcfg["exclude_locked_bars"],
        confirm_max_wait=pcfg["entry_max_wait"],
    )
    return candidates[-1] if candidates else None


def _level_overlay_pair(tf_bars: pd.DataFrame, pos: int, price: float, label: str,
                        color: str | None = None) -> list[dict]:
    ts = int(pd.Timestamp(tf_bars["date"].iloc[pos]).timestamp() * 1000)
    point = {"timestamp": ts, "value": price}
    styles = {"line": {"color": color}, "text": {"color": color}} if color else {}
    return [
        {"name": "priceLine", "points": [point], "extendData": label,
         "lock": True, "styles": {"line": {"color": color}} if color else {}},
        {"name": "simpleAnnotation", "points": [point], "extendData": label,
         "lock": True, "styles": styles},
    ]


def get_chart(
    con, symbol: str, tf: str = "D", bars: int = 250, chart_type: str = "Candle",
    overlays: list[str] | None = None, avwap: str = "(none)",
    show_pattern: bool = True, show_all_tf: bool = True,
) -> dict:
    isin = isin_for(con, symbol)
    if not isin:
        raise ValueError(f"Unknown symbol: {symbol}")

    daily = _load_daily(con, isin, bars)
    if daily.empty:
        raise ValueError("No bars for this symbol yet.")

    bars_df = {"D": daily, "W": rs.to_weekly(daily), "M": rs.to_monthly(daily)}[tf]
    if bars_df.empty:
        raise ValueError("Not enough history for this timeframe yet.")
    bars_df = bars_df.reset_index(drop=True)

    pattern_daily = _load_daily(con, isin, PATTERN_LOOKBACK_BARS)
    pattern_bars_df = {"D": pattern_daily, "W": rs.to_weekly(pattern_daily),
                       "M": rs.to_monthly(pattern_daily)}[tf]
    pattern_bars_df = pattern_bars_df.reset_index(drop=True)

    if chart_type == "Heikin Ashi":
        display_df = rs.to_heikin_ashi(bars_df)
    elif chart_type == "Renko":
        ccfg = CFG["chart"]
        display_df = rs.to_renko(bars_df, brick_mode=ccfg["renko_brick_mode"],
                                 brick_atr_mult=ccfg["renko_brick_atr_mult"])
    else:
        display_df = bars_df

    vol = display_df["volume"] if "volume" in display_df.columns else None
    out_bars = [
        {"date": pd.Timestamp(d).strftime("%Y-%m-%dT%H:%M:%S"),
         "open": float(o), "high": float(h), "low": float(l), "close": float(c),
         "volume": float(vol.iloc[i]) if vol is not None and vol.iloc[i] == vol.iloc[i] else 0}
        for i, (d, o, h, l, c) in enumerate(zip(
            display_df["date"], display_df["open"], display_df["high"],
            display_df["low"], display_df["close"]))
    ]

    chart_style = "area" if chart_type == "Line" else "candle_solid"
    indicators = [f"MA:{','.join(o[3:] for o in overlays)}"] if overlays else []

    last = daily.iloc[-1]
    close_val = float(bars_df["close"].iloc[-1])
    metrics_src = (last.to_dict() if tf == "D" else
                  _load_feature_row(con, isin, tf, pd.Timestamp(bars_df["date"].iloc[-1]).date()))

    def fmt(col: str, digits: int = 1) -> str:
        v = metrics_src.get(col)
        return f"{v:.{digits}f}" if v is not None and v == v else "—"

    active = _active_pattern(pattern_bars_df) if show_pattern else None

    metrics = {
        "close": close_val, "adr_pct": fmt("adr_pct20"), "adx": fmt("adx14"),
        "rsi": fmt("rsi14"), "delivery_pct": fmt("deliv_pct_sma20"),
        "rs_rank": fmt("rs_rank_pct", 0), "pattern_found": bool(active),
    }

    server_overlays: list[dict] = []
    if show_pattern and show_all_tf:
        per_tf_bars = {"D": pattern_daily, "W": rs.to_weekly(pattern_daily),
                       "M": rs.to_monthly(pattern_daily)}
        for label_tf, tf_bars in per_tf_bars.items():
            if tf_bars.empty:
                continue
            tf_active = active if label_tf == tf else _active_pattern(tf_bars.reset_index(drop=True))
            if not tf_active:
                continue
            color = TF_MARKER_COLOR[label_tf]
            for lvl, price, pos in (("L1", tf_active.l1_price, tf_active.l1_pos),
                                    ("L2", tf_active.l2_price, tf_active.l2_pos)):
                server_overlays.extend(_level_overlay_pair(tf_bars, pos, price, f"{label_tf}-{lvl}", color))
    elif show_pattern and active:
        for label, price, pos in (("L1", active.l1_price, active.l1_pos),
                                  ("L2", active.l2_price, active.l2_pos),
                                  ("neckline", active.neckline, active.neckline_pos)):
            server_overlays.extend(_level_overlay_pair(pattern_bars_df, pos, price, label))

    if avwap != "(none)" and "vwap" in bars_df.columns:
        lookback = 252 if tf == "D" else 52
        if avwap == "52-week low":
            pos = int(bars_df["low"].tail(lookback).idxmin())
        elif avwap == "52-week high":
            pos = int(bars_df["high"].tail(lookback).idxmax())
        else:
            pos = 0
            if active:
                l1_date = pattern_bars_df["date"].iloc[active.l1_pos]
                matches = bars_df.index[bars_df["date"] == l1_date]
                if len(matches):
                    pos = int(matches[0])
        av, _, _ = ind.anchored_vwap(bars_df["vwap"].fillna(bars_df["close"]), bars_df["volume"], pos)
        points = [{"timestamp": int(pd.Timestamp(bars_df["date"].iloc[i]).timestamp() * 1000),
                  "value": float(v)}
                 for i, v in enumerate(av) if v == v]
        if len(points) >= 2:
            server_overlays.append({"name": "path", "points": points, "lock": True})

    timeframe_key = TIMEFRAMES[tf]
    user_drawings = load_drawings(con, isin, timeframe_key)

    return {
        "bars": out_bars, "chart_style": chart_style, "indicators": indicators,
        "metrics": metrics, "server_overlays": server_overlays, "user_drawings": user_drawings,
    }
