import type { ColumnDef } from "@tanstack/react-table"
import type { ReactNode } from "react"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { DataTable } from "@/components/ui/data-table"
import { Input } from "@/components/ui/input"
import { PageTitle, Section } from "@/components/ui/section"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { SymbolLink } from "@/components/ui/symbol-link"
import type { RecentTradeRow } from "@/api/backtest"
import { useOpenChart } from "@/store/chartDrawer"
import { useBacktestConfig, useRunRecent } from "@/queries/backtest"

// Same explainer copy as Backtest.tsx's SingleRunPanel -- kept in sync by
// hand, same convention as this project's other UI-facing copies of
// backend rules.
const ENTRY_HELP: Record<string, string> = {
  E1: "Next bar after the W confirms — earliest entry, most trades, most failures.",
  E2: "Close above L1 (the \"reclaim\" rule) — shakeout confirmed. Default, best-tested.",
  E3: "Close above the neckline — latest entry, best win rate, worst reward:risk.",
  E4: "Close above SMA20 — momentum confirmation.",
  E5: "Close above an anchored VWAP from L1.",
}
const EXIT_HELP: Record<string, string> = {
  X1: "Fixed % target (config: target_pct).",
  X2: "R-multiple target — a fixed multiple of initial risk (config: target_r).",
  X3: "Measured move — neckline + (neckline − L2), the classic W-pattern target. Matches New Opportunity's suggested target.",
  X4: "Trail below a moving average (config: trail_sma) once price closes above entry.",
  X5: "ATR chandelier trail — trails a multiple of ATR below the running high.",
  X6: "Pure time stop — exits after a fixed number of bars, no price target at all.",
}

const EXIT_REASON_LABEL: Record<string, string> = {
  target_hit: "Target hit",
  target_hit_ambiguous: "Target hit (same-bar tie → assumed stop)",
  stop_hit: "Stop hit",
  stop_hit_ambiguous: "Stop hit (same-bar tie)",
  time_stop: "Time stop",
  end_of_data: "Still open",
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-muted-foreground text-xs">{label}</label>
      {children}
    </div>
  )
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

function inr(n: number): string {
  return `₹${Math.round(n).toLocaleString("en-IN")}`
}
function pct(n: number | null, digits = 1): string {
  return n === null ? "—" : `${n.toFixed(digits)}%`
}

const COLUMNS: ColumnDef<RecentTradeRow, unknown>[] = [
  {
    accessorKey: "symbol", header: "Symbol",
    cell: ({ getValue }) => <SymbolLink symbol={String(getValue())} />,
  },
  {
    id: "entry", header: "Entry",
    cell: ({ row }) => {
      const t = row.original
      return <span className="font-mono-tabular text-xs">{t.entry_date} @ {t.entry_price.toFixed(2)}</span>
    },
  },
  {
    id: "exit", header: "Exit",
    cell: ({ row }) => {
      const t = row.original
      return <span className="font-mono-tabular text-xs">{t.exit_date} @ {t.exit_price.toFixed(2)}</span>
    },
  },
  {
    accessorKey: "exit_reason", header: "Reason",
    cell: ({ getValue }) => {
      const v = String(getValue())
      return v === "end_of_data" ? <span className="text-warning">{EXIT_REASON_LABEL[v] ?? v}</span> : (EXIT_REASON_LABEL[v] ?? v)
    },
  },
  {
    accessorKey: "net_pnl", header: "P&L",
    cell: ({ getValue }) => {
      const v = getValue() as number
      return <span className={v >= 0 ? "text-primary" : "text-destructive"}>{inr(v)}</span>
    },
  },
  {
    accessorKey: "r_multiple", header: "R",
    cell: ({ getValue }) => { const v = getValue() as number | null; return v === null ? "—" : `${v.toFixed(2)}R` },
  },
  {
    accessorKey: "holding_days", header: "Holding days",
    cell: ({ getValue }) => `${getValue()}d`,
  },
]

