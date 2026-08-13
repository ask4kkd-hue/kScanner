# TASK: kScanner v2 — complete UI rebuild

## Context

Existing project at D:\Work\kTradeApps\kScanner\nse_scanner
Python + DuckDB + NiceGUI. Read CLAUDE.md and SCANNER_DESIGN.md first.

The backend is working and tested. DO NOT modify:
  db.py, indicators.py, patterns.py, universe.py, ingest.py,
  validate.py, features.py, backtest.py, journal.py

You may ADD new backend modules and ADD tables. You may change scan.py
only where specified below. Everything else you touch is under web/.

Delete app_streamlit.py. Replace the current five-tab web/app.py entirely.

Work in a branch: git checkout -b v2-ui. Commit after each screen works.

---

## GLOBAL RULES

1. Long work goes through components.run_bg(). Never block the event loop.
2. Holdings ARE `trades WHERE status='open'`. Do not create a holdings table.
3. Chart types (Heikin Ashi, Renko) and timeframes (W, M) are Python data
   transforms. The JS chart only draws what it is given — no indicator or
   transform maths in JavaScript.
4. Filter chips are declared in config.yaml. Adding a chip must require a
   config edit only, never a Python change.
5. The hold/exit advisor is DESCRIPTIVE ONLY. Every statement cites a number
   from this user's own backtest_curves / backtest_metrics / bars_1d.
   Never the words "will", "expect", "likely", "should buy", "should sell".
   No price predictions. If no backtest exists for a preset, say exactly that.
6. Prices are EOD only. Latest bars_1d close. Never fetch live quotes.
7. Every statistic displays its trade count. Anything below
   backtest.min_trades_for_conclusion renders greyed with "insufficient
   sample" — never presented as a finding.
8. Keep the existing theme tokens in web/theme.py. Dense, monospace tabular
   numerals, single accent, red reserved for things actually wrong.
9. This app runs offline. Vendor KLineChart locally under web/static/.
   No CDN.

---

## PART A — NEW BACKEND SUPPORT

### A1. Schema additions (append to db.py SCHEMA)

CREATE TABLE IF NOT EXISTS watchlist (
    isin VARCHAR PRIMARY KEY, symbol VARCHAR, added_on DATE,
    note TEXT, target_price DOUBLE, tags VARCHAR
);
CREATE TABLE IF NOT EXISTS drawings (
    isin VARCHAR, timeframe VARCHAR, payload VARCHAR, updated_at TIMESTAMP,
    PRIMARY KEY (isin, timeframe)
);
CREATE TABLE IF NOT EXISTS ui_prefs (key VARCHAR PRIMARY KEY, value VARCHAR);

ALTER TABLE trades ADD COLUMN timeframe VARCHAR DEFAULT '1d';

### A2. Create src/resample.py

to_weekly(df) / to_monthly(df)
  - Group by ACTUAL TRADING SESSIONS, never calendar dates. A Friday holiday
    must not produce a wrong weekly low.
  - OHLC = first open, max high, min low, last close. Volume summed.
    VWAP volume-weighted.
  - Label each row with the LAST trading day of the period.
  - Always drop the current incomplete period.
  - Add a 'thin' boolean column for periods with fewer than 3 sessions.

to_heikin_ashi(df)
  ha_close = (o+h+l+c)/4
  ha_open  = (prev_ha_open + prev_ha_close)/2, seeded with (o+c)/2
  ha_high  = max(h, ha_open, ha_close)
  ha_low   = min(l, ha_open, ha_close)

to_renko(df, brick_mode='atr', brick_atr_mult=1.0, brick_pct=None)
  - Brick size from ATR14 at the first bar, or a fixed percentage.
  - New brick each time close moves a full brick from the last brick close.
  - Reversal requires 2 bricks (standard rule).
  - Carry the source bar's date so tooltips work. Return a note that the
    x-axis is not time-linear.

### A3. Create src/watchlist.py

