import { api } from "./client"

export interface PositionRow {
  trade_id: number
  symbol: string
  entry_date: string
  entry_price: number
  qty: number
  stop_price: number
  close: number | null
  days_held: number | null
  pnl_pct: number | null
  pnl_rupees: number | null
  r_multiple: number | null
  mae_pct: number | null
  mfe_pct: number | null
  status: "HOLD" | "WATCH" | "REVIEW"
  reasons: string[]
  lifecycle_status: "OPEN" | "PARTIAL_PROFIT" | "PARTIAL_LOSS" | "CLOSED"
  remaining_qty: number
  partial_pnl_rupees: number | null
}

export interface TradeOpenRequest {
  symbol: string
  entry_date: string
  entry_price: number
  qty: number
  stop_price: number
  target_price?: number
  preset_name?: string
  thesis?: string
}

export interface TradeCloseRequest {
  exit_date: string
  exit_price: number
  exit_reason: "target" | "stop" | "time_stop" | "discretionary"
  followed_plan: boolean
  review_note?: string
  tags?: string[]
}

export interface TradePartialCloseRequest {
  exit_date: string
  exit_price: number
  qty: number
  exit_reason: "target" | "stop" | "time_stop" | "discretionary"
  note?: string
}

export interface TradeUpdateRequest {
  entry_date?: string
  entry_price?: number
  qty?: number
  stop_price?: number
  target_price?: number
  thesis?: string
}

export const holdingsApi = {
  openPositions: () => api.get<PositionRow[]>("/api/trades/open"),
  open: (body: TradeOpenRequest) => api.post<{ trade_id: number }>("/api/trades", body),
  close: (tradeId: number, body: TradeCloseRequest) =>
    api.post<{ trade_id: number; net_pnl: number }>(`/api/trades/${tradeId}/close`, body),
  partialClose: (tradeId: number, body: TradePartialCloseRequest) =>
    api.post<{ partial_id: number; trade_id: number; qty: number; net_pnl: number; remaining_qty: number }>(
      `/api/trades/${tradeId}/partial-close`, body,
    ),
  update: (tradeId: number, body: TradeUpdateRequest) =>
    api.patch<{ updated: number }>(`/api/trades/${tradeId}`, body),
  remove: (tradeId: number) => api.delete<{ deleted: number }>(`/api/trades/${tradeId}`),
}
