import { useOpenChart } from "@/store/chartDrawer"

/** Any symbol, anywhere, clickable straight into the chart drawer. */
export function SymbolLink({ symbol, className }: { symbol: string; className?: string }) {
  const openChart = useOpenChart()
  return (
    <button
      type="button"
      onClick={() => openChart(symbol)}
      className={className ?? "font-semibold hover:text-primary hover:underline"}
    >
      {symbol}
    </button>
  )
}
