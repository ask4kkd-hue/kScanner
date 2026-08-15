import { create } from "zustand"

/**
 * The "click any stock anywhere to open its chart" mechanism — a slide-over
 * drawer (Zerodha/Upstox-style quick look) rather than full navigation, so
 * whatever screen you clicked from stays visible behind it. Any component
 * app-wide just needs a symbol string to open it; see useOpenChart() below.
 */
interface ChartDrawerState {
  isOpen: boolean
  symbol: string | null
  timeframe: "D" | "W" | "M"
  open: (symbol: string, timeframe?: "D" | "W" | "M") => void
  close: () => void
}

export const useChartDrawer = create<ChartDrawerState>((set) => ({
  isOpen: false,
  symbol: null,
  timeframe: "D",
  open: (symbol, timeframe = "D") => set({ isOpen: true, symbol, timeframe }),
  close: () => set({ isOpen: false }),
}))

/** Convenience hook: `const openChart = useOpenChart(); <tr onClick={() => openChart("RELIANCE")}>`. */
export function useOpenChart() {
  return useChartDrawer((s) => s.open)
}
