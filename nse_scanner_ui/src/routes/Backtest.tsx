import type { ColumnDef } from "@tanstack/react-table"
import { useEffect, useState } from "react"
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend,
} from "recharts"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { DataTable } from "@/components/ui/data-table"
import { Input } from "@/components/ui/input"
import { PageTitle } from "@/components/ui/section"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { MarginalRow, SweepRow } from "@/api/backtest"
import {
  useBacktestConfig, useBacktestRun, useRunBacktest, useRunMarginal, useRunSweep,
} from "@/queries/backtest"

function num(n: number | null | undefined, digits = 2): string {
  return n === null || n === undefined ? "—" : n.toFixed(digits)
}
function pct(n: number | null | undefined, digits = 1): string {
  return n === null || n === undefined ? "—" : `${n.toFixed(digits)}%`
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

function metricsColumns<T extends { trades: number; win_rate: number; expectancy_r: number; profit_factor: number | null; max_dd_pct: number; total_return_pct: number }>(
  extra: ColumnDef<T, unknown>[]
): ColumnDef<T, unknown>[] {
  return [
    ...extra,
    { accessorKey: "trades", header: "Trades" },
    { accessorKey: "win_rate", header: "Win rate", cell: ({ getValue }) => pct(getValue() as number) },
    { accessorKey: "expectancy_r", header: "Expectancy (R)", cell: ({ getValue }) => num(getValue() as number) },
    {
      accessorKey: "profit_factor", header: "Profit factor",
      cell: ({ getValue }) => { const v = getValue() as number | null; return v === null ? "∞" : num(v) },
    },
    { accessorKey: "max_dd_pct", header: "Max DD", cell: ({ getValue }) => pct(getValue() as number) },
    { accessorKey: "total_return_pct", header: "Total return", cell: ({ getValue }) => pct(getValue() as number) },
  ]
}

function SingleRunPanel() {
  const config = useBacktestConfig()
  const runBacktest = useRunBacktest()
  const [preset, setPreset] = useState("")
  const [entry, setEntry] = useState("")
  const [exit, setExit] = useState("")
  const [sample, setSample] = useState<"in" | "out">("in")
  const [limitSymbols, setLimitSymbols] = useState<string>("")
  const [runId, setRunId] = useState<string | null>(null)
  const run = useBacktestRun(runId ?? undefined)

  useEffect(() => {
    if (config.data) {
      if (!preset && config.data.presets.length) setPreset(config.data.presets[0])
      if (!entry && config.data.entry_variants.length) setEntry(config.data.entry_variants[0])
      if (!exit && config.data.exit_variants.length) setExit(config.data.exit_variants[0])
    }
  }, [config.data, preset, entry, exit])

  const handleRun = () => {
    if (!preset || !entry || !exit) return
    runBacktest.mutate(
      {
        preset_name: preset, entry_variant: entry, exit_variant: exit, sample,
        limit_symbols: limitSymbols ? Number(limitSymbols) : null,
      },
      {
        onSuccess: (r) => { setRunId(r.run_id); toast.success(`Backtest run ${r.run_id} complete.`) },
        onError: (err) => toast.error(err instanceof Error ? err.message : "Backtest failed."),
      }
    )
  }

  const m = run.data?.metrics

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <Select value={preset} onValueChange={setPreset}>
          <SelectTrigger className="w-44"><SelectValue placeholder="Preset" /></SelectTrigger>
          <SelectContent>
            {(config.data?.presets ?? []).map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={entry} onValueChange={setEntry}>
          <SelectTrigger className="w-32"><SelectValue placeholder="Entry" /></SelectTrigger>
          <SelectContent>
            {(config.data?.entry_variants ?? []).map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={exit} onValueChange={setExit}>
          <SelectTrigger className="w-32"><SelectValue placeholder="Exit" /></SelectTrigger>
          <SelectContent>
            {(config.data?.exit_variants ?? []).map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={sample} onValueChange={(v) => setSample(v as "in" | "out")}>
          <SelectTrigger className="w-32"><SelectValue placeholder="Sample" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="in">In-sample</SelectItem>
            <SelectItem value="out">Out-of-sample</SelectItem>
          </SelectContent>
        </Select>
        <Input
          type="number" placeholder="Limit symbols (optional)" className="w-44"
          value={limitSymbols} onChange={(e) => setLimitSymbols(e.target.value)}
        />
        <Button onClick={handleRun} disabled={runBacktest.isPending || !preset}>
          {runBacktest.isPending ? "Running…" : "Run backtest"}
        </Button>
      </div>

      {m && (
        <>
          {config.data && m.trades < config.data.min_trades_for_conclusion && (
            <p className="text-warning text-xs">
              Fewer than {config.data.min_trades_for_conclusion} trades — treat this run as directional, not conclusive.
            </p>
          )}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile label="Trades" value={String(m.trades)} />
            <StatTile label="Win rate" value={pct(m.win_rate)} />
            <StatTile label="Expectancy (R)" value={num(m.expectancy_r)} />
            <StatTile label="Profit factor" value={m.profit_factor === null ? "∞" : num(m.profit_factor)} />
            <StatTile label="Max drawdown" value={pct(m.max_dd_pct)} />
            <StatTile label="Total return" value={pct(m.total_return_pct)} />
            <StatTile label="CAGR" value={pct(m.cagr_pct)} />
            <StatTile label="Median hold (days)" value={num(m.median_hold_days, 1)} />
          </div>

          <Card>
            <CardHeader><CardTitle>MFE / MAE by day held — where the curve flattens is your holding period</CardTitle></CardHeader>
            <CardContent>
              {run.data && run.data.curves.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={run.data.curves} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                    <XAxis dataKey="day_n" tick={{ fill: "var(--color-muted-foreground)", fontSize: 11 }} />
                    <YAxis tick={{ fill: "var(--color-muted-foreground)", fontSize: 11 }} />
                    <Tooltip
                      contentStyle={{ background: "var(--color-card)", border: "1px solid var(--color-border)", fontSize: 12 }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line type="monotone" dataKey="median_mfe" stroke="var(--color-primary)" strokeWidth={2} dot={false} name="Median MFE" />
                    <Line type="monotone" dataKey="p75_mfe" stroke="var(--color-accent)" strokeWidth={1.5} strokeDasharray="4 3" dot={false} name="75th pct MFE" />
                    <Line type="monotone" dataKey="median_mae" stroke="var(--color-destructive)" strokeWidth={2} dot={false} name="Median MAE" />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-muted-foreground text-sm">No forward curves for this run.</p>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

function SweepPanel() {
  const config = useBacktestConfig()
  const runSweep = useRunSweep()
  const [preset, setPreset] = useState("")
  const [sample, setSample] = useState<"in" | "out">("in")
  const [limitSymbols, setLimitSymbols] = useState<string>("")

  useEffect(() => {
    if (config.data && !preset && config.data.presets.length) setPreset(config.data.presets[0])
  }, [config.data, preset])

  const columns = metricsColumns<SweepRow>([
    { accessorKey: "entry", header: "Entry" },
    { accessorKey: "exit", header: "Exit" },
  ])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <Select value={preset} onValueChange={setPreset}>
          <SelectTrigger className="w-44"><SelectValue placeholder="Preset" /></SelectTrigger>
          <SelectContent>
            {(config.data?.presets ?? []).map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={sample} onValueChange={(v) => setSample(v as "in" | "out")}>
          <SelectTrigger className="w-32"><SelectValue placeholder="Sample" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="in">In-sample</SelectItem>
            <SelectItem value="out">Out-of-sample</SelectItem>
          </SelectContent>
        </Select>
        <Input
          type="number" placeholder="Limit symbols (optional)" className="w-44"
          value={limitSymbols} onChange={(e) => setLimitSymbols(e.target.value)}
        />
        <Button
          onClick={() => runSweep.mutate(
            { preset_name: preset, sample, limit_symbols: limitSymbols ? Number(limitSymbols) : null },
            { onError: (err) => toast.error(err instanceof Error ? err.message : "Sweep failed.") }
          )}
          disabled={runSweep.isPending || !preset}
        >
          {runSweep.isPending ? "Running the full entry × exit grid…" : "Run sweep (30 cells)"}
        </Button>
      </div>
      <p className="text-muted-foreground text-xs">
        Runs every entry × exit combination for this preset. Each cell is a full backtest — this can take a few minutes.
      </p>
      {runSweep.data && (
        <DataTable columns={columns} data={runSweep.data} emptyMessage="No results." />
      )}
    </div>
  )
}

function MarginalPanel() {
  const config = useBacktestConfig()
  const runMarginal = useRunMarginal()
  const [entry, setEntry] = useState("")
  const [exit, setExit] = useState("")
  const [limitSymbols, setLimitSymbols] = useState<string>("")

  useEffect(() => {
    if (config.data) {
      if (!entry && config.data.entry_variants.length) setEntry(config.data.entry_variants[0])
      if (!exit && config.data.exit_variants.length) setExit(config.data.exit_variants[0])
    }
  }, [config.data, entry, exit])

  const columns = metricsColumns<MarginalRow>([
    { accessorKey: "preset", header: "Preset (baseline first)" },
  ]).concat([
    {
      accessorKey: "delta_expectancy", header: "Δ Expectancy",
      cell: ({ getValue }) => num(getValue() as number | undefined),
    },
    {
      accessorKey: "trade_retention_pct", header: "Trade retention",
      cell: ({ getValue }) => pct(getValue() as number | undefined),
    },
    {
      accessorKey: "enough_trades", header: "Enough trades?",
      cell: ({ getValue }) => (getValue() ? "Yes" : "No"),
    },
  ])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <Select value={entry} onValueChange={setEntry}>
          <SelectTrigger className="w-32"><SelectValue placeholder="Entry" /></SelectTrigger>
          <SelectContent>
            {(config.data?.entry_variants ?? []).map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={exit} onValueChange={setExit}>
          <SelectTrigger className="w-32"><SelectValue placeholder="Exit" /></SelectTrigger>
          <SelectContent>
            {(config.data?.exit_variants ?? []).map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}
          </SelectContent>
        </Select>
        <Input
          type="number" placeholder="Limit symbols (optional)" className="w-44"
          value={limitSymbols} onChange={(e) => setLimitSymbols(e.target.value)}
        />
        <Button
          onClick={() => runMarginal.mutate(
            { entry_variant: entry, exit_variant: exit, limit_symbols: limitSymbols ? Number(limitSymbols) : null },
            { onError: (err) => toast.error(err instanceof Error ? err.message : "Marginal contribution failed.") }
          )}
          disabled={runMarginal.isPending || !entry || !exit}
        >
          {runMarginal.isPending ? "Running baseline + each filter…" : "Run marginal contribution"}
        </Button>
      </div>
      <p className="text-muted-foreground text-xs">
        Baseline first, then each SMA/volume filter with its delta vs baseline — a filter that lifts expectancy
        but guts trade count has found a coincidence, not an edge.
      </p>
      {runMarginal.data && (
        <DataTable columns={columns} data={runMarginal.data} emptyMessage="No results." />
      )}
    </div>
  )
}

export default function Backtest() {
  return (
    <div className="flex flex-col gap-4">
      <PageTitle text="Backtest" subtitle="Same pattern code as the live scanner, replayed bar by bar." />
      <Tabs defaultValue="single">
        <TabsList>
          <TabsTrigger value="single">Single run</TabsTrigger>
          <TabsTrigger value="sweep">Sweep</TabsTrigger>
          <TabsTrigger value="marginal">Marginal contribution</TabsTrigger>
        </TabsList>
        <TabsContent value="single"><SingleRunPanel /></TabsContent>
        <TabsContent value="sweep"><SweepPanel /></TabsContent>
        <TabsContent value="marginal"><MarginalPanel /></TabsContent>
      </Tabs>
    </div>
  )
}
