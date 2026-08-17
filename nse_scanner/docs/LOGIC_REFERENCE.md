# kScanner — Logic Reference

This documents the **actual as-implemented logic** of every major component, with exact formulas and `file:line` references so each claim below can be checked directly against source. This is distinct from `SCANNER_DESIGN.md` (design *rationale* — why choices were made) and `CLAUDE.md` (working invariants) — this doc is "what the code currently does," including the v4 partial-exit/backtest-speedup work.

No code was changed to produce this document.

---

## 1. Data layers & gap handling

**Three layers** (`db.py`):
- `bars_1d` — facts only (OHLCV, delivery %, VWAP, trades). Never a calculated value.
- `features_1d` / `features_1w` / `features_1m` — fully rebuildable indicator output. `DROP TABLE` is always safe.
- `signals_1d` — append-only scan output log.

**Gap detection is a query, not a pointer** (`ingest.py:262` `missing_pairs()`). There is no `last_updated_date` field anywhere. Instead, one SQL anti-join finds every `(isin, date)` pair that's missing:

```sql
active symbols × trading_calendar dates
LEFT JOIN bars_1d
WHERE bars_1d.date IS NULL
```

This single query handles a fresh install, a normal daily run, and a four-day-old gap identically — there's no separate "backfill mode." It only considers dates from `trading_calendar WHERE bhavcopy_available` (real trading days) and only from each symbol's `first_seen` onward.

**Staleness guard** (`validate.py:84` `data_is_stale()`): compares `MAX(bars_1d.date)` against the calendar's actual last trading day. If the stored data is behind, `scan.py` refuses to run (`scan.py:153-160`) unless explicitly overridden with `--ignore-stale`. This is what stops you from acting on a signal computed from 4-day-old prices.

---

## 2. Universe selection

`universe.py:225` `active_universe(con, as_of)` — the symbols a scan/backtest will even look at. A symbol must pass **all** of:

| Filter | Rule |
|---|---|
| Series | `series` in `universe.series_allowed` (EQ only by default) |
| Surveillance | not on ASM/GSM latest flag (if `exclude_asm`/`exclude_gsm`) |
| Liquidity | `MEDIAN(close × volume)` over the last 20 bars ≥ `min_turnover_cr` (crore → rupees) — **measured in rupees, not share count** |
| Price | last close ≥ `min_price` (default ₹20) |
| History | total bars ≥ `min_bars_history` (default 260) |

---

## 3. Indicators (`indicators.py`)

Three conventions exist specifically to match TradingView, because standard libraries (pandas-ta) drift on them:

1. **Wilder's RMA**, not SMA/EMA, for ATR/RSI/ADX:
   `RMA_t = RMA_{t-1} * (n-1)/n + x_t/n`, seeded with a simple mean of the first `n` values (`indicators.py:63-89`).
2. **Bollinger uses population stdev** (`ddof=0`), not pandas' default sample stdev (`ddof=1`) — `indicators.py:127`.
3. **Supertrend uses locked bands** — the final upper band only ratchets *down* while price stays below it, the final lower band only ratchets *up* while price stays above it (`indicators.py:236-241`). Without this, bands whipsaw on every ATR wiggle and produce more flips than the reference chart.

