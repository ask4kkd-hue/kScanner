import type { CellContext, ColumnDef } from "@tanstack/react-table"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { DataTable } from "@/components/ui/data-table"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { DistributionChart } from "@/components/ui/distribution-chart"
import { Input } from "@/components/ui/input"
import { PageTitle } from "@/components/ui/section"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { SymbolLink } from "@/components/ui/symbol-link"
import type { ChipState } from "@/api/scan"
import { useOpenChart } from "@/store/chartDrawer"
import { useAddToWatchlist } from "@/queries/watchlist"
import { useFilterChips, usePresets, useRunScan, useSavePreset, useScanFilter } from "@/queries/scan"

const PRESET_NAME_RE = /^[a-zA-Z_][a-zA-Z0-9_]*$/
const TIMEFRAMES = { D: "1d", W: "1w", M: "1m" } as const

export default function Scan() {
  const chipsQuery = useFilterChips()
  const presetsQuery = usePresets()
  const runScan = useRunScan()
  const savePreset = useSavePreset()
  const addToWatchlist = useAddToWatchlist()
  const openChart = useOpenChart()

  const [preset, setPreset] = useState<string>("")
  const [timeframe, setTimeframe] = useState<keyof typeof TIMEFRAMES>("D")
  const [scanId, setScanId] = useState<string | null>(null)
  const [chipState, setChipState] = useState<Record<string, ChipState>>({})
  const [saveDialogOpen, setSaveDialogOpen] = useState(false)
  const [presetName, setPresetName] = useState("")
  const [watchSymbol, setWatchSymbol] = useState<string>("")

  useEffect(() => {
    if (!preset && presetsQuery.data?.length) setPreset(presetsQuery.data[0])
  }, [presetsQuery.data, preset])

  const filterQuery = useScanFilter(scanId, chipState)

  const applyPreselect = (ids: string[]) => {
    if (!chipsQuery.data) return
    const next: Record<string, ChipState> = {}
    for (const chip of chipsQuery.data) {
      next[chip.id] = { active: ids.includes(chip.id), value: chip.default ?? null }
    }
    setChipState(next)
  }

  const handleRunScan = () => {
    if (!preset) return
    runScan.mutate({ presetName: preset, timeframe: TIMEFRAMES[timeframe] }, {
      onSuccess: (result) => {
        setScanId(result.scan_id)
        applyPreselect(result.preselected_chip_ids)
        toast.success(
          `Scan complete: ${result.total_count} candidates. ` +
          `Preset turned on: ${result.preselected_chip_ids.length ? result.preselected_chip_ids.join(", ") : "none"}.`
        )
      },
      onError: (err) => toast.error(err instanceof Error ? err.message : "Scan failed."),
    })
  }

  const toggleChip = (id: string) => {
    setChipState((cur) => ({ ...cur, [id]: { ...cur[id], active: !cur[id]?.active } }))
  }
  const setChipValue = (id: string, value: number) => {
    setChipState((cur) => ({ ...cur, [id]: { ...cur[id], value } }))
  }

  const activeConditions = () => {
    if (!chipsQuery.data) return []
    return chipsQuery.data
      .filter((c) => chipState[c.id]?.active)
      .map((c) => c.expr.replace("{v}", String(chipState[c.id]?.value ?? c.default)))
  }

  const handleSavePreset = () => {
    const conditions = activeConditions()
    if (conditions.length === 0) {
      toast.warning("No chips are active — nothing to save.")
      return
    }
    if (!PRESET_NAME_RE.test(presetName)) {
      toast.warning("Enter a valid preset name (letters, numbers, underscore).")
      return
    }
    savePreset.mutate({ name: presetName, conditions }, {
      onSuccess: () => {
        toast.success(`Saved preset '${presetName}' to config.yaml.`)
        setSaveDialogOpen(false)
        setPresetName("")
        presetsQuery.refetch()
      },
      onError: (err) => toast.error(err instanceof Error ? err.message : "Failed to save preset."),
    })
  }

  const rows = filterQuery.data?.rows ?? []
  const columns: ColumnDef<Record<string, unknown>, unknown>[] = [
    {
      accessorKey: "symbol", header: "Symbol",
      cell: (c: CellContext<Record<string, unknown>, unknown>) => <SymbolLink symbol={String(c.getValue())} />,
    },
    { accessorKey: "trigger_price", header: "Trigger" },
    { accessorKey: "l1_price", header: "L1" },
    { accessorKey: "l2_price", header: "L2" },
    { accessorKey: "neckline", header: "Neckline" },
    { accessorKey: "depth_pct", header: "Depth%" },
    { accessorKey: "stop_suggested", header: "Stop" },
    { accessorKey: "target_suggested", header: "Target" },
    { accessorKey: "bottom_at_sma", header: "Bottom @" },
    { accessorKey: "sma_stack", header: "SMA stack" },
    { accessorKey: "rs_rank_pct", header: "RS rank" },
  ].filter((col) => rows.length === 0 || "accessorKey" in col && (col.accessorKey as string) in rows[0])

  return (
    <div className="flex flex-col gap-3">
      <PageTitle text="Scan" subtitle="Scan once, filter instantly with chips." />

      <div className="flex flex-wrap items-end gap-3">
        <Select value={preset} onValueChange={setPreset}>
          <SelectTrigger className="w-48"><SelectValue placeholder="Preset" /></SelectTrigger>
          <SelectContent>
            {(presetsQuery.data ?? []).map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
          </SelectContent>
        </Select>
        <div className="flex gap-0.5 rounded-md border border-border p-0.5">
          {(["D", "W", "M"] as const).map((tf) => (
            <Button
              key={tf} size="sm" variant={timeframe === tf ? "default" : "ghost"}
              className="h-7 w-8 px-0" onClick={() => setTimeframe(tf)}
            >
              {tf}
            </Button>
          ))}
        </div>
        <Button onClick={handleRunScan} disabled={runScan.isPending || !preset}>
          {runScan.isPending ? "Running…" : "Run scan"}
        </Button>
        {filterQuery.data && (
          <span className="text-muted-foreground text-sm">
            {filterQuery.data.count} of {filterQuery.data.total} signals
          </span>
        )}
        <Button variant="outline" size="sm" onClick={() => setSaveDialogOpen(true)}>
          Save these chips as a preset
        </Button>
      </div>

      {chipsQuery.data && (
        <div className="flex flex-wrap gap-2">
          {chipsQuery.data.map((chip) => {
            const cs = chipState[chip.id]
            const active = cs?.active ?? false
            const hasValue = chip.expr.includes("{v}")
            return (
              <div key={chip.id} className="flex items-center gap-1">
                <Button
                  size="sm" variant={active ? "default" : "outline"}
                  className="h-7 px-2 text-xs" onClick={() => toggleChip(chip.id)}
                >
                  {chip.label}{active && hasValue ? ` ${cs?.value ?? chip.default}` : ""}
                </Button>
                {active && hasValue && (
                  <Input
                    type="number" min={chip.min} max={chip.max} step={chip.step ?? 1}
                    value={Number(cs?.value ?? chip.default)}
                    onChange={(e) => setChipValue(chip.id, Number(e.target.value))}
                    className="h-7 w-16 px-1.5 text-xs"
                  />
                )}
              </div>
            )
          })}
        </div>
      )}

      {!scanId && <p className="text-sm">Click "Run scan" to find candidates.</p>}

      {scanId && filterQuery.data && (
        <>
          <DataTable
            columns={columns}
            data={rows}
            emptyMessage="No signals match the current chips."
            onRowClick={(row) => openChart(String(row.symbol))}
          />

          {rows.length > 0 && (
            <div className="flex items-end gap-2">
              <Select value={watchSymbol} onValueChange={setWatchSymbol}>
                <SelectTrigger className="w-48"><SelectValue placeholder="Add to watchlist" /></SelectTrigger>
                <SelectContent>
                  {rows.map((r) => (
                    <SelectItem key={String(r.symbol)} value={String(r.symbol)}>{String(r.symbol)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                variant="outline" size="sm"
                disabled={!watchSymbol}
                onClick={() => {
                  addToWatchlist.mutate({ symbol: watchSymbol }, {
                    onSuccess: () => toast.success(`Added ${watchSymbol} to watchlist.`),
                    onError: (err) => toast.error(err instanceof Error ? err.message : "Failed to add."),
                  })
                }}
              >
                Add to Watchlist
              </Button>
            </div>
          )}

          <DistributionChart data={filterQuery.data.bottom_at_sma_distribution} />
        </>
      )}

      <Dialog open={saveDialogOpen} onOpenChange={setSaveDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save active chips as a preset</DialogTitle>
          </DialogHeader>
          <Input
            placeholder="Preset name (letters, numbers, underscore)"
            value={presetName}
            onChange={(e) => setPresetName(e.target.value)}
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setSaveDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSavePreset} disabled={savePreset.isPending}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
