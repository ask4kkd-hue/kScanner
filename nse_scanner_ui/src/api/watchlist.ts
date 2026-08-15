import { api } from "./client"

export interface WatchlistRow {
  isin: string
  symbol: string
  added_on: string
  note: string | null
  target_price: number | null
  tags: string | null
  last_date: string | null
  close: number | null
  sma50: number | null
  sma200: number | null
  rsi14: number | null
  adx14: number | null
  rs_rank_pct: number | null
  near_trigger: boolean
  neckline: number | null
}

export const watchlistApi = {
  list: () => api.get<WatchlistRow[]>("/api/watchlist"),
  add: (symbol: string, opts?: { note?: string; target_price?: number; tags?: string }) =>
    api.post<{ added: string }>("/api/watchlist", { symbol, ...opts }),
  remove: (isin: string) => api.delete<{ removed: string }>(`/api/watchlist/${isin}`),
}
