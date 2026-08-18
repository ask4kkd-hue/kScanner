import { Badge } from "@/components/ui/badge"

const VARIANT = {
  HOLD: "default",
  WATCH: "warning",
  REVIEW: "destructive",
  // position lifecycle status (distinct from the advisor guidance above)
  OPEN: "outline",
  PARTIAL_PROFIT: "default",
  PARTIAL_LOSS: "warning",
  CLOSED: "outline",
  // New Opportunity's descriptive forward-outcome status (today.py's
  // _signal_outcomes) -- reports what already happened, not a forecast.
  "SL hit": "destructive",
  "Target hit": "default",
  "Towards target": "warning",
  "Open for trade": "outline",
} as const

const LABEL: Record<string, string> = {
  PARTIAL_PROFIT: "Partial Profit",
  PARTIAL_LOSS: "Partial Loss",
}

/** Direct port of theme.py's status_class() / components.py's status_badge(). */
export function StatusBadge({ status }: { status: string }) {
  const variant = VARIANT[status as keyof typeof VARIANT] ?? "outline"
  return <Badge variant={variant}>{LABEL[status] ?? status}</Badge>
}
