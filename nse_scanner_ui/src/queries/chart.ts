import { useQuery } from "@tanstack/react-query"

import { chartApi } from "@/api/chart"

export const useChartSymbols = () =>
  useQuery({ queryKey: ["chart", "symbols"], queryFn: chartApi.symbols })
