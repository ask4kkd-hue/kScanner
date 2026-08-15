import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { watchlistApi } from "@/api/watchlist"

export const useWatchlist = () =>
  useQuery({ queryKey: ["watchlist"], queryFn: watchlistApi.list })

export const useAddToWatchlist = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ symbol, ...opts }: { symbol: string; note?: string; target_price?: number; tags?: string }) =>
      watchlistApi.add(symbol, opts),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlist"] }),
  })
}

export const useRemoveFromWatchlist = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (isin: string) => watchlistApi.remove(isin),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlist"] }),
  })
}
