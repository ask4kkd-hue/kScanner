import type { ColumnDef } from "@tanstack/react-table"
import { useEffect, useState } from "react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { DataTable } from "@/components/ui/data-table"
import { EquityDrawdownChart } from "@/components/ui/equity-drawdown-chart"
import { PageTitle } from "@/components/ui/section"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { AttributionRow } from "@/api/performance"
import {
  useAdherence, useAttribution, useCompare, useEquityCurve, usePresetsTraded,
  useSnapshot, useSnapshotMetrics, useSummary, useTags,
} from "@/queries/performance"

function pct(n: number | undefined | null, digits = 1): string {
  return n === null || n === undefined ? "—" : `${n.toFixed(digits)}%`
}
function num(n: number | undefined | null, digits = 2): string {
  return n === null || n === undefined ? "—" : n.toFixed(digits)
}
function inr(n: number | undefined | null): string {
  return n === null || n === undefined ? "—" : `₹${Math.round(n).toLocaleString("en-IN")}`
}

function StatTile({ label, value, thin }: { label: string; value: string; thin?: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-muted-foreground font-normal">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="font-mono-tabular text-xl font-bold">{value}</div>
        {thin && <p className="text-warning mt-1 text-xs">Thin sample</p>}
      </CardContent>
    </Card>
  )
}

function attributionColumns(dimKey: string, dimLabel: string): ColumnDef<AttributionRow, unknown>[] {
  return [
    {
      accessorKey: dimKey, header: dimLabel,
      cell: ({ row }) => (
        <span>
          {String(row.original[dimKey] ?? "—")}
          {row.original.thin && <span className="text-warning ml-1 text-xs">(thin)</span>}
        </span>
      ),
    },
    { accessorKey: "trades", header: "Trades" },
    { accessorKey: "win_rate", header: "Win rate", cell: ({ getValue }) => pct(getValue() as number) },
    { accessorKey: "avg_r", header: "Avg R", cell: ({ getValue }) => num(getValue() as number) },
    { accessorKey: "net_pnl", header: "Net P&L", cell: ({ getValue }) => inr(getValue() as number) },
  ]
}

