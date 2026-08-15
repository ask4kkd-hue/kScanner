import { api } from "./client"

export interface FilterChip {
  id: string
  label: string
  expr: string
  default?: number | string
  min?: number
  max?: number
  step?: number
}

export interface ChipState {
  active: boolean
  value: number | string | null
}

export interface ScanRunResponse {
  scan_id: string
  total_count: number
  preselected_chip_ids: string[]
}

export interface ScanFilterResponse {
  count: number
  total: number
  rows: Record<string, unknown>[]
  bottom_at_sma_distribution: Record<string, number>
}

export const scanApi = {
  filterChips: () => api.get<FilterChip[]>("/api/scan/filter-chips"),
  presets: () => api.get<string[]>("/api/scan/presets"),
  preselect: (preset: string) => api.get<string[]>(`/api/scan/presets/${encodeURIComponent(preset)}/preselect`),
  run: (presetName: string, timeframe: string) =>
    api.post<ScanRunResponse>("/api/scan/run", { preset_name: presetName, timeframe }),
  filter: (scanId: string, chips: Record<string, ChipState>) =>
    api.post<ScanFilterResponse>(`/api/scan/${scanId}/filter`, { chips }),
  savePreset: (name: string, conditions: string[]) =>
    api.post<{ saved: string }>("/api/scan/save-preset", { name, conditions }),
}
