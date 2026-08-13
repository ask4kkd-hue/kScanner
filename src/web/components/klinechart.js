// KLineChart wrapper — Vue component for ui.element(KLineChart).
//
// API surface verified against the vendored klinecharts 10.0.2 package's own
// index.d.ts (not guessed from memory/docs): setDataLoader (v10 replaced the
// old applyNewData/updateData with an async DataLoader), createIndicator's
// pane placement via paneId on the indicator object, overrideOverlay for
// global per-overlay event hooks (there is no chart-level "overlay changed"
// ActionType in this version), and the real built-in overlay name strings
// pulled from the bundled source.
import * as kc from "klinecharts";

const MAIN_PANE_INDICATORS = new Set(["MA", "EMA", "SMA", "BOLL", "SAR", "BBI"]);

// v2_instructions.md's six drawing tools, mapped to klinecharts' actual
// built-in overlay names (there is no direct 1:1 name match for most of these).
const DRAWING_TOOLS = {
  horizontal_line: "horizontalStraightLine",
  trend_line: "segment",
  ray: "rayLine",
  rectangle: "rect",
  fibonacci_retracement: "fibonacciLine",
  text_note: "text",
};

export default {
  template: `<div style="width:100%;height:100%;min-height:480px;"></div>`,
  props: {
    initialType: { type: String, default: "candle_solid" },
  },
  data() {
    return {
      chart: null,
      bars: [],
      loadSeq: 0,
      overlayDebounceTimer: null,
    };
  },
  mounted() {
    this.chart = kc.init(this.$el, {
      styles: {
        grid: {
          horizontal: { color: "#232928" },
          vertical: { color: "#232928" },
        },
        candle: {
          type: this.initialType,
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
    });

    // v10's async data-loader: we already hold the full window server-side
    // (Python decides the lookback), so getBars always returns everything
    // currently in `this.bars` and reports nothing more to page in.
    this.chart.setDataLoader({
      getBars: ({ callback }) => {
        callback(this.bars, { forward: false, backward: false });
      },
    });
    this.chart.setPeriod({ type: "day", span: 1 });
    this.chart.setSymbol({ ticker: "sym#0" });

    const emitOverlaysChanged = () => {
      clearTimeout(this.overlayDebounceTimer);
      this.overlayDebounceTimer = setTimeout(() => {
        // groupId "server" marks overlays the page injects itself (W-pattern
        // lines, AVWAP) — informational, recomputed on every refresh, never
        // something the user drew. Excluding them here is what stops them
        // from being saved back into `drawings` as if they were.
        const overlays = this.chart
          .getOverlays()
          .filter((o) => o.groupId !== "server")
          .map((o) => ({
            id: o.id,
            name: o.name,
            points: o.points,
            styles: o.styles,
            lock: o.lock,
            visible: o.visible,
            mode: o.mode,
          }));
        this.$emit("overlays-changed", overlays);
      }, 500);
    };

    // Global hooks apply to every overlay regardless of how it was created —
    // via createOverlay() from Python or drawn through the toolbar — which
    // is what makes drawings persist no matter how the user made them.
    this.chart.overrideOverlay({
      onDrawEnd: () => emitOverlaysChanged(),
      onPressedMoveEnd: () => emitOverlaysChanged(),
      onRemoved: () => emitOverlaysChanged(),
    });

    this.chart.subscribeAction("onCrosshairChange", (crosshair) => {
      if (crosshair && crosshair.dataIndex !== undefined) {
        this.$emit("crosshair", crosshair.dataIndex);
      }
    });
  },
  beforeUnmount() {
    clearTimeout(this.overlayDebounceTimer);
    if (this.chart) kc.dispose(this.$el);
  },
  methods: {
    // date, open, high, low, close, volume
    set_bars(bars) {
      this.bars = (bars || []).map((b) => ({
        timestamp: typeof b.date === "number" ? b.date : new Date(b.date).getTime(),
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
        volume: b.volume,
      }));
      // Re-triggers the data loader's 'init' call with the new bars. The
      // ticker value itself is never shown; only its identity has to change
      // for klinecharts to treat this as a fresh symbol load.
      this.loadSeq += 1;
      this.chart.setSymbol({ ticker: "sym#" + this.loadSeq });
    },
    // e.g. ['MA:10,20,50', 'VOL']
    set_indicators(list) {
      this.chart.removeIndicator();
      for (const spec of list || []) {
        const [name, paramsStr] = spec.split(":");
        const calcParams = paramsStr ? paramsStr.split(",").map(Number) : undefined;
        const onMainPane = MAIN_PANE_INDICATORS.has(name);
        const value = { name };
        if (calcParams) value.calcParams = calcParams;
        if (onMainPane) value.paneId = "candle_pane";
        this.chart.createIndicator(value, !onMainPane);
      }
    },
    set_style(chartType) {
      this.chart.setStyles({
        candle: { type: chartType === "area" ? "area" : "candle_solid" },
      });
    },
    // Replaces everything: user_drawings (loaded from the drawings table)
    // plus server_overlays (W-pattern lines, AVWAP — tagged groupId
    // "server" so they never get mistaken for user drawings later).
    load_overlays(user_drawings, server_overlays) {
      this.chart.removeOverlay();
      for (const ov of user_drawings || []) {
        this.chart.createOverlay(ov);
      }
      for (const ov of server_overlays || []) {
        this.chart.createOverlay({ ...ov, groupId: "server" });
      }
    },
    clear_overlays() {
      this.chart.removeOverlay();
    },
    // "Clear all" drawing-tool action — removes only what the user drew,
    // leaves the server-computed pattern/AVWAP lines in place.
    clear_user_overlays() {
      const ids = this.chart
        .getOverlays()
        .filter((o) => o.groupId !== "server")
        .map((o) => o.id);
      for (const id of ids) this.chart.removeOverlay({ id });
      // removeOverlay() with no args does not fire onRemoved per-overlay in
      // every version, so emit explicitly rather than rely on the hook.
      this.$emit("overlays-changed", []);
    },
    // name: one of DRAWING_TOOLS' keys
    start_drawing(name) {
      const overlayName = DRAWING_TOOLS[name];
      if (!overlayName) {
        console.error("kline: unknown drawing tool", name);
        return;
      }
      this.chart.createOverlay(overlayName);
    },
    resize() {
      if (this.chart) this.chart.resize();
    },
  },
};
