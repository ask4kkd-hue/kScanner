import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import { todayApi, type OpportunityBlock } from "@/api/today"
import NewOpportunity from "./NewOpportunity"

vi.mock("@/api/today", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/today")>()),
  todayApi: { get: vi.fn(), opportunities: vi.fn(), opportunityDates: vi.fn() },
}))

const LATEST: OpportunityBlock[] = [
  {
    timeframe: "1d", built: true, total_signals: 2, already_tracked_count: 1,
    new_signals: [{
      symbol: "TCS", trigger_price: 4000, l1_price: 3900, l2_price: 3950,
      l1_l2_distance_pct: -1.28, neckline: 4100, depth_pct: 5.0,
      stop_suggested: 3850, target_suggested: 4300,
      bottom_at_sma: "at_sma50", sma_stack: "mixed", rs_rank_pct: 88,
      // today's own signal -- no forward bars yet, so no outcome
      outcome_status: null, outcome_date: null, pct_since_signal: null,
      quality_score: 2, quality_score_max: 3,
      quality_checklist: [
        { label: "Low relative strength (reversal setup, not already extended)", passed: true },
        { label: "Deep pattern (larger measured-move target)", passed: true },
        { label: "Above-average volatility (more room to travel)", passed: false },
      ],
      historical_hit_rate_pct: 83.0, historical_sample_size: 7951, historical_thin: false,
    }],
  },
  { timeframe: "1w", built: false, total_signals: 0, new_signals: [], already_tracked_count: 0 },
  { timeframe: "1m", built: false, total_signals: 0, new_signals: [], already_tracked_count: 0 },
]

const PAST: OpportunityBlock[] = [
  {
    timeframe: "1d", built: true, total_signals: 1, already_tracked_count: 0,
    new_signals: [{
      symbol: "INFY", trigger_price: 1800, l1_price: 1750, l2_price: 1770,
      l1_l2_distance_pct: -1.1, neckline: 1850, depth_pct: 4.5,
      stop_suggested: 1720, target_suggested: 1930,
      bottom_at_sma: "at_sma200", sma_stack: "stacked_up", rs_rank_pct: 75,
      // a past signal that has since hit its stop
      outcome_status: "SL hit", outcome_date: "2026-08-15", pct_since_signal: -4.4,
      quality_score: 0, quality_score_max: 3,
      quality_checklist: [
        { label: "Low relative strength (reversal setup, not already extended)", passed: false },
        { label: "Deep pattern (larger measured-move target)", passed: false },
        { label: "Above-average volatility (more room to travel)", passed: false },
      ],
      historical_hit_rate_pct: 75.6, historical_sample_size: 11935, historical_thin: false,
    }],
  },
  { timeframe: "1w", built: false, total_signals: 0, new_signals: [], already_tracked_count: 0 },
  { timeframe: "1m", built: false, total_signals: 0, new_signals: [], already_tracked_count: 0 },
]

