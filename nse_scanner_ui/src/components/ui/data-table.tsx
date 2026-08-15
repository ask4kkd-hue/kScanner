import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table"
import { ArrowUpDown } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

/**
 * Generic sortable table — the direct replacement for web/components.py's
 * dataframe_grid() / NiceGUI's ui.aggrid. Headless (TanStack Table) styled
 * with the shadcn Table primitives; nothing here needs AG Grid's
 * pivoting/grouping/enterprise features, every current grid is plain
 * sortable + row-click.
 */
export function DataTable<TData>({
  columns,
  data,
  emptyMessage = "No rows.",
  onRowClick,
}: {
  columns: ColumnDef<TData, unknown>[]
  data: TData[]
  emptyMessage?: string
  onRowClick?: (row: TData) => void
}) {
  const [sorting, setSorting] = useState<SortingState>([])

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (data.length === 0) {
    return <p className="text-muted-foreground text-sm">{emptyMessage}</p>
  }

  return (
    <Table>
      <TableHeader>
        {table.getHeaderGroups().map((headerGroup) => (
          <TableRow key={headerGroup.id}>
            {headerGroup.headers.map((header) => (
              <TableHead key={header.id}>
                {header.isPlaceholder ? null : header.column.getCanSort() ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="-ml-3 h-7 px-2 text-xs font-medium"
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    <ArrowUpDown className="ml-1 size-3" />
                  </Button>
                ) : (
                  flexRender(header.column.columnDef.header, header.getContext())
                )}
              </TableHead>
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {table.getRowModel().rows.map((row) => (
          <TableRow
            key={row.id}
            className={onRowClick ? "cursor-pointer" : undefined}
            onClick={() => onRowClick?.(row.original)}
          >
            {row.getVisibleCells().map((cell) => (
              <TableCell key={cell.id}>
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
