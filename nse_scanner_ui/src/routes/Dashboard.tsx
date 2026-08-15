import { Link } from "react-router-dom"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { EquityDrawdownChart } from "@/components/ui/equity-drawdown-chart"
import { PageTitle } from "@/components/ui/section"
import { StatusBadge } from "@/components/ui/status-badge"
import { SymbolLink } from "@/components/ui/symbol-link"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useEquityCurve, useSummary } from "@/queries/performance"
import { useToday } from "@/queries/today"

const TIMEFRAME_LABEL: Record<string, string> = {
  "1d": "Short term (1D)",
  "1w": "Medium term (1W)",
  "1m": "Long term (1M)",
}

function inr(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : `₹${Math.round(n).toLocaleString("en-IN")}`
}
function pct(n: number | null | undefined, digits = 1): string {
  return n === null || n === undefined ? "—" : `${n.toFixed(digits)}%`
}
function num(n: number | null | undefined, digits = 2): string {
  return n === null || n === undefined ? "—" : n.toFixed(digits)
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-muted-foreground font-normal">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="font-mono-tabular text-xl font-bold">{value}</div>
      </CardContent>
    </Card>
  )
}

/**
 * Analytics-first Dashboard: a big equity/P&L chart up top, headline stats
 * below it, and Positions/New Opportunities/Watchlist condensed into tabs
 * underneath — each with a link to its own full screen. Distinct from the
 * New Opportunity screen, which shows the full per-timeframe signal list
 * this only previews.
 */
export default function Dashboard() {
  const { data } = useToday()
  const summary = useSummary()
  const equity = useEquityCurve()
  if (!data) return null

  const { status, positions, total_open_pnl, at_risk_count, opportunities, watchlist_near_trigger } = data
  const s = summary.data

  return (
    <div className="flex flex-col gap-4">
      <PageTitle text="Dashboard" subtitle={`Market regime: ${status.regime}`} />

      <Card>
        <CardHeader><CardTitle>Equity curve &amp; drawdown</CardTitle></CardHeader>
        <CardContent>
          <EquityDrawdownChart data={equity.data ?? []} />
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Win rate" value={s ? pct(s.win_rate) : "—"} />
        <StatTile label="Expectancy (R)" value={s ? num(s.expectancy_r) : "—"} />
        <StatTile label="Open P&L" value={inr(total_open_pnl)} />
        <StatTile label="At risk" value={`${at_risk_count} of ${positions.length}`} />
      </div>

      <Tabs defaultValue="positions">
        <TabsList>
          <TabsTrigger value="positions">Positions ({positions.length})</TabsTrigger>
          <TabsTrigger value="opportunities">New Opportunities</TabsTrigger>
          <TabsTrigger value="watchlist">Watchlist near trigger ({watchlist_near_trigger.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="positions" className="flex flex-col gap-2">
          {positions.length === 0 ? (
            <p className="text-sm">No open positions.</p>
          ) : (
            positions.map((p) => (
              <div key={p.trade_id} className="flex items-center gap-4 rounded-md border border-border p-2 text-sm">
                <SymbolLink symbol={p.symbol} className="w-28 font-semibold hover:text-primary hover:underline" />
                <span className="text-muted-foreground w-16 text-xs">day {p.days_held ?? "—"}</span>
                <span className="w-16">
                  {p.r_multiple !== null ? `${p.r_multiple >= 0 ? "+" : ""}${p.r_multiple.toFixed(2)}R` : "—"}
                </span>
                <StatusBadge status={p.status} />
              </div>
            ))
          )}
          <Link to="/positions" className="text-primary text-xs hover:underline">See all Positions</Link>
        </TabsContent>

        <TabsContent value="opportunities" className="flex flex-col gap-3">
          {opportunities.map((block) => (
            <div key={block.timeframe}>
              <p className="text-muted-foreground text-xs font-semibold">{TIMEFRAME_LABEL[block.timeframe]}</p>
              {!block.built ? (
                <p className="text-sm">Not built yet.</p>
              ) : block.new_signals.length === 0 ? (
                <p className="text-sm">No new signals.</p>
              ) : (
                <div className="flex flex-col gap-1">
                  {block.new_signals.slice(0, 3).map((sig) => (
                    <div key={sig.symbol} className="flex gap-4 text-sm">
                      <SymbolLink symbol={sig.symbol} className="w-28 font-semibold hover:text-primary hover:underline" />
                      <span className="w-20">{sig.trigger_price.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
          <Link to="/new-opportunity" className="text-primary text-xs hover:underline">See full New Opportunity list</Link>
        </TabsContent>

        <TabsContent value="watchlist" className="flex flex-col gap-2">
          {watchlist_near_trigger.length === 0 ? (
            <p className="text-sm">Nothing near trigger.</p>
          ) : (
            watchlist_near_trigger.map((r) => (
              <div key={r.symbol} className="flex gap-4 text-sm">
                <SymbolLink symbol={r.symbol} className="w-28 font-semibold hover:text-primary hover:underline" />
                <span>close {r.close?.toFixed(2) ?? "—"}</span>
                {r.target_price != null && <span>target {r.target_price.toFixed(2)}</span>}
              </div>
            ))
          )}
          <Link to="/watchlist" className="text-primary text-xs hover:underline">See full Watchlist</Link>
        </TabsContent>
      </Tabs>
    </div>
  )
}
