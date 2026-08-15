import { Link } from "react-router-dom"

import { EquitySparkline } from "@/components/ui/equity-chart"
import { PageTitle, Section } from "@/components/ui/section"
import { StatusBadge } from "@/components/ui/status-badge"
import { SymbolLink } from "@/components/ui/symbol-link"
import { useToday } from "@/queries/today"

const TIMEFRAME_LABEL: Record<string, string> = {
  "1d": "Short term — 1D signals",
  "1w": "Medium term — 1W signals",
  "1m": "Long term — 1M signals",
}

function inr(n: number): string {
  return `₹${Math.round(n).toLocaleString("en-IN")}`
}

export default function Today() {
  const { data } = useToday()
  if (!data) return null

  const { status, positions, total_open_pnl, at_risk_count, opportunities, pnl, equity_curve, watchlist_near_trigger } = data

  return (
    <div className="flex flex-col gap-3">
      <PageTitle text="Today" />

      {/* 1. STATUS */}
      <Section title="Status">
        {status.stale ? (
          <p className="text-destructive text-sm font-semibold">
            Run refresh — {status.sessions_behind} session{status.sessions_behind !== 1 ? "s" : ""} behind
          </p>
        ) : (
          <p className="text-primary text-sm font-semibold">Data current</p>
        )}
        <div className="text-muted-foreground mt-1 flex gap-6 text-xs">
          <span>latest bar {status.latest_bar ?? "—"}</span>
          <span>last trading day {status.latest_cal ?? "—"}</span>
          <span>validation fails (7d) {status.validation_fails_7d}</span>
          <span>market regime {status.regime}</span>
        </div>
      </Section>

      {/* 2. YOUR POSITIONS */}
      <Section title="Your Positions">
        {positions.length === 0 ? (
          <p className="text-sm">No open positions.</p>
        ) : (
          <>
            <div className="flex flex-col gap-2">
              {positions.map((p) => (
                <div key={p.trade_id} className="rounded-md border border-border p-2">
                  <div className="flex w-full items-center gap-4">
                    <SymbolLink symbol={p.symbol} className="w-28 font-semibold hover:text-primary hover:underline" />
                    <span className="text-muted-foreground w-16 text-xs">day {p.days_held ?? "—"}</span>
                    <span className="w-16 text-xs">{p.pnl_pct !== null ? `${p.pnl_pct >= 0 ? "+" : ""}${p.pnl_pct.toFixed(1)}%` : "—"}</span>
                    <span className="w-16 text-xs">{p.r_multiple !== null ? `${p.r_multiple >= 0 ? "+" : ""}${p.r_multiple.toFixed(2)}R` : "—"}</span>
                    <StatusBadge status={p.status} />
                  </div>
                  {p.reasons.map((reason, i) => (
                    <p key={i} className="text-muted-foreground mt-1 text-xs">· {reason}</p>
                  ))}
                </div>
              ))}
            </div>
            <div className="mt-2 flex gap-6 text-sm">
              <span className="font-semibold">Total open P&amp;L: {inr(total_open_pnl)}</span>
              <span className="font-semibold">At risk: {at_risk_count} of {positions.length}</span>
            </div>
          </>
        )}
      </Section>

      {/* 3. NEW OPPORTUNITIES */}
      <Section title="New Opportunities">
        <div className="flex flex-col gap-3">
          {opportunities.map((block) => (
            <Section key={block.timeframe} title={TIMEFRAME_LABEL[block.timeframe]}>
              {!block.built ? (
                <p className="text-muted-foreground text-sm">
                  Not built yet — run features.py for {block.timeframe}
                </p>
              ) : block.total_signals === 0 ? (
                <p className="text-sm">No signals from the last scan.</p>
              ) : (
                <>
                  <p className="text-muted-foreground text-xs">
                    {block.total_signals} signals — {block.new_signals.length} new,{" "}
                    {block.already_tracked_count} already tracked
                  </p>
                  <div className="mt-1 flex flex-col gap-1">
                    {block.new_signals.map((s) => (
                      <div key={s.symbol} className="flex gap-4 text-sm">
                        <SymbolLink symbol={s.symbol} className="w-28 font-semibold hover:text-primary hover:underline" />
                        <span className="w-20">{s.trigger_price.toFixed(2)}</span>
                        <span className="w-16">
                          {s.rs_rank_pct !== null ? `RS ${s.rs_rank_pct.toFixed(0)}` : "RS —"}
                        </span>
                      </div>
                    ))}
                  </div>
                  <Link to="/scan" className="text-primary mt-1 inline-block text-xs hover:underline">
                    See all in Scan
                  </Link>
                </>
              )}
            </Section>
          ))}
        </div>
      </Section>

      {/* 4. P&L */}
      <Section title="P&L" collapsed>
        <div className="flex gap-6 text-sm">
          <span>Today: {inr(pnl.today)}</span>
          <span>This week: {inr(pnl.this_week)}</span>
          <span>This month: {inr(pnl.this_month)}</span>
          <span>All time: {inr(pnl.all_time)}</span>
          <span>Unrealised: {inr(pnl.unrealised)}</span>
        </div>
        <EquitySparkline data={equity_curve} />
      </Section>

      {/* 5. WATCHLIST NEAR TRIGGER */}
      <Section title={`Watchlist Near Trigger (${watchlist_near_trigger.length})`} collapsed={watchlist_near_trigger.length === 0}>
        {watchlist_near_trigger.length === 0 ? (
          <p className="text-sm">Nothing near trigger.</p>
        ) : (
          <div className="flex flex-col gap-1">
            {watchlist_near_trigger.map((r) => (
              <div key={r.symbol} className="flex gap-4 text-sm">
                <SymbolLink symbol={r.symbol} className="w-28 font-semibold hover:text-primary hover:underline" />
                <span>close {r.close?.toFixed(2) ?? "—"}</span>
                {r.target_price != null && <span>target {r.target_price.toFixed(2)}</span>}
                {r.neckline != null && <span>neckline {r.neckline.toFixed(2)}</span>}
              </div>
            ))}
          </div>
        )}
      </Section>
    </div>
  )
}