export default function RecentSignals() {
  const config = useBacktestConfig()
  const runRecent = useRunRecent()
  const openChart = useOpenChart()

  const [preset, setPreset] = useState("")
  const [entry, setEntry] = useState("")
  const [exitVariant, setExitVariant] = useState("")
  const [daysBack, setDaysBack] = useState("20")
  const [limitSymbols, setLimitSymbols] = useState("")

  useEffect(() => {
    if (config.data) {
      if (!preset && config.data.presets.length) setPreset(config.data.presets[0])
      if (!entry && config.data.entry_variants.length) setEntry(config.data.entry_variants[0])
      if (!exitVariant && config.data.exit_variants.length) setExitVariant(config.data.exit_variants[0])
    }
  }, [config.data, preset, entry, exitVariant])

  const handleRun = () => {
    if (!preset || !entry || !exitVariant || !daysBack) return
    runRecent.mutate(
      {
        preset_name: preset, entry_variant: entry, exit_variant: exitVariant,
        days_back: Number(daysBack), limit_symbols: limitSymbols ? Number(limitSymbols) : null,
      },
      { onError: (err) => toast.error(err instanceof Error ? err.message : "Recent signals report failed.") }
    )
  }

  const report = runRecent.data
  const s = report?.summary

  return (
    <div className="flex flex-col gap-4">
      <PageTitle
        text="Recent Signals"
        subtitle="What actually happened to each W-pattern signal from the last N days — per symbol, not just an aggregate."
      />

      <Section title="How to read this">
        <div className="flex flex-col gap-2 text-sm">
          <p>
            Runs the same backtest engine as the Backtest screen, over a recent window instead of the multi-year
            in/out-of-sample range, and shows every individual trade it found — buy date/price, sell date/price,
            and whether target or stop was actually hit. A trade entered too recently to have resolved yet (within
            roughly the last two weeks) shows as <b>Still open</b> rather than being silently counted as a win or loss.
          </p>
          <p>
            This is a small, recent sample by nature — read it as a spot-check on what New Opportunity's signals
            actually did, not as a statistically meaningful conclusion (the Backtest screen's multi-year runs are
            for that).
          </p>
        </div>
      </Section>

      <div className="flex flex-wrap items-end gap-3">
        <Field label="Preset — which W-pattern conditions to require">
          <Select value={preset} onValueChange={setPreset}>
            <SelectTrigger className="w-44"><SelectValue placeholder="Preset" /></SelectTrigger>
            <SelectContent>
              {(config.data?.presets ?? []).map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
            </SelectContent>
          </Select>
        </Field>
        <Field label="Entry rule — when to buy after the W confirms">
          <Select value={entry} onValueChange={setEntry}>
            <SelectTrigger className="w-32"><SelectValue placeholder="Entry" /></SelectTrigger>
            <SelectContent>
              {(config.data?.entry_variants ?? []).map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
        </Field>
        <Field label="Exit rule — when to sell">
          <Select value={exitVariant} onValueChange={setExitVariant}>
            <SelectTrigger className="w-32"><SelectValue placeholder="Exit" /></SelectTrigger>
            <SelectContent>
              {(config.data?.exit_variants ?? []).map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
        </Field>
        <Field label="Days back — how far back to look for signals">
          <Input
            type="number" min={1} placeholder="e.g. 20" className="w-32"
            value={daysBack} onChange={(e) => setDaysBack(e.target.value)}
          />
        </Field>
        <Field label="Limit symbols — optional, for a fast trial run">
          <Input
            type="number" placeholder="e.g. 200" className="w-44"
            value={limitSymbols} onChange={(e) => setLimitSymbols(e.target.value)}
          />
        </Field>
        <Button onClick={handleRun} disabled={runRecent.isPending || !preset}>
          {runRecent.isPending ? "Running…" : "Run"}
        </Button>
      </div>

      {(entry || exitVariant) && (
        <p className="text-muted-foreground text-xs">
          {entry && <><b>{entry}</b>: {ENTRY_HELP[entry]}</>}
          {entry && exitVariant && "  ·  "}
          {exitVariant && <><b>{exitVariant}</b>: {EXIT_HELP[exitVariant]}</>}
        </p>
      )}

      {s && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile label="Resolved trades" value={String(s.resolved_trades)} />
            <StatTile label="Still open" value={String(s.still_open)} />
            <StatTile label="Win rate" value={pct(s.win_rate)} />
            <StatTile label="Target hits" value={String(s.target_hits)} />
            <StatTile label="Stop hits" value={String(s.stop_hits)} />
            <StatTile label="Time-stop exits" value={String(s.time_stop_exits)} />
            <StatTile label="Realized P&L" value={inr(s.realized_pnl)} />
            <StatTile label="Unrealized P&L (still open)" value={inr(s.unrealized_pnl)} />
          </div>

          {report && report.trades.length > 0 ? (
            <DataTable
              columns={COLUMNS}
              data={report.trades}
              emptyMessage="No signals in this window."
              onRowClick={(row) => openChart(row.symbol)}
            />
          ) : (
            <p className="text-sm">No signals triggered in the last {report?.days_back} days for this preset.</p>
          )}
        </>
      )}
    </div>
  )
}
