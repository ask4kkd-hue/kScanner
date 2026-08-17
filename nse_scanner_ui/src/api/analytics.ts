import { api } from "./client"

export interface AnalysisTypeInfo {
  id: string
  label: string
  param_label: string
  min_default: number
  max_default: number
}

export interface AnalyticsConfig {
  types: AnalysisTypeInfo[]
}

export interface RunAnalysisRequest {
  analysis_type: string
  min_pct: number
  max_pct: number
}

export interface AnalyticsRow {
  symbol: string
  name: string | null
  sector: string | null
  ath: number
  ath_date: string
  last_close: number
  last_date: string
  pct_down_from_ath: number
}

export const analyticsApi = {
  config: () => api.get<AnalyticsConfig>("/api/analytics/config"),
  run: (body: RunAnalysisRequest) => api.post<AnalyticsRow[]>("/api/analytics/run", body),
}
