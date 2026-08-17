import {
  BarChart3,
  CandlestickChart,
  ChevronLeft,
  ChevronRight,
  Database,
  Eye,
  FlaskConical,
  History,
  LayoutDashboard,
  Search,
  Sparkles,
  TrendingUp,
  Wallet,
} from "lucide-react"
import { NavLink } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useUiPrefs } from "@/store/uiPrefs"

const ITEMS = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/new-opportunity", label: "New Opportunity", icon: Sparkles },
  { to: "/scan", label: "Scans", icon: Search },
  { to: "/chart", label: "Charts", icon: CandlestickChart },
  { to: "/positions", label: "Positions", icon: Wallet },
  { to: "/watchlist", label: "Watchlist", icon: Eye },
  { to: "/performance", label: "Performance", icon: TrendingUp },
  { to: "/backtest", label: "Backtest", icon: FlaskConical },
  { to: "/recent-signals", label: "Recent Signals", icon: History },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/data", label: "Data", icon: Database },
]

export function Nav() {
  const { navCollapsed, toggleNav } = useUiPrefs()

  return (
    <nav
      className={cn(
        "flex h-full flex-col gap-0.5 border-r border-border bg-card p-2 transition-[width]",
        navCollapsed ? "w-16" : "w-44"
      )}
    >
      <Button variant="ghost" size="icon" className="mb-1 self-start" onClick={toggleNav}>
        {navCollapsed ? <ChevronRight className="size-4" /> : <ChevronLeft className="size-4" />}
      </Button>
      {ITEMS.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-accent",
              isActive && "bg-primary/15 text-primary"
            )
          }
        >
          <Icon className="size-4 shrink-0" />
          {!navCollapsed && <span>{label}</span>}
        </NavLink>
      ))}
    </nav>
  )
}
