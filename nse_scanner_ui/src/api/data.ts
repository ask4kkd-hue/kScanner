import { api } from "./client"

export interface TableCounts {
  bars_1d: number | null
  instruments: number | null
  trading_calendar: number | null
  features_1d: number | null
  signals_1d: number | null
  validation_log: number | null
  backtest_trades: number | null
  trades: number | null
}

export interface ValidationFailureRow {
  date: string | null
  symbol: string
  yf_close: number | null
  bhav_close: number | null
  pct_diff: number | null
}

export interface ValidationFailuresResponse {
  rows: ValidationFailureRow[]
  flagged_15pct: number
}

export interface IngestLogRow {
  run_ts: string | null
  scope: string
  date_from: string | null
  date_to: string | null
  rows_added: number | null
  symbols_ok: number | null
  symbols_failed: number | null
  status: string
  note: string | null
}

export interface SymbolGapRow {
  symbol: string
  status: string
  consecutive_misses: number
  last_success: string | null
}

export const dataApi = {
  tableCounts: () => api.get<TableCounts>("/api/data/table-counts"),
  validationFailures: (days = 30) =>
    api.get<ValidationFailuresResponse>(`/api/data/validation-failures?days=${days}`),
  ingestLog: (limit = 20) => api.get<IngestLogRow[]>(`/api/data/ingest-log?limit=${limit}`),
  symbolGaps: () => api.get<SymbolGapRow[]>("/api/data/symbol-gaps"),
}
