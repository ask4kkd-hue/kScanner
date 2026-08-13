# NSE Swing & Position Scanner — Design Document

**Version:** 1.1
**Last updated:** 12 Aug 2026
**Owner:** (you)
**Status:** Built — v1 code complete, pending first data run

---

## 0. How to use this document

This is the reference spec. When you change a design decision later, do two things:

1. Edit the relevant section.
2. Add a row to the **Change Log** (Section 13) with the date and the reason.

The reason matters more than the change. Six months from now you will want to know *why* you set `ADR% ≥ 2.5`, not just that you did.

---

## 1. Purpose & Scope

### 1.1 Goal
A locally-run stock scanner for NSE cash equities, replacing Chartink, with data and logic fully under your control.

### 1.2 Primary objective
**Accuracy over everything.** Speed, feature count, and elegance are all secondary. A scanner that produces confident wrong signals is worse than no scanner.

### 1.3 Timeframe roles

| Timeframe | Purpose | Typical hold |
|---|---|---|
| **1D** | Trading | 5–10 days, 5%+ target |
| **1W** | Longer-hold swings | Weeks to months |
| **1M** | Investing / regime | Months to years |

### 1.4 Primary pattern
**W-pattern (double bottom)** — the second low undercuts the prior swing low, then price closes back above that prior swing low.

### 1.5 Explicitly out of scope (v1)
- Intraday timeframes (1h, 4h) — deferred
- Order placement / execution
- F&O, commodities, BSE
- Volume Profile / POC / Value Area (impossible from daily bars)

---

## 2. Architecture

### 2.1 Layer model

```
  ┌──────────────────────────────────────────────┐
  │ RAW FILES        raw/                        │  Immutable. Append-only.
  │ bhavcopy zips, universe snapshots            │  Your audit trail.
  └────────────────────┬─────────────────────────┘
                       ↓
  ┌──────────────────────────────────────────────┐
  │ LAYER 1: FACTS   bars_1d                     │  Never contains a
  │ OHLCV + delivery + vwap + trades             │  calculated value.
  └────────────────────┬─────────────────────────┘
                       ↓
  ┌──────────────────────────────────────────────┐
  │ LAYER 2: FEATURES  features_1d/1w/1m         │  Fully rebuildable.
  │ SMA, ATR, Supertrend, AVWAP, RS...           │  Drop & recreate freely.
  └────────────────────┬─────────────────────────┘
                       ↓
  ┌──────────────────────────────────────────────┐
  │ LAYER 3: SIGNALS   signals_1d                │  Scan output log.
  │ what fired, when, at what price              │  Never overwritten.
  └──────────────────────────────────────────────┘
```

### 2.2 The non-negotiable rule
**A calculated value never enters Layer 1.** You will change indicator logic dozens of times. Layer separation means `DROP TABLE features_1d` is always safe and your source of truth never moves.

### 2.3 Directory layout

```
D:\Work\kTradeApps\kScanner\nse_scanner\
├── db\market.duckdb          ← the only file you query
├── raw\
│   ├── bhavcopy\YYYY\        ← downloaded zips, never modified
│   ├── universe\             ← dated EQUITY_L.csv snapshots
│   └── flags\                ← ASM/GSM daily snapshots
├── logs\
├── exports\                  ← xlsx / csv scan outputs
└── src\                      ← the code
```

**Do not place `D:\Work\kTradeApps\kScanner\nse_scanner\` inside OneDrive or Google Drive.** Sync-while-writing corrupts DuckDB files. Back up with a scheduled copy instead.

---

## 3. Data Sources

### 3.1 Source matrix

| Source | Provides | Role | Cost |
|---|---|---|---|
| **yfinance** | OHLCV, split-adjusted | Primary price series | Free |
| **NSE bhavcopy** | Delivery %, VWAP, trades, turnover, series | Enrichment **and** validator | Free |
| **NSE ASM/GSM lists** | Surveillance flags | Tradability filter | Free |
| **NSE index files** | Nifty 50/500 OHLC, constituents, sector | Benchmark + classification | Free |
| **NSE corporate actions** | Splits, bonus, ex-dates | Validates yfinance adjustments | Free |

### 3.2 yfinance settings — critical

```python
yf.download(tickers, auto_adjust=False, group_by='ticker', threads=True)
```

- **`auto_adjust=False`** — Yahoo's raw OHLC is already split-adjusted; `Adj Close` *additionally* strips dividends. You want split-adjusted, dividend-**un**adjusted, so plain OHLC is exactly right.
- **Ignore `Adj Close` entirely.**
- Ticker format: `SYMBOL.NS`
- Batch ~50 tickers, sleep 1–2s between batches. Yahoo rate-limits aggressively.

### 3.3 Bhavcopy validation rule

**Compare yesterday's close only.** No corporate action has occurred since, so both sources must agree.

- Threshold: flag `abs(pct_diff) > 0.1%`
- Log every comparison — pass and fail — to `validation_log`
- **The high-value catch:** bhavcopy shows normal trading, yfinance shows a 40% gap ⇒ Yahoo missed a bonus issue. This is yfinance's most common NSE failure and it manufactures textbook fake W-bottoms.

### 3.4 Column ownership

| Column | Source | Why |
|---|---|---|
| open, high, low, close | **yfinance** | split-adjusted |
| volume | yfinance | split-adjusted |
| deliv_qty, deliv_pct | **bhavcopy** | ratio/count — adjustment-neutral |
| vwap, no_of_trades | bhavcopy | adjustment-neutral |
| series | bhavcopy | metadata |

Joined on `(isin, date)`.

### 3.5 Known fragility
NSE periodically changes bhavcopy URL structure. The downloader **will** break. Wrap it so it fails **loudly** — a scanner silently running on stale data is worse than one that's visibly down.

### 3.6 Timing
Bhavcopy publishes from ~4:00–4:30 PM IST, delivery report alongside or shortly after. Run after **5:30 PM** and handle late delivery data.

---

## 4. Database Schema

### 4.1 Layer 1 — Facts

```sql
CREATE TABLE bars_1d (
  isin          VARCHAR NOT NULL,
  symbol        VARCHAR NOT NULL,
  date          DATE    NOT NULL,
  open          DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
  prev_close    DOUBLE,
  volume        BIGINT,
  vwap          DOUBLE,
  no_of_trades  BIGINT,
  deliv_qty     BIGINT,
  deliv_pct     DOUBLE,
  series        VARCHAR,
  PRIMARY KEY (isin, date)
);
```

`PRIMARY KEY (isin, date)` makes every re-run idempotent. This is what lets gap-filling be safe.

### 4.2 Reference tables

```sql
CREATE TABLE instruments (
  isin VARCHAR PRIMARY KEY, symbol VARCHAR, name VARCHAR,
  series VARCHAR, sector VARCHAR, industry VARCHAR,
  first_seen DATE, last_seen DATE
);

