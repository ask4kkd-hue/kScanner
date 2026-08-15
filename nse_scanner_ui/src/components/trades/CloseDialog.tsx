import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { useCloseTrade } from "@/queries/holdings"

const EXIT_REASONS = ["target", "stop", "time_stop", "discretionary"] as const
const BEHAVIOUR_TAGS = ["chased_entry", "moved_stop", "revenge_trade", "oversized", "exited_early"]

export function CloseDialog({
  open, onOpenChange, tradeId, symbol, onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  tradeId: number
  symbol: string
  onSaved?: () => void
}) {
  const closeTrade = useCloseTrade()

  const [exitDate, setExitDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [exitPrice, setExitPrice] = useState("")
  const [reason, setReason] = useState<(typeof EXIT_REASONS)[number]>("discretionary")
  const [followedPlan, setFollowedPlan] = useState(true)
  const [tags, setTags] = useState<string[]>([])
  const [note, setNote] = useState("")

  const toggleTag = (tag: string) => {
    setTags((cur) => (cur.includes(tag) ? cur.filter((t) => t !== tag) : [...cur, tag]))
  }

  const save = () => {
    if (!exitPrice) {
      toast.warning("Exit price is required.")
      return
    }
    closeTrade.mutate({
      tradeId,
      body: {
        exit_date: exitDate, exit_price: Number(exitPrice), exit_reason: reason,
        followed_plan: followedPlan, review_note: note, tags,
      },
    }, {
      onSuccess: () => {
        toast.success(`Closed ${symbol}.`)
        onOpenChange(false)
        onSaved?.()
      },
      onError: (err) => toast.error(err instanceof Error ? err.message : "Could not close position."),
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Close {symbol}</DialogTitle></DialogHeader>
        <div className="flex flex-col gap-2">
          <div className="flex gap-2">
            <Input type="date" value={exitDate} onChange={(e) => setExitDate(e.target.value)} className="w-36" />
            <Input type="number" step="0.05" placeholder="Exit price" value={exitPrice}
                  onChange={(e) => setExitPrice(e.target.value)} className="w-32" />
          </div>
          <Select value={reason} onValueChange={(v) => setReason(v as typeof reason)}>
            <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
            <SelectContent>
              {EXIT_REASONS.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
            </SelectContent>
          </Select>
          <label className="flex items-center gap-1.5 text-sm">
            <Checkbox checked={followedPlan} onCheckedChange={(v) => setFollowedPlan(v === true)} />
            Followed the plan
          </label>
          <div className="flex flex-wrap gap-1">
            {BEHAVIOUR_TAGS.map((tag) => (
              <Button
                key={tag} size="sm" variant={tags.includes(tag) ? "default" : "outline"}
                className="h-6 px-2 text-xs" onClick={() => toggleTag(tag)}
              >
                {tag}
              </Button>
            ))}
          </div>
          <Textarea placeholder="Review note" value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="destructive" onClick={save} disabled={closeTrade.isPending}>Close position</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
