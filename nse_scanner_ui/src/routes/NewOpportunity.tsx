import { Link } from "react-router-dom"

import { Badge } from "@/components/ui/badge"
import { PageTitle } from "@/components/ui/section"
import { SymbolLink } from "@/components/ui/symbol-link"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useToday } from "@/queries/today"

const TIMEFRAME_LABEL: Record<string, string> = {
  "1d": "Short term (1D)",
  "1w": "Medium term (1W)",
  "1m": "Long term (1M)",
}

/** The full per-timeframe fresh-signal list — Dashboard only previews the top 3 of each. */
export default function NewOpportunity() {
  const { data } = useToday()
  if (!data) return null
  const { opportunities } = data

  return (
    <div className="flex flex-col gap-3">
      <PageTitle text="New Opportunity" subtitle="Fresh W-pattern signals from the last scan, by timeframe." />
      <Tabs defaultValue={opportunities[0]?.timeframe ?? "1d"}>
        <TabsList>
          {opportunities.map((block) => (
            <TabsTrigger key={block.timeframe} value={block.timeframe} className="gap-2">
              {TIMEFRAME_LABEL[block.timeframe]}
              {block.built && block.new_signals.length > 0 && (
                <Badge className="h-4 px-1.5 text-[10px]">{block.new_signals.length}</Badge>
              )}
            </TabsTrigger>
          ))}
        </TabsList>
        {opportunities.map((block) => (
          <TabsContent key={block.timeframe} value={block.timeframe}>
            {!block.built ? (
              <p className="text-muted-foreground text-sm">
                Not built yet — run features.py for {block.timeframe}
              </p>
            ) : block.total_signals === 0 ? (
              <p className="text-sm">No signals from the last scan.</p>
            ) : (
              <>
                <p className="text-muted-foreground text-xs">
                  {block.total_signals} signals — {block.new_signals.length} new,{" "}
                  {block.already_tracked_count} already tracked
                </p>
                <div className="mt-1 flex flex-col gap-1">
                  {block.new_signals.map((s) => (
                    <div key={s.symbol} className="flex gap-4 text-sm">
                      <SymbolLink symbol={s.symbol} className="w-28 font-semibold hover:text-primary hover:underline" />
                      <span className="w-20">{s.trigger_price.toFixed(2)}</span>
                      <span className="w-16">
                        {s.rs_rank_pct !== null ? `RS ${s.rs_rank_pct.toFixed(0)}` : "RS —"}
                      </span>
                    </div>
                  ))}
                </div>
                <Link to="/scan" className="text-primary mt-1 inline-block text-xs hover:underline">
                  See all in Scan
                </Link>
              </>
            )}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
