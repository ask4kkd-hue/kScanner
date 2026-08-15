"""
api/services/holdings.py — open-position listing, shared by /api/today and /api/trades/open.

Direct port of the logic web/pages/today.py and web/pages/holdings.py each had their own
copy of (position_status per trade, REVIEW>WATCH>HOLD sort, pnl_pct/r_multiple). One
shared function here is a small, safe cleanup — not a scope change, both call sites did
the exact same thing.
"""

from __future__ import annotations

import advisor

_STATUS_ORDER = {"REVIEW": 0, "WATCH": 1, "HOLD": 2}


def _latest_close(con, isin: str) -> float | None:
    row = con.execute(
        "SELECT close FROM bars_1d WHERE isin = ? ORDER BY date DESC LIMIT 1", [isin]
    ).fetchone()
    return float(row[0]) if row else None


def list_open_positions(con) -> list[dict]:
    """Returns rows shaped for schemas.today.PositionRow, sorted REVIEW>WATCH>HOLD."""
    open_trades = con.execute("""
        SELECT trade_id, isin, symbol, entry_date, entry_price, qty, stop_price
        FROM trades WHERE status = 'open'
    """).df()

    rows = []
    for _, t in open_trades.iterrows():
        s = advisor.position_status(con, int(t["trade_id"]))
        close = _latest_close(con, t["isin"])
        pnl_pct = (close / t["entry_price"] - 1.0) * 100.0 if close else None
        risk = t["entry_price"] - t["stop_price"]
        r_mult = (close - t["entry_price"]) / risk if close and risk > 0 else None
        rows.append({
            "trade_id": int(t["trade_id"]),
            "symbol": t["symbol"],
            "entry_date": t["entry_date"],
            "entry_price": float(t["entry_price"]),
            "qty": int(t["qty"]),
            "stop_price": float(t["stop_price"]),
            "days_held": s["metrics"].get("days_held"),
            "pnl_pct": pnl_pct,
            "r_multiple": r_mult,
            "status": s["status"],
            "reasons": s["reasons"],
            "_close": close,  # kept for total_pnl calc in the today service; not in the schema
        })

    rows.sort(key=lambda r: _STATUS_ORDER.get(r["status"], 3))
    return rows
