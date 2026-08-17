import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { analyticsApi, type AnalyticsRow } from "@/api/analytics"
import Analytics from "./Analytics"

vi.mock("@/api/analytics", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/analytics")>()),
  analyticsApi: {
    config: vi.fn().mockResolvedValue({
      types: [
        { id: "down_from_ath", label: "Down X% from All-Time High", param_label: "% down from ATH", min_default: 70, max_default: 100 },
      ],
    }),
    run: vi.fn(),
  },
}))

const FIXTURE: AnalyticsRow[] = [
  {
    symbol: "RCOM", name: "Reliance Communications", sector: "Telecom",
    ath: 844.0, ath_date: "2010-06-28T00:00:00", last_close: 0.81, last_date: "2026-08-14T00:00:00",
    pct_down_from_ath: 99.9,
  },
]

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}><Analytics /></QueryClientProvider>
  )
}

describe("Analytics screen", () => {
  it("defaults min/max from config and runs the selected analysis as a range", async () => {
    vi.mocked(analyticsApi.run).mockResolvedValue(FIXTURE)
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByText("Down X% from All-Time High")).toBeInTheDocument()
    expect(screen.getByDisplayValue("70")).toBeInTheDocument()
    expect(screen.getByDisplayValue("100")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Run" }))

    expect(await screen.findByText("RCOM")).toBeInTheDocument()
    expect(screen.getByText("99.9%")).toBeInTheDocument()
    expect(vi.mocked(analyticsApi.run)).toHaveBeenCalledWith(
      expect.objectContaining({ analysis_type: "down_from_ath", min_pct: 70, max_pct: 100 })
    )
  }, 10000)

  it("sends a custom min/max range as numbers", async () => {
    vi.mocked(analyticsApi.run).mockResolvedValue(FIXTURE)
    const user = userEvent.setup()
    renderPage()

    const minInput = await screen.findByDisplayValue("70")
    await user.clear(minInput)
    await user.type(minInput, "70")
    const maxInput = screen.getByDisplayValue("100")
    await user.clear(maxInput)
    await user.type(maxInput, "85")

    await user.click(screen.getByRole("button", { name: "Run" }))

    expect(vi.mocked(analyticsApi.run)).toHaveBeenCalledWith(
      expect.objectContaining({ min_pct: 70, max_pct: 85 })
    )
  }, 10000)

  it("warns instead of running when min is greater than max", async () => {
    vi.mocked(analyticsApi.run).mockClear()
    vi.mocked(analyticsApi.run).mockResolvedValue(FIXTURE)
    const user = userEvent.setup()
    renderPage()

    const minInput = await screen.findByDisplayValue("70")
    await user.clear(minInput)
    await user.type(minInput, "95")
    const maxInput = screen.getByDisplayValue("100")
    await user.clear(maxInput)
    await user.type(maxInput, "90")

    await user.click(screen.getByRole("button", { name: "Run" }))

    expect(vi.mocked(analyticsApi.run)).not.toHaveBeenCalled()
  }, 10000)
})
