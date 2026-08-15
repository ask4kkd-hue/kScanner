import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Palette } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { chartApi } from "@/api/chart"
import { SymbolCombobox } from "@/components/chart/SymbolCombobox"
import { KLineChartWidget, type KLineChartHandle, type OverlayPayload } from "@/components/chart/KLineChartWidget"
import { useChartSymbols } from "@/queries/chart"
import { L1L2_LABEL_FORMAT_LABELS, type L1L2LabelFormat, type L1L2LineStyle, useUiPrefs } from "@/store/uiPrefs"

const TIMEFRAMES = { D: "1d", W: "1w", M: "1m" } as const
const CHART_TYPES = ["Candle", "Line", "Heikin Ashi", "Renko"] as const
const OVERLAY_OPTIONS = ["sma10", "sma20", "sma50", "sma100", "sma200"]
const AVWAP_OPTIONS = ["(none)", "52-week low", "52-week high", "last W first low"]
const L1L2_LINE_STYLES: L1L2LineStyle[] = ["solid", "dashed", "dotted"]
const L1L2_LABEL_FORMATS: L1L2LabelFormat[] = ["both", "level", "price"]
const DRAWING_TOOLS: [string, string][] = [
  ["horizontal_line", "H-Line"], ["trend_line", "Trend"], ["ray", "Ray"],
  ["rectangle", "Rect"], ["fibonacci_retracement", "Fib"], ["text_note", "Text"],
]

/**
 * The shared chart component — rendered by BOTH routes/Chart.tsx (full page)
 * and ChartDrawer (slide-over). Ports web/pages/chart.py's refresh() as a
 * query + a set of imperative calls into KLineChartWidget, since the widget
 * itself has no reactive props (klinecharts owns its own canvas/DOM, same
 * reasoning the original Vue wrapper used).
 */