export default function Performance() {
  const summary = useSummary()
  const equity = useEquityCurve()
  const attribution = useAttribution()
  const adherence = useAdherence()
  const tags = useTags()
  const snapshotMetrics = useSnapshotMetrics()
  const [metric, setMetric] = useState<string>("")
  const snapshot = useSnapshot(metric || undefined)
  const presetsTraded = usePresetsTraded()
  const [comparePreset, setComparePreset] = useState<string>("")
  const compare = useCompare(comparePreset || undefined)

  useEffect(() => {
    if (!metric && snapshotMetrics.data?.length) setMetric(snapshotMetrics.data[0])
  }, [snapshotMetrics.data, metric])
  useEffect(() => {
    if (!comparePreset && presetsTraded.data?.length) setComparePreset(presetsTraded.data[0])
  }, [presetsTraded.data, comparePreset])

  const s = summary.data

  return (
    <div className="flex flex-col gap-4">
      <PageTitle text="Performance" subtitle="Live trade journal — what actually happened." />

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="attribution">Attribution</TabsTrigger>
          <TabsTrigger value="adherence">Adherence</TabsTrigger>
          <TabsTrigger value="tags">Tags</TabsTrigger>
          <TabsTrigger value="snapshot">Snapshot</TabsTrigger>
          <TabsTrigger value="compare">Vs backtest</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="flex flex-col gap-4">
          {s && s.trades === 0 && (
            <p className="text-sm">No closed trades yet — this fills in as you close positions.</p>
          )}
          {s && s.trades > 0 && (
            <>
              {s.thin && (
                <p className="text-warning text-xs">
                  Fewer than {s.min_trades_for_conclusion} closed trades — treat these numbers as directional, not conclusive.
                </p>
              )}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <StatTile label="Closed trades" value={String(s.trades)} />
                <StatTile label="Win rate" value={pct(s.win_rate)} />
                <StatTile label="Expectancy (R)" value={num(s.expectancy_r)} />
                <StatTile label="Profit factor" value={s.profit_factor === null ? "∞" : num(s.profit_factor)} />
                <StatTile label="Avg win (R)" value={num(s.avg_win_r)} />
                <StatTile label="Avg loss (R)" value={num(s.avg_loss_r)} />
                <StatTile label="Net P&L" value={inr(s.net_pnl)} />
                <StatTile label="Median hold (days)" value={num(s.median_hold_days, 1)} />
              </div>
            </>
          )}
          <Card>
            <CardHeader><CardTitle>Equity curve &amp; drawdown</CardTitle></CardHeader>
            <CardContent>
              <EquityDrawdownChart data={equity.data ?? []} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="attribution" className="flex flex-col gap-4">
          {attribution.data && (
            <>
              <p className="text-muted-foreground text-xs">{attribution.data.bottom_at_sma_note}</p>
              <Card>
                <CardHeader><CardTitle>By preset</CardTitle></CardHeader>
                <CardContent>
                  <DataTable columns={attributionColumns("preset_name", "Preset")} data={attribution.data.by_preset} />
                </CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle>By timeframe</CardTitle></CardHeader>
                <CardContent>
                  <DataTable columns={attributionColumns("tf_label", "Timeframe")} data={attribution.data.by_timeframe} />
                </CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle>By sector</CardTitle></CardHeader>
                <CardContent>
                  <DataTable columns={attributionColumns("sector", "Sector")} data={attribution.data.by_sector} />
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>

        <TabsContent value="adherence">
          <DataTable
            emptyMessage="No closed trades yet."
            columns={[
              { accessorKey: "followed_plan", header: "Followed plan", cell: ({ getValue }) => (getValue() ? "Yes" : "No") },
              { accessorKey: "trades", header: "Trades" },
              { accessorKey: "avg_r", header: "Avg R", cell: ({ getValue }) => num(getValue() as number) },
              { accessorKey: "win_rate", header: "Win rate", cell: ({ getValue }) => pct(getValue() as number) },
              { accessorKey: "net_pnl", header: "Net P&L", cell: ({ getValue }) => inr(getValue() as number) },
            ]}
            data={adherence.data ?? []}
          />
        </TabsContent>

        <TabsContent value="tags">
          <DataTable
            emptyMessage="No tagged trades yet."
            columns={[
              { accessorKey: "tag", header: "Tag" },
              { accessorKey: "trades", header: "Trades" },
              { accessorKey: "avg_r", header: "Avg R", cell: ({ getValue }) => num(getValue() as number) },
              { accessorKey: "net_pnl", header: "Net P&L", cell: ({ getValue }) => inr(getValue() as number) },
            ]}
            data={tags.data ?? []}
          />
        </TabsContent>

        <TabsContent value="snapshot" className="flex flex-col gap-3">
          <Select value={metric} onValueChange={setMetric}>
            <SelectTrigger className="w-56"><SelectValue placeholder="Metric" /></SelectTrigger>
            <SelectContent>
              {(snapshotMetrics.data ?? []).map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
            </SelectContent>
          </Select>
          <DataTable
            emptyMessage="No closed trades yet."
            columns={[
              { accessorKey: "bucket", header: "Bucket" },
              { accessorKey: "trades", header: "Trades" },
              { accessorKey: "avg_r", header: "Avg R", cell: ({ getValue }) => num(getValue() as number) },
              { accessorKey: "win_rate", header: "Win rate", cell: ({ getValue }) => pct(getValue() as number) },
            ]}
            data={snapshot.data ?? []}
          />
        </TabsContent>

        <TabsContent value="compare" className="flex flex-col gap-3">
          {presetsTraded.data && presetsTraded.data.length === 0 && (
            <p className="text-sm">No live trades tagged with a preset yet.</p>
          )}
          {presetsTraded.data && presetsTraded.data.length > 0 && (
            <>
              <Select value={comparePreset} onValueChange={setComparePreset}>
                <SelectTrigger className="w-56"><SelectValue placeholder="Preset" /></SelectTrigger>
                <SelectContent>
                  {presetsTraded.data.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                </SelectContent>
              </Select>
              <DataTable
                emptyMessage="No comparison data."
                columns={[
                  { accessorKey: "source", header: "Source" },
                  { accessorKey: "trades", header: "Trades" },
                  { accessorKey: "win_rate", header: "Win rate", cell: ({ getValue }) => pct(getValue() as number) },
                  { accessorKey: "avg_r", header: "Avg R", cell: ({ getValue }) => num(getValue() as number) },
                  { accessorKey: "median_hold", header: "Median hold", cell: ({ getValue }) => num(getValue() as number, 1) },
                  { accessorKey: "median_mae", header: "Median MAE", cell: ({ getValue }) => pct(getValue() as number) },
                  { accessorKey: "median_mfe", header: "Median MFE", cell: ({ getValue }) => pct(getValue() as number) },
                ]}
                data={compare.data ?? []}
              />
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
