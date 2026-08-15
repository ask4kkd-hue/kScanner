import { useEffect, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import type { PositionRow } from "@/api/holdings"
import { useUpdateTrade } from "@/queries/holdings"

/** Edit an open position's entry-side details — correcting a fat-fingered
 * entry price, adjusting a stop, updating the thesis. Not for exiting —
 * that's the close ("×") action, which keeps the trade's history intact. */
export function EditDialog({
  open, onOpenChange, position,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  position: PositionRow | null
}) {
  const updateTrade = useUpdateTrade()

  const [entryDate, setEntryDate] = useState("")
  const [entryPrice, setEntryPrice] = useState("")
  const [qty, setQty] = useState("")
  const [stopPrice, setStopPrice] = useState("")
  const [thesis, setThesis] = useState("")

  useEffect(() => {
    if (open && position) {
      setEntryDate(position.entry_date)
      setEntryPrice(String(position.entry_price))
      setQty(String(position.qty))
      setStopPrice(String(position.stop_price))
      setThesis("")
    }
  }, [open, position])

  const save = () => {
    if (!position) return
    if (!entryPrice || !stopPrice || !qty) {
      toast.warning("Entry price, stop price and qty are required.")
      return
    }
    updateTrade.mutate({
      tradeId: position.trade_id,
      body: {
        entry_date: entryDate, entry_price: Number(entryPrice),
        qty: Number(qty), stop_price: Number(stopPrice),
        ...(thesis ? { thesis } : {}),
      },
    }, {
      onSuccess: () => {
        toast.success(`Updated ${position.symbol}.`)
        onOpenChange(false)
      },
      onError: (err) => toast.error(err instanceof Error ? err.message : "Could not update position."),
    })
  }

  if (!position) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Edit {position.symbol}</DialogTitle></DialogHeader>
        <div className="flex flex-col gap-2">
          <div className="flex gap-2">
            <Input type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} className="w-36" />
            <Input type="number" step="0.05" placeholder="Entry price" value={entryPrice}
                  onChange={(e) => setEntryPrice(e.target.value)} className="w-32" />
            <Input type="number" min={1} placeholder="Qty" value={qty}
                  onChange={(e) => setQty(e.target.value)} className="w-20" />
          </div>
          <Input type="number" step="0.05" placeholder="Stop price" value={stopPrice}
                onChange={(e) => setStopPrice(e.target.value)} className="w-32" />
          <Textarea placeholder="Update thesis (optional, leave blank to keep as-is)"
                   value={thesis} onChange={(e) => setThesis(e.target.value)} />
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={save} disabled={updateTrade.isPending}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
