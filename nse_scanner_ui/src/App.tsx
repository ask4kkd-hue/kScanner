import type { ReactNode } from "react"
import { Route, Routes } from "react-router-dom"

import { ChartDrawer } from "@/components/chart/ChartDrawer"
import { Header } from "@/components/shell/Header"
import { HealthRail } from "@/components/shell/HealthRail"
import { Nav } from "@/components/shell/Nav"
import Chart from "@/routes/Chart"
import Data from "@/routes/Data"
import Placeholder from "@/routes/Placeholder"
import Today from "@/routes/Today"

function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen flex-col">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Nav />
        <main className="flex-1 overflow-y-auto p-4">
          <HealthRail />
          {children}
        </main>
      </div>
      <ChartDrawer />
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout><Today /></Layout>} />
      <Route path="/scan" element={<Layout><Placeholder screen="Scan" phase="Phase 4" /></Layout>} />
      <Route path="/chart" element={<Layout><Chart /></Layout>} />
      <Route path="/chart/:symbol" element={<Layout><Chart /></Layout>} />
      <Route path="/watchlist" element={<Layout><Placeholder screen="Watchlist" phase="Phase 5" /></Layout>} />
      <Route path="/holdings" element={<Layout><Placeholder screen="Holdings" phase="Phase 5" /></Layout>} />
      <Route path="/performance" element={<Layout><Placeholder screen="Performance" phase="Phase 6" /></Layout>} />
      <Route path="/backtest" element={<Layout><Placeholder screen="Backtest" phase="Phase 6" /></Layout>} />
      <Route path="/data" element={<Layout><Data /></Layout>} />
    </Routes>
  )
}
