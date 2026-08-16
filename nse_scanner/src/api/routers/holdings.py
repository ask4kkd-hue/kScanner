"""api/routers/holdings.py — open positions, entry, and close."""

from __future__ import annotations

import journal as jr
from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_cursor
from api.schemas.today import PositionRow
from api.schemas.trades import (
    TradeCloseRequest, TradeOpenRequest, TradePartialCloseRequest, TradeUpdateRequest,
)
from api.services.holdings import list_open_positions

router = APIRouter(prefix="/trades", tags=["holdings"])


@router.get("/open", response_model=list[PositionRow])
def get_open_positions(cur=Depends(get_cursor)) -> list[dict]:
    # list_open_positions() already calls jr.update_open_trades(cur) itself.
    return [{k: v for k, v in p.items() if k != "_close"} for p in list_open_positions(cur)]


@router.post("")
def post_open_trade(body: TradeOpenRequest, cur=Depends(get_cursor)) -> dict:
    # journal.open_trade() does NOT validate the symbol exists — an unknown
    # symbol silently inserts a trade with isin=NULL (found by testing this
    # exact path: it also crashed update_open_trades() afterward, since a
    # NULL/NaN isin passed as a query parameter makes DuckDB infer a DOUBLE
    # parameter type and try to cast the isin VARCHAR column to match). The
    # NiceGUI original never hit this because its symbol field was a
    # dropdown of real symbols only; an API has no such implicit guard, so
    # it has to check explicitly, same as chart.py/watchlist.py's routers.
    row = cur.execute("SELECT 1 FROM instruments WHERE symbol = ?", [body.symbol]).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {body.symbol}")
    try:
        trade_id = jr.open_trade(
            cur, body.symbol, body.entry_date, body.entry_price, body.qty, body.stop_price,
            target_price=body.target_price, preset_name=body.preset_name, thesis=body.thesis,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not open position: {e}") from e
    return {"trade_id": trade_id}


@router.post("/{trade_id}/close")
def post_close_trade(trade_id: int, body: TradeCloseRequest, cur=Depends(get_cursor)) -> dict:
    try:
        result = jr.close_trade(
            cur, trade_id, body.exit_date, body.exit_price, body.exit_reason,
            followed_plan=body.followed_plan, review_note=body.review_note,
        )
        if body.tags:
            jr.add_tags(cur, trade_id, body.tags)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not close position: {e}") from e
    return result


@router.post("/{trade_id}/partial-close")
def post_partial_close_trade(trade_id: int, body: TradePartialCloseRequest, cur=Depends(get_cursor)) -> dict:
    try:
        return jr.partial_close(
            cur, trade_id, body.exit_date, body.exit_price, body.qty,
            body.exit_reason, note=body.note,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not partially close position: {e}") from e


@router.patch("/{trade_id}")
def patch_trade(trade_id: int, body: TradeUpdateRequest, cur=Depends(get_cursor)) -> dict:
    row = cur.execute("SELECT status FROM trades WHERE trade_id = ?", [trade_id]).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"No trade {trade_id}")
    if row[0] != "open":
        raise HTTPException(status_code=400, detail="Only open positions can be edited — this one is closed.")
    try:
        jr.update_trade(cur, trade_id, **body.model_dump(exclude_none=True))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not update position: {e}") from e
    return {"updated": trade_id}


@router.delete("/{trade_id}")
def delete_trade_endpoint(trade_id: int, cur=Depends(get_cursor)) -> dict:
    row = cur.execute("SELECT 1 FROM trades WHERE trade_id = ?", [trade_id]).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"No trade {trade_id}")
    jr.delete_trade(cur, trade_id)
    return {"deleted": trade_id}