function renderPage() {
  vi.mocked(todayApi.opportunities).mockImplementation((asOfDate?: string) =>
    Promise.resolve(asOfDate ? PAST : LATEST)
  )
  vi.mocked(todayApi.opportunityDates).mockResolvedValue({
    dates: ["2026-08-17", "2026-08-14", "2026-08-13", "2026-08-12"], // latest, T-1, T-2, T-3 (no T-4)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><NewOpportunity /></MemoryRouter>
    </QueryClientProvider>
  )
}

describe("New Opportunity screen", () => {
  it("renders the default (latest) opportunity tab's signals", async () => {
    renderPage()
    expect(await screen.findByText("TCS")).toBeInTheDocument()
    expect(vi.mocked(todayApi.opportunities)).toHaveBeenCalledWith(undefined)
  })

  it("switching tabs reveals that timeframe's content", async () => {
    const user = userEvent.setup()
    renderPage()

    await screen.findByText("TCS")
    expect(screen.queryByText("Not built yet — run features.py for 1w")).not.toBeInTheDocument()

    await user.click(screen.getByRole("tab", { name: /Medium term \(1W\)/ }))
    expect(await screen.findByText("Not built yet — run features.py for 1w")).toBeInTheDocument()
  })

  it("T-1 quick-select fetches the previous scanned date, and T-4 is disabled when no data exists that far back", async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText("TCS")

    expect(await screen.findByRole("button", { name: "T-4" })).toBeDisabled()

    await user.click(screen.getByRole("button", { name: "T-1" }))

    expect(await screen.findByText("INFY")).toBeInTheDocument()
    expect(vi.mocked(todayApi.opportunities)).toHaveBeenLastCalledWith("2026-08-14")
    expect(screen.getByText("Showing 2026-08-14's scan.")).toBeInTheDocument()
  })

  it("picking a date directly also re-fetches", async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText("TCS")

    const dateInput = screen.getByDisplayValue("")
    await user.type(dateInput, "2026-08-13")

    expect(await screen.findByText("INFY")).toBeInTheDocument()
    expect(vi.mocked(todayApi.opportunities)).toHaveBeenLastCalledWith("2026-08-13")
  })

  it("shows no outcome for today's own signal, and a real outcome once browsing a past date", async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText("TCS")

    // Today's signal has no forward bars yet -- both new columns show "—".
    const tcsRow = screen.getByText("TCS").closest("tr")!
    expect(tcsRow.textContent).toContain("—")

    await user.click(screen.getByRole("button", { name: "T-1" }))
    await screen.findByText("INFY")

    expect(screen.getByText("SL hit")).toBeInTheDocument()
    expect(screen.getByText("-4.4%")).toBeInTheDocument()
  })

  it("shows the quality score and historical hit rate for 1D signals", async () => {
    renderPage()
    await screen.findByText("TCS")
    expect(screen.getByText("2/3")).toBeInTheDocument()
    expect(screen.getByText("(83%)")).toBeInTheDocument()
  })

  it("W-1 quick-select on the 1W tab uses 1W's own scan-date history, independently of 1D's", async () => {
    const user = userEvent.setup()

    const weeklyLatest: OpportunityBlock[] = [
      LATEST[0],
      { timeframe: "1w", built: true, total_signals: 1, already_tracked_count: 0, new_signals: [{
        symbol: "RELIANCE", trigger_price: 2900, l1_price: 2800, l2_price: 2820,
        l1_l2_distance_pct: -0.7, neckline: 3000, depth_pct: 6.0,
        stop_suggested: 2700, target_suggested: 3200,
        bottom_at_sma: "at_sma50", sma_stack: "mixed", rs_rank_pct: 60,
        outcome_status: null, outcome_date: null, pct_since_signal: null,
        // 1W has no comparable backtest history to score against yet
        quality_score: null, quality_score_max: null, quality_checklist: null,
        historical_hit_rate_pct: null, historical_sample_size: null, historical_thin: null,
      }] },
      LATEST[2],
    ]
    const weeklyPast: OpportunityBlock[] = [
      PAST[0],
      { timeframe: "1w", built: true, total_signals: 1, already_tracked_count: 0, new_signals: [{
        symbol: "WIPRO", trigger_price: 500, l1_price: 480, l2_price: 485,
        l1_l2_distance_pct: -1.0, neckline: 520, depth_pct: 6.5,
        stop_suggested: 460, target_suggested: 555,
        bottom_at_sma: "at_sma200", sma_stack: "stacked_up", rs_rank_pct: 70,
        outcome_status: "Target hit", outcome_date: "2026-08-10", pct_since_signal: 12.0,
        quality_score: null, quality_score_max: null, quality_checklist: null,
        historical_hit_rate_pct: null, historical_sample_size: null, historical_thin: null,
      }] },
      PAST[2],
    ]
    vi.mocked(todayApi.opportunities).mockImplementation((asOfDate?: string) =>
      Promise.resolve(asOfDate ? weeklyPast : weeklyLatest)
    )
    // 1D and 1W have independent scan-date histories -- the T-1/W-1 button
    // must resolve against whichever timeframe tab is currently active.
    vi.mocked(todayApi.opportunityDates).mockImplementation((timeframe: string) =>
      Promise.resolve({
        dates: timeframe === "1w"
          ? ["2026-08-17", "2026-08-16"] // 1w has only just started accumulating history
          : ["2026-08-17", "2026-08-14", "2026-08-13", "2026-08-12"],
      })
    )
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter><NewOpportunity /></MemoryRouter>
      </QueryClientProvider>
    )

    await screen.findByText("TCS")
    await user.click(screen.getByRole("tab", { name: /Medium term \(1W\)/ }))
    await screen.findByText("RELIANCE")

    await user.click(screen.getByRole("button", { name: "T-1" }))

    expect(await screen.findByText("WIPRO")).toBeInTheDocument()
    expect(screen.getByText("Target hit")).toBeInTheDocument()
    expect(vi.mocked(todayApi.opportunities)).toHaveBeenLastCalledWith("2026-08-16")
  })
})
