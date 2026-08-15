import { useEffect, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { SymbolCombobox } from "@/components/chart/SymbolCombobox"
import { useChartSymbols } from "@/queries/chart"
import { useOpenTrade } from "@/queries/holdings"

/**
 * Shared position-entry form — used by BOTH Holdings' "+ New position" and
 * Watchlist's "Promote to holding" (prefillSymbol), same as
 * web/pages/holdings.py's open_entry_dialog() being imported by
 * pages/watchlist.py rather than duplicated.
 */
export function EntryDialog({
  open, onOpenChange, prefillSymbol, onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  prefillSymbol?: string
  onSaved?: () => void
}) {
  const symbolsQuery = useChartSymbols()
  const openTrade = useOpenTrade()

  const [symbol, setSymbol] = useState("")
  const [entryDate, setEntryDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [entryPrice, setEntryPrice] = useState("")
  const [qty, setQty] = useState("1")
  const [stopPrice, setStopPrice] = useState("")
  const [targetPrice, setTargetPrice] = useState("")
  const [presetName, setPresetName] = useState("")
  const [thesis, setThesis] = useState("")

  useEffect(() => {
    if (open) setSymbol(prefillSymbol ?? "")
  }, [open, prefillSymbol])

  const reset = () => {
    setEntryPrice(""); setQty("1"); setStopPrice(""); setTargetPrice("")
    setPresetName(""); setThesis("")
  }

  const save = () => {
    if (!symbol || !entryPrice || !stopPrice) {
      toast.warning("Symbol, entry price and stop price are required.")
      return
    }
    openTrade.mutate({
      symbol, entry_date: entryDate, entry_price: Number(entryPrice), qty: Number(qty) || 1,
      stop_price: Number(stopPrice), target_price: targetPrice ? Number(targetPrice) : undefined,
      preset_name: presetName, thesis,
    }, {
      onSuccess: () => {
        toast.success(`Opened ${symbol}.`)
        onOpenChange(false)
        reset()
        onSaved?.()
      },
      onError: (err) => toast.error(err instanceof Error ? err.message : "Could not open position."),
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>New position</DialogTitle></DialogHeader>
        <div className="flex flex-col gap-2">
          <SymbolCombobox symbols={symbolsQuery.data ?? []} value={symbol} onChange={setSymbol} />
          <div className="flex gap-2">
            <Input type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} className="w-36" />
            <Input type="number" step="0.05" placeholder="Entry price" value={entryPrice}
                  onChange={(e) => setEntryPrice(e.target.value)} className="w-32" />
            <Input type="number" min={1} placeholder="Qty" value={qty}
                  onChange={(e) => setQty(e.target.value)} className="w-20" />
          </div>
          <div className="flex gap-2">
            <Input type="number" step="0.05" placeholder="Stop price" value={stopPrice}
                  onChange={(e) => setStopPrice(e.target.value)} className="w-32" />
            <Input type="number" step="0.05" placeholder="Target price" value={targetPrice}
                  onChange={(e) => setTargetPrice(e.target.value)} className="w-32" />
          </div>
          <Input placeholder="Preset name (optional)" value={presetName}
                onChange={(e) => setPresetName(e.target.value)} />
          <Textarea placeholder="Thesis" value={thesis} onChange={(e) => setThesis(e.target.value)} />
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={save} disabled={openTrade.isPending}>Open position</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
