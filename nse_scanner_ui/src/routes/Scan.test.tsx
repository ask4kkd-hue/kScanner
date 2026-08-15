import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import { scanApi } from "@/api/scan"
import Scan from "./Scan"

vi.mock("@/api/scan", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/scan")>()),
  scanApi: {
    filterChips: vi.fn().mockResolvedValue([
      { id: "above_sma200", label: "Close > SMA200", expr: "close > sma200" },
      { id: "rsi_above", label: "RSI >", expr: "rsi14 > {v}", default: 30, min: 0, max: 100 },
    ]),
    presets: vi.fn().mockResolvedValue(["w_naked", "w_baseline"]),
    preselect: vi.fn(),
    run: vi.fn().mockResolvedValue({
      scan_id: "abc123", total_count: 3, preselected_chip_ids: ["above_sma200"],
    }),
    filter: vi.fn().mockResolvedValue({
      count: 2, total: 3,
      rows: [
        { symbol: "RELIANCE", trigger_price: 1400, l1_price: 1300, l2_price: 1320, neckline: 1450, depth_pct: 8.5, stop_suggested: 1280, target_suggested: 1550, bottom_at_sma: "at_sma200", sma_stack: "stacked_up", rs_rank_pct: 72 },
        { symbol: "TCS", trigger_price: 4000, l1_price: 3900, l2_price: 3950, neckline: 4100, depth_pct: 5.0, stop_suggested: 3850, target_suggested: 4300, bottom_at_sma: "at_sma50", sma_stack: "mixed", rs_rank_pct: 60 },
      ],
      bottom_at_sma_distribution: { at_sma200: 1, at_sma50: 1 },
    }),
    savePreset: vi.fn(),
  },
}))

function renderScan() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><Scan /></MemoryRouter>
    </QueryClientProvider>
  )
}

describe("Scan screen", () => {
  it("running a scan shows results and pre-selects the matching chip", async () => {
    const user = userEvent.setup()
    renderScan()

    await screen.findByText("Close > SMA200") // chips loaded
    await user.click(screen.getByRole("button", { name: /Run scan/ }))

    expect(await screen.findByText("RELIANCE")).toBeInTheDocument()
    expect(screen.getByText("TCS")).toBeInTheDocument()
    expect(screen.getByText("2 of 3 signals")).toBeInTheDocument()
    expect(vi.mocked(scanApi.run)).toHaveBeenCalledWith("w_naked")

    // preselected_chip_ids included "above_sma200" -> the filter call that
    // follows should have actually turned that chip on (the real behavior
    // that matters — not a CSS class check on the button).
    await waitFor(() => {
      const lastCall = vi.mocked(scanApi.filter).mock.calls.at(-1)
      expect(lastCall?.[1].above_sma200?.active).toBe(true)
      expect(lastCall?.[1].rsi_above?.active).toBe(false)
    })
  }, 10000)

  it("toggling a chip re-filters via the API", async () => {
    const user = userEvent.setup()
    renderScan()

    await user.click(screen.getByRole("button", { name: /Run scan/ }))
    await screen.findByText("RELIANCE")

    const rsiChip = screen.getByRole("button", { name: /RSI >/ })
    await user.click(rsiChip)

    await waitFor(() => {
      const lastCall = vi.mocked(scanApi.filter).mock.calls.at(-1)
      expect(lastCall?.[1].rsi_above?.active).toBe(true)
    })
  })
})
