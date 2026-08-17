import { useMutation, useQuery } from "@tanstack/react-query"

import { analyticsApi, type RunAnalysisRequest } from "@/api/analytics"

export const useAnalyticsConfig = () =>
  useQuery({ queryKey: ["analytics", "config"], queryFn: analyticsApi.config })

export const useRunAnalysis = () =>
  useMutation({ mutationFn: (body: RunAnalysisRequest) => analyticsApi.run(body) })
