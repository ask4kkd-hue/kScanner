import type { ReactNode } from "react"
import { useEffect } from "react"
import { Route, Routes } from "react-router-dom"

import { ChartDrawer } from "@/components/chart/ChartDrawer"
import { Header } from "@/components/shell/Header"
import { HealthRail } from "@/components/shell/HealthRail"
import { Nav } from "@/components/shell/Nav"
import Backtest from "@/routes/Backtest"
import Chart from "@/routes/Chart"
import Dashboard from "@/routes/Dashboard"
import Data from "@/routes/Data"
import NewOpportunity from "@/routes/NewOpportunity"
import Performance from "@/routes/Performance"
import Positions from "@/routes/Positions"
import Scan from "@/routes/Scan"
import Watchlist from "@/routes/Watchlist"
import { useUiPrefs } from "@/store/uiPrefs"

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
  const theme = useUiPrefs((s) => s.theme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  return (
    <Routes>
      <Route path="/" element={<Layout><Dashboard /></Layout>} />
      <Route path="/new-opportunity" element={<Layout><NewOpportunity /></Layout>} />
      <Route path="/scan" element={<Layout><Scan /></Layout>} />
      <Route path="/chart" element={<Layout><Chart /></Layout>} />
      <Route path="/chart/:symbol" element={<Layout><Chart /></Layout>} />
      <Route path="/positions" element={<Layout><Positions /></Layout>} />
      <Route path="/watchlist" element={<Layout><Watchlist /></Layout>} />
      <Route path="/performance" element={<Layout><Performance /></Layout>} />
      <Route path="/backtest" element={<Layout><Backtest /></Layout>} />
      <Route path="/data" element={<Layout><Data /></Layout>} />
    </Routes>
  )
}
