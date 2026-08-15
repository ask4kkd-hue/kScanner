import * as kc from "klinecharts"
import type { CandleType, Crosshair } from "klinecharts"
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react"

/**
 * React port of nse_scanner/src/web/components/klinechart.js (the NiceGUI
 * Vue wrapper) — same klinecharts 10.0.2 API surface, verified against the
 * vendored package's own index.d.ts there, not re-verified here since
 * it's the identical npm package version (see package.json). Kept as a
 * near-literal port on purpose: the 500ms debounce and the groupId="server"
 * filter encode a real invariant (server-computed W-pattern/AVWAP overlays
 * must never round-trip back into `drawings` as if the user drew them) and
 * must be reproduced exactly, not just similarly.
 */

const MAIN_PANE_INDICATORS = new Set(["MA", "EMA", "SMA", "BOLL", "SAR", "BBI"])

// The six drawing tools, mapped to klinecharts' actual built-in overlay
// names (no direct 1:1 name match for most of these).
const DRAWING_TOOLS: Record<string, string> = {
  horizontal_line: "horizontalStraightLine",
  trend_line: "segment",
  ray: "rayLine",
  rectangle: "rect",
  fibonacci_retracement: "fibonacciLine",
  text_note: "text",
}

export interface ChartBarInput {
  date: string | number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface OverlayPayload {
  id?: string
  name: string
  points: unknown[]
  styles?: unknown
  lock?: boolean
  visible?: boolean
  mode?: string
  extendData?: unknown
  groupId?: string
}

export interface KLineChartHandle {
  set_bars: (bars: ChartBarInput[]) => void
  set_indicators: (list: string[]) => void
  set_style: (chartType: "area" | "candle_solid") => void
  load_overlays: (userDrawings: OverlayPayload[], serverOverlays: OverlayPayload[]) => void
  clear_overlays: () => void
  clear_user_overlays: () => void
  start_drawing: (name: string) => void
  resize: () => void
}

export interface KLineChartWidgetProps {
  initialType?: CandleType
  onOverlaysChanged?: (overlays: OverlayPayload[]) => void
  onCrosshairChange?: (dataIndex: number) => void
}

export const KLineChartWidget = forwardRef<KLineChartHandle, KLineChartWidgetProps>(
  function KLineChartWidget({ initialType = "candle_solid", onOverlaysChanged, onCrosshairChange }, ref) {
    const containerRef = useRef<HTMLDivElement>(null)
    const chartRef = useRef<ReturnType<typeof kc.init>>(null)
    const barsRef = useRef<{ timestamp: number; open: number; high: number; low: number; close: number; volume: number }[]>([])
    const loadSeqRef = useRef(0)
    const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
    // Latest-callback refs so the mount effect (which only runs once) always
    // calls the CURRENT handler, not whatever was passed on first render.
    const onOverlaysChangedRef = useRef(onOverlaysChanged)
    const onCrosshairChangeRef = useRef(onCrosshairChange)
    onOverlaysChangedRef.current = onOverlaysChanged
    onCrosshairChangeRef.current = onCrosshairChange

    useEffect(() => {
      if (!containerRef.current) return
      const chart = kc.init(containerRef.current, {
        styles: {
          grid: {
            horizontal: { color: "#232928" },
            vertical: { color: "#232928" },
          },
          candle: {
            type: initialType,
            bar: {
              upColor: "#26a69a",
              downColor: "#ef5350",
              noChangeColor: "#8B9694",
              upBorderColor: "#26a69a",
              downBorderColor: "#ef5350",
              noChangeBorderColor: "#8B9694",
              upWickColor: "#26a69a",
              downWickColor: "#ef5350",
              noChangeWickColor: "#8B9694",
            },
            priceMark: {
              last: { upColor: "#26a69a", downColor: "#ef5350" },
            },
          },
          xAxis: {
            axisLine: { color: "#232928" },
            tickText: { color: "#8B9694" },
            tickLine: { color: "#232928" },
          },
          yAxis: {
            axisLine: { color: "#232928" },
            tickText: { color: "#8B9694" },
            tickLine: { color: "#232928" },
          },
          crosshair: {
            horizontal: { line: { color: "#8B9694" }, text: { backgroundColor: "#232928" } },
            vertical: { line: { color: "#8B9694" }, text: { backgroundColor: "#232928" } },
          },
          separator: { color: "#232928" },
        },
      })
      chartRef.current = chart
      if (!chart) return

      // v10's async data-loader: we already hold the full window
      // server-side (the API decides the lookback), so getBars always
      // returns everything currently in barsRef and reports nothing more
      // to page in.
      chart.setDataLoader({
        getBars: ({ callback }) => {
          callback(barsRef.current, { forward: false, backward: false })
        },
      })
      chart.setPeriod({ type: "day", span: 1 })
      chart.setSymbol({ ticker: "sym#0" })

      const emitOverlaysChanged = () => {
        if (debounceRef.current) clearTimeout(debounceRef.current)
        debounceRef.current = setTimeout(() => {
          const overlays = chart
            .getOverlays()
            .filter((o) => o.groupId !== "server")
            .map((o) => ({
              id: o.id, name: o.name, points: o.points, styles: o.styles,
              lock: o.lock, visible: o.visible, mode: o.mode,
            }))
          onOverlaysChangedRef.current?.(overlays)
        }, 500)
      }

      chart.overrideOverlay({
        onDrawEnd: () => { emitOverlaysChanged(); return true },
        onPressedMoveEnd: () => { emitOverlaysChanged(); return true },
        onRemoved: () => { emitOverlaysChanged(); return true },
      })

      chart.subscribeAction("onCrosshairChange", (data) => {
        const crosshair = data as Crosshair | undefined
        if (crosshair && crosshair.dataIndex !== undefined) {
          onCrosshairChangeRef.current?.(crosshair.dataIndex)
        }
      })

      return () => {
        if (debounceRef.current) clearTimeout(debounceRef.current)
        if (containerRef.current) kc.dispose(containerRef.current)
        chartRef.current = null
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps -- mount/unmount only, same as Vue's mounted()/beforeUnmount()
    }, [])

    useImperativeHandle(ref, () => ({
      set_bars(bars) {
        barsRef.current = (bars || []).map((b) => ({
          timestamp: typeof b.date === "number" ? b.date : new Date(b.date).getTime(),
          open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume,
        }))
        loadSeqRef.current += 1
        chartRef.current?.setSymbol({ ticker: "sym#" + loadSeqRef.current })
      },
      set_indicators(list) {
        const chart = chartRef.current
        if (!chart) return
        chart.removeIndicator()
        for (const spec of list || []) {
          const [name, paramsStr] = spec.split(":")
          const calcParams = paramsStr ? paramsStr.split(",").map(Number) : undefined
          const onMainPane = MAIN_PANE_INDICATORS.has(name)
          const value: Record<string, unknown> = { name }
          if (calcParams) value.calcParams = calcParams
          if (onMainPane) value.paneId = "candle_pane"
          chart.createIndicator(value as never, !onMainPane)
        }
      },
      set_style(chartType) {
        chartRef.current?.setStyles({
          candle: { type: chartType === "area" ? "area" : "candle_solid" },
        })
      },
      load_overlays(userDrawings, serverOverlays) {
        const chart = chartRef.current
        if (!chart) return
        chart.removeOverlay()
        for (const ov of userDrawings || []) chart.createOverlay(ov as never)
        for (const ov of serverOverlays || []) chart.createOverlay({ ...ov, groupId: "server" } as never)
      },
      clear_overlays() {
        chartRef.current?.removeOverlay()
      },
      clear_user_overlays() {
        const chart = chartRef.current
        if (!chart) return
        const ids = chart.getOverlays().filter((o) => o.groupId !== "server").map((o) => o.id)
        for (const id of ids) chart.removeOverlay({ id })
        onOverlaysChangedRef.current?.([])
      },
      start_drawing(name) {
        const overlayName = DRAWING_TOOLS[name]
        if (!overlayName) {
          console.error("kline: unknown drawing tool", name)
          return
        }
        chartRef.current?.createOverlay(overlayName)
      },
      resize() {
        chartRef.current?.resize()
      },
    }), [])

    return <div ref={containerRef} style={{ width: "100%", height: "100%", minHeight: 480 }} />
  }
)
