import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { useChartDrawer } from "@/store/chartDrawer"

/**
 * Rendered once at the app shell level (App.tsx) so ANY screen's click
 * handler can open it via useOpenChart() without prop-drilling. Placeholder
 * body for now — the real <ChartPanel/> (klinecharts, drawing tools,
 * overlays) lands in Phase 3 and gets rendered here AND at the dedicated
 * /chart/:symbol route, both from the same component (never duplicated).
 */
export function ChartDrawer() {
  const { isOpen, symbol, close } = useChartDrawer()

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && close()}>
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle>{symbol ?? "Chart"}</SheetTitle>
        </SheetHeader>
        <div className="text-muted-foreground px-4 text-sm">
          Chart panel — coming in Phase 3.
        </div>
      </SheetContent>
    </Sheet>
  )
}
