"""
watchlist.py — symbols you're tracking but haven't traded yet.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

import indicators as ind
import patterns as pat
from backtest import load_symbol_frame
from config import CFG


def add(con, symbol: str, note: str = "", target_price: float | None = None,
        tags: str = "") -> None:
    row = con.execute("SELECT isin FROM instruments WHERE symbol = ?",
                      [symbol]).fetchone()
    if not row:
        raise ValueError(f"Unknown symbol '{symbol}'")
    con.execute("""
        INSERT INTO watchlist (isin, symbol, added_on, note, target_price, tags)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT (isin) DO UPDATE SET
            note = excluded.note,
            target_price = excluded.target_price,
            tags = excluded.tags
    """, [row[0], symbol, date.today(), note, target_price, tags])


def remove(con, isin: str) -> None:
    con.execute("DELETE FROM watchlist WHERE isin = ?", [isin])


def list_with_status(con, near_pct: float = 2.0) -> pd.DataFrame:
    """
    Watchlist joined to latest bars/features, plus a near_trigger flag when
    price is within near_pct% of target_price or of a detected W neckline.
    """
    wl = con.execute("SELECT * FROM watchlist ORDER BY added_on DESC").df()
    if wl.empty:
        return wl

    latest = con.execute("""
        SELECT b.isin, b.date AS last_date, b.close,
               f.sma50, f.sma200, f.rsi14, f.adx14, f.rs_rank_pct
        FROM bars_1d b
        LEFT JOIN features_1d f ON f.isin = b.isin AND f.date = b.date
        QUALIFY ROW_NUMBER() OVER (PARTITION BY b.isin ORDER BY b.date DESC) = 1
    """).df()
    out = wl.merge(latest, on="isin", how="left")

    end = con.execute("SELECT MAX(date) FROM bars_1d").fetchone()[0]
    pcfg = CFG["pattern"]

    near_flags, necklines = [], []
    for _, row in out.iterrows():
        close = row.get("close")
        near = False
        neckline = None

        target = row.get("target_price")
        if close is not None and target and target > 0:
            near = abs(close - target) / target * 100.0 <= near_pct

        if not near and close is not None and end is not None:
            start = end - timedelta(days=400)
            df = load_symbol_frame(con, row["isin"], start, end)
            if len(df) >= 260:
                atr_s = df["atr14"]
                if atr_s.isna().all():
                    atr_s = ind.atr(df["high"], df["low"], df["close"])
                found = pat.find_w_patterns(
                    df, atr_s,
                    zigzag_pct=pcfg["zigzag_pct"],
                    min_separation=pcfg["min_separation"],
                    max_separation=pcfg["max_separation"],
                    require_undercut=pcfg["require_undercut"],
                    min_depth_pct=pcfg["min_depth_pct"],
                    exclude_locked_bars=pcfg["exclude_locked_bars"],
                    confirm_max_wait=pcfg["entry_max_wait"],
                )
                if found:
                    neckline = found[-1].neckline
                    if neckline:
                        near = abs(close - neckline) / neckline * 100.0 <= near_pct

        near_flags.append(near)
        necklines.append(neckline)

    out["near_trigger"] = near_flags
    out["neckline"] = necklines
    return out
