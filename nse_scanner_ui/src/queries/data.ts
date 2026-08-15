import { useQuery } from "@tanstack/react-query"

import { dataApi } from "@/api/data"

export const useTableCounts = () =>
  useQuery({ queryKey: ["data", "table-counts"], queryFn: dataApi.tableCounts })

export const useValidationFailures = (days = 30) =>
  useQuery({
    queryKey: ["data", "validation-failures", days],
    queryFn: () => dataApi.validationFailures(days),
  })

export const useIngestLog = (limit = 20) =>
  useQuery({ queryKey: ["data", "ingest-log", limit], queryFn: () => dataApi.ingestLog(limit) })

export const useSymbolGaps = () =>
  useQuery({ queryKey: ["data", "symbol-gaps"], queryFn: dataApi.symbolGaps })