CREATE TABLE symbol_status (
  isin VARCHAR PRIMARY KEY,
  status VARCHAR,               -- active | suspended | delisted
  consecutive_misses INT,
  last_success DATE
);

CREATE TABLE trading_calendar (
  date DATE PRIMARY KEY,
  bhavcopy_available BOOLEAN
);

CREATE TABLE flags (
  date DATE, isin VARCHAR,
  asm BOOLEAN, gsm BOOLEAN, price_band DOUBLE,
  PRIMARY KEY (date, isin)
);

CREATE TABLE index_bars (
  index_name VARCHAR, date DATE,
  open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
  PRIMARY KEY (index_name, date)
);

CREATE TABLE index_membership (
  index_name VARCHAR, isin VARCHAR, as_of DATE,
  PRIMARY KEY (index_name, isin, as_of)
);

CREATE TABLE corp_actions (
  isin VARCHAR, ex_date DATE, action_type VARCHAR, ratio DOUBLE
);

CREATE TABLE fundamentals (            -- monthly refresh
  isin VARCHAR, as_of DATE,
  market_cap DOUBLE, free_float_pct DOUBLE,
  PRIMARY KEY (isin, as_of)
);

CREATE TABLE fii_dii_flows (           -- market-level, standalone
  date DATE PRIMARY KEY,
  fii_buy DOUBLE, fii_sell DOUBLE, dii_buy DOUBLE, dii_sell DOUBLE
);
```

### 4.3 Layer 2 — Features

```sql
CREATE TABLE features_1d (
  isin VARCHAR NOT NULL,
  date DATE NOT NULL,
  bars_available INT,              -- for warm-up gating

  -- trend
  sma20 FLOAT, sma50 FLOAT, sma100 FLOAT, sma200 FLOAT,
  ema10 FLOAT, ema21 FLOAT,
  hma10 FLOAT, hma50 FLOAT,
  supertrend_20_3 FLOAT, st_dir SMALLINT,

  -- volatility
  atr14 FLOAT, adr_pct20 FLOAT,
  bb_mid FLOAT, bb_upper FLOAT, bb_lower FLOAT, bb_width FLOAT,

  -- momentum
  rsi14 FLOAT, adx14 FLOAT, di_plus FLOAT, di_minus FLOAT,
  macd FLOAT, macd_signal FLOAT,

  -- volume & delivery
  vol_sma20 BIGINT, rvol FLOAT,
  turnover FLOAT, turnover_sma20 FLOAT,
  deliv_pct_sma20 FLOAT, deliv_surge FLOAT,
  avg_trade_size FLOAT,

  -- position
  dist_sma200_pct FLOAT,
  dist_52w_high_pct FLOAT, dist_52w_low_pct FLOAT,

  -- relative strength (PASS 2 — cross-sectional)
  ret_55d FLOAT, rs_vs_bench FLOAT, rs_rank_pct FLOAT,

  feature_version VARCHAR,
  PRIMARY KEY (isin, date)
);
```

Mirror as `features_1w` and `features_1m` — **separate tables, not a `timeframe` column.**

### 4.4 Anchored VWAP (own table — see Section 6)

```sql
CREATE TABLE avwap (
  isin VARCHAR, anchor_type VARCHAR, anchor_date DATE, date DATE,
  avwap FLOAT, avwap_upper FLOAT, avwap_lower FLOAT,
  PRIMARY KEY (isin, anchor_type, anchor_date, date)
);
```

### 4.5 Layer 3 — Signals & operational logs

```sql
CREATE TABLE signals_1d (
  scan_date DATE, isin VARCHAR, preset_name VARCHAR,
  signal_type VARCHAR, trigger_price DOUBLE,
  l1_date DATE, l1_price DOUBLE,
  l2_date DATE, l2_price DOUBLE,
  neckline DOUBLE, stop_suggested DOUBLE,
  feature_version VARCHAR, config_hash VARCHAR,
  PRIMARY KEY (scan_date, isin, preset_name)
);

