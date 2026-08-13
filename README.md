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
```

Expected: **46 passed** (`test_core.py`), **13 passed** (`test_resample.py`), **15 passed** (`test_advisor.py`), 0 failed across all three. `test_core.py` checks Wilder's RMA, population stdev, locked Supertrend bands, anchored VWAP, pivot detection, and the look-ahead guard — if any of these fail, stop, every number downstream would be wrong. `test_resample.py` checks the D/W/M and Heikin Ashi/Renko chart transforms; `test_advisor.py` checks the position-status rules never invent a number or predict a price.

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

### Step 5 — First scan

```cmd
python scan.py --preset w_baseline --export
```

### Step 6 — Launch the app

```cmd
cd web
python main.py
```

Opens at `http://localhost:8080`. Eight screens on the left: Today (default landing) · Scan · Chart · Watchlist · Holdings · Performance · Backtest · Data.

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
cd web
python main.py
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

## Part 6 — Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `STALE DATA — latest stored bar is…` | You have not ingested recently | Run `run_daily.bat`. This guard is deliberate — it stops you acting on signals that are no longer true. |
| Bhavcopy downloads all fail | NSE changed the URL | Update `BHAV_URL_TMPL` in `ingest.py`. This *will* happen eventually. |
| yfinance returns nothing mid-run | Rate limited | Raise `ingest.yf_sleep_seconds` to 3.0, rerun. It resumes automatically. |
| Scan returns zero signals | Filters too tight, or features not built | Try `--preset w_naked` first to isolate which. |
| Indicators do not match TradingView | Warm-up region | The first 250 bars per symbol are discarded by design. Check `bars_available`. |
| Many symbols with `consecutive_misses` | Delisted, or symbol renamed | Expected. They auto-retire after 10 misses; history is kept. |
| `features.py` is very slow | Full universe, full history | Normal — 10–30 min. Use `--symbol RELIANCE` to debug one name. |
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

- `features_1w`/`features_1m` are empty — weekly/monthly indicator values (SMA, RSI, etc.) were never populated, only OHLCV bars. The Today screen's medium/long-term opportunity sections detect this and say "not built yet" rather than reporting zero signals.

---

## Command reference

```cmd
python universe.py                                  # refresh instruments + ASM/GSM
python universe.py --local-csv PATH                 # use your own EQUITY_L.csv

python ingest.py                                    # daily update / fill any gaps
python ingest.py --backfill --start 2010-01-01      # first-time full history

python validate.py --days 1                         # reconcile vs bhavcopy
python validate.py --days 5                         # wider check

python features.py                                  # incremental rebuild
python features.py --full                           # weekly full rebuild
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
cd web && python main.py                            # the UI
```

---

## The one-paragraph version

Run `run_daily.bat`, then `cd web && python main.py`. Skipped days fix themselves. Run `run_weekly.bat` on Sundays. Before you trust any backtest number, run the `w_naked` control first and check the trade count is above 100.
