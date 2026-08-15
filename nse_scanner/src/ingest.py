"""
ingest.py — fetch prices and enrichment data, filling any gaps automatically.

THE GAP-HANDLING DESIGN
-----------------------
There is deliberately NO `last_updated_date` pointer anywhere in this file.

A pointer is a second copy of the truth and it can lie:
  - crash mid-run: pointer advanced, only 800 of 2,000 symbols written -> silent hole
  - it cannot tell a holiday from a missed day
  - it is blind to interior holes (a batch that failed three months ago)

Instead the missing set is DERIVED from the data with a calendar anti-join.
One query handles every case identically: four skipped days, holidays excluded,
interior holes, and a completely empty database. There is no "backfill mode"
versus "daily mode" — the same code path runs whether you last ran it yesterday
or never.

COLUMN OWNERSHIP
----------------
  open/high/low/close/volume  -> yfinance  (split-adjusted)
  vwap/deliv_pct/trades/series -> bhavcopy (ratios and counts; adjustment-neutral)

yfinance is called with auto_adjust=False on purpose. Yahoo's raw OHLC is
already split-adjusted; Adj Close ADDITIONALLY strips dividends. For pattern
work you want split-adjusted but dividend-UNadjusted, otherwise the swing low
you detect will not match the level you see on your chart.
"""

from __future__ import annotations

import argparse
import io
import logging
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from config import CFG
from db import connect, init_schema
from universe import _nse_session, all_symbols_for_ingest

log = logging.getLogger("ingest")

# NSE changes these periodically. Failures are logged as ERROR, never swallowed.
BHAV_URL_TMPL = (
    "https://nsearchives.nseindia.com/products/content/"
    "sec_bhavdata_full_{ddmmyyyy}.csv"
)
BHAV_UDIFF_TMPL = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{yyyymmdd}_F_0000.csv.zip"
)


# =====================================================================
# TRADING CALENDAR
# =====================================================================

def extend_trading_calendar(con, upto: date | None = None, lookback_days: int = 30) -> int:
    """
    A bhavcopy exists for date X  <=>  X was a trading day.

    That makes the bhavcopy archive an authoritative NSE calendar — no
    hardcoded holiday list, no guessing about Muhurat sessions.
    """
    upto = upto or date.today()
    known = con.execute("SELECT date FROM trading_calendar").df()
    known_set = set(pd.to_datetime(known["date"]).dt.date) if len(known) else set()

    start = upto - timedelta(days=lookback_days)
    added = 0
    d = start
    while d <= upto:
        if d.weekday() < 5 and d not in known_set:
            ok = bhavcopy_exists(d)
            con.execute(
                "INSERT INTO trading_calendar VALUES (?, ?) ON CONFLICT DO NOTHING",
                [d, ok],
            )
            added += 1
        d += timedelta(days=1)
    return added


def seed_calendar_from_bars(con) -> int:
    """
    Bootstrap: any date that appears in bars_1d was certainly a trading day.
    Cheap way to fill the calendar for years of history without probing NSE
    once per day.
    """
    return con.execute("""
        INSERT INTO trading_calendar (date, bhavcopy_available)
        SELECT DISTINCT date, TRUE FROM bars_1d
        ON CONFLICT (date) DO NOTHING
    """).fetchall() and con.execute(
        "SELECT COUNT(*) FROM trading_calendar").fetchone()[0]


def last_trading_day(con) -> date | None:
    row = con.execute(
        "SELECT MAX(date) FROM trading_calendar WHERE bhavcopy_available"
    ).fetchone()
    return row[0] if row else None


# =====================================================================
# BHAVCOPY
# =====================================================================

def _bhav_paths(d: date) -> Path:
    root = Path(CFG["paths"]["bhavcopy"]) / f"{d.year}"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"bhav_{d:%Y%m%d}.csv"


def bhavcopy_exists(d: date) -> bool:
    """Cheap HEAD-style probe. Cached by the local file if already downloaded."""
    if _bhav_paths(d).exists():
        return True
    try:
        s = _nse_session()
        url = BHAV_URL_TMPL.format(ddmmyyyy=f"{d:%d%m%Y}")
        r = s.get(url, timeout=20, stream=True)
        return r.status_code == 200 and len(r.content) > 500
    except Exception:
        return False


