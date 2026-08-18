import type { ColumnDef } from "@tanstack/react-table"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { DataTable } from "@/components/ui/data-table"
import { Input } from "@/components/ui/input"
import { PageTitle } from "@/components/ui/section"
import { StatusBadge } from "@/components/ui/status-badge"
import { SymbolLink } from "@/components/ui/symbol-link"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { OpportunitySignal } from "@/api/today"
import { useOpenChart } from "@/store/chartDrawer"
import { useOpportunities, useOpportunityDates } from "@/queries/today"

const TIMEFRAME_LABEL: Record<string, string> = {
  "1d": "Short term (1D)",
  "1w": "Medium term (1W)",
  "1m": "Long term (1M)",
}

function num(v: number | null, digits = 2): string {
  return v === null ? "—" : v.toFixed(digits)
}
function pct(v: number | null, digits = 1): string {
  return v === null ? "—" : `${v.toFixed(digits)}%`
}

/** Header label with a native hover tooltip explaining the column — same
 * lightweight `title`-attribute convention already used elsewhere on this
 * page (the T-1..T-4 quick-select buttons) rather than a new component. */
function Th(label: string, tip: string) {
  return <span title={tip}>{label}</span>
}

const COLUMNS: ColumnDef<OpportunitySignal, unknown>[] = [
  {
    accessorKey: "symbol", header: "Symbol",
    cell: ({ getValue }) => <SymbolLink symbol={String(getValue())} />,
  },
  {
    accessorKey: "trigger_price", header: () => Th("Entry", "Close price that confirmed the pattern entry trigger."),
    cell: ({ getValue }) => num(getValue() as number),
  },
  {
    accessorKey: "l1_price", header: () => Th("L1", "First bottom of the W pattern (the earlier swing low)."),
    cell: ({ getValue }) => num(getValue() as number | null),
  },
  {
    accessorKey: "l2_price",
    header: () => Th("L2", "Second bottom of the W pattern — must be near or undercut L1."),
    cell: ({ getValue }) => num(getValue() as number | null),
  },
  {
    accessorKey: "l1_l2_distance_pct",
    header: () => Th("L1-L2 dist%", "% price distance between the first and second bottoms."),
    cell: ({ getValue }) => pct(getValue() as number | null),
  },
  {
    accessorKey: "neckline",
    header: () => Th("Neckline", "Peak between L1 and L2 — a close above it confirms the pattern."),
    cell: ({ getValue }) => num(getValue() as number | null),
  },
  {
    accessorKey: "depth_pct",
    header: () => Th("Depth%", "(Neckline − L2) / Neckline × 100 — how deep the pattern is."),
    cell: ({ getValue }) => num(getValue() as number | null, 1),
  },
  {
    accessorKey: "stop_suggested",
    header: () => Th("Stop", "Suggested stop-loss: L2 minus an ATR multiple."),
    cell: ({ getValue }) => num(getValue() as number | null),
  },
  {
    accessorKey: "target_suggested",
    header: () => Th("Target", "Measured-move target: Neckline + (Neckline − L2)."),
    cell: ({ getValue }) => num(getValue() as number | null),
  },
  {
    accessorKey: "bottom_at_sma",
    header: () => Th("Bottom @", "Which SMA (20/50/100/200) the second bottom formed within 1 ATR of, or \"none\"."),
    cell: ({ getValue }) => (getValue() as string | null) ?? "—",
  },
  {
    accessorKey: "sma_stack",
    header: () => Th("SMA stack", "MA alignment at the signal bar: stacked_up (10>20>50>100>200), stacked_down, mixed, or unknown."),
    cell: ({ getValue }) => (getValue() as string | null) ?? "—",
  },
  {
    accessorKey: "rs_rank_pct",
    header: () => Th("RS rank", "Percentile rank of this symbol's 55-day return vs the whole universe on that date."),
    cell: ({ getValue }) => { const v = getValue() as number | null; return v === null ? "—" : v.toFixed(0) },
  },
  {
    accessorKey: "quality_score",
    header: () => Th(
      "Score",
      "1D only. Counts backtest-validated favorable factors (0-3): low relative strength (a reversal setup with "
      + "room to run), a deep pattern (bigger target), above-average volatility. Hover a row's score for the "
      + "checklist and this codebase's own historical hit rate for that score -- an empirical base rate from your "
      + "backtest, never a prediction about this specific signal."
    ),
    cell: ({ row }) => {
      const s = row.original
      if (s.quality_score === null || s.quality_score_max === null) return "—"
      const checklist = (s.quality_checklist ?? [])
        .map((c) => `${c.passed ? "✓" : "✗"} ${c.label}`)
        .join("\n")
      const hitRate = s.historical_hit_rate_pct !== null
        ? `Historically ${s.historical_hit_rate_pct.toFixed(0)}% of similarly-scored signals hit target before stop`
          + ` (n=${s.historical_sample_size}${s.historical_thin ? ", thin sample" : ""}).`
        : "No historical basis yet."
      return (
        <span title={`${checklist}\n\n${hitRate}`}>
          <span className="font-mono-tabular">{s.quality_score}/{s.quality_score_max}</span>
          {s.historical_hit_rate_pct !== null && (
            <span className="text-muted-foreground text-xs"> ({s.historical_hit_rate_pct.toFixed(0)}%)</span>
          )}
        </span>
      )
    },
  },
  {
    accessorKey: "outcome_status",
    header: () => Th(
      "Status",
      "What actually happened since this signal, using stored price data -- SL hit, Target hit, Towards target, "
      + "or Open for trade. Only available once you browse a past date (T-1+); today's own signal has no forward "
      + "bars yet."
    ),
    cell: ({ row }) => {
      const v = row.original.outcome_status
      return v === null ? "—" : <StatusBadge status={v} />
    },
  },
  {
    accessorKey: "pct_since_signal",
    header: () => Th("% since signal", "Latest close vs the signal's entry price. Only available for past dates."),
    cell: ({ getValue }) => {
      const v = getValue() as number | null
      if (v === null) return "—"
      return <span className={v >= 0 ? "text-primary" : "text-destructive"}>{pct(v)}</span>
    },
  },
]

