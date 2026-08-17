import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { backtestApi, type RecentReport } from "@/api/backtest"
import RecentSignals from "./RecentSignals"

vi.mock("@/api/backtest", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/backtest")>()),
  backtestApi: {
    config: vi.fn().mockResolvedValue({
      presets: ["w_naked", "w_baseline"],
      entry_variants: ["E1", "E2"],
      exit_variants: ["X1", "X3"],
      min_trades_for_conclusion: 100,
    }),
    recent: vi.fn(),
  },
}))

const FIXTURE: RecentReport = {
  run_id: "abc123",
  days_back: 20,
  trades: [
    {
      symbol: "TCS", entry_date: "2026-08-01", entry_price: 4000,
      exit_date: "2026-08-11", exit_price: 4300, exit_reason: "target_hit",
      net_pnl: 4500, r_multiple: 1.8, holding_days: 10,
    },
    {
      symbol: "INFY", entry_date: "2026-08-14", entry_price: 1800,
      exit_date: "2026-08-17", exit_price: 1790, exit_reason: "end_of_data",
      net_pnl: -180, r_multiple: -0.2, holding_days: 3,
    },
  ],
  summary: {
    total_trades: 2, resolved_trades: 1, still_open: 1, win_rate: 100.0,
    target_hits: 1, stop_hits: 0, time_stop_exits: 0,
    realized_pnl: 4500, unrealized_pnl: -180,
  },
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}><RecentSignals /></QueryClientProvider>
  )
}

describe("Recent Signals screen", () => {
  it("runs the report and shows both resolved and still-open trades with the summary", async () => {
    vi.mocked(backtestApi.recent).mockResolvedValue(FIXTURE)
    const user = userEvent.setup()
    renderPage()

    await screen.findByText("w_naked")
    await user.click(screen.getByRole("button", { name: "Run" }))

    expect(await screen.findByText("TCS")).toBeInTheDocument()
    expect(screen.getByText("INFY")).toBeInTheDocument()
    // "Still open" appears both as the stat tile label and the row's reason cell
    expect(screen.getAllByText("Still open").length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText("Target hit")).toBeInTheDocument()

    expect(vi.mocked(backtestApi.recent)).toHaveBeenCalledWith(
      expect.objectContaining({ preset_name: "w_naked", days_back: 20 })
    )
  }, 10000)

  it("sends a custom days_back value as a number", async () => {
    vi.mocked(backtestApi.recent).mockResolvedValue(FIXTURE)
    const user = userEvent.setup()
    renderPage()

    await screen.findByText("w_naked")
    const daysInput = screen.getByPlaceholderText("e.g. 20")
    await user.clear(daysInput)
    await user.type(daysInput, "45")
    await user.click(screen.getByRole("button", { name: "Run" }))

    expect(vi.mocked(backtestApi.recent)).toHaveBeenCalledWith(
      expect.objectContaining({ days_back: 45 })
    )
  }, 10000)
})
