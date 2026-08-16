"""
api/services/holdings.py — open-position listing, shared by /api/today and /api/trades/open.

Direct port of the logic web/pages/today.py and web/pages/holdings.py each had their own
copy of (position_status per trade, REVIEW>WATCH>HOLD sort, pnl_pct/r_multiple). One
shared function here is a small, safe cleanup — not a scope change, both call sites did
the exact same thing.
"""

from __future__ import annotations

import advisor
import journal as jr

_STATUS_ORDER = {"REVIEW": 0, "WATCH": 1, "HOLD": 2}


def _latest_close(con, isin: str) -> float | None:
    row = con.execute(
        "SELECT close FROM bars_1d WHERE isin = ? ORDER BY date DESC LIMIT 1", [isin]
    ).fetchone()
    return float(row[0]) if row else None


def _partial_pnl(con, trade_id: int) -> float | None:
    """Sum of net_pnl already booked via partial exits, or None if there are none."""
    row = con.execute(
        "SELECT SUM(net_pnl) FROM trade_partials WHERE trade_id = ?", [trade_id]
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def list_open_positions(con) -> list[dict]:
    """Returns rows shaped for schemas.today.PositionRow, sorted REVIEW>WATCH>HOLD.

    Refreshes mae_pct/mfe_pct for open trades first (jr.update_open_trades) —
    both web/pages/today.py and web/pages/holdings.py did this before reading
    trades, so this shared function does it once rather than leaving it to
    each caller to remember."""
    jr.update_open_trades(con)

    open_trades = con.execute("""
        SELECT trade_id, isin, symbol, entry_date, entry_price, qty, stop_price
        FROM trades WHERE status = 'open'
    """).df()

    rows = []
    for _, t in open_trades.iterrows():
        trade_id = int(t["trade_id"])
        s = advisor.position_status(con, trade_id)
        close = _latest_close(con, t["isin"])

        remaining = jr.remaining_qty(con, trade_id)
        partial_pnl = _partial_pnl(con, trade_id)
        if remaining == int(t["qty"]):
            lifecycle_status = "OPEN"
        else:
            lifecycle_status = "PARTIAL_PROFIT" if (partial_pnl or 0.0) >= 0 else "PARTIAL_LOSS"

        # Unrealised P&L is against the qty still actually held — a
        # partially-booked position no longer owns its original full qty.
        pnl_pct = (close / t["entry_price"] - 1.0) * 100.0 if close else None
        pnl_rupees = (close - t["entry_price"]) * remaining if close is not None else None
        risk = t["entry_price"] - t["stop_price"]
        r_mult = (close - t["entry_price"]) / risk if close and risk > 0 else None
        m = s["metrics"]
        rows.append({
            "trade_id": trade_id,
            "symbol": t["symbol"],
            "entry_date": t["entry_date"],
            "entry_price": float(t["entry_price"]),
            "qty": int(t["qty"]),
            "stop_price": float(t["stop_price"]),
            "close": close,
            "days_held": m.get("days_held"),
            "pnl_pct": pnl_pct,
            "pnl_rupees": pnl_rupees,
            "r_multiple": r_mult,
            "mae_pct": m.get("mae_pct"),
            "mfe_pct": m.get("mfe_pct"),
            "status": s["status"],
            "reasons": s["reasons"],
            "lifecycle_status": lifecycle_status,
            "remaining_qty": remaining,
            "partial_pnl_rupees": partial_pnl,
            "_close": close,  # kept for total_pnl calc in the today service; not in the schema
        })

    rows.sort(key=lambda r: _STATUS_ORDER.get(r["status"], 3))
    return rows
