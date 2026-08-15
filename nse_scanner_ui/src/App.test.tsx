import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import App from "./App"

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
      "Today", "Scan", "Chart", "Watchlist", "Holdings", "Performance", "Backtest", "Data",
    ]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument()
    }
  })

  it("renders the Data screen's section titles at /data", () => {
    renderApp("/data")
    expect(screen.getByText("Table sizes")).toBeInTheDocument()
    expect(screen.getByText("Validation failures (last 30 days)")).toBeInTheDocument()
  })

  it("renders a not-yet-built placeholder for an unwired screen", () => {
    renderApp("/scan")
    expect(screen.getByText(/Coming in Phase 4/)).toBeInTheDocument()
  })
})