export function ChartPanel({ initialSymbol }: { initialSymbol?: string }) {
  const [symbol, setSymbol] = useState(initialSymbol ?? "")
  const [bars, setBars] = useState(250)
  const [timeframe, setTimeframe] = useState<keyof typeof TIMEFRAMES>("D")
  const [chartType, setChartType] = useState<(typeof CHART_TYPES)[number]>("Candle")
  const [overlays, setOverlays] = useState<string[]>(["sma50", "sma200"])
  const [avwap, setAvwap] = useState(AVWAP_OPTIONS[0])
  const [showPattern, setShowPattern] = useState(true)
  const [showAllTf, setShowAllTf] = useState(true)
  const { l1l2Color, l1l2LineStyle, l1l2LineWidth, l1l2LabelFormat, setL1L2Style } = useUiPrefs()

  useEffect(() => {
    if (initialSymbol) setSymbol(initialSymbol)
  }, [initialSymbol])

  const symbolsQuery = useChartSymbols()

  const chartQuery = useQuery({
    queryKey: [
      "chart", symbol, timeframe, bars, chartType, overlays, avwap, showPattern, showAllTf,
      l1l2Color, l1l2LineStyle, l1l2LineWidth, l1l2LabelFormat,
    ],
    queryFn: () =>
      chartApi.get(symbol, {
        timeframe, bars, chart_type: chartType, overlays, avwap,
        show_pattern: showPattern, show_all_tf: showAllTf,
        l1l2_color: l1l2Color, l1l2_line_style: l1l2LineStyle, l1l2_line_width: l1l2LineWidth,
        l1l2_label_format: l1l2LabelFormat,
      }),
    enabled: !!symbol,
  })

  const queryClient = useQueryClient()
  const saveDrawings = useMutation({
    mutationFn: (overlays: OverlayPayload[]) => chartApi.saveDrawings(symbol, TIMEFRAMES[timeframe], overlays),
  })
  const clearDrawings = useMutation({
    mutationFn: () => chartApi.clearDrawings(symbol, TIMEFRAMES[timeframe]),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["chart", symbol] }),
  })

  const chartRef = useRef<KLineChartHandle>(null)

  useEffect(() => {
    const data = chartQuery.data
    const chart = chartRef.current
    if (!data || !chart) return
    chart.set_bars(data.bars)
    chart.set_style(data.chart_style)
    chart.set_indicators(data.indicators)
    chart.load_overlays(data.user_drawings, data.server_overlays)
  }, [chartQuery.data])

  if (!symbolsQuery.data) return null

  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex flex-wrap items-end gap-2">
        <SymbolCombobox symbols={symbolsQuery.data} value={symbol} onChange={setSymbol} />

        <div className="flex flex-col gap-1">
          <label className="text-muted-foreground text-xs">Bars</label>
          <input
            type="number" min={100} max={2000} value={bars}
            onChange={(e) => setBars(Number(e.target.value))}
            className="border-input h-8 w-20 rounded-md border bg-transparent px-2 text-sm"
          />
        </div>

        <div className="flex gap-0.5 rounded-md border border-border p-0.5">
          {(["D", "W", "M"] as const).map((tf) => (
            <Button
              key={tf} size="sm" variant={timeframe === tf ? "default" : "ghost"}
              className="h-7 w-8 px-0" onClick={() => setTimeframe(tf)}
            >
              {tf}
            </Button>
          ))}
        </div>

        <Select value={chartType} onValueChange={(v) => setChartType(v as typeof chartType)}>
          <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
          <SelectContent>
            {CHART_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
          </SelectContent>
        </Select>

        <div className="flex flex-col gap-1">
          <label className="text-muted-foreground text-xs">Overlays</label>
          <div className="flex gap-1">
            {OVERLAY_OPTIONS.map((o) => (
              <Button
                key={o} size="sm" variant={overlays.includes(o) ? "default" : "outline"}
                className="h-7 px-2 text-xs"
                onClick={() => setOverlays((cur) => cur.includes(o) ? cur.filter((x) => x !== o) : [...cur, o])}
              >
                {o.replace("sma", "")}
              </Button>
            ))}
          </div>
        </div>

        <Select value={avwap} onValueChange={setAvwap}>
          <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
          <SelectContent>
            {AVWAP_OPTIONS.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
          </SelectContent>
        </Select>

        <label className="flex items-center gap-1.5 text-xs">
          <Checkbox checked={showPattern} onCheckedChange={(v) => setShowPattern(v === true)} />
          Mark last W L1/L2
        </label>
        <label className="flex items-center gap-1.5 text-xs">
          <Checkbox checked={showAllTf} onCheckedChange={(v) => setShowAllTf(v === true)} />
          D/W/M together
        </label>

        <Popover>
          <PopoverTrigger asChild>
            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" title="L1/L2 marker style">
              <Palette className="size-3.5" />
              Style
            </Button>
          </PopoverTrigger>
          <PopoverContent className="flex flex-col gap-3 p-3">
            <p className="text-muted-foreground text-xs">
              L1/L2/neckline marker style.{showAllTf && " Color is fixed per timeframe while \"D/W/M together\" is on."}
            </p>
            <div className="flex items-center justify-between gap-2">
              <label className="text-xs">Color</label>
              <input
                type="color" value={l1l2Color} disabled={showAllTf}
                onChange={(e) => setL1L2Style({ l1l2Color: e.target.value })}
                className="h-7 w-14 rounded border border-input bg-transparent disabled:opacity-50"
              />
            </div>
            <div className="flex items-center justify-between gap-2">
              <label className="text-xs">Line style</label>
              <Select value={l1l2LineStyle} onValueChange={(v) => setL1L2Style({ l1l2LineStyle: v as L1L2LineStyle })}>
                <SelectTrigger className="h-7 w-28 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {L1L2_LINE_STYLES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between gap-2">
              <label className="text-xs">Width</label>
              <Input
                type="number" min={1} max={5} value={l1l2LineWidth}
                onChange={(e) => setL1L2Style({ l1l2LineWidth: Number(e.target.value) })}
                className="h-7 w-14 px-1.5 text-xs"
              />
            </div>
            <div className="flex items-center justify-between gap-2">
              <label className="text-xs">Label</label>
              <Select
                value={l1l2LabelFormat}
                onValueChange={(v) => setL1L2Style({ l1l2LabelFormat: v as L1L2LabelFormat })}
              >
                <SelectTrigger className="h-7 w-40 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {L1L2_LABEL_FORMATS.map((f) => (
                    <SelectItem key={f} value={f}>{L1L2_LABEL_FORMAT_LABELS[f]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </PopoverContent>
        </Popover>
      </div>

      <div className="flex gap-1">
        {DRAWING_TOOLS.map(([id, label]) => (
          <Button key={id} size="sm" variant="ghost" className="h-7 px-2 text-xs"
                 onClick={() => chartRef.current?.start_drawing(id)}>
            {label}
          </Button>
        ))}
        <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => clearDrawings.mutate()}>
          Clear all
        </Button>
      </div>

      {chartQuery.data && (
        <div className="flex gap-6 text-sm">
          {[
            ["close", chartQuery.data.metrics.close.toFixed(2)],
            ["ADR%", chartQuery.data.metrics.adr_pct],
            ["ADX", chartQuery.data.metrics.adx],
            ["RSI", chartQuery.data.metrics.rsi],
            ["delivery%", chartQuery.data.metrics.delivery_pct],
            ["RS rank", chartQuery.data.metrics.rs_rank],
            ["pattern", chartQuery.data.metrics.pattern_found ? "W found" : "none"],
          ].map(([label, val]) => (
            <div key={label} className="flex flex-col gap-0">
              <span className="text-muted-foreground text-xs">{label}</span>
              <span className="font-mono-tabular text-sm">{val}</span>
            </div>
          ))}
        </div>
      )}

      {chartQuery.isError && (
        <p className="text-destructive text-sm">
          {chartQuery.error instanceof Error ? chartQuery.error.message : "Failed to load chart."}
        </p>
      )}

      <div className="min-h-0 flex-1">
        <KLineChartWidget
          ref={chartRef}
          onOverlaysChanged={(overlays) => saveDrawings.mutate(overlays)}
        />
      </div>
    </div>
  )
}
