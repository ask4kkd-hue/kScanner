"""api/routers/chart.py — symbol list, chart data, and drawings persistence."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_cursor
from api.schemas.chart import ChartResponse
from api.services import chart as chart_service

router = APIRouter(tags=["chart"])


@router.get("/instruments/symbols")
def get_symbols(cur=Depends(get_cursor)) -> list[str]:
    return chart_service.symbols(cur)


@router.get("/chart/{symbol}", response_model=ChartResponse)
def get_chart(
    symbol: str,
    timeframe: str = "D",
    bars: int = 250,
    chart_type: str = "Candle",
    overlays: str = "",
    avwap: str = "(none)",
    show_pattern: bool = True,
    show_all_tf: bool = True,
    l1l2_color: str | None = None,
    l1l2_line_style: str | None = None,
    l1l2_line_width: int | None = None,
    cur=Depends(get_cursor),
) -> dict:
    overlay_list = [o for o in overlays.split(",") if o]
    try:
        return chart_service.get_chart(
            cur, symbol, tf=timeframe, bars=bars, chart_type=chart_type,
            overlays=overlay_list, avwap=avwap, show_pattern=show_pattern, show_all_tf=show_all_tf,
            l1l2_color=l1l2_color, l1l2_line_style=l1l2_line_style, l1l2_line_width=l1l2_line_width,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/chart/{symbol}/drawings")
def get_drawings(symbol: str, timeframe: str = "1d", cur=Depends(get_cursor)) -> list[dict]:
    isin = chart_service.isin_for(cur, symbol)
    if not isin:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")
    return chart_service.load_drawings(cur, isin, timeframe)


@router.put("/chart/{symbol}/drawings")
def put_drawings(symbol: str, overlays: list[dict[str, Any]], timeframe: str = "1d",
                 cur=Depends(get_cursor)) -> dict:
    isin = chart_service.isin_for(cur, symbol)
    if not isin:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")
    chart_service.save_drawings(cur, isin, timeframe, overlays)
    return {"saved": len(overlays)}


@router.delete("/chart/{symbol}/drawings")
def delete_drawings(symbol: str, timeframe: str = "1d", cur=Depends(get_cursor)) -> dict:
    isin = chart_service.isin_for(cur, symbol)
    if not isin:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")
    chart_service.save_drawings(cur, isin, timeframe, [])
    return {"cleared": True}
