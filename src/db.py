"""
db.py — DuckDB connection and schema.

Layer model (see design doc §2). The rule that matters:
    Layer 1 (bars_1d)      never contains a calculated value
    Layer 2 (features_1d)  is fully rebuildable — DROP and recreate freely
    Layer 3 (signals_1d)   scan output, append-only

Because Layer 2 can be destroyed at any time without risk, you can change
indicator logic as often as you like and your source of truth never moves.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

from config import CFG


def db_path() -> Path:
    p = Path(CFG["paths"]["db"]).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open the DuckDB file. Use read_only=True for the Streamlit app."""
    con = duckdb.connect(str(db_path()), read_only=read_only)
    con.execute("SET TimeZone='Asia/Kolkata'")
    return con


SCHEMA = """
-- ===================================================================
-- LAYER 1 : FACTS.  No calculated values ever live here.
-- ===================================================================
CREATE TABLE IF NOT EXISTS bars_1d (
    isin          VARCHAR NOT NULL,
    symbol        VARCHAR NOT NULL,
    date          DATE    NOT NULL,
    open          DOUBLE,
    high          DOUBLE,
    low           DOUBLE,
    close         DOUBLE,
    prev_close    DOUBLE,
    volume        BIGINT,
    vwap          DOUBLE,           -- bhavcopy AVG_PRICE, powers anchored VWAP
    no_of_trades  BIGINT,
    deliv_qty     BIGINT,
    deliv_pct     DOUBLE,
    series        VARCHAR,
    PRIMARY KEY (isin, date)
);

-- ===================================================================
-- REFERENCE
-- ===================================================================
CREATE TABLE IF NOT EXISTS instruments (
    isin        VARCHAR PRIMARY KEY,
    symbol      VARCHAR,
    name        VARCHAR,
    series      VARCHAR,
    sector      VARCHAR,
    industry    VARCHAR,
    first_seen  DATE,
    last_seen   DATE
);

CREATE TABLE IF NOT EXISTS symbol_status (
    isin                VARCHAR PRIMARY KEY,
    status              VARCHAR,     -- active | suspended | delisted
    consecutive_misses  INTEGER DEFAULT 0,
    last_success        DATE
);

-- A bhavcopy exists for date X  <=>  X was a trading day.
-- This is the authoritative calendar, no hardcoded holiday list needed.
CREATE TABLE IF NOT EXISTS trading_calendar (
    date                DATE PRIMARY KEY,
    bhavcopy_available  BOOLEAN
);

CREATE TABLE IF NOT EXISTS flags (
    date        DATE,
    isin        VARCHAR,
    asm         BOOLEAN,
    gsm         BOOLEAN,
    price_band  DOUBLE,
    PRIMARY KEY (date, isin)
);

CREATE TABLE IF NOT EXISTS index_bars (
    index_name VARCHAR,
    date       DATE,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
    PRIMARY KEY (index_name, date)
);

CREATE TABLE IF NOT EXISTS index_membership (
    index_name VARCHAR,
    isin       VARCHAR,
    as_of      DATE,
    PRIMARY KEY (index_name, isin, as_of)
);

CREATE TABLE IF NOT EXISTS corp_actions (
    isin        VARCHAR,
    ex_date     DATE,
    action_type VARCHAR,
    ratio       DOUBLE
);

CREATE TABLE IF NOT EXISTS fundamentals (
    isin           VARCHAR,
    as_of          DATE,
    market_cap     DOUBLE,
    free_float_pct DOUBLE,
    PRIMARY KEY (isin, as_of)
);

CREATE TABLE IF NOT EXISTS fii_dii_flows (
    date DATE PRIMARY KEY,
    fii_buy DOUBLE, fii_sell DOUBLE,
    dii_buy DOUBLE, dii_sell DOUBLE
);

-- ===================================================================
-- LAYER 2 : FEATURES.  Rebuildable. FLOAT not DOUBLE (halves the size).
-- ===================================================================
CREATE TABLE IF NOT EXISTS features_1d (
    isin VARCHAR NOT NULL,
    date DATE    NOT NULL,
    bars_available INTEGER,          -- warm-up gate

    sma10 FLOAT, sma20 FLOAT, sma50 FLOAT, sma100 FLOAT, sma200 FLOAT,
    sma50_slope FLOAT, sma200_slope FLOAT,
    ema10 FLOAT, ema21 FLOAT,
    hma10 FLOAT, hma50 FLOAT,
    supertrend FLOAT, st_dir SMALLINT,

    atr14 FLOAT, adr_pct20 FLOAT,
    bb_mid FLOAT, bb_upper FLOAT, bb_lower FLOAT, bb_width FLOAT,

    rsi14 FLOAT, adx14 FLOAT, di_plus FLOAT, di_minus FLOAT,
    macd FLOAT, macd_signal FLOAT,

    vol_sma20 DOUBLE, rvol FLOAT,
    turnover DOUBLE, turnover_sma20 DOUBLE,
    deliv_pct_sma20 FLOAT, deliv_surge FLOAT,
    avg_trade_size FLOAT,

    dist_sma200_pct FLOAT,
    dist_52w_high_pct FLOAT, dist_52w_low_pct FLOAT,
    sma_compression FLOAT,
    sma_stack VARCHAR,

    ret_55d FLOAT, rs_vs_bench FLOAT, rs_rank_pct FLOAT,

    feature_version VARCHAR,
    PRIMARY KEY (isin, date)
);

CREATE TABLE IF NOT EXISTS features_1w AS SELECT * FROM features_1d WHERE 1=0;
CREATE TABLE IF NOT EXISTS features_1m AS SELECT * FROM features_1d WHERE 1=0;

-- Anchored VWAP lives in its own table: it is O(bars since anchor) PER anchor,
-- so only the standard anchors are stored. Ad-hoc anchors are computed live.
CREATE TABLE IF NOT EXISTS avwap (
    isin        VARCHAR,
    anchor_type VARCHAR,     -- w_l1 | swing_low | 52w_low | 52w_high
    anchor_date DATE,
    date        DATE,
    avwap       FLOAT,
    avwap_upper FLOAT,
    avwap_lower FLOAT,
    PRIMARY KEY (isin, anchor_type, anchor_date, date)
);

-- ===================================================================
-- LAYER 3 : SIGNALS
-- ===================================================================
CREATE TABLE IF NOT EXISTS signals_1d (
    scan_date     DATE,
    isin          VARCHAR,
    symbol        VARCHAR,
    preset_name   VARCHAR,
    timeframe     VARCHAR,
    signal_type   VARCHAR,
    trigger_price DOUBLE,
    l1_date DATE, l1_price DOUBLE,
    l2_date DATE, l2_price DOUBLE,
    neckline DOUBLE, depth_pct DOUBLE, separation INTEGER,
    stop_suggested DOUBLE, target_suggested DOUBLE,
    bottom_at_sma VARCHAR,
    sma_stack VARCHAR,
    feature_version VARCHAR,
    config_hash VARCHAR,
    PRIMARY KEY (scan_date, isin, preset_name, timeframe)
);

-- ===================================================================
-- OPERATIONAL LOGS
-- ===================================================================
CREATE TABLE IF NOT EXISTS validation_log (
    date DATE, isin VARCHAR, symbol VARCHAR,
    yf_close DOUBLE, bhav_close DOUBLE, pct_diff DOUBLE, passed BOOLEAN
);

CREATE TABLE IF NOT EXISTS ingest_log (
    run_ts TIMESTAMP, scope VARCHAR,
    date_from DATE, date_to DATE,
    rows_added INTEGER, symbols_ok INTEGER, symbols_failed INTEGER,
    status VARCHAR, note VARCHAR
);

-- ===================================================================
-- BACKTEST
-- ===================================================================
CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id VARCHAR PRIMARY KEY,
    run_ts TIMESTAMP,
    label VARCHAR,
    preset_name VARCHAR,
    entry_variant VARCHAR,
    exit_variant VARCHAR,
    filters VARCHAR,
    config_hash VARCHAR,
    feature_version VARCHAR,
    date_from DATE, date_to DATE,
    sample VARCHAR                    -- in | out
);

CREATE TABLE IF NOT EXISTS backtest_trades (
    run_id VARCHAR, trade_seq INTEGER,
    isin VARCHAR, symbol VARCHAR,
    signal_date DATE, entry_date DATE, entry_price DOUBLE, qty INTEGER,
    stop_price DOUBLE, target_price DOUBLE,
    exit_date DATE, exit_price DOUBLE, exit_reason VARCHAR,
    gross_pnl DOUBLE, costs DOUBLE, net_pnl DOUBLE,
    r_multiple FLOAT, holding_days INTEGER,
    mae_pct FLOAT, mfe_pct FLOAT,
    -- feature snapshot at signal time: lets you slice results afterwards
    bottom_at_sma VARCHAR, sma_stack VARCHAR,
    regime_state VARCHAR, rs_rank_pct FLOAT,
    adr_pct FLOAT, deliv_pct FLOAT, dist_sma200_pct FLOAT,
    depth_pct FLOAT, separation INTEGER
);

-- Forward return curves: how MFE/MAE evolve day by day after a signal.
-- This is what tells you the holding period instead of guessing it.
CREATE TABLE IF NOT EXISTS backtest_curves (
    run_id VARCHAR, trade_seq INTEGER, day_n INTEGER,
    ret_pct FLOAT, mfe_pct FLOAT, mae_pct FLOAT
);

CREATE TABLE IF NOT EXISTS backtest_metrics (
    run_id VARCHAR PRIMARY KEY,
    trades INTEGER, win_rate FLOAT,
    expectancy_r FLOAT, avg_win_r FLOAT, avg_loss_r FLOAT,
    profit_factor FLOAT, max_dd_pct FLOAT,
    total_return_pct FLOAT, cagr_pct FLOAT,
    median_hold_days FLOAT, median_mae FLOAT, median_mfe FLOAT,
    benchmark_cagr_pct FLOAT
);

-- ===================================================================
-- TRADE JOURNAL
-- ===================================================================
CREATE SEQUENCE IF NOT EXISTS trade_id_seq START 1;

CREATE TABLE IF NOT EXISTS trades (
    trade_id INTEGER PRIMARY KEY,
    signal_id VARCHAR,                -- links back to the scan that found it
    isin VARCHAR, symbol VARCHAR,
    preset_name VARCHAR,
    entry_date DATE, entry_price DOUBLE, qty INTEGER,
    stop_price DOUBLE, target_price DOUBLE,
    exit_date DATE, exit_price DOUBLE, exit_reason VARCHAR,
    gross_pnl DOUBLE, costs DOUBLE, net_pnl DOUBLE,
    r_multiple FLOAT, holding_days INTEGER,
    mae_pct FLOAT, mfe_pct FLOAT,     -- auto-computed from bars_1d
    followed_plan BOOLEAN,
    thesis TEXT, review_note TEXT,
    status VARCHAR                    -- open | closed
);

CREATE TABLE IF NOT EXISTS trade_snapshot (
    trade_id INTEGER, metric VARCHAR, value DOUBLE
);

CREATE TABLE IF NOT EXISTS trade_tags (
    trade_id INTEGER, tag VARCHAR
);

CREATE TABLE IF NOT EXISTS missed_trades (
    signal_id VARCHAR, scan_date DATE, isin VARCHAR, symbol VARCHAR,
    skip_reason VARCHAR, hypothetical_r FLOAT
);
"""


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Create every table. Safe to run repeatedly."""
    for stmt in SCHEMA.split(";"):
        s = stmt.strip()
        if s:
            con.execute(s)


def table_counts(con: duckdb.DuckDBPyConnection) -> dict:
    """Row counts for the tables worth watching. Used by the app's health page."""
    names = [
        "bars_1d", "instruments", "trading_calendar", "features_1d",
        "signals_1d", "validation_log", "backtest_trades", "trades",
    ]
    out = {}
    for t in names:
        try:
            out[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except Exception:
            out[t] = None
    return out
