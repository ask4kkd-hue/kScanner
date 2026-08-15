import { useQuery } from "@tanstack/react-query"

import { todayApi } from "@/api/today"

export const useToday = () =>
  useQuery({ queryKey: ["today"], queryFn: todayApi.get })
