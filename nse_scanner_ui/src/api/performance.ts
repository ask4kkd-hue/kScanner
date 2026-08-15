import { api } from "./client"

export interface Summary {
  trades: number
  win_rate?: number
  expectancy_r?: number
  avg_win_r?: number
  avg_loss_r?: number
  profit_factor?: number | null
  net_pnl?: number
  median_hold_days?: number
  median_mae?: number
  median_mfe?: number
  min_trades_for_conclusion: number
  thin: boolean
}

export interface EquityPoint {
  exit_date: string
  cum_pnl: number
  drawdown: number
}

export interface AttributionRow {
  trades: number
  avg_r?: number
  win_rate?: number
  net_pnl?: number
  thin: boolean
  [key: string]: unknown // preset_name | tf_label | sector, whichever cut this row is
}

export interface Attribution {
  by_preset: AttributionRow[]
  by_timeframe: AttributionRow[]
  by_sector: AttributionRow[]
  bottom_at_sma_note: string
}

export interface AdherenceRow {
  followed_plan: boolean
  trades: number
  avg_r: number
  net_pnl: number
  win_rate: number
}

export interface TagRow {
  tag: string
  trades: number
  avg_r: number
  net_pnl: number
}

export interface SnapshotRow {
  bucket: string
  trades: number
  avg_r: number
  win_rate: number
}

export interface CompareRow {
  source: "live" | "backtest"
  trades: number
  win_rate: number
  avg_r: number
  median_hold: number
  median_mae: number
  median_mfe: number
}

export const performanceApi = {
  summary: () => api.get<Summary>("/api/performance/summary"),
  equityCurve: () => api.get<EquityPoint[]>("/api/performance/equity-curve"),
  attribution: () => api.get<Attribution>("/api/performance/attribution"),
  adherence: () => api.get<AdherenceRow[]>("/api/performance/adherence"),
  tags: () => api.get<TagRow[]>("/api/performance/tags"),
  snapshotMetrics: () => api.get<string[]>("/api/performance/snapshot-metrics"),
  snapshot: (metric: string) => api.get<SnapshotRow[]>(`/api/performance/snapshot?metric=${metric}`),
  presetsTraded: () => api.get<string[]>("/api/performance/presets-traded"),
  compare: (presetName: string) =>
    api.get<CompareRow[]>(`/api/performance/compare?preset_name=${encodeURIComponent(presetName)}`),
}
