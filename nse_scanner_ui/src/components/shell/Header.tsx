import { MoreVertical, RefreshCw } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

export function Header() {
  // Refresh / full-rebuild / exports-reveal wire up to real endpoints in
  // Phase 7 (SSE refresh stream, job-polling full rebuild) — placeholder
  // for now so the shell layout is complete and testable from Phase 1.
  const notReady = () => toast.info("Wired up in a later phase — not yet.")

  return (
    <header className="flex h-12 items-center justify-between border-b border-border bg-card px-3">
      <span className="text-sm font-bold tracking-wide">kSCANNER</span>
      <div className="flex items-center gap-1">
        <Button size="sm" onClick={notReady}>
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
            <DropdownMenuItem onClick={notReady}>Run full rebuild (1D + 1W + 1M)</DropdownMenuItem>
            <DropdownMenuItem onClick={notReady}>Open exports folder</DropdownMenuItem>
            <DropdownMenuItem onClick={notReady}>Reset drawings for this symbol</DropdownMenuItem>
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
