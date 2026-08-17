import type { ColumnDef } from "@tanstack/react-table"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { DataTable } from "@/components/ui/data-table"
import { Input } from "@/components/ui/input"
import { PageTitle } from "@/components/ui/section"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { SymbolLink } from "@/components/ui/symbol-link"
import type { AnalyticsRow } from "@/api/analytics"
import { useOpenChart } from "@/store/chartDrawer"
import { useAnalyticsConfig, useRunAnalysis } from "@/queries/analytics"

function num(n: number): string {
  return n.toFixed(2)
}
function pct(n: number): string {
  return `${n.toFixed(1)}%`
}
function dateOnly(iso: string): string {
  return iso.slice(0, 10)
}

const COLUMNS: ColumnDef<AnalyticsRow, unknown>[] = [
  {
    accessorKey: "symbol", header: "Symbol",
    cell: ({ getValue }) => <SymbolLink symbol={String(getValue())} />,
  },
  {
    accessorKey: "sector", header: "Sector",
    cell: ({ getValue }) => (getValue() as string | null) ?? "—",
  },
  {
    id: "ath", header: "All-time high",
    cell: ({ row }) => (
      <span className="font-mono-tabular text-xs">
        {num(row.original.ath)} ({dateOnly(row.original.ath_date)})
      </span>
    ),
  },
  {
    id: "last", header: "Last close",
    cell: ({ row }) => (
      <span className="font-mono-tabular text-xs">
        {num(row.original.last_close)} ({dateOnly(row.original.last_date)})
      </span>
    ),
  },
  {
    accessorKey: "pct_down_from_ath", header: "Down from ATH",
    cell: ({ getValue }) => (
      <span className="text-destructive font-mono-tabular">{pct(getValue() as number)}</span>
    ),
  },
]

export default function Analytics() {
  const config = useAnalyticsConfig()
  const runAnalysis = useRunAnalysis()
  const openChart = useOpenChart()

  const [analysisType, setAnalysisType] = useState("")
  const [minPct, setMinPct] = useState("")
  const [maxPct, setMaxPct] = useState("")

  const activeType = config.data?.types.find((t) => t.id === analysisType)

  useEffect(() => {
    if (config.data && !analysisType && config.data.types.length) {
      const first = config.data.types[0]
      setAnalysisType(first.id)
      setMinPct(String(first.min_default))
      setMaxPct(String(first.max_default))
    }
  }, [config.data, analysisType])

  const handleRun = () => {
    if (!analysisType || !minPct || !maxPct) return
    if (Number(minPct) > Number(maxPct)) {
      toast.warning("Min must be less than or equal to max.")
      return
    }
    runAnalysis.mutate(
      { analysis_type: analysisType, min_pct: Number(minPct), max_pct: Number(maxPct) },
      { onError: (err) => toast.error(err instanceof Error ? err.message : "Analysis failed.") }
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <PageTitle text="Analytics" subtitle="Ad-hoc screens over the full price history — not filtered by liquidity, unlike Scan." />

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-muted-foreground text-xs">Analysis type</label>
          <Select value={analysisType} onValueChange={setAnalysisType}>
            <SelectTrigger className="w-64"><SelectValue placeholder="Analysis type" /></SelectTrigger>
            <SelectContent>
              {(config.data?.types ?? []).map((t) => (
                <SelectItem key={t.id} value={t.id}>{t.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {activeType && (
          <>
            <div className="flex flex-col gap-1">
              <label className="text-muted-foreground text-xs">Min {activeType.param_label}</label>
              <Input
                type="number" min={0} max={100} step={0.5} className="w-32"
                value={minPct} onChange={(e) => setMinPct(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-muted-foreground text-xs">Max {activeType.param_label}</label>
              <Input
                type="number" min={0} max={100} step={0.5} className="w-32"
                value={maxPct} onChange={(e) => setMaxPct(e.target.value)}
              />
            </div>
          </>
        )}
        <Button onClick={handleRun} disabled={runAnalysis.isPending || !analysisType}>
          {runAnalysis.isPending ? "Running…" : "Run"}
        </Button>
      </div>

      {runAnalysis.data && (
        <>
          <p className="text-muted-foreground text-xs">{runAnalysis.data.length} symbols found.</p>
          <DataTable
            columns={COLUMNS}
            data={runAnalysis.data}
            emptyMessage="No symbols matched."
            onRowClick={(row) => openChart(row.symbol)}
          />
        </>
      )}
    </div>
  )
}
