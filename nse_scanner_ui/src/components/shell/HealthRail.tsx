import { useTableCounts } from "@/queries/data"

/**
 * Minimal Phase 1 version — just table counts. The full staleness/latest-bar/
 * regime treatment (web/shell.py::refresh_health) moves here once the
 * /api/today aggregate endpoint exists (Phase 2), since that's where
 * data_is_stale()/regime_state() get exposed.
 */
export function HealthRail() {
  const { data } = useTableCounts()
  if (!data) return null

  return (
    <div className="mb-3 flex gap-0 overflow-hidden rounded-md border border-border font-mono-tabular text-xs">
      {[
        ["bars", data.bars_1d],
        ["features", data.features_1d],
        ["signals", data.signals_1d],
      ].map(([label, value]) => (
        <div key={label} className="border-r border-border px-3 py-2 last:border-r-0">
          <span className="text-muted-foreground">{label} </span>
          <b className="font-medium">{value?.toLocaleString() ?? "—"}</b>
        </div>
      ))}
    </div>
  )
}