CREATE TABLE validation_log (
  date DATE, isin VARCHAR,
  yf_close DOUBLE, bhav_close DOUBLE, pct_diff DOUBLE, passed BOOLEAN
);

CREATE TABLE ingest_log (
  run_ts TIMESTAMP, scope VARCHAR, date_from DATE, date_to DATE,
  rows_added INT, symbols_ok INT, symbols_failed INT,
  status VARCHAR, note VARCHAR
);
```

### 4.6 Type & sizing notes
- Use **`FLOAT` (4-byte) for indicators**, not `DOUBLE`. You don't need 15 significant digits for an SMA, and `features_1d` will be 3–4× wider than `bars_1d`.
- Expected sizes: `bars_1d` ≈ 200 MB, `features_1d` ≈ 600–800 MB after compression.
- **Wide table, not key-value (EAV).** Fixed indicator set, columnar storage, fast scans. Adding one later is just `ALTER TABLE ADD COLUMN`. An EAV table makes every scan a self-join.

---

## 5. Feature Registry — the "everything is optional" design

### 5.1 The requirement
Every indicator must be individually switchable so you can test combinations without editing code.

### 5.2 The pattern: declarative registry + dependency resolution

Each feature is **declared**, not hard-coded into a pipeline:

```python
FEATURES = {
  "atr14": {
      "deps": [],
      "params": {"length": 14},
      "min_bars": 100,
      "fn": compute_atr,
      "outputs": ["atr14"],
  },
  "supertrend_20_3": {
      "deps": ["atr14"],                 # ← resolved automatically
      "params": {"length": 20, "mult": 3},
      "min_bars": 100,
      "fn": compute_supertrend,
      "outputs": ["supertrend_20_3", "st_dir"],
  },
  "rs_rank": {
      "deps": ["ret_55d"],
      "pass": 2,                         # ← cross-sectional
      "min_bars": 60,
      "fn": compute_rs_rank,
      "outputs": ["ret_55d", "rs_vs_bench", "rs_rank_pct"],
  },
}
```

### 5.3 Config drives everything

```yaml
features:
  enabled:
    - sma20
    - sma50
    - sma200
    - atr14
    - adr_pct20
    - supertrend_20_3
    - hma10
    - hma50
    - adx14
    - rvol
    - deliv_pct_sma20
    - avwap
    # - bollinger        ← commented out = not computed, not stored
    # - macd
    # - rs_rank
```

### 5.4 Resolution rules
1. Read `enabled` list from config.
2. **Walk dependencies transitively** — enabling `supertrend_20_3` auto-enables `atr14` even if you didn't list it.
3. Topologically sort → compute order.
4. Split into **pass 1** (per-symbol) and **pass 2** (cross-sectional). Pass 2 runs only after pass 1 completes for the **entire universe** — computing ranks against a partial universe produces plausible, wrong numbers.
5. Hash the resolved config → `feature_version`. Stamp every row.

### 5.5 Scan rules are also declarative

```yaml
presets:
  baseline_w:
    conditions:
      - "close > sma50"
      - "adx14 >= 20"
      - "adr_pct20 >= 2.5"
      - "turnover_sma20 >= 50000000"
      - "deliv_pct_sma20 >= 40"
    pattern: w_double_bottom

  w_with_rs:
    inherits: baseline_w
    conditions_add:
      - "rs_rank_pct >= 70"

  w_aggressive:
    inherits: baseline_w
    overrides:
      adr_pct20: 4.0
