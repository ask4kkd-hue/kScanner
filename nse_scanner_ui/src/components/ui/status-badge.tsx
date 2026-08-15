import { Badge } from "@/components/ui/badge"

const VARIANT = {
  HOLD: "default",
  WATCH: "warning",
  REVIEW: "destructive",
} as const

/** Direct port of theme.py's status_class() / components.py's status_badge(). */
export function StatusBadge({ status }: { status: string }) {
  const variant = VARIANT[status as keyof typeof VARIANT] ?? "outline"
  return <Badge variant={variant}>{status}</Badge>
}
