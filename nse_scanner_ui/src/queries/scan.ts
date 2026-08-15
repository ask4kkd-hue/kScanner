import { useMutation, useQuery } from "@tanstack/react-query"

import { scanApi, type ChipState } from "@/api/scan"

export const useFilterChips = () =>
  useQuery({ queryKey: ["scan", "filter-chips"], queryFn: scanApi.filterChips })

export const usePresets = () =>
  useQuery({ queryKey: ["scan", "presets"], queryFn: scanApi.presets })

export const useRunScan = () =>
  useMutation({ mutationFn: (presetName: string) => scanApi.run(presetName) })

export const useScanFilter = (scanId: string | null, chips: Record<string, ChipState>) =>
  useQuery({
    queryKey: ["scan", "filter", scanId, chips],
    queryFn: () => scanApi.filter(scanId!, chips),
    enabled: !!scanId,
  })

export const useSavePreset = () =>
  useMutation({ mutationFn: ({ name, conditions }: { name: string; conditions: string[] }) =>
    scanApi.savePreset(name, conditions) })
