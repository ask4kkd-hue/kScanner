import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { holdingsApi, type TradeCloseRequest, type TradeOpenRequest, type TradeUpdateRequest } from "@/api/holdings"

export const useOpenPositions = () =>
  useQuery({ queryKey: ["trades", "open"], queryFn: holdingsApi.openPositions })

export const useOpenTrade = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TradeOpenRequest) => holdingsApi.open(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trades", "open"] })
      queryClient.invalidateQueries({ queryKey: ["today"] })
    },
  })
}

export const useCloseTrade = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ tradeId, body }: { tradeId: number; body: TradeCloseRequest }) =>
      holdingsApi.close(tradeId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trades", "open"] })
      queryClient.invalidateQueries({ queryKey: ["today"] })
    },
  })
}

export const useUpdateTrade = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ tradeId, body }: { tradeId: number; body: TradeUpdateRequest }) =>
      holdingsApi.update(tradeId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trades", "open"] })
      queryClient.invalidateQueries({ queryKey: ["today"] })
    },
  })
}

export const useDeleteTrade = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (tradeId: number) => holdingsApi.remove(tradeId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trades", "open"] })
      queryClient.invalidateQueries({ queryKey: ["today"] })
    },
  })
}
