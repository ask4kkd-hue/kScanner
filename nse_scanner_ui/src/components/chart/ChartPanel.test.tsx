import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { chartApi } from "@/api/chart"
import { ChartPanel } from "./ChartPanel"

vi.mock("@/api/chart", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/chart")>()),
  chartApi: {
    symbols: vi.fn().mockResolvedValue(["RELIANCE", "TCS", "ZEEL"]),
    get: vi.fn().mockResolvedValue({
      bars: [{ date: "2026-08-01", open: 100, high: 101, low: 99, close: 100.5, volume: 1000 }],
      chart_style: "candle_solid",
      indicators: [],
      metrics: { close: 100.5, adr_pct: "1.2", adx: "20.0", rsi: "55.0", delivery_pct: "40.0", rs_rank: "70", pattern_found: true },
      server_overlays: [],
      user_drawings: [],
    }),
    saveDrawings: vi.fn(),
    clearDrawings: vi.fn(),
  },
}))

// jsdom has no <canvas> implementation, so klinecharts' real init() throws
// (calcTextWidth -> getContext('2d') -> null -> .scale crashes) — a known,
// documented limitation (see the plan's verification notes), not something
// worth installing the `canvas` native package to work around. Mocking the
// widget itself lets everything AROUND it (controls, query params, metrics
// rendering) stay genuinely tested; the actual klinecharts render remains
// manual-browser-only.
vi.mock("@/components/chart/KLineChartWidget", () => ({
  KLineChartWidget: () => <div data-testid="kline-chart-stub" />,
}))

describe("ChartPanel", () => {
  it("renders controls and metrics, and calls the API with the right query params", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <ChartPanel initialSymbol="RELIANCE" />
      </QueryClientProvider>
    )

    expect(await screen.findByText("Mark last W L1/L2")).toBeInTheDocument()
    expect(screen.getByText("D/W/M together")).toBeInTheDocument()
    expect(await screen.findByText("W found")).toBeInTheDocument()
    expect(vi.mocked(chartApi.get)).toHaveBeenCalledWith(
      "RELIANCE",
      expect.objectContaining({ timeframe: "D", show_pattern: true, show_all_tf: true })
    )
  }, 10000)
})