Other formulas actually in use:
- **ADR%** (`adr_pct`, `indicators.py:108`): `mean((High−Low)/Low) over 20 bars × 100`.
- **ADX** (`indicators.py:150`): double-smoothed (RMA of DX, itself built from RMA'd DM/TR) — needs ~150 bars before it's trustworthy, not 14.
- **Anchored VWAP** (`indicators.py:272`): `Σ(vwap_i × vol_i) / Σvol_i` from an anchor bar forward, using bhavcopy's daily VWAP (not derivable from OHLC alone — this is why bhavcopy enrichment matters). Bands are ± `band_mult × running stdev of price around the AVWAP`.
- **HMA** (`indicators.py:51`): `WMA(2×WMA(n/2) − WMA(n), √n)`.

---

## 4. Feature registry (`features.py`)

Every indicator is a `REGISTRY` entry (`features.py:205`) declaring `deps` (other features it needs), `min_bars` (warm-up requirement), and `outputs` (columns written). Enabling a feature in `config.yaml` auto-pulls in its dependencies transitively (e.g. `supertrend` pulls in `atr14`).

Two-pass computation: **pass 1** is per-symbol indicators (SMA, ATR, RSI, ADX, Supertrend, etc.); **pass 2** is cross-sectional (`rs_rank`, relative-strength percentile rank against the *entire universe as of that date* — this can't be computed per-symbol in isolation).

Warm-up: the trailing context pulled per symbol is `warmup_discard_bars` (250) + the neediest enabled feature's `min_bars`. Rows still in warm-up read as `NaN`, and the condition evaluator treats `NaN` as **False**, never as "pass" — a symbol without enough history is silently excluded, not silently included.

---

## 5. W-pattern detection (`patterns.py`)

### Zigzag (`patterns.py:69`)
Confirmed swing points on **close** (not high/low). A swing point isn't reported until price has reversed `zigzag_pct%` (default 5%) away from it — that reversal *is* the look-ahead guard: you couldn't have known bar `i` was the bottom until price closed 5% above it.

### Double-bottom rule (`find_w_patterns`, `patterns.py:146`)
For every adjacent pair of confirmed zigzag lows (L1 = older, L2 = newer — **not** any combinatorial pair of lows in the window):

1. Separation `L2.pos − L1.pos` must be within `[min_separation, max_separation]` (10–60 bars by default).
2. If `require_undercut` (default on): L2 price must be strictly below L1 price (the "shakeout").
3. **The pattern does not exist until close reclaims L1 after L2**, within `confirm_max_wait` bars (default 30). This reclaim bar is `confirm_pos` — the earliest bar the pattern is legitimately knowable. If the reclaim never happens, the L1/L2 pair is discarded entirely, not returned as an unconfirmed candidate.
4. **Neckline** = highest high strictly between L1 and L2.
5. **Depth** = `(neckline − L2) / neckline × 100` must be ≥ `min_depth_pct` (3% default) — filters out flat noise.

Circuit-locked bars (`high == low == close`) are masked before detection — otherwise they create fake swing points.

### Entry triggers (`find_entry_trigger`, `patterns.py:261`)
Searching forward from `confirm_pos`, each variant finds the first bar where:

| Variant | Trigger condition |
|---|---|
| E1 | (none — fires immediately at `confirm_pos`) |
| E2 | close > L1 price (the default; "the reclaim rule") |
| E3 | close > neckline |
| E4 | close > SMA20 |
| E5 | close > Anchored VWAP anchored at L1 |

### Which pattern gets acted on (`select_active_pattern`, `patterns.py:331`)
A symbol can have several valid W-patterns stacked up over its history. The rule: keep only patterns whose entry trigger actually fired, then take the **most recent** trigger. The live scan additionally requires `max_bars_since_trigger` (2 bars) so only *fresh* triggers count — this is the one selection rule shared by the scan list and the chart markup, so what's drawn on the chart always matches why (or why not) a symbol is in the signal list.

### Classification (informational, not filters)
- `classify_bottom_vs_sma` (`patterns.py:381`): which SMA (20/50/100/200) the L2 bottom formed within 1 ATR of.
- `sma_stack_state` (`patterns.py:419`): `stacked_up` (10>20>50>100>200), `stacked_down`, or `mixed`.

---

## 6. Suggested stop/target (`scan.py:226-240`)

Computed for every live signal (this is what shows on Scan/New Opportunity — the "New Position" dialog itself does **not** calculate anything, it's a plain manual input):

```python
stop_suggested    = L2_price − stop_atr_mult × ATR14_at_L2      # stop_atr_mult = 0.5
target_suggested  = neckline + (neckline − L2_price)             # "measured move"
```

- **Stop**: sits just below the pattern's actual low, with a volatility cushion (half an ATR) so normal noise around L2 doesn't stop you out, but a genuine break of the double-bottom low does.
- **Target**: classic double-bottom measured-move projection — project the pattern's own depth (`neckline − L2`) upward again from the neckline. This is the *same* formula as backtest exit variant **X3** (§8), so it isn't a separate live-only heuristic.

This is a **structural** projection from the pattern's geometry, not a statistically-fitted number — the backtest engine treats it as one of six competing exit rules to evaluate, not a presumed-correct default.

---

## 7. Live scan pipeline (`scan.py:129` `scan()`)

1. Refuse to run if data is stale (unless overridden).
2. Resolve `regime_state()` — index close vs its SMA50/SMA200 → `bull`/`bear`/`neutral`/`unknown`. Always computed even when the regime filter is off, because "you can't A/B test a filter you have no data for."
3. If the regime filter is on and set to `block` mode and regime is `bear`: emit zero signals.
4. `active_universe()` → for each symbol, load bars+features (`load_symbol_frame_tf` — daily is a straight passthrough; weekly/monthly resample `bars_1d` on the fly via `resample.py`, joined against `features_1w`/`features_1m`).
5. Run W-pattern detection + `select_active_pattern` (entry variant fixed at E2 for live scanning).
6. `apply_preset=True` (default): also apply the preset's `conditions` (from `config.yaml`) and the relative-strength filter if enabled.
   `apply_preset=False`: skip conditions/RS filter entirely and attach **every** `features_1d` column to the row — this is the "superset" the Scan screen fetches once, then filters client-side in-memory via filter chips (no re-scan per chip toggle).
7. `filter_to_preset()` (`scan.py:267`) derives an `apply_preset=True`-equivalent result from an already-fetched superset by reusing the *exact same* `_passes_conditions`/RS-filter logic `scan()` uses inline — so it can never drift from what a live scan would find.
8. `store_signals()` writes to `signals_1d`, append-only, `ON CONFLICT DO NOTHING` keyed on `(scan_date, isin, preset_name, timeframe)`.

---

## 8. Backtest engine (`backtest.py`)

### Two-stage design
Stage 1 (pattern/signal generation) is independent of stage 2 (trade simulation) — as of the v4 speedup work, this is now actually implemented as a cache, not just an intent: `_prepare_universe()` (`backtest.py:307`) bulk-loads every symbol's bars+features for a date range in one query and runs `find_w_patterns()` **once** per symbol, since pattern detection depends only on price history and the fixed `pattern:` config — never on entry/exit variant or preset. `sweep()` (30 cells) and `marginal_contribution()` (8 presets) build this cache once and share it across every cell instead of re-detecting from scratch per cell.

### The three honesty rules (`simulate_exit`, `backtest.py:101`)
1. **Entry at the next bar's open**, never the signal-day close (the signal is only knowable after that day's close).
2. **Stop and target hit on the same bar → assume the stop was hit.** Daily bars can't resolve intraday order; assuming target-first is the most common way backtests inflate results (typically 20-40%). Config: `same_day_stop_and_target: "stop"`.
3. **A gap through the stop fills at the open**, not at the stop price.

Trailing stops (X4/X5) read **yesterday's** indicator value, never today's — otherwise the trail is look-ahead.

### Entry variants
Same E1–E5 as §5.

### Exit variants (`simulate_exit`, `backtest.py:101-194`)

| ID | Rule |
|---|---|
| X1 | Fixed % target (`target_pct`, default 5%) |
| X2 | R-multiple target (`target_r`, default 2.0 × risk) |
| X3 | Measured move — same formula as `target_suggested` in §6 |
| X4 | Trail below SMA(`trail_sma`, default 20) |
| X5 | ATR chandelier trail — `running_high − chandelier_atr_mult × ATR` |
| X6 / no target hit within `time_stop_bars` | Pure time stop, exits at close |

### Costs (`round_trip_costs`, `backtest.py:67`)
Brokerage + STT (buy/sell separately) + other charges + flat DP charge, plus slippage (`apply_slippage`, applied against entry on buy and exit on sell). Always applied — a backtest without costs shows an edge that doesn't survive contact with reality (~17% of gain eaten on a 2% winner, per the cost model at default settings).

### Metrics (`compute_metrics`, `backtest.py:466`)
`win_rate`, `expectancy_r = win% × avg_win_R + (1-win%) × avg_loss_R`, `profit_factor = gross_win / gross_loss`, max drawdown off the cumulative-net-P&L equity curve, `CAGR` from total return over the trade span.

### Forward curves (`analyse_curves`, `backtest.py:512`)
Per day-held: `median_mfe` (where this flattens is the natural holding period), `p85_mae_win` (85th-percentile drawdown among *winners only* — a stop-placement candidate), `pct_positive` (survival curve), `marginal_mfe` (gain from one more day — near zero means the edge is spent). Deliberately ignores stops/targets — shows what the move *does*, not what current rules happen to capture.

### Overfitting guardrails
In-sample ends `2020-12-31`; out-of-sample starts `2021-01-01` and is meant to be looked at once. `min_trades_for_conclusion` = 100. `sweep()`/`marginal_contribution()` report `trade_retention_pct` alongside deltas specifically so a filter that "improves" expectancy by cutting trades from 800 to 40 is visibly a coincidence, not an edge.

---

## 9. Trade journal (`journal.py`)

### Core numbers
- `R = (exit − entry) / (entry − stop)`, so every trade is comparable regardless of position size.
- **MAE/MFE** (`compute_mae_mfe`, `journal.py:155`): worst/best price excursion while held, computed fresh from `bars_1d` — `(low.min()/entry − 1) × 100` and `(high.max()/entry − 1) × 100` over `[entry_date, exit_date]`.
- **Feature snapshot** (`snapshot_features`, `journal.py:61`): freezes the feature vector (ADR%, ATR, ADX, RSI, RVOL, delivery%, distance-from-SMA200, RS rank, SMA compression, turnover) at entry time into `trade_snapshot` — so "do my winners have higher delivery% than my losers?" is answerable later using what was true *then*, not today's values.

### Partial exits (v4 — new)
`trades.qty` keeps its original meaning: the total qty originally bought, a fact, never mutated. A new `trade_partials` table records each partial exit (qty, exit price/date, P&L for that slice). **Remaining qty is always derived, never stored**:

```python
remaining_qty = qty − SUM(trade_partials.qty)   # 0 if trades.status == 'closed'
```

(The `status == 'closed'` special case matters: `close_trade()` settles the final leg directly on `trades` rather than inserting one more `trade_partials` row for itself, so the raw arithmetic alone would still show leftover qty after a full close.)

`partial_close()` (`journal.py`) rejects `qty >= remaining_qty` — exiting *all* of what's left is a full close and must go through `close_trade()`, so the two paths never overlap.

`close_trade()` now closes whatever qty remains (not the original `trades.qty`), and aggregates **whole-trade totals across every leg**:
- `net_pnl`/`gross_pnl`/`costs` = sum of every partial leg's + the final leg's.
- `r_multiple` = **qty-weighted average R across every leg**: `Σ(R_i × qty_i) / Σqty_i`, where each partial leg's `R_i` is computed from its own `exit_price` against the trade's fixed `entry_price`/`stop_price`.
- `holding_days`/MAE/MFE stay whole-position (entry → final exit date) — they're price-excursion measures, independent of qty.

Unrealised P&L for still-open positions (`api/services/holdings.py::list_open_positions`) is computed against **remaining_qty**, not the original qty — a position that's already sold half no longer owns the full original quantity, so pricing it as if it did overstates both P&L and risk.

### Analytics (all read-only queries over `trades`/`trade_snapshot`/`trade_tags`)
- `adherence_report`: P&L split by `followed_plan` — usually the most uncomfortable table in the journal.
- `preset_attribution`: which preset actually makes money.
- `tag_analysis`: P&L by behavioural tag (chased_entry, moved_stop, revenge_trade, oversized, exited_early).
- `compare_with_backtest`: backtest numbers vs. your actual trades — the gap is diagnostic (lower live win-rate than backtest = execution gap; shorter live holding period = exiting early; smaller live MAE = stopping out on noise).

---

## 10. Position lifecycle status (v4 — new, `api/services/holdings.py`)

A **separate concept** from the advisor's HOLD/WATCH/REVIEW (§11) — that's trading guidance, this is what has actually happened to the position. Computed, never stored:

| Condition | `lifecycle_status` |
|---|---|
| `remaining_qty == qty` and `status == 'open'` | `OPEN` |
| `0 < remaining_qty < qty` and `status == 'open'`, booked partial `net_pnl` ≥ 0 | `PARTIAL_PROFIT` |
| same, but booked partial `net_pnl` < 0 | `PARTIAL_LOSS` |
| `status == 'closed'` | `CLOSED` |

The Positions screen only ever lists rows with `remaining_qty > 0` (same as before v4) — a `CLOSED` trade drops off the list exactly as it always did; historical/closed-trade analysis lives in Performance.

---

## 11. Advisor — position status (`advisor.py:37` `position_status()`)

**Descriptive only** — never "will"/"expect"/"likely", never a price prediction. Every statement cites a real number from *this user's own* backtest for the trade's preset. If no backtest run exists for that preset, it says exactly that instead of guessing.

Status starts at `HOLD` and can only escalate (`HOLD → WATCH → REVIEW`), driven by five independent rules, each appending its own reason string:

1. **Held past the median winner's peak**: if `days_held > backtest_metrics.median_hold_days` for the latest run of this preset → `REVIEW`.
2. **Marginal MFE turned non-positive**: if the backtest's `marginal_mfe` at this exact `days_held` is ≤ 0 (the edge, per the backtest, is statistically spent at this day) → `REVIEW`.
3. **Drawdown approaching the 85th-percentile winner MAE**: if current drawdown ≥ `MAE_APPROACH_FRACTION` (0.8) × the backtest's `p85_mae_win` at this day → `WATCH` (or stays `REVIEW` if already there).
4. **Running behind the backtest's typical path**: if current MFE < the backtest's `median_mfe` at this exact day-held → `WATCH`.
5. **Running ahead of the 75th-percentile path**: if current MFE > `p75_mfe` at this day → adds a positive reason string, but never *downgrades* a status already raised by rules 1-4.

If none of the rules fire, the single reason is just "Day N, up X%. No backtest threshold crossed yet."

---

## 12. Config-driven behavior (`config.yaml`)

Two things are deliberately **never hard-coded in Python**:
- **Scan presets** (`presets:` block) — a named preset is a `conditions:` list of `column operator value` expressions (e.g. `"close > sma200"`), resolved by `config.resolve_preset()` which also supports `inherits`/`conditions_add`/`overrides` so variants don't repeat themselves. `save_preset()` does a surgical text insert into the YAML file (not a full re-dump) so hand-formatting and comments survive.
- **Scan-screen filter chips** (`filter_chips:` block) — each chip is `{id, label, expr}`, optionally with a numeric slider (`default`/`min`/`max`/`step`). Adding a chip is a YAML edit, never a code change.

Thresholds generally live here rather than in the database specifically so that changing a threshold never triggers a feature rebuild (`docs/CLAUDE.md`'s rule: "Thresholds live in presets, never in the database").
