import { useQuery } from "@tanstack/react-query"

import { todayApi } from "@/api/today"

export const useToday = () =>
  useQuery({ queryKey: ["today"], queryFn: todayApi.get })

export const useOpportunities = (asOfDate?: string) =>
  useQuery({
    queryKey: ["today", "opportunities", asOfDate ?? "latest"],
    queryFn: () => todayApi.opportunities(asOfDate),
  })

export const useOpportunityDates = (timeframe: string) =>
  useQuery({
    queryKey: ["today", "opportunity-dates", timeframe],
    queryFn: () => todayApi.opportunityDates(timeframe),
  })
