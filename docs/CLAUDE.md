# kScanner — NSE Swing & Position Scanner

Local stock scanner for NSE cash equities. Replaces Chartink. Python + DuckDB + Streamlit.

**Full design rationale lives in `SCANNER_DESIGN.md` (19 sections). Read the relevant section before changing anything in that area — do not infer intent from the code alone.** Operational commands are in `README.md`.

---

## The one thing to understand first

**Accuracy beats every other consideration in this project.** A scanner that produces confident wrong signals is worse than no scanner, because the signals are indistinguishable from good ones. When a change trades correctness for speed, convenience, or feature count, say so explicitly and let me decide.

---

## Invariants — do not violate without flagging it

### Data layers
- `bars_1d` is **facts only**. Never write a calculated value into it.
- `features_1d` is **fully rebuildable**. `DROP TABLE` must always be safe.
- Never store a cheap boolean (`close > sma50`). Store expensive state; compute comparisons at scan time. Thresholds live in `config.yaml` presets, never in the database.

### Gap handling
- **There is no `last_updated_date` pointer anywhere, by design.** State is derived from the data via the calendar anti-join in `ingest.missing_pairs()`. Do not add a pointer, watermark, or "last run" field to fix a bug — it will reintroduce silent holes.
- One code path for fresh install, daily run, and a four-day gap. No "backfill mode".
- After writing, **re-run the anti-join to verify**. Never assume the write worked.

### Look-ahead
- A pivot low with right-window R is knowable only R bars later. `WPattern.confirm_pos` is the earliest usable bar. Nothing may act before it.
- Backtest entries fill at the **next bar's open**, never the signal-day close.
- Trailing stops read **yesterday's** indicator value.
- Cross-sectional ranks must rank against the universe **as of that date**.

### Backtest honesty
- Stop and target both touched on the same bar → **assume the stop was hit**. Daily bars cannot resolve intraday order.
- Gap through the stop fills at the open, not the stop price.
- Costs are always applied. They are ~17% of the gain on a 2% winner.

### Indicator conventions
These three decide whether numbers match TradingView. They are the reason indicators are hand-coded rather than taken from `pandas-ta`:
1. ATR/ADX/RSI use **Wilder's RMA**, not SMA or EMA.
2. Bollinger uses **population stdev** (`ddof=0`), not pandas' default sample stdev.
3. Supertrend uses **locked bands** — the final upper band ratchets down only.

### Warm-up
- The first 250 bars per symbol are discarded. Indicators return values long before those values are trustworthy — ADX(14) needs ~150 bars because it is double-smoothed.
- Every feature declares `min_bars`. Scans gate on `bars_available`.
- In the condition evaluator, **NaN evaluates to False** — a symbol still in warm-up is excluded, never silently passed.

### Scanner / backtest parity
`scan.py` and `backtest.py` both call `patterns.py`. Neither gets its own copy of the pattern logic. If they diverge, backtest conclusions stop transferring to live trading.

---

## Working agreements

- **Adding an indicator combination = editing `config.yaml` presets.** Never hard-code a filter in Python. If a request seems to need a code change for this, push back first.
- **Adding an indicator = adding a `REGISTRY` entry in `features.py`** with `deps`, `min_bars`, and `outputs`. Dependencies resolve transitively; do not call one feature function from inside another.
- **After changing `features.enabled` or any indicator maths → `python features.py --full`.** Mixed `feature_version` rows inside one backtest are silent poison.
- **Run `python test_core.py` after touching `indicators.py` or `patterns.py`.** Expect 45 passed, 0 failed.
- NSE URL formats change periodically. Downloaders must fail **loudly** — a scanner silently running on stale data is worse than one that is visibly down.
- Delisted symbols: stop fetching, but **never delete their history**. Removing it reintroduces survivorship bias into every backtest.

---

## Methodology rules (these are about analysis, not code)

- **Always run the `w_naked` control before any filtered variant.** Without a baseline number, "W + SMA50 gives 48%" is meaningless.
- **No conclusion from a cell with under 100 trades.** Report the trade count next to every statistic.
- A filter that lifts expectancy but cuts trades from 800 to 40 has found a coincidence. Report `trade_retention_pct` alongside `delta_expectancy`.
- In-sample ends 2020-12-31. **Do not touch out-of-sample data during tuning.** It gets looked at once, at the end.
- Prefer parameter plateaus over sharp peaks.
- If I ask for a result that requires breaking one of these, say so rather than producing the number.

---

## Context I don't want to re-explain

- Strategy: **W-pattern (double bottom)** where the second low undercuts the prior swing low, then price closes back above it. Holding 5–10 days, ~5% target.
- Timeframes: **1D = trading, 1W = longer holds, 1M = investing.** Intraday (1h/4h) is deliberately out of scope for v1.
- Monthly SMA200 needs ~17 years and most of the universe lacks it — use SMA 12/24/36 on monthly.
- I am **not an algo trader.** Broker/Dhan order integration is deferred (see §16). Do not propose auto-execution.
- Data: yfinance for prices (`auto_adjust=False` — split-adjusted, dividend-unadjusted), NSE bhavcopy for delivery %/VWAP/trades and as the daily validator.
- Liquidity is measured in **rupees**, never share count.

---

## My preferences

- Answer point-wise, in short crisp English.
- Tell me when something is a bad idea. I would rather hear it than find out from a backtest.
- Explain trade-offs, not just the recommendation.
