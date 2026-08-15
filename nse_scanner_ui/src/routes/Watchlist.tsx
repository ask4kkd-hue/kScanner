import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { PageTitle } from "@/components/ui/section"
import { SymbolLink } from "@/components/ui/symbol-link"
import { SymbolCombobox } from "@/components/chart/SymbolCombobox"
import { EntryDialog } from "@/components/trades/EntryDialog"
import { useChartSymbols } from "@/queries/chart"
import { useAddToWatchlist, useRemoveFromWatchlist, useWatchlist } from "@/queries/watchlist"

export default function Watchlist() {
  const symbolsQuery = useChartSymbols()
  const watchlistQuery = useWatchlist()
  const addToWatchlist = useAddToWatchlist()
  const removeFromWatchlist = useRemoveFromWatchlist()

  const [symbol, setSymbol] = useState("")
  const [note, setNote] = useState("")
  const [targetPrice, setTargetPrice] = useState("")
  const [tags, setTags] = useState("")
  const [promoteSymbol, setPromoteSymbol] = useState<string | null>(null)

  const add = () => {
    if (!symbol) {
      toast.warning("Pick a symbol.")
      return
    }
    addToWatchlist.mutate(
      { symbol, note, target_price: targetPrice ? Number(targetPrice) : undefined, tags },
      {
        onSuccess: () => {
          toast.success(`Added ${symbol} to watchlist.`)
          setSymbol(""); setNote(""); setTargetPrice(""); setTags("")
        },
        onError: (err) => toast.error(err instanceof Error ? err.message : "Failed to add."),
      }
    )
  }

  const rows = watchlistQuery.data ?? []

  return (
    <div className="flex flex-col gap-3">
      <PageTitle text="Watchlist" />

      <div className="flex flex-wrap items-end gap-2">
        <SymbolCombobox symbols={symbolsQuery.data ?? []} value={symbol} onChange={setSymbol} />
        <Input placeholder="Note" value={note} onChange={(e) => setNote(e.target.value)} className="w-48" />
        <Input type="number" step="0.05" placeholder="Target price" value={targetPrice}
              onChange={(e) => setTargetPrice(e.target.value)} className="w-32" />
        <Input placeholder="Tags" value={tags} onChange={(e) => setTags(e.target.value)} className="w-32" />
        <Button onClick={add} disabled={addToWatchlist.isPending}>Add</Button>
      </div>

      {rows.length === 0 && <p className="text-muted-foreground mt-2 text-sm">Watchlist is empty.</p>}

      <div className="flex flex-col gap-2">
        {rows.map((row) => (
          <div
            key={row.isin}
            className="rounded-md border p-3"
            style={{ borderColor: row.near_trigger ? "var(--color-warning)" : "var(--color-border)" }}
          >
            <div className="flex w-full items-center justify-between">
              <div className="flex items-center gap-3">
                <SymbolLink symbol={row.symbol} className="text-base font-bold hover:text-primary hover:underline" />
                {row.near_trigger && (
                  <span className="text-warning bg-warning/15 rounded px-1.5 py-0.5 text-xs font-semibold">
                    NEAR TRIGGER
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline" onClick={() => setPromoteSymbol(row.symbol)}>
                  Promote to holding
                </Button>
                <Button
                  size="icon" variant="ghost" className="size-7"
                  onClick={() => removeFromWatchlist.mutate(row.isin, {
                    onSuccess: () => toast.success("Removed."),
                  })}
                >
                  &times;
                </Button>
              </div>
            </div>
            <div className="text-muted-foreground mt-1 flex gap-6 text-xs">
              <span>close {row.close !== null ? row.close.toFixed(2) : "—"}</span>
              <span>target {row.target_price !== null ? row.target_price.toFixed(2) : "—"}</span>
              {row.close !== null && row.target_price ? (
                <span>{(Math.abs(row.close - row.target_price) / row.target_price * 100).toFixed(1)}% from target</span>
              ) : null}
              {row.note && <span>note: {row.note}</span>}
              {row.tags && <span>tags: {row.tags}</span>}
            </div>
          </div>
        ))}
      </div>

      <EntryDialog
        open={!!promoteSymbol}
        onOpenChange={(open) => !open && setPromoteSymbol(null)}
        prefillSymbol={promoteSymbol ?? undefined}
      />
    </div>
  )
}
