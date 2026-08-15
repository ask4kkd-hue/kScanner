import type { ReactNode } from "react"
import { Route, Routes } from "react-router-dom"

import { ChartDrawer } from "@/components/chart/ChartDrawer"
import { Header } from "@/components/shell/Header"
import { HealthRail } from "@/components/shell/HealthRail"
import { Nav } from "@/components/shell/Nav"
import Backtest from "@/routes/Backtest"
import Chart from "@/routes/Chart"
import Data from "@/routes/Data"
import Holdings from "@/routes/Holdings"
import Performance from "@/routes/Performance"
import Scan from "@/routes/Scan"
import Today from "@/routes/Today"
import Watchlist from "@/routes/Watchlist"

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
      <Route path="/scan" element={<Layout><Scan /></Layout>} />
      <Route path="/chart" element={<Layout><Chart /></Layout>} />
      <Route path="/chart/:symbol" element={<Layout><Chart /></Layout>} />
      <Route path="/watchlist" element={<Layout><Watchlist /></Layout>} />
      <Route path="/holdings" element={<Layout><Holdings /></Layout>} />
      <Route path="/performance" element={<Layout><Performance /></Layout>} />
      <Route path="/backtest" element={<Layout><Backtest /></Layout>} />
      <Route path="/data" element={<Layout><Data /></Layout>} />
    </Routes>
  )
}
