import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  backtestApi,
  type RunMarginalRequest,
  type RunSingleRequest,
  type RunSweepRequest,
} from "@/api/backtest"

export const useBacktestConfig = () =>
  useQuery({ queryKey: ["backtest", "config"], queryFn: backtestApi.config })

export const useBacktestRun = (runId: string | undefined) =>
  useQuery({
    queryKey: ["backtest", "run", runId],
    queryFn: () => backtestApi.getRun(runId as string),
    enabled: !!runId,
  })

export const useRunBacktest = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: RunSingleRequest) => backtestApi.run(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["backtest"] })
    },
  })
}

export const useRunSweep = () =>
  useMutation({ mutationFn: (body: RunSweepRequest) => backtestApi.sweep(body) })

export const useRunMarginal = () =>
  useMutation({ mutationFn: (body: RunMarginalRequest) => backtestApi.marginal(body) })
