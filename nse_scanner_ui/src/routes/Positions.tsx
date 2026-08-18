import type { ColumnDef } from "@tanstack/react-table"
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { DataTable } from "@/components/ui/data-table"
import { PageTitle } from "@/components/ui/section"
import { StatusBadge } from "@/components/ui/status-badge"
import { SymbolLink } from "@/components/ui/symbol-link"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ClosedPositionsTable } from "@/components/trades/ClosedPositionsTable"
import { EntryDialog } from "@/components/trades/EntryDialog"
import { CloseDialog } from "@/components/trades/CloseDialog"
import { EditDialog } from "@/components/trades/EditDialog"
import type { PositionRow } from "@/api/holdings"
import { useDeleteTrade, useOpenPositions } from "@/queries/holdings"

function inr(n: number): string {
  return `₹${Math.round(n).toLocaleString("en-IN")}`
}
function pnlText(n: number | null): string {
  return n === null ? "—" : inr(n)
}
function pnlClass(n: number | null): string {
  if (n === null) return ""
  return n >= 0 ? "text-primary" : "text-destructive"
}

export default function Positions() {
  const { data: positions } = useOpenPositions()
  const deleteTrade = useDeleteTrade()
  const [entryOpen, setEntryOpen] = useState(false)
  const [closeTarget, setCloseTarget] = useState<{ id: number; symbol: string; remainingQty: number } | null>(null)
  const [editTarget, setEditTarget] = useState<PositionRow | null>(null)

  const removePosition = (p: PositionRow) => {
    if (!window.confirm(`Delete ${p.symbol}? This removes the trade entirely — use "close" instead if you actually exited.`)) return
    deleteTrade.mutate(p.trade_id, {
      onSuccess: () => toast.success(`Deleted ${p.symbol}.`),
      onError: (err) => toast.error(err instanceof Error ? err.message : "Could not delete position."),
    })
  }

  const totalPnl = (positions ?? []).reduce((sum, p) => sum + (p.pnl_rupees ?? 0), 0)
  const atRisk = (positions ?? []).filter((p) => p.status === "WATCH" || p.status === "REVIEW").length

  const columns: ColumnDef<PositionRow, unknown>[] = [
    {
      accessorKey: "symbol", header: "Symbol",
      cell: ({ row }) => <SymbolLink symbol={row.original.symbol} className="font-bold hover:text-primary hover:underline" />,
    },
    {
      id: "lifecycle_status", header: "Status",
      cell: ({ row }) => <StatusBadge status={row.original.lifecycle_status} />,
    },
    {
      accessorKey: "status", header: "Guidance",
      cell: ({ getValue }) => <StatusBadge status={String(getValue())} />,
    },
    {
      id: "entry", header: "Entry",
      cell: ({ row }) => {
        const p = row.original
        return <span className="font-mono-tabular text-xs">{p.entry_date} @ {p.entry_price.toFixed(2)} × {p.qty}</span>
      },
    },
    {
      accessorKey: "remaining_qty", header: "Remaining qty",
      cell: ({ getValue }) => <span className="font-mono-tabular">{String(getValue())}</span>,
    },
    {
      accessorKey: "pnl_rupees", header: "Unrealised P&L",
      cell: ({ getValue }) => {
        const v = getValue() as number | null
        return <span className={`font-mono-tabular ${pnlClass(v)}`}>{pnlText(v)}</span>
      },
    },
    {
      accessorKey: "r_multiple", header: "R",
      cell: ({ getValue }) => { const v = getValue() as number | null; return v === null ? "—" : `${v.toFixed(2)}R` },
    },
    {
      accessorKey: "partial_pnl_rupees", header: "Partial P&L booked",
      cell: ({ getValue }) => {
        const v = getValue() as number | null
        return <span className={`font-mono-tabular ${pnlClass(v)}`}>{pnlText(v)}</span>
      },
    },
    {
      accessorKey: "days_held", header: "Holding period",
      cell: ({ getValue }) => { const v = getValue() as number | null; return v === null ? "—" : `${v}d` },
    },
    {
      id: "mae_mfe", header: "MAE / MFE",
      cell: ({ row }) => {
        const p = row.original
        const mae = p.mae_pct !== null ? `${p.mae_pct.toFixed(1)}%` : "—"
        const mfe = p.mfe_pct !== null ? `${p.mfe_pct.toFixed(1)}%` : "—"
        return <span className="font-mono-tabular text-xs">{mae} / {mfe}</span>
      },
    },
    {
      id: "reasons", header: "Reasons",
      cell: ({ row }) => (
        <div className="flex flex-col gap-0">
          {row.original.reasons.map((reason, i) => (
            <span key={i} className="text-muted-foreground text-xs">· {reason}</span>
          ))}
        </div>
      ),
    },
    {
      id: "actions", header: "",
      cell: ({ row }) => {
        const p = row.original
        return (
          <div className="flex items-center justify-end gap-3">
            <button
              type="button" className="text-muted-foreground hover:text-foreground text-xs underline"
              onClick={() => setEditTarget(p)}
            >
              edit
            </button>
            <button
              type="button" className="text-muted-foreground hover:text-destructive text-xs underline"
              onClick={() => removePosition(p)}
            >
              delete
            </button>
            <Button
              size="sm" variant="outline" className="h-6 px-2 text-xs"
              onClick={() => setCloseTarget({ id: p.trade_id, symbol: p.symbol, remainingQty: p.remaining_qty })}
            >
              close
            </Button>
          </div>
        )
      },
    },
  ]

  return (
    <div className="flex flex-col gap-3">
      <PageTitle text="Positions" />

      <Button onClick={() => setEntryOpen(true)} className="w-fit">+ New position</Button>

      <Tabs defaultValue="open">
        <TabsList>
          <TabsTrigger value="open">Open</TabsTrigger>
          <TabsTrigger value="closed">Closed</TabsTrigger>
        </TabsList>

        <TabsContent value="open" className="flex flex-col gap-3">
          {positions && positions.length === 0 && <p className="text-sm">No open positions.</p>}

          {positions && positions.length > 0 && (
            <>
              <div className="flex gap-6 text-sm">
                <span className="font-semibold">Total open P&amp;L: {inr(totalPnl)}</span>
                <span className="font-semibold">At risk: {atRisk} of {positions.length}</span>
              </div>

              <DataTable columns={columns} data={positions} emptyMessage="No open positions." />
            </>
          )}
        </TabsContent>

        <TabsContent value="closed">
          <ClosedPositionsTable />
        </TabsContent>
      </Tabs>

      <EntryDialog open={entryOpen} onOpenChange={setEntryOpen} />
      <EditDialog open={!!editTarget} onOpenChange={(open) => !open && setEditTarget(null)} position={editTarget} />
      {closeTarget && (
        <CloseDialog
          open={!!closeTarget}
          onOpenChange={(open) => !open && setCloseTarget(null)}
          tradeId={closeTarget.id}
          symbol={closeTarget.symbol}
          remainingQty={closeTarget.remainingQty}
        />
      )}
    </div>
  )
}