add(symbol, note='', target_price=None, tags='')
remove(isin)
list_with_status()
  -> watchlist joined to latest bars + features, plus a near_trigger flag
     when price is within 2% of target_price or of a detected W neckline.

### A4. Create src/advisor.py

position_status(con, trade_id) -> dict:
  status: 'HOLD' | 'WATCH' | 'REVIEW'
  reasons: list[str]
  metrics: days_held, current_pnl_pct, mae_pct, mfe_pct,
           backtest_median_hold, backtest_median_mfe_at_day, backtest_p85_mae

Rules — implement exactly these, each citing real numbers:

  days_held > median_hold_days
    -> REVIEW  "Day 11. Your backtest median winner peaked at day 8."
  marginal_mfe at current day <= 0
    -> REVIEW  "Marginal MFE turned negative at day 9 in your backtest."
  mae_pct approaching p85_mae_win
    -> WATCH   "Down 2.1%. 85% of your winners never drew down more than 2.4%."
  current MFE < backtest median MFE at that day
    -> WATCH   "Up 1.4% at day 6. Backtest median at day 6 was 3.9%."
  MFE > p75 curve
    -> HOLD    "Up 7.2% at day 5, above your 75th-percentile path."
  no backtest_runs row for that preset
    -> WATCH   "No backtest run for this preset — no basis for timing guidance."

### A5. Modify scan.py

scan() gains apply_preset: bool = True.
When False, apply ONLY pattern rules and hard tradability filters (EQ series,
ASM/GSM exclusion, minimum liquidity) and return a SUPERSET with every
features_1d column for the signal bar attached to each row.
backtest.py keeps calling it with the default — its behaviour is unchanged.

### A6. Add to config.yaml

chart:
  default_timeframe: "1d"
  default_type: "candle"
  renko_brick_mode: "atr"
  renko_brick_atr_mult: 1.0

filter_chips:
  - {id: above_sma200,   label: "Close > SMA200",    expr: "close > sma200"}
  - {id: above_sma50,    label: "Close > SMA50",     expr: "close > sma50"}
  - {id: sma200_rising,  label: "SMA200 rising",     expr: "sma200_slope > 0"}
  - {id: stacked,        label: "SMAs stacked up",   expr: "sma_stack = 'stacked_up'"}
  - {id: bottom_sma200,  label: "Bottom at SMA200",  expr: "bottom_at_sma = 'at_sma200'"}
  - {id: undercut,       label: "Undercut L1",       expr: "undercut = true"}
  - {id: rsi_above,      label: "RSI >",       expr: "rsi14 > {v}",        default: 30,  min: 0, max: 100}
  - {id: rsi_below,      label: "RSI <",       expr: "rsi14 < {v}",        default: 70,  min: 0, max: 100}
  - {id: adx_above,      label: "ADX >",       expr: "adx14 > {v}",        default: 20,  min: 0, max: 60}
  - {id: adr_above,      label: "ADR% >",      expr: "adr_pct20 > {v}",    default: 2.5, min: 0, max: 10, step: 0.1}
  - {id: deliv_above,    label: "Delivery% >", expr: "deliv_pct_sma20 > {v}", default: 40, min: 0, max: 100}
  - {id: turnover_above, label: "Turnover ≥ ₹cr", expr: "turnover_sma20 > {v}*10000000", default: 5, min: 0, max: 100}
  - {id: rs_above,       label: "RS rank >",   expr: "rs_rank_pct > {v}",  default: 70,  min: 0, max: 100}
  - {id: rvol_above,     label: "RVOL >",      expr: "rvol > {v}",         default: 1.5, min: 0.5, max: 5, step: 0.1}

---

## PART B — SHELL AND NAVIGATION

Create web/shell.py.

