# HOW TO RUN

Operational guide. For *why* things are built this way, see `SCANNER_DESIGN.md`.

---

## Part 1 — One-time setup

### 1.1 Install Python

- Get **Python 3.11 or 3.12** from [python.org](https://www.python.org/downloads/).
- **Not the Microsoft Store version** — it sandboxes file paths and will fight your `D:\Work\kTradeApps\kScanner\nse_scanner\` folder.
- During install, tick **"Add Python to PATH"**.

Verify:
```cmd
python --version
```

### 1.2 Create the folders

**Where the zip goes.** The zip already contains a top-level `nse_scanner\` folder, so extract it into the *parent* directory:

```
Extract nse_scanner.zip  ->  D:\Work\kTradeApps\kScanner\
```

That produces your base folder. Do **not** extract into `nse_scanner\` itself, or you will end up with `nse_scanner\nse_scanner\`.

Final layout:

```
D:\Work\kTradeApps\kScanner\nse_scanner\
├── README.md
├── SCANNER_DESIGN.md
├── db\            <-- created below (market.duckdb lives here)
├── raw\           <-- bhavcopy zips, universe snapshots (your audit trail)
├── logs\
├── exports\       <-- xlsx / csv scan output
└── src\           <-- all the code, already in the zip
```

The zip ships `src\` and the docs. Create the four data folders:

```cmd
cd /d D:\Work\kTradeApps\kScanner\nse_scanner
mkdir db raw logs exports
```

> **Do not put `D:\Work\kTradeApps\kScanner\nse_scanner\` inside OneDrive or Google Drive.** Sync-while-writing corrupts DuckDB files. Back up by copying the `.duckdb` file out on a schedule instead.

### 1.3 Create the environment and install

```cmd
cd D:\Work\kTradeApps\kScanner\nse_scanner\src
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

If a downloaded `.py` file refuses to run, Windows has blocked it: right-click → Properties → tick **Unblock**.

### 1.4 Check the config

Open `src\config.yaml`. It is already set to your folder — just confirm it matches:

```yaml
paths:
  root: "D:/Work/kTradeApps/kScanner/nse_scanner"        # forward slashes are fine on Windows
```

Everything else has working defaults. If you ever move the project, this one line is the only path you need to change.

### 1.5 Verify the maths before trusting anything

```cmd
python test_core.py
python test_resample.py
python test_advisor.py
python test_features.py
python test_api.py
```

Expected: **46 passed** (`test_core.py`), **13 passed** (`test_resample.py`), **15 passed** (`test_advisor.py`), **9 passed** (`test_features.py`), **104 passed** (`test_api.py`), 0 failed across all five. `test_core.py` checks Wilder's RMA, population stdev, locked Supertrend bands, anchored VWAP, pivot detection, and the look-ahead guard — if any of these fail, stop, every number downstream would be wrong. `test_resample.py` checks the D/W/M and Heikin Ashi/Renko chart transforms; `test_advisor.py` checks the position-status rules never invent a number or predict a price; `test_features.py` checks the daily incremental windowing never rewrites an already-correct historical row with a value re-derived from a shorter window (a real bug this project shipped and caught pre-production — see SCANNER_DESIGN.md's 14 Aug 2026 changelog entry); `test_api.py` exercises every FastAPI router in-process (`TestClient`, real DB), including the built-mode SPA fallback.

---

## Part 2 — First run (the backfill)

Run these **in order**. Each depends on the one before it.

### Step 1 — Build the universe

```cmd
python universe.py
```

Downloads `NSE_STOCKS_LIST.csv.csv` and the ASM/GSM surveillance lists, then populates `instruments`.

Already have an NSE_STOCKS_LIST.csv.csv?
```cmd
python universe.py --local-csv "D:\Work\kTradeApps\kScanner\nse_scanner\raw\NSE_STOCKS_LIST.csv"
```

**Verify:** should report roughly 1,800–2,200 instruments.

### Step 2 — Backfill prices

```cmd
python ingest.py --backfill --start 2010-01-01
```

**This takes hours.** yfinance is throttled to ~50 tickers per batch with a 1.5s pause — deliberately, because unthrottled loops get blocked mid-run.

