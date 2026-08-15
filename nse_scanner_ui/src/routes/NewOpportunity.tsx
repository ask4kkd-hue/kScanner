import type { ColumnDef } from "@tanstack/react-table"

import { Badge } from "@/components/ui/badge"
import { DataTable } from "@/components/ui/data-table"
import { PageTitle } from "@/components/ui/section"
import { SymbolLink } from "@/components/ui/symbol-link"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { OpportunitySignal } from "@/api/today"
import { useOpenChart } from "@/store/chartDrawer"
import { useToday } from "@/queries/today"

const TIMEFRAME_LABEL: Record<string, string> = {
  "1d": "Short term (1D)",
  "1w": "Medium term (1W)",
  "1m": "Long term (1M)",
}

function num(v: number | null, digits = 2): string {
  return v === null ? "—" : v.toFixed(digits)
}

const COLUMNS: ColumnDef<OpportunitySignal, unknown>[] = [
  {
    accessorKey: "symbol", header: "Symbol",
    cell: ({ getValue }) => <SymbolLink symbol={String(getValue())} />,
  },
  { accessorKey: "trigger_price", header: "Entry", cell: ({ getValue }) => num(getValue() as number) },
  { accessorKey: "l1_price", header: "L1", cell: ({ getValue }) => num(getValue() as number | null) },
  { accessorKey: "l2_price", header: "L2", cell: ({ getValue }) => num(getValue() as number | null) },
  {
    accessorKey: "l1_l2_distance", header: "L1-L2 dist",
    cell: ({ getValue }) => num(getValue() as number | null),
  },
  { accessorKey: "neckline", header: "Neckline", cell: ({ getValue }) => num(getValue() as number | null) },
  { accessorKey: "depth_pct", header: "Depth%", cell: ({ getValue }) => num(getValue() as number | null, 1) },
  { accessorKey: "stop_suggested", header: "Stop", cell: ({ getValue }) => num(getValue() as number | null) },
  { accessorKey: "target_suggested", header: "Target", cell: ({ getValue }) => num(getValue() as number | null) },
  { accessorKey: "bottom_at_sma", header: "Bottom @", cell: ({ getValue }) => (getValue() as string | null) ?? "—" },
  { accessorKey: "sma_stack", header: "SMA stack", cell: ({ getValue }) => (getValue() as string | null) ?? "—" },
  {
    accessorKey: "rs_rank_pct", header: "RS rank",
    cell: ({ getValue }) => { const v = getValue() as number | null; return v === null ? "—" : v.toFixed(0) },
  },
]

/** The full per-timeframe fresh-signal table — Dashboard only previews it. */
export default function NewOpportunity() {
  const { data } = useToday()
  const openChart = useOpenChart()
  if (!data) return null
  const { opportunities } = data

  return (
    <div className="flex flex-col gap-3">
      <PageTitle text="New Opportunity" subtitle="Fresh W-pattern signals from the last scan, by timeframe." />
      <Tabs defaultValue={opportunities[0]?.timeframe ?? "1d"}>
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
              <p className="text-sm">No signals from the last scan.</p>
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
