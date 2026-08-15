import { useQuery } from "@tanstack/react-query"

import { performanceApi } from "@/api/performance"

export const useSummary = () =>
  useQuery({ queryKey: ["performance", "summary"], queryFn: performanceApi.summary })

export const useEquityCurve = () =>
  useQuery({ queryKey: ["performance", "equity-curve"], queryFn: performanceApi.equityCurve })

export const useAttribution = () =>
  useQuery({ queryKey: ["performance", "attribution"], queryFn: performanceApi.attribution })

export const useAdherence = () =>
  useQuery({ queryKey: ["performance", "adherence"], queryFn: performanceApi.adherence })

export const useTags = () =>
  useQuery({ queryKey: ["performance", "tags"], queryFn: performanceApi.tags })

export const useSnapshotMetrics = () =>
  useQuery({ queryKey: ["performance", "snapshot-metrics"], queryFn: performanceApi.snapshotMetrics })

export const useSnapshot = (metric: string | undefined) =>
  useQuery({
    queryKey: ["performance", "snapshot", metric],
    queryFn: () => performanceApi.snapshot(metric as string),
    enabled: !!metric,
  })

export const usePresetsTraded = () =>
  useQuery({ queryKey: ["performance", "presets-traded"], queryFn: performanceApi.presetsTraded })

export const useCompare = (presetName: string | undefined) =>
  useQuery({
    queryKey: ["performance", "compare", presetName],
    queryFn: () => performanceApi.compare(presetName as string),
    enabled: !!presetName,
  })
