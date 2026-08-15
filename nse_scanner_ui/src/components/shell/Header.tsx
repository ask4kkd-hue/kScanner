import { useQueryClient } from "@tanstack/react-query"
import { MoreVertical, RefreshCw } from "lucide-react"
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
import { exportsApi } from "@/api/exports"
import { jobsApi } from "@/api/jobs"

type RefreshEvent = { step: string | null; status: "running" | "done" | "error" | "complete"; detail?: string }

export function Header() {
  const queryClient = useQueryClient()
  const [busy, setBusy] = useState(false)
  const esRef = useRef<EventSource | null>(null)

  const refetchHealth = () => {
    queryClient.invalidateQueries({ queryKey: ["data", "table-counts"] })
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
      <span className="text-sm font-bold tracking-wide">kSCANNER</span>
      <div className="flex items-center gap-1">
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
