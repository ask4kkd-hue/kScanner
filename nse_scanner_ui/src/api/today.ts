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
  lifecycle_status: "OPEN" | "PARTIAL_PROFIT" | "PARTIAL_LOSS" | "CLOSED"
  remaining_qty: number
  partial_pnl_rupees: number | null
}

export interface QualityChecklistItem {
  label: string
  passed: boolean
}

export interface OpportunitySignal {
  symbol: string
  trigger_price: number
  l1_price: number | null
  l2_price: number | null
  l1_l2_distance_pct: number | null
  neckline: number | null
  depth_pct: number | null
  stop_suggested: number | null
  target_suggested: number | null
  bottom_at_sma: string | null
  sma_stack: string | null
  rs_rank_pct: number | null
  // Descriptive-only forward outcome since the signal's scan_date -- null for
  // today's own signal (no bar after it yet); populated once you browse T-1+.
  outcome_status: "SL hit" | "Target hit" | "Towards target" | "Open for trade" | null
  outcome_date: string | null
  pct_since_signal: number | null
  // Evidence-calibrated quality score (scoring.py) -- 1D only, null for 1W/1M
  // (no comparable backtest history to calibrate against yet).
  quality_score: number | null
  quality_score_max: number | null
  quality_checklist: QualityChecklistItem[] | null
  historical_hit_rate_pct: number | null
  historical_sample_size: number | null
  historical_thin: boolean | null
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
  opportunities: (asOfDate?: string) => {
    const params = asOfDate ? `?as_of_date=${asOfDate}` : ""
    return api.get<OpportunityBlock[]>(`/api/today/opportunities${params}`)
  },
  opportunityDates: (timeframe: string) =>
    api.get<{ dates: string[] }>(`/api/today/opportunity-dates?timeframe=${timeframe}`),
}