```

Conditions are strings evaluated as SQL against the features table. Adding a new combination = editing YAML, never touching Python.

### 5.6 Design principles
- **Store the expensive state, compute the cheap logic at scan time.** Store SMAs, ATR, ranks. Do *not* store `close > sma50` — that's free at query time, and storing it means every threshold tweak triggers a rebuild.
- **Thresholds live in presets, never in the database.**
- **Disabled features are not computed and not stored.** The table has the column; it stays NULL.

### 5.7 Warm-up gating
Every feature declares `min_bars`. At scan time:

```sql
WHERE bars_available >= (min_bars of every feature used by this preset)
```

Without this, symbols return values that exist but are wrong — the worst failure mode, because nothing looks broken.

---

## 6. Anchored VWAP — specification

### 6.1 Formula

```
AVWAP(t) = Σ(vwap_i × volume_i) / Σ(volume_i)     for i = anchor_date .. t
```

Uses bhavcopy's daily `AVG_PRICE` as `vwap_i`. Most daily-only scanners cannot do this because they lack per-day VWAP — **this is a genuine edge in your setup.**

### 6.2 Bands

```
AVWAP_upper = AVWAP + k × σ(price around AVWAP since anchor)
AVWAP_lower = AVWAP − k × σ(...)          default k = 1.0
```

### 6.3 Anchor types

| `anchor_type` | Anchor date | Precomputed? |
|---|---|---|
| `w_l1` | First low of a detected W-pattern | Yes — on signal |
| `swing_low` | Most recent confirmed pivot low | Yes — rolling |
| `52w_low` | Date of 52-week low | Yes |
| `52w_high` | Date of 52-week high | Yes |
| `custom` | Any user-picked date | **No — computed on demand** |

### 6.4 Storage strategy — important
Anchored VWAP is O(bars since anchor) **per anchor**. Storing every possible anchor explodes the table.

**Rule:**
- **Precompute and store** only the 4 standard anchors above, and only for **active symbols**.
- **Compute on demand** (not stored) for user-picked anchors in the UI. It's a single cumulative sum — milliseconds.
- Prune `avwap` rows where `anchor_date` is older than 2 years.

### 6.5 Why it matters for your W-pattern
Anchor at **L1** (first low of the W). Price reclaiming that AVWAP means everyone who bought since the first bottom is now in profit. That is a materially stronger confirmation than a plain neckline break, and it is specific to your pattern.

---

## 7. Timeframe Construction (1W / 1M)

- Derive from `bars_1d`. **Do not store 1W/1M bars** — they would drift from the source.
- Group by **actual trading sessions**, never calendar dates. A Friday holiday makes naive `resample('W-FRI')` produce wrong weekly lows.
- Aggregation: `O` = first open, `H` = max high, `L` = min low, `C` = last close, `V` = sum, `vwap` = volume-weighted mean.
- Label by the **last trading day** of the period.
- **Drop the current in-progress week/month before scanning** — otherwise Wednesday's signal vanishes by Friday.
- Flag weeks with < 3 sessions; their pivots are unreliable.

### 7.1 Monthly history constraint
Monthly SMA200 needs ~17 years — most of your universe won't have it.

**Use SMA 12 / 24 / 36 on monthly instead** (1/2/3 years). Same purpose, actually available. Gate with `bars_available`.

---

## 8. Gap Handling (manual runs)

### 8.1 Principle
**No `last_updated_date` pointer.** A pointer is a second copy of the truth and it can lie:
- Crash mid-run → pointer advanced, only 800 of 2,000 symbols written. Silent hole.
- It cannot distinguish a holiday from a missed day.
- It is blind to interior holes (a batch that failed three months ago).

**The data is the state. Query it.**

### 8.2 The calendar anti-join

```sql
SELECT i.isin, c.date
FROM instruments i
CROSS JOIN trading_calendar c
LEFT JOIN bars_1d b ON b.isin = i.isin AND b.date = c.date
JOIN symbol_status s ON s.isin = i.isin
WHERE s.status = 'active'
  AND c.date BETWEEN i.first_seen AND current_date
  AND b.date IS NULL;
```

One query handles every case: 4 skipped days, holidays excluded, interior holes, fresh empty install. **One code path — no "backfill mode" vs "daily mode".**

### 8.3 Run sequence

```
1. Extend trading_calendar (probe bhavcopy for unknown dates)
2. Anti-join → missing (isin, date) set
3. Group into contiguous ranges → fetch min..max per symbol
4. UPSERT into bars_1d
5. Join bhavcopy enrichment columns for those dates
6. RE-RUN the anti-join → anything still missing = genuine failure, log it
7. Rebuild features for affected windows
8. Validate
9. Scan
```

**Step 6 is the important one.** Verify by re-asking the question, not by assuming step 4 worked.

### 8.4 Standing guards

**A. Always refetch the last 7 days**, even if not "missing". yfinance silently restates recent bars; the overwrite is free under the PK and self-heals bad data.

**B. Staleness guard before scanning:**
```
if MAX(date) in bars_1d != last trading day:
    ABORT loudly
