import type { ColumnDef } from "@tanstack/react-table"

import { DataTable } from "@/components/ui/data-table"
import { PageTitle, Section } from "@/components/ui/section"
import type { IngestLogRow, SymbolGapRow, ValidationFailureRow } from "@/api/data"
import { useIngestLog, useSymbolGaps, useTableCounts, useValidationFailures } from "@/queries/data"

const validationColumns: ColumnDef<ValidationFailureRow, unknown>[] = [
  { accessorKey: "date", header: "Date" },
  { accessorKey: "symbol", header: "Symbol" },
  { accessorKey: "yf_close", header: "yfinance close" },
  { accessorKey: "bhav_close", header: "Bhavcopy close" },
  { accessorKey: "pct_diff", header: "% diff" },
]

const ingestColumns: ColumnDef<IngestLogRow, unknown>[] = [
  { accessorKey: "run_ts", header: "Run" },
  { accessorKey: "scope", header: "Scope" },
  { accessorKey: "date_from", header: "From" },
  { accessorKey: "date_to", header: "To" },
  { accessorKey: "rows_added", header: "Rows added" },
  { accessorKey: "symbols_ok", header: "OK" },
  { accessorKey: "symbols_failed", header: "Failed" },
  { accessorKey: "status", header: "Status" },
]

const gapColumns: ColumnDef<SymbolGapRow, unknown>[] = [
  { accessorKey: "symbol", header: "Symbol" },
  { accessorKey: "status", header: "Status" },
  { accessorKey: "consecutive_misses", header: "Consecutive misses" },
  { accessorKey: "last_success", header: "Last success" },
]

export default function Data() {
  const counts = useTableCounts()
  const failures = useValidationFailures(30)
  const ingestLog = useIngestLog(20)
  const gaps = useSymbolGaps()

  return (
    <div className="flex flex-col gap-3">
      <PageTitle text="Data" />

      <Section title="Table sizes">
        {counts.data && (
          <DataTable
            columns={[
              { accessorKey: "table", header: "Table" },
              { accessorKey: "rows", header: "Rows" },
            ]}
            data={Object.entries(counts.data).map(([table, rows]) => ({ table, rows }))}
          />
        )}
      </Section>

      <Section title="Validation failures (last 30 days)">
        {failures.data && failures.data.rows.length === 0 && (
          <p className="text-primary text-sm">No mismatches against the official bhavcopy.</p>
        )}
        {failures.data && failures.data.rows.length > 0 && (
          <>
            <DataTable columns={validationColumns} data={failures.data.rows} />
            {failures.data.flagged_15pct > 0 && (
              <p className="text-destructive mt-2 text-sm">
                {failures.data.flagged_15pct} rows differ by 15%+ — these are almost certainly
                corporate actions yfinance missed. They manufacture fake W-bottoms. Investigate
                before trading those symbols.
              </p>
            )}
          </>
        )}
      </Section>

      <Section title="Recent ingest runs" collapsed>
        <DataTable columns={ingestColumns} data={ingestLog.data ?? []} />
      </Section>

      <Section title="Symbols with residual gaps" collapsed>
        <p className="text-muted-foreground mb-2 text-xs">
          These failed to fill even after the anti-join retried them.
        </p>
        <DataTable columns={gapColumns} data={gaps.data ?? []} />
      </Section>
    </div>
  )
}