HEADER (fixed, always visible):
  - "kSCANNER" wordmark left, hamburger toggling the drawer
  - REFRESH BUTTON, prominent, right side. On click:
      runs universe -> ingest -> validate -> features in sequence via run_bg()
      shows a progress notification naming the current step
      refreshes the health rail when done
      on failure STOPS and shows which step failed — never continues silently
  - Overflow ui.menu: Run full rebuild (features --full), Open exports folder,
    Reset drawings for this symbol, About

HEALTH RAIL: directly under the header, on every screen. Green left edge =
current. Red = stale, and say "N sessions behind".

LEFT DRAWER (ui.left_drawer), collapsible to icons-only, state persisted in
ui_prefs:
  Today · Scan · Chart · Watchlist · Holdings · Performance · Backtest · Data

CONTENT AREA swaps by calling the active page module's render().

Create web/pages/ with one module per screen, each exposing render():
  today.py scan.py chart.py watchlist.py holdings.py performance.py
  backtest.py data.py

Move the existing Scan, Backtest, Journal and Data tab code into
scan.py, backtest.py, holdings.py, data.py — behaviour unchanged for now.

Add to web/components.py:
  section(title, *, collapsed=False)   collapsible panel using ui.expansion,
                                        styled with existing theme tokens
  page_title(text, subtitle="")
  status_badge(status)                  HOLD/WATCH/REVIEW coloured pill

Default route: today.

---

## PART C — CHART SCREEN

Create web/components/klinechart.js (Vue component) and web/kline.py.

class KLineChart(ui.element, component='components/klinechart.js')

Python API:
  set_bars(bars)            date, open, high, low, close, volume
  set_indicators(list)      e.g. ['MA:10,20,50', 'VOL']
  set_style(chart_type)     candle_solid | area
  load_overlays(payload)
  clear_overlays()

Events back to Python:
  overlays_changed(payload)  -> UPSERT into drawings, debounced 500ms
  crosshair(index)

DRAWING TOOLS: horizontal line, trend line, ray, rectangle, fibonacci
retracement, text note, plus clear-all.

PERSISTENCE: drawings keyed on (isin, timeframe). A daily drawing must NOT
appear on the weekly chart. On symbol or timeframe change, load that row and
call load_overlays.

web/pages/chart.py controls:
  Symbol selector with type-ahead
  Timeframe: D / W / M                       (default D)
  Chart type: Candle / Line / Heikin Ashi / Renko   (default Candle)
  Overlays multiselect: sma10/20/50/100/200
  AVWAP anchor: none / 52w low / 52w high / last W first low
  Metrics strip below: close, ADR%, ADX, RSI, delivery%, RS rank, pattern found
  W-pattern markers drawn as overlays: L1, L2, neckline, stop, target

Heikin Ashi and Renko call resample.py server-side and pass the result as
ordinary bars.

---

## PART D — SCAN SCREEN

Rebuild web/pages/scan.py around instant filtering.

FLOW: run the scan ONCE (expensive, server-side pattern detection). It returns
a superset with full feature vectors. Chips then filter that in-memory set with
no re-scan.

  - Preset selector: selecting a preset PRE-SELECTS chips rather than filtering
    server-side. Show which chips it turned on.
  - Chip bar: click to add a filter. Chips containing {v} render an inline
    number input with the configured min/max/step/default. Each chip has an x
    to remove it.
  - Live count updating as chips change: "38 of 214 signals"
  - "Save these chips as a preset" — writes an equivalent entry into the
    presets block of config.yaml
  - AG Grid results: sortable, filterable, resizable. Row click opens Chart.
  - Per-row actions: Add to Watchlist, Open chart
  - Distribution bar chart: where the second bottom formed

Filter in Python and update rowData. If laggy above 200 rows, switch to
grid.run_grid_method('setFilterModel', ...).

---

## PART E — WATCHLIST SCREEN

  - Grid: symbol, last close, % from target, near_trigger flag, note, tags
  - Add form: symbol type-ahead, note, target price, tags
  - Remove action
  - "Promote to holding" opens the position entry form
  - Near-trigger rows visually flagged

