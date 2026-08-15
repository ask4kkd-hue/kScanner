"""api/routers/watchlist.py — thin wrapper around watchlist.py's add/remove/list_with_status."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import watchlist as wl

from api.deps import get_cursor
from api.util import jsonable_df

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("")
def get_watchlist(cur=Depends(get_cursor)) -> list[dict]:
    return jsonable_df(wl.list_with_status(cur))


class AddWatchlistRequest(BaseModel):
    symbol: str
    note: str = ""
    target_price: float | None = None
    tags: str = ""


@router.post("")
def post_watchlist(body: AddWatchlistRequest, cur=Depends(get_cursor)) -> dict:
    try:
        wl.add(cur, body.symbol, note=body.note, target_price=body.target_price, tags=body.tags)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"added": body.symbol}


@router.delete("/{isin}")
def delete_watchlist(isin: str, cur=Depends(get_cursor)) -> dict:
    wl.remove(cur, isin)
    return {"removed": isin}
