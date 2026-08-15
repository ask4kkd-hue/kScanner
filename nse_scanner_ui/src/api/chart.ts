import { api } from "./client"
import type { OverlayPayload } from "@/components/chart/KLineChartWidget"

export interface ChartBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface ChartMetrics {
  close: number
  adr_pct: string
  adx: string
  rsi: string
  delivery_pct: string
  rs_rank: string
  pattern_found: boolean
}

export interface ChartResponse {
  bars: ChartBar[]
  chart_style: "area" | "candle_solid"
  indicators: string[]
  metrics: ChartMetrics
  server_overlays: OverlayPayload[]
  user_drawings: OverlayPayload[]
}

export interface ChartQuery {
  timeframe?: "D" | "W" | "M"
  bars?: number
  chart_type?: "Candle" | "Line" | "Heikin Ashi" | "Renko"
  overlays?: string[]
  avwap?: string
  show_pattern?: boolean
  show_all_tf?: boolean
}

export const chartApi = {
  symbols: () => api.get<string[]>("/api/instruments/symbols"),

  get: (symbol: string, q: ChartQuery = {}) => {
    const params = new URLSearchParams()
    if (q.timeframe) params.set("timeframe", q.timeframe)
    if (q.bars) params.set("bars", String(q.bars))
    if (q.chart_type) params.set("chart_type", q.chart_type)
    if (q.overlays) params.set("overlays", q.overlays.join(","))
    if (q.avwap) params.set("avwap", q.avwap)
    if (q.show_pattern !== undefined) params.set("show_pattern", String(q.show_pattern))
    if (q.show_all_tf !== undefined) params.set("show_all_tf", String(q.show_all_tf))
    return api.get<ChartResponse>(`/api/chart/${encodeURIComponent(symbol)}?${params}`)
  },

  getDrawings: (symbol: string, timeframe: string) =>
    api.get<OverlayPayload[]>(
      `/api/chart/${encodeURIComponent(symbol)}/drawings?timeframe=${timeframe}`
    ),

  saveDrawings: (symbol: string, timeframe: string, overlays: OverlayPayload[]) =>
    api.put<{ saved: number }>(
      `/api/chart/${encodeURIComponent(symbol)}/drawings?timeframe=${timeframe}`,
      overlays
    ),

  clearDrawings: (symbol: string, timeframe: string) =>
    api.delete<{ cleared: boolean }>(
      `/api/chart/${encodeURIComponent(symbol)}/drawings?timeframe=${timeframe}`
    ),
}
