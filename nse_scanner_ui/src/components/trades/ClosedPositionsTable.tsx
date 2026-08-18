import type { ColumnDef } from "@tanstack/react-table"

import { DataTable } from "@/components/ui/data-table"
import { SymbolLink } from "@/components/ui/symbol-link"
import type { ClosedPositionRow } from "@/api/holdings"
import { useClosedPositions } from "@/queries/holdings"

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

const COLUMNS: ColumnDef<ClosedPositionRow, unknown>[] = [
  {
    accessorKey: "symbol", header: "Symbol",
    cell: ({ row }) => <SymbolLink symbol={row.original.symbol} className="font-bold hover:text-primary hover:underline" />,
  },
  {
    id: "entry", header: "Entry",
    cell: ({ row }) => {
      const p = row.original
      return <span className="font-mono-tabular text-xs">{p.entry_date} @ {p.entry_price.toFixed(2)} × {p.qty}</span>
    },
  },
  {
    id: "exit", header: "Exit",
    cell: ({ row }) => {
      const p = row.original
      return <span className="font-mono-tabular text-xs">{p.exit_date} @ {p.exit_price.toFixed(2)}</span>
    },
  },
  {
    accessorKey: "exit_reason", header: "Exit reason",
    cell: ({ getValue }) => (getValue() as string | null) ?? "—",
  },
  {
    accessorKey: "net_pnl", header: "Net P&L",
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
    accessorKey: "holding_days", header: "Holding period",
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
]

/** Row-level closed-trade history — shared by Positions' "Closed" tab and
 * Performance's "Trade History" tab, since both want the exact same list. */
export function ClosedPositionsTable() {
  const { data: positions } = useClosedPositions()

  return (
    <DataTable
      columns={COLUMNS}
      data={positions ?? []}
      emptyMessage="No closed positions yet."
    />
  )
}