```
Manual operation means you *will* one day scan on 4-day-old data. The scanner must refuse.

### 8.5 Dead symbols
- Delisted/suspended stocks appear "missing" forever. Left alone you'll make 200 pointless API calls per run within a year.
- After **10 consecutive misses** → `status = 'delisted'`, stop fetching.
- **Keep their history** — required for survivorship-free backtesting.
- Re-check delisted symbols monthly in case a suspension lifted.

---

## 9. Rebuild Policy

| Trigger | Action | Rationale |
|---|---|---|
| **Every run** | Recompute last **250 rows/symbol** | SMA200 needs 200 bars; 250 gives margin |
| **Weekly** | **Full rebuild from scratch** | Corporate actions retroactively change history; yfinance restates past bars. Incremental never catches this. |
| **Gap filled** | Rebuild from `min(filled_date)`, reading bars from `−250 trading days` | Filling a 4-day hole invalidates all features after it |
| **Any logic change** | Full rebuild + bump `feature_version` | Mixed-version features are silent poison in a backtest |
| **Gap older than 6 months** | Full rebuild | Cheaper than reasoning about it |

The **weekly full rebuild is the one most people skip**, and it's how wrong history quietly accumulates.

---

## 10. Accuracy Traps — checklist

### 10.1 Data
- [ ] `auto_adjust=False`; ignore `Adj Close`
- [ ] Bhavcopy reconciliation logged for every bar
- [ ] Bonus/split detection cross-checked against corporate actions file
- [ ] Universe built from **historical bhavcopies**, not today's `EQUITY_L.csv` (survivorship bias)
- [ ] EQ series only; ASM/GSM excluded
- [ ] Liquidity floor: turnover ≥ ₹5 cr/day (**not** a share-count filter — 100,000 shares of a ₹8 stock is nothing)
- [ ] Circuit-locked bars (`high == low == close`) excluded from pivot detection

### 10.2 Indicator maths — these three make your numbers differ from TradingView
- [ ] **ATR uses Wilder's RMA**, not SMA or EMA. `RMA = prev × (n−1)/n + current/n`. Get this wrong and **Supertrend flips on different days.**
- [ ] **Bollinger uses population stdev** (`ddof=0`). Pandas defaults to sample (`ddof=1`).
- [ ] **Supertrend must use locked bands** — final upper band only ratchets down while in downtrend. Unlocked versions produce noticeably more flips.

### 10.3 Warm-up periods

| Indicator | Bars to be *correct* |
|---|---|
| Bollinger(20,2) | ~25 |
| RSI(14) | ~100 |
| Supertrend(20,3) | ~100 |
| **ADX(14)** | **~150** (double-smoothed — this one bites people) |
| SMA200 | 200 |

**Discard the first 250 bars of every symbol's features.** They will have values; those values are wrong.

### 10.4 Backtesting
- [ ] **No look-ahead in pivot marking.** A pivot low with right-window N is only knowable N bars later. Mark it on the confirmation date, not the low date.
- [ ] Regime and RS filters evaluated as of the signal date, never restated
- [ ] Delisted symbols included in the universe

### 10.5 Validation discipline
Validate every indicator against TradingView on **3 stocks × 10 dates** before trusting it — the same discipline as the data layer.

For the ~5 indicators you actually depend on (Supertrend, ATR, ADX, HMA, ADR%), **hand-code them** rather than relying on `pandas-ta`. That's ~150 lines and permanently removes library version drift. Given accuracy is the stated priority, this is worth the afternoon.

---

## 11. W-Pattern Specification

### 11.1 Pivot detection
- Pivot low = candle whose Low is lower than **N** candles left and **N** right.
- `N = 3` on daily, `N = 2` on weekly/monthly.
- A pivot is **confirmed N bars later**. Never mark it earlier.

### 11.2 Pattern rules

| Rule | Default | Notes |
|---|---|---|
| Bottom tolerance | `abs(L2 − L1) ≤ 0.5 × ATR14` | **ATR-based, not a flat %** — adapts to each stock's own volatility |
| Undercut condition | `L2 < L1` | Your stated preference: second low undercuts the first |
| Reclaim condition | `close > L1` after L2 | Confirms the undercut was a shakeout |
| Bottom separation | 10–60 bars | Prevents counting one swing twice |
| Neckline | Highest high between L1 and L2 | |
| Volume tell | `vol(L2) < vol(L1)` | Optional; classic confirmation |
| Delivery tell | `deliv_pct(L2) > deliv_pct(L1)` | India-specific; accumulation into the second low |
| AVWAP confirm | `close > AVWAP(anchor = L1)` | See §6.5 |

### 11.3 Higher-leverage filters
These two were flagged as likely to affect hit-rate more than pattern parameter tuning:

- **`ADR% ≥ 2.5`** — a 1.2% ADR stock structurally cannot deliver 5% in 7 days without a gap.
- **ATR-based bottom tolerance** (above) instead of a fixed 3%.

---

## 12. Module Map

| Module | Responsibility | Depends on |
|---|---|---|
| `config.py` / `config.yaml` | All tunables, preset resolution, config hashing | — |
| `db.py` | DuckDB connection, full schema DDL | config |
| `indicators.py` | Hand-coded indicators (see §10.2) | — |
| `patterns.py` | Pivot detection, W-pattern, entry triggers, SMA classification | indicators |
| `universe.py` | Instrument master, ISIN mapping, ASM/GSM, liquidity filter | db |
| `ingest.py` | yfinance prices, bhavcopy enrichment, calendar anti-join gap fill | db, universe |
| `validate.py` | Bhavcopy reconciliation, staleness guard | db, ingest |
| `features.py` | Feature registry, dependency resolution, 2-pass compute | indicators, db |
| `scan.py` | Live scan, regime state, signal storage | patterns, features, validate |
| `backtest.py` | Entry/exit grid, exit simulation, forward curves, metrics | patterns, features |
| `journal.py` | Trade log, auto MAE/MFE, analytics, live-vs-backtest | db |
| `app.py` | Streamlit UI | everything |
| `test_core.py` | Unit tests for the accuracy-critical maths | indicators, patterns |

**The rule enforced by this layout:** `scan.py` and `backtest.py` both call `patterns.py`. Neither has its own copy of the pattern logic. If they ever diverge, backtest conclusions stop transferring to live trading.

---

## 13. Backtest Engine

### 13.1 Two-stage design

**Stage 1 — signal generation.** Pattern detection over stored features. Fast, reusable.
**Stage 2 — trade simulation.** Portfolio rules applied to those signals.

Split because changing "max 5 open positions → 8" should not re-run stage 1.

### 13.2 The three honesty rules

These are implemented in `simulate_exit()` and are not configurable away casually.

**1. Entry at the NEXT bar's open.**
The signal is computed after the close. Entering at the signal-day close is look-ahead.

**2. Stop and target touched on the same bar → assume the STOP was hit.**
Daily bars cannot resolve intraday order. Assuming target-first is the single most common way backtests inflate results, typically by 20–40%. Config key: `same_day_stop_and_target: "stop"`.

**3. Gap through the stop fills at the OPEN, not the stop price.**

### 13.3 Costs

Round-trip Indian delivery is ~0.25–0.35% plus slippage. Measured against the cost model in `config.yaml`:

| Gross gain | Costs as % of the gain |
|---|---|
| 2% | **~17%** |
| 5% | **~7%** |
| 10% | ~3.5% |

Slippage (default 0.15% each way) applies on top, at fill. A backtest without costs shows an edge that does not survive contact with reality — and the smaller your target, the more it matters.

### 13.4 Entry variants

| ID | Trigger | Trade-off |
|---|---|---|
| E1 | Next bar after confirmation | Earliest, most trades, most failures |
| E2 | Close above L1 (the reclaim rule) | Confirms the undercut was a shakeout |
| E3 | Close above neckline | Latest, best win rate, worst R:R |
| E4 | Close above SMA20 | Momentum confirmation |
| E5 | Close above AVWAP anchored at L1 | Everyone since the first bottom is in profit |

**Compare on expectancy, not win rate.** E3 will show the best win rate and may still be the worst choice, because most of the move has already been paid away.

### 13.5 Exit variants

| ID | Rule |
|---|---|
| X1 | Fixed % target |
| X2 | R-multiple target |
| X3 | Measured move (`neckline + (neckline − L2)`) |
| X4 | Trail below SMA(n) |
| X5 | ATR chandelier trail |
| X6 | Pure time stop, no target |

Trailing stops read **yesterday's** indicator value, never today's — otherwise the trail is look-ahead.

### 13.6 Deriving holding period from data

`analyse_curves()` returns, per day 1..N after entry:

| Column | How to read it |
|---|---|
| `median_mfe` | **Where this flattens IS the holding period** |
| `marginal_mfe` | Gain from one more day; ~0 means the edge is spent |
| `p85_mae_win` | **Stop candidate** — drawdown 85% of eventual winners never exceeded |
| `pct_positive` | Survival curve; sharp decay after day N → time stop is N |
| `p75_mfe` | What a good trade reaches |

Forward curves deliberately **ignore stops and targets**. You want to see what the move *does*, not what your current rules happen to capture.

### 13.7 Control-first methodology

`marginal_contribution()` runs the baseline, then each candidate, and reports deltas.

**Run `w_naked` first, always.** Without a control number, "W + SMA50 gives 48% win rate" is meaningless — you cannot tell whether the SMA helped, hurt, or did nothing. This is the step most people skip, and skipping it invalidates everything after it.

Read `trade_retention_pct` alongside `delta_expectancy`: a filter that lifts expectancy but cuts trades from 800 to 40 has found a coincidence, not an edge.

### 13.8 Overfitting guardrails

With ~15 toggles there are ~32,768 combinations. Some will look spectacular purely by chance.

1. **In-sample ends 2020-12-31. Out-of-sample starts 2021-01-01.** Tune on in-sample only.
2. **Minimum 100 trades** (`min_trades_for_conclusion`) before believing anything. The app warns below this.
3. **Prefer plateaus over peaks.** If ADR ≥ 2.5 works and 2.4 and 2.6 also work, that is real. If 2.5 works and 2.4 fails badly, that is curve-fitting.
4. **Test combinations you have a reason for.** 30 grid cells with a rationale, not 5,000 by brute force.
5. **Every run is logged** with its `config_hash`. The count of runs is itself your overfitting risk.

> Honest note: the engine is easy. The discipline is not. This is where self-built scanners usually go wrong.

### 13.9 Expectation setting

The naked W-pattern will probably show a weak or negative edge. Almost all standalone chart patterns do. **The value is in discovering which *slice* works** — at the 200 DMA, in a bull regime, with rising delivery. Go in expecting to find a subset, not a universal edge.

---

## 14. Trade Journal

### 14.1 The core idea

Every entry carries `signal_id`, linking back to the scan that produced it. That join answers *"which preset actually makes money"* — unanswerable from a spreadsheet that lives apart from the screener.

### 14.2 Auto-computed, never typed

- **MAE** (worst drawdown while held) → is your stop too tight?
- **MFE** (best unrealised gain) → are you exiting too early?

Both are derived from `bars_1d`. You already own the price history.

### 14.3 R-multiple as the primary unit

`R = (exit − entry) / (entry − stop)`. Makes every trade comparable regardless of size.
`Expectancy = win% × avg_win_R − loss% × avg_loss_R`. That one number says whether the system is viable.

### 14.4 Feature snapshot at entry

`snapshot_features()` freezes the feature vector when the trade opens. Six months later, *"do my winners have higher delivery % than my losers?"* is answerable — but only if it was captured at the time. Reading today's values would be meaningless.

### 14.5 Analytics provided

| Function | Question answered |
|---|---|
| `adherence_report()` | Did following the plan pay? (usually the most uncomfortable table) |
| `preset_attribution()` | Which preset earns its place |
| `tag_analysis()` | Where the behavioural leaks are |
| `snapshot_analysis()` | Do winners differ on metric X? |
| `compare_with_backtest()` | Execution gap vs logic gap |

### 14.6 The feedback loop

`compare_with_backtest()` is the payoff:

| Observation | Diagnosis |
|---|---|
| Backtest 45% win rate, you 32% | **Execution gap**, not a logic problem |
| Backtest holds 7 days, you hold 3 | **You are exiting early** |
| Backtest MAE 1.8%, yours 0.9% | **You are stopping out on noise** |

The backtest says what the logic can do. The journal says what you did. The gap is where the money is.

### 14.7 Missed trades

`log_missed()` records signals you saw and skipped, with a reason. Most traders skip their best setups; without this you never find out.

---

## 15. User Interface

### 15.0 v2 — NiceGUI rebuild (branch `v2-ui`, in progress)

**v1 (Streamlit, `app.py`) is preserved on `main` as the working fallback** — `git checkout main && streamlit run app.py` always gets it back. v2 is a ground-up rebuild on branch `v2-ui`, built screen-by-screen per `docs/v2_instructions.md`, each screen committed once it passed available verification. Not yet merged to `main`; pending the user's own browser click-through (no browser-automation tool was available while building it — every screen was verified by isolated server-side render checks and, where the logic could be exercised directly, by calling it outside the UI entirely. See §18 for exactly what was and wasn't confirmed this way).

**Eight screens**, left-drawer nav (collapsible, state persisted in `ui_prefs`): Today (default landing) · Scan · Chart · Watchlist · Holdings · Performance · Backtest · Data.

- **Today** — status, open positions with advisor reasons, new opportunities, P&L, watchlist near-trigger. Reads the *last persisted* `signals_1d` scan rather than running a live scan, specifically to hit the "loads in under 2s" requirement — measured 0.23–0.34s.
- **Chart** — D/W/M timeframes and Candle/Line/Heikin Ashi/Renko chart types, all resampled server-side (`resample.py`) so no indicator or transform math runs in JavaScript. A vendored `klinecharts` 10.0.2 (no CDN, per the offline requirement) renders candles; drawings (horizontal line, trend line, ray, rectangle, fibonacci retracement, text) persist per `(isin, timeframe)` in a new `drawings` table. W-pattern L1/L2/neckline markers and AVWAP are computed server-side and injected as overlays tagged `groupId="server"`, so they're never mistaken for — or saved back as — user drawings.
- **Scan** — runs `scan.scan(apply_preset=False)` once per click (a superset with every `features_1d` column attached), then filters that cached DataFrame in-memory as filter chips (declared in `config.yaml`, not Python) are toggled — no re-scan per chip change.
- **Watchlist / Holdings** — manual entry only (no broker fetch). Every position card's numbers come from one `advisor.position_status()` call, so the card and its stated reasons can never disagree.
- **Performance** — equity curve, attribution by preset/timeframe/sector, adherence and behaviour-tag analysis, live-vs-backtest comparison. "By where the second bottom formed" was dropped after discovering the live `trades` table never actually captures `bottom_at_sma` (categorical fields aren't in journal.py's entry-snapshot) — flagged explicitly in the UI rather than faked.
- **Backtest / Data** — ported from v1 behaviour-unchanged, rebuilt against the same `backtest.py`/`table_counts()` functions.

New, additive-only backend support: `resample.py` (weekly/monthly bar grouping — by actual trading sessions, not calendar dates, so a holiday-shortened week doesn't manufacture a wrong low; Heikin Ashi; Renko with the standard 2-brick reversal rule), `watchlist.py`, `advisor.py` (descriptive-only position status — never "will"/"expect"/"likely", never a price prediction; if no backtest exists for a preset it says exactly that), and `scan.scan(..., apply_preset=False)`. `db.py` gained three new tables (`watchlist`, `drawings`, `ui_prefs`) and `trades.timeframe`, appended to the existing schema — nothing existing was altered.

### 15.1 One deliberate design decision (carries over to v2)

**The data-health strip sits above everything, always visible.** Accuracy is this project's stated priority, so the interface makes data trustworthiness the first thing on screen rather than burying it in a settings page.

- Green left edge → current, safe to scan.
- Red left edge → stale; nothing below it should be traded.
- Shows: latest bar, last trading day, row counts, validation failures in the last 7 days.

### 15.2 Filters are toggles, not code

Relative strength and the regime filter are switches in the sidebar (v1) / Scan screen (v2), **off by default**, so they can be A/B tested honestly. The underlying index data is fetched and stored regardless — you cannot test a filter you have no data for. v2 extends this: Scan-screen filter chips are declared entirely in `config.yaml`'s `filter_chips:` block — adding one never requires a Python change.

### 15.3 Backtest

Three modes: single run, entry × exit sweep, marginal contribution. Trade counts are shown next to every statistic, and results below `min_trades_for_conclusion` are flagged as noise rather than presented as findings.

---

## 16. Broker Integration (deferred)

Not in v1. Recorded here so the design does not have to change later.

### 16.1 What is known

- **Dhan's Order APIs are free** (limits: 10/sec, 250/min, 7,000/day). The ₹499/mo subscription covers *Data* APIs only.
- **SEBI's retail algo framework** (Feb 2025 circular) became mandatory for all brokers from **1 April 2026**. API-based strategies are treated as algo trading and are not exempt. Orders placed by an algorithm require an exchange-issued **Algo-ID**; brokers must block non-whitelisted/dynamic IPs; OAuth 2FA and auto-logout before pre-open are required.
- The registration threshold is **10 orders/sec per exchange** — far above a swing trader's volume.

### 16.2 The intended path

**Semi-automatic.** The app prepares the order (symbol, qty, price, stop); the user clicks to submit. That is a person trading with a tool, not an unattended algorithm.

**Confirm the specific setup with Dhan's API support before wiring execution.** The direct question: *"does a manual-click order originating from my own script require an Algo-ID?"* This is not legal advice and the rules are still settling.

### 16.3 Design constraints (apply whenever this is built)

- `broker.py` stays **completely separate** from `scan.py`. Execution never touches scan logic.
- `paper_mode: true` is the default; orders go to a simulated fill table until explicitly flipped.
- Hard rails **in code**: max orders/day, max position size %, max open positions, per-trade capital cap, kill switch.
- API keys in a gitignored `.env`, never in `config.yaml`.
- Log every order request and response — now a regulatory expectation, not just hygiene.

### 16.4 Sequencing rationale

**Journal before broker integration.** The journal makes money by revealing which presets work and where you leak. Broker integration only makes you faster — and faster execution of an unvalidated edge loses money more efficiently.

Order: **scanner → journal → 3 months of real data → broker integration.**

---

## 17. Build Order & Verification Gates

| # | Module | Verify before proceeding |
|---|---|---|
| 1 | `db.py` / schema | Tables exist, primary keys enforced |
| 2 | `test_core.py` | **45 passed, 0 failed** |
| 3 | `universe.py` | ~1,800–2,200 instruments, no duplicate ISINs |
| 4 | `ingest.py` | **Run it twice → second run adds zero rows** (proves idempotency) |
| 5 | `validate.py` | Failure rate < 0.5%; investigate every 15%+ flag |
| 6 | `features.py` | **3 stocks × 10 dates checked against TradingView** |
| 7 | `scan.py` | Eyeball 10 signals on real charts |
| 8 | `backtest.py` | Control (`w_naked`) run before any filtered variant |
| 9 | `app.py` | Health strip green |

**Verify the data layer before writing or trusting any pattern logic.** Bad data produces confident, plausible, wrong signals — and they are indistinguishable from good ones.

---

## 18. Change Log

| Date | Section | Change | Reason |
|---|---|---|---|
| 12 Aug 2026 | — | Initial design | Chartink replacement, accuracy-first |
| 12 Aug 2026 | §1.5 | Dropped 1h/4h from v1 | Eliminates intraday corporate-action adjustment; broker intraday data is unadjusted |
| 12 Aug 2026 | §3.1 | Dhan → yfinance + bhavcopy | Dhan Data API is ₹499/mo; daily-only does not need it |
| 12 Aug 2026 | §2 | DuckDB over ArcticDB/Parquet/SQLite | Dataset fits in RAM; SQL matters more than raw speed for validation queries |
| 12 Aug 2026 | §8.1 | Anti-join over `last_updated_date` | Pointer cannot see interior holes or distinguish holidays |
| 12 Aug 2026 | §5 | Feature registry + YAML presets | Requirement: test arbitrary indicator combinations without code edits |
| 12 Aug 2026 | §6 | Anchored VWAP added | Daily VWAP from bhavcopy enables this; edge over typical daily scanners |
| 12 Aug 2026 | §13 | Backtest engine specified and built | Requirement: derive entry/exit/holding period from data, not assumption |
| 12 Aug 2026 | §14 | Trade journal specified and built | Closes the loop between scanner and outcome |
| 12 Aug 2026 | §15 | Streamlit chosen for UI | Pure Python, no build step, reuses the data layer directly |
| 12 Aug 2026 | §16 | Broker integration deferred | Not an algo trader; SEBI framework mandatory from Apr 2026; edge unvalidated |
| 12 Aug 2026 | §10.2 | Indicators hand-coded, not pandas-ta | Wilder RMA / population stdev / locked Supertrend bands decide whether numbers match TradingView; library versions drift on all three |
| 13 Aug 2026 | §15 | v2 UI rebuild started on branch `v2-ui`: NiceGUI, 8 screens (Today/Scan/Chart/Watchlist/Holdings/Performance/Backtest/Data) | User-directed rebuild (`docs/v2_instructions.md`); v1 (Streamlit) kept on `main` as the revert path throughout |
| 13 Aug 2026 | §4 | Added `watchlist`, `drawings`, `ui_prefs` tables + `trades.timeframe`, additive only | v2 UI needs watchlist state, persisted chart drawings, and drawer/nav prefs |
| 13 Aug 2026 | §15 | Vendored `klinecharts` 10.0.2 locally for the Chart screen, no CDN | Offline-only requirement; API verified against the package's own `index.d.ts` (v10 replaced `applyNewData`/`updateData` with an async `setDataLoader`, and there is no chart-level "overlay changed" event — `overrideOverlay`'s per-overlay callbacks are the real mechanism) |
| 13 Aug 2026 | §14 | `advisor.py` added: descriptive-only position status (HOLD/WATCH/REVIEW), 6 rules, every statement cites a real backtest_curves/backtest_metrics number | Holdings/Today screens need timing guidance without ever predicting a price or outcome |
| 13 Aug 2026 | §15 | Dropped "by bottom_at_sma" from the live Performance attribution | `trades` never captured this field (categorical, not in journal.py's numeric entry-snapshot) and `signal_id` isn't an actual foreign key into `signals_1d` — rather than fake the cut, it's labelled unavailable and points at the backtest's own slicing instead |

---

## 19. Open Decisions

| # | Decision | Status |
|---|---|---|
| 1 | Backfill start year (2010 default — earlier for monthly W-patterns?) | Open |
| 2 | Monthly timeframe: confirm SMA 12/24/36 instead of 200 | Open |
| 3 | Weekly/monthly feature tables (`features_1w`, `features_1m`) — schema exists, resampler not yet built | **Deferred to v1.1** |
| 4 | Sector concentration warning at entry | Deferred to v2 |
| 5 | Broker execution | Deferred — see §16 |

---

*End of document.*