It is **resumable**. If it dies, just run it again: the calendar anti-join works out what is still missing. There is no separate "resume" flag.

**Verify:**
```cmd
python -c "import duckdb;c=duckdb.connect('D:/Work/kTradeApps/kScanner/nse_scanner/db/market.duckdb');print(c.execute('SELECT COUNT(*), MIN(date), MAX(date) FROM bars_1d').fetchall())"
```

### Step 3 — Validate against the official bhavcopy

```cmd
python validate.py --days 5
```

**Do not skip this.** It reconciles yfinance against NSE's own numbers.

- Failure rate under 0.5% → fine.
- Anything flagged at 15%+ → yfinance almost certainly missed a bonus or split. Those manufacture textbook fake W-bottoms. Investigate before trading that symbol.

### Step 4 — Build features

```cmd
python features.py --full
```

Computes every enabled indicator. Takes 10–30 minutes for a full universe.

Optional: `python features.py --full --timeframe 1w` / `1m` build `features_1w`/`features_1m` the same way, from bars_1d resampled to weekly/monthly (see "Pending features" — scanning against them isn't wired up yet, only the Chart screen uses them so far).

### Step 5 — First scan

```cmd
python scan.py --preset w_baseline --export
```

### Step 6 — Launch the app

```cmd
cd D:\Work\kTradeApps\kScanner
dev.bat
```

Starts the FastAPI backend (`:8000`) and the React frontend (`:5173`) together, killing anything already running on those ports first. Opens at `http://localhost:5173`. Eight screens on the left: Today (default landing) · Scan · Chart · Watchlist · Holdings · Performance · Backtest · Data.

(The old NiceGUI app is retired — `git checkout v2-nicegui` restores it if you ever need to compare against the pre-React version.)

---

## Part 3 — Daily use

You run this manually. **It does not matter if you skip days.**

```cmd
cd D:\Work\kTradeApps\kScanner\nse_scanner\src
run_daily.bat
```

That runs: universe → ingest → validate → features.

Skipped four days? The calendar anti-join finds exactly what is missing — holidays correctly excluded — and fills it. Same command. There is no catch-up mode because there is no need for one.

Then:
```cmd
cd D:\Work\kTradeApps\kScanner
dev.bat
```

### Weekly — do not skip this

```cmd
run_weekly.bat
```

Full feature rebuild. Corporate actions retroactively change history and yfinance silently restates past bars; incremental updates catch neither. **This is how wrong history quietly accumulates in most home-built scanners.** Sunday is a good habit.

---

## Part 4 — The backtest study

Run these in order. The order is the method, not a suggestion.

### 4.1 The control — always first

```cmd
python backtest.py --preset w_naked --entry E2 --exit X1 --limit 200
```

`--limit 200` gives you a fast trial run. Drop it for the real thing.

**Without this baseline number, no result below means anything.** You cannot tell whether a filter helped, hurt, or did nothing.

### 4.2 Does each SMA filter actually add anything?

```cmd
python backtest.py --marginal
```

Prints baseline vs each SMA variant with deltas. Read it like this:

| Column | What it tells you |
|---|---|
| `delta_expectancy` | Did the filter improve the edge? |
| `trade_retention_pct` | What fraction of trades survived? |
| `enough_trades` | `False` = below 100 trades = **noise, not a result** |

> A filter that lifts expectancy but cuts trades from 800 to 40 has not helped you. It has found a coincidence.

### 4.3 Find your real entry, exit and holding period

```cmd
python backtest.py --preset w_baseline --sweep
```

30 cells (5 entries × 6 exits). Sorted by expectancy — **check the trade count before believing the top row.**

Then for the winning cell, look at the curves:

```cmd
python backtest.py --preset w_baseline --entry E2 --exit X1
```

The curve table is the answer to "how long should I hold?":

| Column | How to read it |
|---|---|
| `median_mfe` | **Where this flattens is your holding period** |
| `marginal_mfe` | Gain from one more day. When it reaches ~0, the edge is spent |
| `p85_mae_win` | **Set your stop just past this** — the drawdown 85% of winners never exceeded |
| `pct_positive` | Survival curve. Sharp decay after day N → time stop is N |

This is how you *derive* your rules instead of assuming them.

### 4.4 The out-of-sample check — once, at the very end

```cmd
python backtest.py --preset w_full --entry E2 --exit X1 --sample out
```

Pick your final 2–3 candidates. Run this **once**. If you run it repeatedly while tuning, it stops being out-of-sample and you have simply overfit a larger dataset.

---

## Part 5 — Adding your own combinations

Edit `config.yaml`. **Never edit Python for this.**

```yaml
presets:
  my_idea:
    inherits: w_baseline
    conditions_add:
      - "close > sma50"
      - "rsi14 < 45"
      - "deliv_pct_sma20 >= 50"
```

Available columns are the `features_1d` columns: `sma10/20/50/100/200`, `sma50_slope`, `sma200_slope`, `sma_stack`, `sma_compression`, `atr14`, `adr_pct20`, `rsi14`, `adx14`, `rvol`, `turnover_sma20`, `deliv_pct_sma20`, `dist_sma200_pct`, `rs_rank_pct`, plus `close`/`high`/`low`/`volume`.

Then:
```cmd
python backtest.py --preset my_idea
```

### Turning indicators on and off

```yaml
features:
  enabled:
    - sma50
    - supertrend       # atr14 is pulled in automatically
    # - bollinger      # commented out = not computed, not stored
```

After changing this list:
```cmd
python features.py --full
```

Required — the feature version changes, and mixing versions inside one backtest is silent poison.

---

## Using the Scan screen

The Scan screen (left nav) is the day-to-day way to find candidates — the CLI (`scan.py`, Part 4/5) is for the backtest study, this is for "what looks tradeable right now." It scans the whole universe once and lets you slice the result instantly with chips, rather than re-scanning per filter change.

**Controls:**

| Control | What it does |
|---|---|
| **Preset** | Which `config.yaml` preset's conditions to apply (`w_naked`, `w_baseline`, `w_sma200_trend`, …) plus the hard tradability filters (EQ series, ASM/GSM excluded, minimum liquidity) that always apply regardless of preset. |
| **D / W / M** | Scan daily, weekly, or monthly bars — same pattern code, resampled bars (see `resample.py`), against `features_1d`/`features_1w`/`features_1m` respectively. A preset that checks `sma200` will find fewer monthly signals for younger symbols — see Pending Features. |
| **Run scan** | Runs pattern detection across the full universe once, at that preset+timeframe. The result is cached — a preset+timeframe already scanned earlier the same trading day comes back instantly instead of re-scanning (see `scan_result_cache` below). |
| **Filter chips** | Toggle on/off, filtered against the SAME cached result in-memory — no re-scan per click. Each chip mirrors a real preset condition (e.g. `above_sma200` ↔ `close > sma200`), so running a preset auto-selects the matching chips. |
| **Save these chips as a preset** | Writes your current active chip conditions to `config.yaml`'s `presets:` block under a name you choose (letters/numbers/underscore only) — the same file Part 5 describes editing by hand. |

**Filter chips available:**

| Chip | Condition | Notes |
|---|---|---|
| Close > SMA200 / SMA50 | `close > sma200` / `close > sma50` | Trend filters |
| SMA200 rising | `sma200_slope > 0` | Long-term trend still rising, not just above |
| SMAs stacked up | `sma_stack = 'stacked_up'` | 10>20>50>100>200 in order |
| Bottom at SMA200 | `bottom_at_sma = 'at_sma200'` | Where the pattern's L2 formed relative to major SMAs |
| RSI > / RSI < | `rsi14 > N` / `rsi14 < N` | Adjustable threshold |
| ADX > | `adx14 > N` | Trend strength |
| ADR% > | `adr_pct20 > N` | Average daily range — volatility floor |
| Delivery% > | `deliv_pct_sma20 > N` | Real buying, not just churn |
| Turnover ≥ ₹cr | `turnover_sma20 > N*1cr` | Liquidity floor |
| RS rank > | `rs_rank_pct > N` | Relative strength vs the benchmark, percentile |
| RVOL > | `rvol > N` | Relative volume vs its own recent average |

**Why re-scanning the same thing is now instant:** every "Run scan" result is saved to a `scan_result_cache` table keyed by (preset, timeframe, trading day) — a re-run of the same combination later the same day is a cache hit, not a fresh universe scan. The backend also pre-warms `config.yaml`'s `startup_warm_scans` list in the background when it starts, so the presets you use most are often already cached before you ask. On this reference machine a full-universe daily scan takes roughly 1–2 minutes; because that work competes with the app's own request handling for CPU time (a known Python threading trade-off, not a bug), the very first warm-up after a fresh start can take noticeably longer than a scan you trigger yourself — it still finishes in the background without blocking the app either way.

---

## Using the Backtest screen

The Backtest screen has its own in-app "How to backtest" explanation (expand it at the top of the screen) covering the same ground as this section — this is the reference copy.

A backtest replays the exact W-pattern detector the Scan screen uses against history, applies an **entry rule** (when to buy) and an **exit rule** (when to sell), and reports what would have happened.

**Entry rules** (`patterns.py::find_entry_trigger`):

| Rule | Fires when |
|---|---|
| E1 | Next bar after the W confirms — earliest, most trades, most failures |
| E2 | Close above L1 (the "reclaim" rule) — shakeout confirmed. **Default, best-tested.** |
| E3 | Close above the neckline — latest, best win rate, worst reward:risk |
| E4 | Close above SMA20 — momentum confirmation |
| E5 | Close above an anchored VWAP from L1 |

**Exit rules** (`backtest.py::simulate_exit`):

| Rule | Behavior |
|---|---|
| X1 | Fixed % target (`backtest.target_pct`) |
| X2 | R-multiple target — a fixed multiple of initial risk (`backtest.target_r`) |
| X3 | Measured move — neckline + (neckline − L2), the classic W-pattern target |
| X4 | Trail below a moving average (`backtest.trail_sma`) |
| X5 | ATR chandelier trail — trails a multiple of ATR below the running high |
| X6 | Pure time stop — exits after `backtest.time_stop_bars`, no price target |

**The three run modes, and the recommended order:**

1. **Single run, preset `w_naked`** — no filters at all. This is the control. Without this baseline you cannot tell whether any filter helps or just looks good.
2. Check the **trade count** shown after any run — below `backtest.min_trades_for_conclusion` (100), treat the result as noise, not a conclusion.
3. **Sweep** a preset — runs all 5 entry × 6 exit combinations (30 backtests), sorted by expectancy, trade count included so a lucky small sample doesn't fool you.
4. **Marginal contribution** — runs the baseline plus each SMA/volume filter preset with the same entry/exit, showing the delta vs baseline. A filter that lifts expectancy but guts trade count has found a coincidence, not an edge.
5. **Out-of-sample, once** — only after you've settled on a preset/entry/exit using in-sample data (`backtest.in_sample_end` and later). Checking it more than once and adjusting turns it back into in-sample tuning wearing a disguise.

**Other fields:** **Sample** picks in-sample vs out-of-sample date ranges (`backtest.in_sample_end`/`out_sample_start` in `config.yaml`). **Limit symbols** caps how many universe symbols are scanned, purely to get a fast trial run while checking a setup works — drop it for a real read.

---

## Part 6 — Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `STALE DATA — latest stored bar is…` | You have not ingested recently | Run `run_daily.bat`. This guard is deliberate — it stops you acting on signals that are no longer true. |
| Bhavcopy downloads all fail | NSE changed the URL | Update `BHAV_URL_TMPL` in `ingest.py`. This *will* happen eventually. |
| yfinance returns nothing mid-run | Rate limited | Raise `ingest.yf_sleep_seconds` to 3.0, rerun. It resumes automatically. |
| Scan returns zero signals | Filters too tight, or features not built | Try `--preset w_naked` first to isolate which. |
| Indicators do not match TradingView | Warm-up region | The first 250 bars per symbol are discarded by design. Check `bars_available`. |
| Many symbols with `consecutive_misses` | Delisted, or symbol renamed | Expected. They auto-retire after 10 misses; history is kept. |
| `features.py --full` is very slow | Full universe, full history, by design | Normal — 10–30 min. Use `--symbol RELIANCE` to debug one name. Daily incremental (`python features.py`, no `--full`) is NOT this slow — it only fetches/recomputes a trailing window per symbol and writes rows strictly newer than what's already stored, so a same-day rerun with no new bars touches nothing. |
| App shows 0 rows everywhere | Wrong `paths.root` | Check `config.yaml` matches your actual folder. |
| `SSLCertVerificationError` from `universe.py` / `validate.py` (uses `requests`) | Antivirus HTTPS scanning (AVG, Avast, Kaspersky, etc.) re-signs traffic with its own root cert, which Windows trusts but Python's `requests`/`certifi` does not | `pip install pip-system-certs` in the venv — makes `requests` trust whatever Windows already trusts. |
| `curl: (60) SSL certificate ... unable to get local issuer certificate` from `ingest.py` (yfinance) | Same AV interception, but yfinance's `curl_cffi` backend ships its own TLS stack — `pip-system-certs` does not reach it | Build a combined CA bundle and point `curl_cffi` at it: <br>1. Export your AV's root cert (Windows: `Cert:\LocalMachine\Root`, find the one with "generated by ... for SSL/TLS scanning" in its subject) to PEM. <br>2. `cat <certifi_cacert.pem> your_av_root.pem > raw/combined_ca_bundle.pem` (find certifi's path with `python -c "import certifi;print(certifi.where())"`). <br>3. Set `CURL_CA_BUNDLE` and `SSL_CERT_FILE` env vars to that combined file before running any script that touches yfinance. `run_daily.bat`/`run_weekly.bat` already do this automatically if `raw/combined_ca_bundle.pem` exists. <br>Regenerate the bundle if your AV rotates its root cert. |

### Reading the health strip

The bar at the top of the app is the first thing on screen on purpose.

- **Green left edge** → data is current, safe to scan.
- **Red left edge** → stale. Nothing below it should be traded.
- **validation fails (7d)** → should be 0 or near it. Rising numbers mean the data layer needs attention before the signals do.

---

## Pending features

Known gaps, not yet built:

- `features_1m` will stay sparse or empty for most symbols even after a rebuild — its warm-up margin is 250 *monthly* bars (~20 years), the same bar-count safety rule daily features use, applied honestly rather than shortened for convenience. Symbols without decades of daily history simply won't clear it yet — so a monthly scan or backtest preset that checks `sma200` will legitimately find little to nothing for younger symbols.
- Weekly/monthly features don't get a relative-strength rank (`rs_rank_pct` stays NULL there) — cross-sectional ranking needs a benchmark series and lookback tuned per timeframe, not yet built.

---

## Command reference

```cmd
python universe.py                                  # refresh instruments + ASM/GSM
python universe.py --local-csv PATH                 # use your own EQUITY_L.csv

python ingest.py                                    # daily update / fill any gaps
python ingest.py --backfill --start 2010-01-01      # first-time full history

python validate.py --days 1                         # reconcile vs bhavcopy
python validate.py --days 5                         # wider check

python features.py                                  # incremental rebuild (features_1d)
python features.py --full                           # weekly full rebuild (features_1d)
python features.py --full --timeframe all           # full rebuild, 1d + 1w + 1m
python features.py --full --timeframe 1w            # features_1w only
python features.py --symbol RELIANCE                # debug one name

python scan.py --preset w_baseline --export         # scan + write xlsx
python scan.py --preset w_naked --ignore-stale      # override the guard

python backtest.py --preset w_naked                 # single run + curves
python backtest.py --marginal                       # do the SMA filters help?
python backtest.py --preset w_baseline --sweep      # entry x exit grid
python backtest.py --preset w_full --sample out     # out-of-sample, ONCE

python test_core.py                                 # verify the maths
python test_resample.py                             # verify D/W/M and chart-type transforms
python test_advisor.py                              # verify the position-status rules
python test_features.py                             # verify incremental windowing never rewrites a stored row
python test_api.py                                  # verify every FastAPI router in-process

cd D:\Work\kTradeApps\kScanner && dev.bat            # the UI (backend :8000 + frontend :5173)
```

---

## The one-paragraph version

Run `run_daily.bat`, then `dev.bat` from `D:\Work\kTradeApps\kScanner`. Skipped days fix themselves. Run `run_weekly.bat` on Sundays. Before you trust any backtest number, run the `w_naked` control first and check the trade count is above 100.
