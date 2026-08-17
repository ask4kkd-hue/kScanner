import { api } from "./client"

export interface BacktestConfig {
  presets: string[]
  entry_variants: string[]
  exit_variants: string[]
  min_trades_for_conclusion: number
}

export interface RunSingleRequest {
  preset_name: string
  entry_variant: string
  exit_variant: string
  sample: "in" | "out"
  limit_symbols?: number | null
  label?: string
}

export interface RunSweepRequest {
  preset_name: string
  sample: "in" | "out"
  limit_symbols?: number | null
}

export interface RunMarginalRequest {
  entry_variant: string
  exit_variant: string
  limit_symbols?: number | null
}

export interface RunRecentRequest {
  preset_name: string
  entry_variant: string
  exit_variant: string
  days_back: number
  limit_symbols?: number | null
}

export interface BacktestMetrics {
  run_id: string
  trades: number
  win_rate: number
  expectancy_r: number
  avg_win_r: number
  avg_loss_r: number
  profit_factor: number | null
  max_dd_pct: number
  total_return_pct: number
  cagr_pct: number
  median_hold_days: number
  median_mae: number
  median_mfe: number
  benchmark_cagr_pct: number | null
}

export interface CurveRow {
  day_n: number
  median_mfe: number
  p75_mfe: number
  median_mae: number
  median_ret: number
  pct_positive: number
  p85_mae_win?: number | null
  marginal_mfe: number
}

export interface BacktestRun {
  metrics: BacktestMetrics | null
  curves: CurveRow[]
  min_trades_for_conclusion: number
}

export interface SweepRow extends BacktestMetrics {
  entry: string
  exit: string
  preset: string
}

export interface MarginalRow extends BacktestMetrics {
  preset: string
  delta_expectancy?: number
  delta_win_rate?: number
  trade_retention_pct?: number
  enough_trades?: boolean
}

export interface RecentTradeRow {
  symbol: string
  entry_date: string
  entry_price: number
  exit_date: string
  exit_price: number
  exit_reason: string
  net_pnl: number
  r_multiple: number | null
  holding_days: number
}

export interface RecentSummary {
  total_trades: number
  resolved_trades: number
  still_open: number
  win_rate: number | null
  target_hits: number
  stop_hits: number
  time_stop_exits: number
  realized_pnl: number
  unrealized_pnl: number
}

export interface RecentReport {
  run_id: string
  days_back: number
  trades: RecentTradeRow[]
  summary: RecentSummary
}

export const backtestApi = {
  config: () => api.get<BacktestConfig>("/api/backtest/config"),
  run: (body: RunSingleRequest) => api.post<{ run_id: string }>("/api/backtest/run", body),
  getRun: (runId: string) => api.get<BacktestRun>(`/api/backtest/${encodeURIComponent(runId)}`),
  sweep: (body: RunSweepRequest) => api.post<SweepRow[]>("/api/backtest/sweep", body),
  marginal: (body: RunMarginalRequest) => api.post<MarginalRow[]>("/api/backtest/marginal", body),
  recent: (body: RunRecentRequest) => api.post<RecentReport>("/api/backtest/recent", body),
}
