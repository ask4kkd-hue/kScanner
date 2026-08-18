import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import { holdingsApi, type ClosedPositionRow } from "@/api/holdings"
import { ClosedPositionsTable } from "./ClosedPositionsTable"

vi.mock("@/api/holdings", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/holdings")>()),
  holdingsApi: { closedPositions: vi.fn() },
}))

const ROWS: ClosedPositionRow[] = [
  {
    trade_id: 25, symbol: "HUBTOWN", preset_name: "", entry_date: "2026-08-17", entry_price: 186.94,
    qty: 500, exit_date: "2026-08-18", exit_price: 180.0, exit_reason: "stop",
    net_pnl: -3470, r_multiple: -1.0, holding_days: 1, mae_pct: -3.94, mfe_pct: 1.1,
  },
]

function renderTable() {
  vi.mocked(holdingsApi.closedPositions).mockResolvedValue(ROWS)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><ClosedPositionsTable /></MemoryRouter>
    </QueryClientProvider>
  )
}

describe("ClosedPositionsTable", () => {
  it("renders a closed trade with its exit reason and net P&L", async () => {
    renderTable()
    expect(await screen.findByText("HUBTOWN")).toBeInTheDocument()
    expect(screen.getByText("stop")).toBeInTheDocument()
    expect(screen.getByText("-1.00R")).toBeInTheDocument()
  })

  it("shows an empty message with no closed trades", async () => {
    vi.mocked(holdingsApi.closedPositions).mockResolvedValue([])
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter><ClosedPositionsTable /></MemoryRouter>
      </QueryClientProvider>
    )
    expect(await screen.findByText("No closed positions yet.")).toBeInTheDocument()
  })
})
