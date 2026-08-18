import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import App from "./App"

// Header's refresh-timestamp indicator (useIngestLog/useToday) would otherwise
// fire real, unmocked network calls on every render here -- harmless when this
// file runs alone, but a source of flaky timeouts under full-suite parallel load.
vi.mock("@/api/data", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/data")>()),
  dataApi: {
    tableCounts: vi.fn().mockResolvedValue({}),
    validationFailures: vi.fn().mockResolvedValue({ rows: [], flagged_15pct: 0 }),
    ingestLog: vi.fn().mockResolvedValue([]),
    symbolGaps: vi.fn().mockResolvedValue([]),
  },
}))
vi.mock("@/api/today", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/today")>()),
  todayApi: {
    get: vi.fn().mockResolvedValue({
      status: { stale: false, latest_bar: null, latest_cal: null, validation_fails_7d: 0, regime: "unknown", sessions_behind: null },
      positions: [], total_open_pnl: 0, at_risk_count: 0, opportunities: [],
      pnl: { today: 0, this_week: 0, this_month: 0, all_time: 0, unrealised: 0 },
      equity_curve: [], watchlist_near_trigger: [],
    }),
    opportunities: vi.fn().mockResolvedValue([]),
    opportunityDates: vi.fn().mockResolvedValue({ dates: [] }),
  },
}))

function renderApp(initialPath = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe("App shell", () => {
  it("renders the header and every nav item", () => {
    renderApp()
    expect(screen.getByText("kSCANNER")).toBeInTheDocument()
    for (const label of [
      "Dashboard", "New Opportunity", "Scans", "Charts", "Positions", "Watchlist",
      "Performance", "Backtest", "Data",
    ]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument()
    }
  })

  it("renders the Data screen's section titles at /data", () => {
    renderApp("/data")
    expect(screen.getByText("Table sizes")).toBeInTheDocument()
    expect(screen.getByText("Validation failures (last 30 days)")).toBeInTheDocument()
  })

  it("renders the Performance screen's tabs at /performance", () => {
    renderApp("/performance")
    expect(screen.getByRole("heading", { name: "Performance" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Overview" })).toBeInTheDocument()
  })

  it("renders the Backtest screen's tabs at /backtest", () => {
    renderApp("/backtest")
    expect(screen.getByRole("heading", { name: "Backtest" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Single run" })).toBeInTheDocument()
  })
})
