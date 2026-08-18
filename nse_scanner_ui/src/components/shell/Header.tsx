import { useQueryClient } from "@tanstack/react-query"
import { MoreVertical, Palette, RefreshCw } from "lucide-react"
import { useRef, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { exportsApi } from "@/api/exports"
import { jobsApi } from "@/api/jobs"
import { useIngestLog } from "@/queries/data"
import { useToday } from "@/queries/today"
import { THEME_LABELS, type Theme, useUiPrefs } from "@/store/uiPrefs"

type RefreshEvent = { step: string | null; status: "running" | "done" | "error" | "complete"; detail?: string }

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60_000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function RefreshStatus() {
  const { data: log } = useIngestLog(1)
  const { data: today } = useToday()
  const last = log?.[0]

  if (!last?.run_ts) return null

  const stale = today?.status.stale ?? false
  return (
    <span
      className={`text-xs ${stale ? "text-destructive" : "text-muted-foreground"}`}
      title={`Last ingest run: ${last.run_ts}${stale ? " — data is stale" : ""}`}
    >
      Data refreshed {timeAgo(last.run_ts)}
    </span>
  )
}

export function Header() {
  const queryClient = useQueryClient()
  const [busy, setBusy] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const { theme, setTheme } = useUiPrefs()

  const refetchHealth = () => {
    queryClient.invalidateQueries({ queryKey: ["data", "table-counts"] })
    queryClient.invalidateQueries({ queryKey: ["data", "ingest-log"] })
    queryClient.invalidateQueries({ queryKey: ["today"] })
  }

  const handleRefresh = () => {
    if (busy) return
    setBusy(true)
    const toastId = toast.loading("Refreshing…")
    const es = new EventSource("/api/refresh/stream")
    esRef.current = es
    es.onmessage = (ev) => {
      const data = JSON.parse(ev.data) as RefreshEvent
      if (data.status === "running") {
        toast.loading(`Refreshing… ${data.step}`, { id: toastId })
      } else if (data.status === "error") {
        toast.error(`Refresh failed at ${data.step}: ${data.detail ?? "unknown error"}`, { id: toastId })
        es.close()
        setBusy(false)
      } else if (data.status === "complete") {
        toast.success("Refresh complete.", { id: toastId })
        es.close()
        setBusy(false)
        refetchHealth()
      }
    }
    es.onerror = () => {
      es.close()
      setBusy(false)
    }
  }

  const pollJob = (jobId: string, toastId: string | number) => {
    jobsApi.get(jobId).then((job) => {
      if (job.status === "done") {
        toast.success("Full rebuild complete (1D + 1W + 1M).", { id: toastId })
        setBusy(false)
        refetchHealth()
      } else if (job.status === "error") {
        toast.error(`Full rebuild failed at ${job.step}: ${job.error ?? "unknown error"}`, { id: toastId })
        setBusy(false)
      } else {
        toast.loading(`Full rebuild… ${job.step ?? "starting"}`, { id: toastId })
        setTimeout(() => pollJob(jobId, toastId), 4000)
      }
    }).catch((err) => {
      toast.error(err instanceof Error ? err.message : "Lost track of the rebuild job.", { id: toastId })
      setBusy(false)
    })
  }

  const handleFullRebuild = () => {
    if (busy) return
    setBusy(true)
    const toastId = toast.loading("Starting full rebuild (1D + 1W + 1M)…")
    jobsApi.startFullRebuild()
      .then((r) => pollJob(r.job_id, toastId))
      .catch((err) => {
        toast.error(err instanceof Error ? err.message : "Failed to start full rebuild.", { id: toastId })
        setBusy(false)
      })
  }

  const handleOpenExports = () => {
    exportsApi.reveal()
      .then((r) => toast.success(r.opened ? "Opened exports folder." : `Exports folder: ${r.path}`))
      .catch((err) => toast.error(err instanceof Error ? err.message : "Failed to open exports folder."))
  }

  return (
    <header className="flex h-12 items-center justify-between border-b border-border bg-card px-3">
      <div className="flex items-center gap-3">
        <span className="text-sm font-bold tracking-wide">kSCANNER</span>
        <RefreshStatus />
      </div>
      <div className="flex items-center gap-1">
        <Select value={theme} onValueChange={(v) => setTheme(v as Theme)}>
          <SelectTrigger className="h-8 w-[168px] text-xs" title="Theme">
            <Palette className="size-3.5" />
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.entries(THEME_LABELS) as [Theme, string][]).map(([value, label]) => (
              <SelectItem key={value} value={value}>{label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button size="sm" onClick={handleRefresh} disabled={busy}>
          <RefreshCw className="size-3.5" />
          Refresh
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon">
              <MoreVertical className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={handleFullRebuild} disabled={busy}>
              Run full rebuild (1D + 1W + 1M)
            </DropdownMenuItem>
            <DropdownMenuItem onClick={handleOpenExports}>Open exports folder</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() =>
                toast("kSCANNER v3 — local NSE swing/position scanner. EOD data only, no live quotes.")
              }
            >
              About
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
