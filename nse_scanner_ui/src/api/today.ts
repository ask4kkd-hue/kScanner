import { api } from "./client"

export interface StatusInfo {
  stale: boolean
  latest_bar: string | null
  latest_cal: string | null
  validation_fails_7d: number
  regime: string
  sessions_behind: number | null
}

export interface PositionRow {
  trade_id: number
  symbol: string
  entry_date: string
  entry_price: number
  qty: number
  stop_price: number
  days_held: number | null
  pnl_pct: number | null
  r_multiple: number | null
  status: "HOLD" | "WATCH" | "REVIEW"
  reasons: string[]
}

export interface OpportunitySignal {
  symbol: string
  trigger_price: number
  l1_price: number | null
  l2_price: number | null
  l1_l2_distance: number | null
  neckline: number | null
  depth_pct: number | null
  stop_suggested: number | null
  target_suggested: number | null
  bottom_at_sma: string | null
  sma_stack: string | null
  rs_rank_pct: number | null
}

export interface OpportunityBlock {
  timeframe: "1d" | "1w" | "1m"
  built: boolean
  total_signals: number
  new_signals: OpportunitySignal[]
  already_tracked_count: number
}

export interface WatchlistNearRow {
  symbol: string
  close: number | null
  target_price: number | null
  neckline: number | null
}

export interface PnlSummary {
  today: number
  this_week: number
  this_month: number
  all_time: number
  unrealised: number
}

export interface EquityPoint {
  exit_date: string
  cum_pnl: number
}

export interface TodayResponse {
  status: StatusInfo
  positions: PositionRow[]
  total_open_pnl: number
  at_risk_count: number
  opportunities: OpportunityBlock[]
  pnl: PnlSummary
  equity_curve: EquityPoint[]
  watchlist_near_trigger: WatchlistNearRow[]
}

export const todayApi = {
  get: () => api.get<TodayResponse>("/api/today"),
}