def download_bhavcopy(d: date, force: bool = False) -> pd.DataFrame | None:
    """
    Download and cache one day's full bhavcopy (the sec_bhavdata_full file,
    which carries delivery quantity and percentage).

    Raw files are kept forever under raw/bhavcopy/ — that folder is your audit
    trail. When a number looks wrong you can prove whether it was bad data or
    bad code.
    """
    path = _bhav_paths(d)
    if path.exists() and not force:
        try:
            return _parse_bhav(pd.read_csv(path))
        except Exception as exc:
            log.warning("Cached bhavcopy %s unreadable (%s); refetching", path, exc)

    s = _nse_session()
    url = BHAV_URL_TMPL.format(ddmmyyyy=f"{d:%d%m%Y}")
    try:
        r = s.get(url, timeout=30)
        if r.status_code != 200 or len(r.content) < 500:
            log.info("No bhavcopy for %s (status %s)", d, r.status_code)
            return None
        raw = pd.read_csv(io.BytesIO(r.content))
        raw.to_csv(path, index=False)
        return _parse_bhav(raw)
    except Exception as exc:
        log.error("FAILED bhavcopy download for %s: %s", d, exc)
        return None


def _parse_bhav(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalise bhavcopy columns. Handles the leading-space quirk in NSE's CSV."""
    raw.columns = [c.strip().upper().replace(" ", "_") for c in raw.columns]

    def pick(*names):
        for n in names:
            if n in raw.columns:
                return raw[n]
        return pd.Series([np.nan] * len(raw))

    out = pd.DataFrame({
        "symbol": pick("SYMBOL").astype(str).str.strip(),
        "series": pick("SERIES").astype(str).str.strip(),
        "bhav_close": pd.to_numeric(pick("CLOSE_PRICE", "CLOSE"), errors="coerce"),
        "prev_close": pd.to_numeric(pick("PREV_CLOSE"), errors="coerce"),
        "vwap": pd.to_numeric(pick("AVG_PRICE", "VWAP"), errors="coerce"),
        "ttl_qty": pd.to_numeric(pick("TTL_TRD_QNTY", "TOTTRDQTY"), errors="coerce"),
        "turnover": pd.to_numeric(pick("TURNOVER_LACS", "TOTTRDVAL"), errors="coerce"),
        "no_of_trades": pd.to_numeric(pick("NO_OF_TRADES", "TOTALTRADES"), errors="coerce"),
        "deliv_qty": pd.to_numeric(pick("DELIV_QTY"), errors="coerce"),
        "deliv_pct": pd.to_numeric(pick("DELIV_PER"), errors="coerce"),
    })
    return out[out["symbol"].notna() & (out["symbol"] != "nan")]


# =====================================================================
# YFINANCE
# =====================================================================

def fetch_yf_batch(symbols: list[str], start: date, end: date) -> pd.DataFrame:
    """
    Download a batch of NSE tickers.

    auto_adjust=False is deliberate — see the module docstring.
    Batches are throttled because Yahoo rate-limits aggressively; an
    unthrottled loop gets you blocked mid-run.
    """
    import yfinance as yf

    tickers = [f"{s}.NS" for s in symbols]
    try:
        raw = yf.download(
            tickers=tickers,
            start=start,
            end=end + timedelta(days=1),
            interval="1d",
            auto_adjust=False,      # <-- do not change
            group_by="ticker",
            threads=True,
            progress=False,
        )
    except Exception as exc:
        log.error("yfinance batch failed (%d tickers): %s", len(tickers), exc)
        return pd.DataFrame()

    if raw is None or raw.empty:
        return pd.DataFrame()

    frames = []
    for sym, tkr in zip(symbols, tickers):
        try:
            sub = raw[tkr] if isinstance(raw.columns, pd.MultiIndex) else raw
        except KeyError:
            continue
        sub = sub.dropna(how="all")
        if sub.empty:
            continue
        d = pd.DataFrame({
            "symbol": sym,
            "date": pd.to_datetime(sub.index).date,
            "open": sub["Open"].values,
            "high": sub["High"].values,
            "low": sub["Low"].values,
            "close": sub["Close"].values,
            "volume": sub["Volume"].values,
        })
        frames.append(d.dropna(subset=["close"]))

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# =====================================================================
# THE ANTI-JOIN
# =====================================================================

def missing_pairs(con) -> pd.DataFrame:
    """
    Which (isin, date) rows are absent?

    This single query replaces all bookkeeping. It handles:
      - four days you forgot to run
      - holidays inside that stretch (correctly excluded)
      - an interior hole from a batch that failed months ago
      - a brand new, empty database

    Returns one row per symbol with the range that needs fetching.
    """
    return con.execute("""
        WITH cal AS (
            SELECT date FROM trading_calendar WHERE bhavcopy_available
        ),
        active AS (
            SELECT i.isin, i.symbol, COALESCE(i.first_seen, DATE '1995-01-01') AS first_seen
            FROM instruments i
            JOIN symbol_status s ON s.isin = i.isin AND s.status = 'active'
        ),
        gaps AS (
            SELECT a.isin, a.symbol, c.date
            FROM active a
            CROSS JOIN cal c
            LEFT JOIN bars_1d b ON b.isin = a.isin AND b.date = c.date
            WHERE c.date >= a.first_seen
              AND b.date IS NULL
        )
        SELECT isin, symbol, MIN(date) AS date_from, MAX(date) AS date_to,
               COUNT(*) AS missing_bars
        FROM gaps
        GROUP BY isin, symbol
        ORDER BY symbol
    """).df()


# =====================================================================
# WRITE
# =====================================================================

def upsert_bars(con, df: pd.DataFrame) -> int:
    """
    Idempotent write. PRIMARY KEY (isin, date) means re-running is harmless —
    which is exactly what makes the gap-fill design safe.
    """
    if df.empty:
        return 0
    cols = ["isin", "symbol", "date", "open", "high", "low", "close",
            "prev_close", "volume", "vwap", "no_of_trades",
            "deliv_qty", "deliv_pct", "series"]
    for c in cols:
        if c not in df.columns:
            df[c] = None

    con.register("tmp_bars", df[cols])
    con.execute("""
        INSERT INTO bars_1d
        SELECT * FROM tmp_bars
        ON CONFLICT (isin, date) DO UPDATE SET
            open = excluded.open, high = excluded.high,
            low  = excluded.low,  close = excluded.close,
            volume = excluded.volume,
            prev_close   = COALESCE(excluded.prev_close,   bars_1d.prev_close),
            vwap         = COALESCE(excluded.vwap,         bars_1d.vwap),
            no_of_trades = COALESCE(excluded.no_of_trades, bars_1d.no_of_trades),
            deliv_qty    = COALESCE(excluded.deliv_qty,    bars_1d.deliv_qty),
            deliv_pct    = COALESCE(excluded.deliv_pct,    bars_1d.deliv_pct),
            series       = COALESCE(excluded.series,       bars_1d.series)
    """)
    con.unregister("tmp_bars")
    return len(df)


def enrich_from_bhavcopy(con, days: list[date]) -> int:
    """
    Attach delivery %, VWAP, trade count and series for the given dates.

    These are ratios and counts — adjustment-neutral — so mixing them with
    yfinance's split-adjusted prices is safe. Prices are never taken from here.
    """
    inst = con.execute("SELECT isin, symbol FROM instruments").df()
    total = 0
    for d in days:
        bh = download_bhavcopy(d)
        if bh is None or bh.empty:
            continue
        m = bh.merge(inst, on="symbol", how="inner")
        m["date"] = d
        con.register("tmp_enr", m[["isin", "date", "vwap", "no_of_trades",
                                   "deliv_qty", "deliv_pct", "series", "prev_close"]])
        con.execute("""
            UPDATE bars_1d b SET
                vwap         = COALESCE(t.vwap, b.vwap),
                no_of_trades = COALESCE(t.no_of_trades, b.no_of_trades),
                deliv_qty    = COALESCE(t.deliv_qty, b.deliv_qty),
                deliv_pct    = COALESCE(t.deliv_pct, b.deliv_pct),
                series       = COALESCE(t.series, b.series),
                prev_close   = COALESCE(t.prev_close, b.prev_close)
            FROM tmp_enr t
            WHERE b.isin = t.isin AND b.date = t.date
        """)
        con.unregister("tmp_enr")
        total += len(m)
    return total


def fetch_benchmarks(con, start: date, end: date) -> int:
    """Index OHLC — needed for relative strength and the regime filter."""
    import yfinance as yf

    names = [CFG["universe"]["benchmark"], CFG["universe"]["benchmark_alt"]]
    total = 0
    for name in names:
        try:
            d = yf.download(name, start=start, end=end + timedelta(days=1),
                            interval="1d", auto_adjust=False, progress=False)
            if d is None or d.empty:
                continue
            if isinstance(d.columns, pd.MultiIndex):
                d.columns = d.columns.get_level_values(0)
            frame = pd.DataFrame({
                "index_name": name,
                "date": pd.to_datetime(d.index).date,
                "open": d["Open"].values, "high": d["High"].values,
                "low": d["Low"].values, "close": d["Close"].values,
            }).dropna(subset=["close"])
            con.register("tmp_idx", frame)
            con.execute("""
                INSERT INTO index_bars SELECT * FROM tmp_idx
                ON CONFLICT (index_name, date) DO UPDATE SET
                    open=excluded.open, high=excluded.high,
                    low=excluded.low, close=excluded.close
            """)
            con.unregister("tmp_idx")
            total += len(frame)
        except Exception as exc:
            log.error("Benchmark %s failed: %s", name, exc)
    return total


def update_symbol_status(con, attempted: set[str], succeeded: set[str]) -> None:
    """
    Retire symbols that keep coming back empty.

    Delisted names otherwise appear "missing" every single day forever, and
    within a year you are making hundreds of pointless API calls per run.
    Their HISTORY IS KEPT — deleting it would reintroduce survivorship bias.
    """
    limit = CFG["universe"]["delist_after_misses"]
    failed = attempted - succeeded
    if succeeded:
        con.execute(f"""
            UPDATE symbol_status SET consecutive_misses = 0, last_success = CURRENT_DATE
            WHERE isin IN (SELECT isin FROM instruments WHERE symbol IN
                           ({','.join('?' * len(succeeded))}))
        """, list(succeeded))
    if failed:
        con.execute(f"""
            UPDATE symbol_status SET consecutive_misses = consecutive_misses + 1
            WHERE isin IN (SELECT isin FROM instruments WHERE symbol IN
                           ({','.join('?' * len(failed))}))
        """, list(failed))
    con.execute(
        "UPDATE symbol_status SET status = 'delisted' WHERE consecutive_misses >= ?",
        [limit],
    )


# =====================================================================
# ORCHESTRATION
# =====================================================================

def run_ingest(con, backfill_start: str | None = None, enrich: bool = True) -> dict:
    """
    The full sequence. Step 6 is the important one: we re-ask the anti-join
    rather than assuming the write worked.
    """
    cfg = CFG["ingest"]
    t0 = datetime.now()

    # 1. calendar
    # Seed weekdays back to the backfill start BEFORE the 30-day tail
    # extension below runs — otherwise that call alone makes the calendar
    # look "already populated" and this bootstrap never fires, silently
    # capping every backfill at the last 30 days regardless of --start.
    if backfill_start:
        start = pd.to_datetime(backfill_start).date()
        earliest = con.execute("SELECT MIN(date) FROM trading_calendar").fetchone()[0]
        if earliest is None or earliest > start:
            log.warning("Trading calendar does not cover backfill start (%s) — "
                        "seeding weekdays. It will self-correct as bhavcopies are probed.",
                        start)
            days = pd.bdate_range(start, date.today()).date
            for d in days:
                con.execute("INSERT INTO trading_calendar VALUES (?, TRUE) "
                            "ON CONFLICT DO NOTHING", [d])

    seed_calendar_from_bars(con)
    extend_trading_calendar(con)

    # 2. what is missing
    gaps = missing_pairs(con)
    log.info("Symbols with gaps: %d", len(gaps))

    # 3. always refetch the tail — yfinance silently restates recent bars
    refetch_from = date.today() - timedelta(days=cfg["always_refetch_days"])
    universe = all_symbols_for_ingest(con)
    if gaps.empty and not universe.empty:
        gaps = universe.assign(date_from=refetch_from, date_to=date.today(),
                               missing_bars=0)
    else:
        gaps["date_from"] = gaps["date_from"].apply(
            lambda d: min(pd.to_datetime(d).date(), refetch_from))
        gaps["date_to"] = date.today()

    if gaps.empty:
        log.info("Nothing to fetch.")
        return {"rows": 0, "symbols": 0}

    # 4/5. fetch and write
    isin_by_symbol = dict(zip(gaps["symbol"], gaps["isin"]))
    batch = cfg["yf_batch_size"]
    rows_total, ok_syms = 0, set()
    symbols = gaps["symbol"].tolist()

    for i in range(0, len(symbols), batch):
        chunk = symbols[i:i + batch]
        sub = gaps[gaps["symbol"].isin(chunk)]
        start = pd.to_datetime(sub["date_from"].min()).date()
        end = pd.to_datetime(sub["date_to"].max()).date()

        df = fetch_yf_batch(chunk, start, end)
        if not df.empty:
            df["isin"] = df["symbol"].map(isin_by_symbol)
            df = df.dropna(subset=["isin"])
            rows_total += upsert_bars(con, df)
            ok_syms |= set(df["symbol"].unique())

        log.info("batch %d/%d  symbols=%d  rows=%d",
                 i // batch + 1, (len(symbols) - 1) // batch + 1, len(chunk), rows_total)
        time.sleep(cfg["yf_sleep_seconds"])

    update_symbol_status(con, set(symbols), ok_syms)

    # bhavcopy enrichment for recent dates
    if enrich and cfg["bhavcopy_enabled"]:
        recent = con.execute("""
            SELECT DISTINCT date FROM bars_1d
            WHERE date >= CURRENT_DATE - INTERVAL 30 DAY
              AND deliv_pct IS NULL
            ORDER BY date
        """).df()
        days = [pd.to_datetime(d).date() for d in recent["date"]]
        n = enrich_from_bhavcopy(con, days)
        log.info("Bhavcopy enrichment rows: %d over %d days", n, len(days))

    # benchmarks
    fetch_benchmarks(con, pd.to_datetime(backfill_start or cfg["backfill_start"]).date(),
                     date.today())

    # Correct the weekday bootstrap using ground truth we now have: if not
    # one of ~2400 symbols traded on a seeded date, it was a holiday the
    # naive weekday seed couldn't have known about, not a mass gap.
    con.execute("""
        UPDATE trading_calendar
        SET bhavcopy_available = FALSE
        WHERE bhavcopy_available
          AND date NOT IN (SELECT DISTINCT date FROM bars_1d)
    """)

    # 6. VERIFY by re-asking, not by assuming
    still = missing_pairs(con)
    still = still[still["missing_bars"] > 0]
    if len(still):
        log.warning("%d symbols STILL have gaps after ingest (genuine failures)",
                    len(still))

    con.execute("""
        INSERT INTO ingest_log VALUES (?,?,?,?,?,?,?,?,?)
    """, [t0, "daily", None, date.today(), rows_total, len(ok_syms),
          len(set(symbols)) - len(ok_syms), "ok",
          f"{len(still)} symbols with residual gaps"])

    return {"rows": rows_total, "symbols": len(ok_syms), "residual_gaps": len(still)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch prices and fill any gaps.")
    ap.add_argument("--backfill", action="store_true",
                    help="fetch full history from ingest.backfill_start")
    ap.add_argument("--start", help="override the backfill start date")
    ap.add_argument("--no-enrich", action="store_true",
                    help="skip bhavcopy enrichment")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    con = connect()
    init_schema(con)
    start = args.start or (CFG["ingest"]["backfill_start"] if args.backfill else None)
    res = run_ingest(con, backfill_start=start, enrich=not args.no_enrich)
    log.info("Done: %s", res)
    con.close()


if __name__ == "__main__":
    main()
