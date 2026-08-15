import { ChartPanel } from "@/components/chart/ChartPanel"
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { useChartDrawer } from "@/store/chartDrawer"

/**
 * Rendered once at the app shell level (App.tsx) so ANY screen's click
 * handler can open it via useOpenChart() without prop-drilling. Same
 * <ChartPanel/> the dedicated /chart/:symbol route renders — one source of
 * truth for chart logic, never duplicated.
 */
export function ChartDrawer() {
  const { isOpen, symbol, close } = useChartDrawer()

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && close()}>
      <SheetContent side="right" className="w-full sm:max-w-4xl">
        <SheetHeader>
          <SheetTitle>{symbol ?? "Chart"}</SheetTitle>
        </SheetHeader>
        <div className="min-h-0 flex-1 px-4 pb-4">
          {symbol && <ChartPanel initialSymbol={symbol} />}
        </div>
      </SheetContent>
    </Sheet>
  )
}
