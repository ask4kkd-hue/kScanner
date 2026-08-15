import { useState } from "react"

import { Button } from "@/components/ui/button"
import { PageTitle } from "@/components/ui/section"
import { StatusBadge } from "@/components/ui/status-badge"
import { SymbolLink } from "@/components/ui/symbol-link"
import { EntryDialog } from "@/components/trades/EntryDialog"
import { CloseDialog } from "@/components/trades/CloseDialog"
import { useOpenPositions } from "@/queries/holdings"

function inr(n: number): string {
  return `₹${Math.round(n).toLocaleString("en-IN")}`
}

export default function Holdings() {
  const { data: positions } = useOpenPositions()
  const [entryOpen, setEntryOpen] = useState(false)
  const [closeTarget, setCloseTarget] = useState<{ id: number; symbol: string } | null>(null)

  const totalPnl = (positions ?? []).reduce((sum, p) => sum + (p.pnl_rupees ?? 0), 0)
  const atRisk = (positions ?? []).filter((p) => p.status === "WATCH" || p.status === "REVIEW").length

  return (
    <div className="flex flex-col gap-3">
      <PageTitle text="Holdings" />

      <Button onClick={() => setEntryOpen(true)} className="w-fit">+ New position</Button>

      {positions && positions.length === 0 && <p className="text-sm">No open positions.</p>}

      {positions && positions.length > 0 && (
        <>
          <div className="flex gap-6 text-sm">
            <span className="font-semibold">Total open P&amp;L: {inr(totalPnl)}</span>
            <span className="font-semibold">At risk: {atRisk} of {positions.length}</span>
          </div>

          <div className="flex flex-col gap-2">
            {positions.map((p) => (
              <div key={p.trade_id} className="rounded-md border border-border p-3">
                <div className="flex w-full items-center justify-between">
                  <div className="flex items-center gap-3">
                    <SymbolLink symbol={p.symbol} className="text-base font-bold hover:text-primary hover:underline" />
                    <StatusBadge status={p.status} />
                  </div>
                  <div className="flex items-center gap-4 font-mono-tabular text-sm">
                    <span className={p.pnl_rupees !== null && p.pnl_rupees >= 0 ? "text-primary" : "text-destructive"}>
                      {p.pnl_rupees !== null ? inr(p.pnl_rupees) : "—"}
                    </span>
                    <span>{p.r_multiple !== null ? `${p.r_multiple.toFixed(2)}R` : "—"}</span>
                    <Button
                      size="icon" variant="ghost" className="size-7"
                      onClick={() => setCloseTarget({ id: p.trade_id, symbol: p.symbol })}
                    >
                      &times;
                    </Button>
                  </div>
                </div>
                <div className="text-muted-foreground mt-1 flex gap-6 text-xs">
                  <span>entry {p.entry_date} @ {p.entry_price.toFixed(2)} x {p.qty}</span>
                  <span>close {p.close !== null ? p.close.toFixed(2) : "—"}</span>
                  <span>day {p.days_held ?? "—"}</span>
                  <span>MAE {p.mae_pct !== null ? `${p.mae_pct.toFixed(1)}%` : "—"}</span>
                  <span>MFE {p.mfe_pct !== null ? `${p.mfe_pct.toFixed(1)}%` : "—"}</span>
                </div>
                <div className="mt-1 flex flex-col gap-0">
                  {p.reasons.map((reason, i) => (
                    <span key={i} className="text-muted-foreground text-xs">· {reason}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      <EntryDialog open={entryOpen} onOpenChange={setEntryOpen} />
      {closeTarget && (
        <CloseDialog
          open={!!closeTarget}
          onOpenChange={(open) => !open && setCloseTarget(null)}
          tradeId={closeTarget.id}
          symbol={closeTarget.symbol}
        />
      )}
    </div>
  )
}
