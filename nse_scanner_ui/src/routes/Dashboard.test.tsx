import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ChartDrawer } from "@/components/chart/ChartDrawer"
import { todayApi, type TodayResponse } from "@/api/today"
import { performanceApi } from "@/api/performance"
import { useChartDrawer } from "@/store/chartDrawer"
import Dashboard from "./Dashboard"

vi.mock("@/api/today", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/today")>()),
  todayApi: { get: vi.fn() },
}))
vi.mock("@/api/performance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/performance")>()),
  performanceApi: {
    ...((await importOriginal<typeof import("@/api/performance")>()).performanceApi),
    summary: vi.fn(),
    equityCurve: vi.fn(),
  },
}))

const FIXTURE: TodayResponse = {
  status: { stale: false, latest_bar: "2026-08-14", latest_cal: "2026-08-14", validation_fails_7d: 0, regime: "bull", sessions_behind: null },
  positions: [
    { trade_id: 1, symbol: "RELIANCE", entry_date: "2026-08-01", entry_price: 1300, qty: 10, stop_price: 1250, days_held: 10, pnl_pct: 2.5, r_multiple: 0.5, status: "HOLD", reasons: ["within normal range"], lifecycle_status: "OPEN", remaining_qty: 10, partial_pnl_rupees: null },
  ],
  total_open_pnl: 3250,
  at_risk_count: 0,
  opportunities: [
    {
      timeframe: "1d", built: true, total_signals: 2, already_tracked_count: 1,
      new_signals: [{
        symbol: "TCS", trigger_price: 4000, l1_price: 3900, l2_price: 3950,
        l1_l2_distance_pct: -1.28, neckline: 4100, depth_pct: 5.0,
        stop_suggested: 3850, target_suggested: 4300,
        bottom_at_sma: "at_sma50", sma_stack: "mixed", rs_rank_pct: 88,
        outcome_status: null, outcome_date: null, pct_since_signal: null,
        quality_score: null, quality_score_max: null, quality_checklist: null,
        historical_hit_rate_pct: null, historical_sample_size: null, historical_thin: null,
      }],
    },
    { timeframe: "1w", built: false, total_signals: 0, new_signals: [], already_tracked_count: 0 },
    { timeframe: "1m", built: false, total_signals: 0, new_signals: [], already_tracked_count: 0 },
  ],
  pnl: { today: 0, this_week: 1000, this_month: 5000, all_time: 20000, unrealised: 3250 },
  equity_curve: [{ exit_date: "2026-08-01", cum_pnl: 1000 }],
  watchlist_near_trigger: [],
}

function renderDashboard() {
  vi.mocked(todayApi.get).mockResolvedValue(FIXTURE)
  vi.mocked(performanceApi.summary).mockResolvedValue({
    trades: 10, win_rate: 60, expectancy_r: 0.4, profit_factor: 1.5, net_pnl: 3250,
    min_trades_for_conclusion: 100, thin: true,
  })
  vi.mocked(performanceApi.equityCurve).mockResolvedValue([{ exit_date: "2026-08-01", cum_pnl: 1000, drawdown: 0 }])

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Dashboard />
        <ChartDrawer />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe("Dashboard screen", () => {
  beforeEach(() => {
    // The chart drawer is a module-level zustand store, not React state — it
    // survives across separate render()s within this file, so a symbol left
    // open by one test would otherwise leak into the next (Radix marks the
    // rest of the page aria-hidden while its dialog is open, hiding content
    // from every later accessibility-role query in this describe block).
    useChartDrawer.getState().close()
  })


  it("renders positions and P&L stat tiles from the API", async () => {
    renderDashboard()
    expect(await screen.findByText("RELIANCE")).toBeInTheDocument()
    expect(screen.getByText("₹3,250")).toBeInTheDocument()
  })

  it("clicking a symbol opens the chart drawer with that symbol", async () => {
    const user = userEvent.setup()
    renderDashboard()

    const symbolButton = await screen.findByRole("button", { name: "RELIANCE" })
    await user.click(symbolButton)

    expect(await screen.findByRole("heading", { name: "RELIANCE" })).toBeInTheDocument()
  })

  it("switching to the opportunities tab previews new signals", async () => {
    const user = userEvent.setup()
    renderDashboard()

    await screen.findByText("RELIANCE")
    await user.click(screen.getByRole("tab", { name: /New Opportunities/ }))
    expect(await screen.findByText("TCS")).toBeInTheDocument()
  })
})