/**
 * T-1/T-2/T-3/T-4 mean "the previous SCANNED date", not a raw calendar-day
 * subtraction (T-1 on a Monday is Friday's scan, not Sunday) — so the quick-
 * select is driven by useOpportunityDates(), the distinct scan_dates that
 * actually have stored signals for the active tab's timeframe, newest first.
 * dates[0] is "latest" (the default view), dates[1..4] are T-1..T-4.
 */
function DateControls({
  timeframe, asOfDate, onSelect,
}: {
  timeframe: string
  asOfDate: string | undefined
  onSelect: (date: string | undefined) => void
}) {
  const { data } = useOpportunityDates(timeframe)
  const dates = data?.dates ?? []

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1">
        <label className="text-muted-foreground text-xs">Quick select</label>
        <div className="flex gap-1">
          <Button
            size="sm" variant={!asOfDate ? "default" : "outline"} className="h-7 px-2 text-xs"
            onClick={() => onSelect(undefined)}
          >
            Latest
          </Button>
          {[1, 2, 3, 4].map((n) => {
            const d = dates[n]
            return (
              <Button
                key={n} size="sm" variant={asOfDate === d ? "default" : "outline"}
                className="h-7 px-2 text-xs" disabled={!d}
                title={d ?? "No scan stored at this offset"}
                onClick={() => d && onSelect(d)}
              >
                T-{n}
              </Button>
            )
          })}
        </div>
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-muted-foreground text-xs">Or pick a date</label>
        <Input
          type="date" className="h-7 w-36 text-xs"
          value={asOfDate ?? ""} onChange={(e) => onSelect(e.target.value || undefined)}
        />
      </div>
      {asOfDate && (
        <p className="text-muted-foreground pb-1.5 text-xs">Showing {asOfDate}'s scan.</p>
      )}
    </div>
  )
}

/** The full per-timeframe fresh-signal table — Dashboard only previews it. */
export default function NewOpportunity() {
  const [activeTab, setActiveTab] = useState("1d")
  const [asOfDate, setAsOfDate] = useState<string | undefined>(undefined)
  const { data: opportunities } = useOpportunities(asOfDate)
  const openChart = useOpenChart()

  const handleSelectDate = (date: string | undefined) => {
    setAsOfDate(date)
  }

  if (!opportunities) return null

  return (
    <div className="flex flex-col gap-3">
      <PageTitle text="New Opportunity" subtitle="Fresh W-pattern signals from the last scan, by timeframe." />
      <DateControls timeframe={activeTab} asOfDate={asOfDate} onSelect={handleSelectDate} />
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          {opportunities.map((block) => (
            <TabsTrigger key={block.timeframe} value={block.timeframe} className="gap-2">
              {TIMEFRAME_LABEL[block.timeframe]}
              {block.built && block.new_signals.length > 0 && (
                <Badge className="h-4 px-1.5 text-[10px]">{block.new_signals.length}</Badge>
              )}
            </TabsTrigger>
          ))}
        </TabsList>
        {opportunities.map((block) => (
          <TabsContent key={block.timeframe} value={block.timeframe} className="flex flex-col gap-2">
            {!block.built ? (
              <p className="text-muted-foreground text-sm">
                Not built yet — run features.py for {block.timeframe}
              </p>
            ) : block.total_signals === 0 ? (
              <p className="text-sm">
                {asOfDate ? `No signals stored for ${asOfDate}.` : "No signals from the last scan."}
              </p>
            ) : (
              <>
                <p className="text-muted-foreground text-xs">
                  {block.total_signals} signals — {block.new_signals.length} new,{" "}
                  {block.already_tracked_count} already tracked
                </p>
                <DataTable
                  columns={COLUMNS}
                  data={block.new_signals}
                  emptyMessage="No new signals."
                  onRowClick={(row) => openChart(row.symbol)}
                />
              </>
            )}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
