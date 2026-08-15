import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import { todayApi, type TodayResponse } from "@/api/today"
import NewOpportunity from "./NewOpportunity"

vi.mock("@/api/today", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/today")>()),
  todayApi: { get: vi.fn() },
}))

const FIXTURE: TodayResponse = {
  status: { stale: false, latest_bar: "2026-08-14", latest_cal: "2026-08-14", validation_fails_7d: 0, regime: "bull", sessions_behind: null },
  positions: [],
  total_open_pnl: 0,
  at_risk_count: 0,
  opportunities: [
    {
      timeframe: "1d", built: true, total_signals: 2, already_tracked_count: 1,
      new_signals: [{
        symbol: "TCS", trigger_price: 4000, l1_price: 3900, l2_price: 3950,
        l1_l2_distance: -50, neckline: 4100, depth_pct: 5.0,
        stop_suggested: 3850, target_suggested: 4300,
        bottom_at_sma: "at_sma50", sma_stack: "mixed", rs_rank_pct: 88,
      }],
    },
    { timeframe: "1w", built: false, total_signals: 0, new_signals: [], already_tracked_count: 0 },
    { timeframe: "1m", built: false, total_signals: 0, new_signals: [], already_tracked_count: 0 },
  ],
  pnl: { today: 0, this_week: 0, this_month: 0, all_time: 0, unrealised: 0 },
  equity_curve: [],
  watchlist_near_trigger: [],
}

function renderPage() {
  vi.mocked(todayApi.get).mockResolvedValue(FIXTURE)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><NewOpportunity /></MemoryRouter>
    </QueryClientProvider>
  )
}

describe("New Opportunity screen", () => {
  it("renders the default (1D) opportunity tab's signals", async () => {
    renderPage()
    expect(await screen.findByText("TCS")).toBeInTheDocument()
  })

  it("switching tabs reveals that timeframe's content", async () => {
    const user = userEvent.setup()
    renderPage()

    await screen.findByText("TCS")
    expect(screen.queryByText("Not built yet — run features.py for 1w")).not.toBeInTheDocument()

    await user.click(screen.getByRole("tab", { name: /Medium term \(1W\)/ }))
    expect(await screen.findByText("Not built yet — run features.py for 1w")).toBeInTheDocument()
  })
})
