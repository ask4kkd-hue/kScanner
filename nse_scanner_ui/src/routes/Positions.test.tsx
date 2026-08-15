import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { holdingsApi } from "@/api/holdings"
import Positions from "./Positions"

vi.mock("@/api/holdings", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/holdings")>()),
  holdingsApi: {
    openPositions: vi.fn().mockResolvedValue([
      {
        trade_id: 1, symbol: "RELIANCE", entry_date: "2026-08-01", entry_price: 1300,
        qty: 10, stop_price: 1250, close: 1330, days_held: 10, pnl_pct: 2.3,
        pnl_rupees: 300, r_multiple: 0.6, mae_pct: -1.2, mfe_pct: 3.1,
        status: "HOLD", reasons: ["within normal range"],
      },
    ]),
    open: vi.fn(),
    close: vi.fn().mockResolvedValue({ trade_id: 1, net_pnl: 300 }),
  },
}))

vi.mock("@/api/chart", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/chart")>()),
  chartApi: { ...((await importOriginal<typeof import("@/api/chart")>()).chartApi), symbols: vi.fn().mockResolvedValue(["RELIANCE", "TCS"]) },
}))

function renderPositions() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}><Positions /></QueryClientProvider>
  )
}

describe("Positions screen", () => {
  it("renders the open position with pnl, R-multiple, and advisor reasons", async () => {
    renderPositions()
    expect(await screen.findByText("RELIANCE")).toBeInTheDocument()
    expect(screen.getByText("₹300")).toBeInTheDocument()
    expect(screen.getByText("0.60R")).toBeInTheDocument()
    expect(screen.getByText("· within normal range")).toBeInTheDocument()
  })

  it("clicking close opens the close dialog and submits the right payload", async () => {
    const user = userEvent.setup()
    renderPositions()
    await screen.findByText("RELIANCE")

    await user.click(screen.getByRole("button", { name: "×" }))
    expect(await screen.findByRole("heading", { name: "Close RELIANCE" })).toBeInTheDocument()

    await user.type(screen.getByPlaceholderText("Exit price"), "1340")
    await user.click(screen.getByRole("button", { name: "Close position" }))

    expect(vi.mocked(holdingsApi.close)).toHaveBeenCalledWith(
      1, expect.objectContaining({ exit_price: 1340, followed_plan: true })
    )
  }, 10000)
})
