import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import { ChartDrawer } from "@/components/chart/ChartDrawer"
import { todayApi, type TodayResponse } from "@/api/today"
import Today from "./Today"

vi.mock("@/api/today", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/today")>()),
  todayApi: { get: vi.fn() },
}))

const FIXTURE: TodayResponse = {
  status: { stale: false, latest_bar: "2026-08-14", latest_cal: "2026-08-14", validation_fails_7d: 0, regime: "bull", sessions_behind: null },
  positions: [
    { trade_id: 1, symbol: "RELIANCE", entry_date: "2026-08-01", entry_price: 1300, qty: 10, stop_price: 1250, days_held: 10, pnl_pct: 2.5, r_multiple: 0.5, status: "HOLD", reasons: ["within normal range"] },
  ],
  total_open_pnl: 3250,
  at_risk_count: 0,
  opportunities: [
    { timeframe: "1d", built: true, total_signals: 2, new_signals: [{ symbol: "TCS", trigger_price: 4000, rs_rank_pct: 88 }], already_tracked_count: 1 },
    { timeframe: "1w", built: false, total_signals: 0, new_signals: [], already_tracked_count: 0 },
    { timeframe: "1m", built: false, total_signals: 0, new_signals: [], already_tracked_count: 0 },
  ],
  pnl: { today: 0, this_week: 1000, this_month: 5000, all_time: 20000, unrealised: 3250 },
  equity_curve: [{ exit_date: "2026-08-01", cum_pnl: 1000 }],
  watchlist_near_trigger: [],
}

function renderToday() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Today />
        <ChartDrawer />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe("Today screen", () => {
  it("renders positions, the default (1D) opportunity tab, and pnl from the API", async () => {
    vi.mocked(todayApi.get).mockResolvedValue(FIXTURE)
    renderToday()

    expect(await screen.findByText("RELIANCE")).toBeInTheDocument()
    expect(screen.getByText("TCS")).toBeInTheDocument()
    expect(screen.getByText("Total open P&L: ₹3,250")).toBeInTheDocument()
  })

  it("switching the opportunities tab reveals that timeframe's content", async () => {
    vi.mocked(todayApi.get).mockResolvedValue(FIXTURE)
    const user = userEvent.setup()
    renderToday()

    await screen.findByText("TCS") // 1D tab content, active by default
    expect(screen.queryByText("Not built yet — run features.py for 1w")).not.toBeInTheDocument()

    await user.click(screen.getByRole("tab", { name: /Medium term \(1W\)/ }))
    expect(await screen.findByText("Not built yet — run features.py for 1w")).toBeInTheDocument()
  })

  it("clicking a symbol opens the chart drawer with that symbol", async () => {
    vi.mocked(todayApi.get).mockResolvedValue(FIXTURE)
    const user = userEvent.setup()
    renderToday()

    const symbolButton = await screen.findByRole("button", { name: "RELIANCE" })
    await user.click(symbolButton)

    expect(await screen.findByRole("heading", { name: "RELIANCE" })).toBeInTheDocument()
  })
})