---

## PART F — HOLDINGS SCREEN

Holdings are trades WHERE status='open'. Manual entry only — no broker fetch,
no CSV import.

Each position renders as a card:
  symbol, entry date/price, qty, current close (EOD)
  unrealised P&L in rupees and in R
  days held, MAE%, MFE%
  advisor status badge (HOLD accent / WATCH amber / REVIEW red)
  reason list expanded underneath

Sort REVIEW first, then WATCH, then HOLD.
Footer: total open P&L, count at risk.
Position entry form and close-position form (exit price, reason, followed-plan
checkbox, behaviour tags, review note) — reuse journal.py functions.

---

## PART G — TODAY SCREEN (default landing, end-of-day use)

Everything important visible without clicking. Collapsible sections in this
order:

1. STATUS (always expanded)
   Latest bar vs last trading day, validation fails, refresh button
   Market regime: Nifty 500 vs its 200 DMA
   One line: "Data current" or "Run refresh — N sessions behind"

2. YOUR POSITIONS (always expanded)
   One compact row per open position: symbol, days held, P&L %, R,
   advisor status badge. Sorted REVIEW first.
   Row click expands the reason list inline.
   Footer: total open P&L, count at risk.

3. NEW OPPORTUNITIES (expanded)
   Three collapsible sub-sections:
     Short term  — 1D signals
     Medium term — 1W signals
     Long term   — 1M signals
   Each: count, top 5 by RS rank, link into Scan with that timeframe
   preselected. Exclude anything already held or watchlisted; label those
   separately as "already tracked".
   If features_1w / features_1m are empty, show "not built yet — run
   features.py for 1w/1m", NOT zero signals.

4. P&L (collapsed)
   Realised: today, this week, this month, all time
   Unrealised: current open
   Small equity sparkline

5. WATCHLIST NEAR TRIGGER (collapsed unless non-empty)

Must load in under 2 seconds.

---

## PART H — PERFORMANCE SCREEN

  Equity curve and drawdown
  Win rate, expectancy R, profit factor, avg win R, avg loss R
  Attribution grids: by preset, by timeframe, by sector, by bottom_at_sma
  Adherence report and behaviour-tag analysis (reuse journal.py)
  Live vs backtest comparison table
  Every stat shows its trade count; under-sample stats greyed with
  "insufficient sample".

---

## PART I — TESTS

Create and pass:
  src/test_resample.py
    known 3-week series aggregates correctly including a holiday week
    incomplete current week excluded
    Heikin Ashi matches a hand-worked 5-bar example
    Renko brick count correct for a clean trend; reversal needs 2 bricks
  src/test_advisor.py
    synthetic backtest_curves row; assert each rule fires on the right input
    no-backtest case returns the no-basis message and never a prediction

Existing test_core.py (45) and test_charts.py (42) must still pass.

---

## ACCEPTANCE CHECKLIST

[ ] Drawer nav works, collapse state survives restart
[ ] Refresh button runs the pipeline, names each step, page stays responsive
[ ] Refresh failure stops and reports the failing step
[ ] Chart: D/W/M and Candle/Line/HA/Renko all switch correctly
[ ] Draw a trendline, switch symbol, switch back — still there
[ ] Switch to weekly — daily drawing NOT shown
[ ] Drawing survives an app restart
[ ] Scan once, then add/remove 5 chips — no re-scan, count updates instantly
[ ] Add a new chip to config.yaml, restart, it appears and works
[ ] Advisor reasons cite real numbers from this user's backtest
[ ] Delete backtest rows -> advisor says "no basis", invents nothing
[ ] Advisor output contains no prediction language anywhere
[ ] Today loads in under 2s and shows positions, opportunities, P&L
[ ] Under-sample stats greyed, not presented as findings
[ ] All four test files pass

Then update SCANNER_DESIGN.md section 15 and add v2 change-log rows.