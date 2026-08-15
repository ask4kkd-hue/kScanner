"""
universe.py — builds the tradeable instrument list.

Two things this module exists to get right:

1. KEY ON ISIN, NOT SYMBOL.
   Symbols get renamed. Key on symbol and a ten-year history silently splits
   into two broken series with no error anywhere.

2. SURVIVORSHIP BIAS.
   Today's EQUITY_L.csv contains only companies that still exist. Backtesting
   against it quietly deletes every company that failed and overstates your
   hit rate. The `--from-bhavcopy` path rebuilds the universe from historical
   bhavcopies, which include the dead ones.
"""

from __future__ import annotations

import argparse
import io
import logging
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from config import CFG
from db import connect, init_schema

log = logging.getLogger("universe")

NSE_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*",
}

EQUITY_L_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"

# NSE periodically changes these URLs. When ingestion breaks, this is the
# first place to look. Failures are logged loudly rather than swallowed —
# a scanner running silently on stale data is worse than one that is down.
ASM_URL = "https://www.nseindia.com/api/reportASM?json=true"
GSM_URL = "https://www.nseindia.com/api/reportGSM?json=true"


def _nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(NSE_HEADERS)
    try:
        s.get("https://www.nseindia.com", timeout=15)  # sets the cookies NSE requires
    except Exception as exc:
        log.warning("Could not prime NSE session: %s", exc)
    return s


# ---------------------------------------------------------------- equity list

def fetch_equity_list(save_dir: str | None = None) -> pd.DataFrame:
    """Download today's EQUITY_L.csv and snapshot it (dated) for the audit trail."""
    s = _nse_session()
    r = s.get(EQUITY_L_URL, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content))
    df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]

    save_dir = save_dir or CFG["paths"]["universe"]
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    out = Path(save_dir) / f"EQUITY_L_{date.today():%Y%m%d}.csv"
    df.to_csv(out, index=False)
    log.info("Saved universe snapshot -> %s (%d rows)", out, len(df))
    return df


def load_local_equity_list(path: str) -> pd.DataFrame:
    """Use an EQUITY_L.csv you already have on disk."""
    df = pd.read_csv(path)
    df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]
    return df


def normalise_equity_list(df: pd.DataFrame) -> pd.DataFrame:
    """Map EQUITY_L columns onto the instruments schema."""
    colmap = {
        "SYMBOL": "symbol",
        "NAME_OF_COMPANY": "name",
        "SERIES": "series",
        "ISIN_NUMBER": "isin",
        "DATE_OF_LISTING": "listing_date",
    }
    keep = {k: v for k, v in colmap.items() if k in df.columns}
    out = df.rename(columns=keep)[list(keep.values())].copy()
    out["symbol"] = out["symbol"].astype(str).str.strip()
    out["isin"] = out["isin"].astype(str).str.strip()
    out["series"] = out["series"].astype(str).str.strip()
    return out[out["isin"].str.startswith("INE") | out["isin"].str.startswith("INF")]


# ---------------------------------------------------------------- surveillance

def fetch_surveillance_lists() -> pd.DataFrame:
    """
    ASM / GSM membership. A textbook W-pattern in a GSM stock is a pattern you
    cannot actually trade — 100% margin, tightened bands, sometimes weekly
    settlement. Excluded at scan time.

    NSE serves these as JSON reports now, not flat CSVs, and the two shapes
    differ: ASM nests rows under longterm/shortterm, GSM is a flat list.

    Returns columns: symbol, asm, gsm.
    """
    s = _nse_session()
    frames = []

    try:
        r = s.get(ASM_URL, timeout=30)
        r.raise_for_status()
        payload = r.json()
        rows = payload.get("longterm", {}).get("data", []) + \
            payload.get("shortterm", {}).get("data", [])
        symbols = {str(row["symbol"]).strip() for row in rows if row.get("symbol")}
        if symbols:
            frames.append(pd.DataFrame({"symbol": sorted(symbols), "asm": True}))
    except Exception as exc:
        # Loud, not silent. See module docstring.
        log.error("FAILED to fetch ASM list (%s): %s", ASM_URL, exc)

    try:
        r = s.get(GSM_URL, timeout=30)
        r.raise_for_status()
        rows = r.json()
        symbols = {str(row["symbol"]).strip() for row in rows if row.get("symbol")}
        if symbols:
            frames.append(pd.DataFrame({"symbol": sorted(symbols), "gsm": True}))
    except Exception as exc:
        log.error("FAILED to fetch GSM list (%s): %s", GSM_URL, exc)

    if not frames:
        return pd.DataFrame(columns=["symbol", "asm", "gsm"])

    out = frames[0]
    for f in frames[1:]:
        out = out.merge(f, on="symbol", how="outer")
    for c in ("asm", "gsm"):
        if c not in out.columns:
            out[c] = False
    return out.fillna({"asm": False, "gsm": False})


# ---------------------------------------------------------------- persistence

def upsert_instruments(con, df: pd.DataFrame) -> int:
    """Insert or update instruments, preserving first_seen."""
    today = date.today()
    df = df.copy()
    df["sector"] = df.get("sector")
    df["industry"] = df.get("industry")
    # NSE's EQUITY_L.csv DATE_OF_LISTING is always DD-MMM-YYYY (e.g.
    # "06-OCT-2008") — verified against a real downloaded file, all rows
    # matching, zero exceptions. An explicit format avoids both the pandas
    # "could not infer format" warning AND the slow per-row dateutil
    # fallback it triggers; dayfirst=True was never actually doing
    # anything here since a month NAME has no day/month ambiguity to
    # resolve.
    df["first_seen"] = pd.to_datetime(
        df.get("listing_date", pd.NaT), format="%d-%b-%Y", errors="coerce"
    ).dt.date
    df["last_seen"] = today

    con.register("tmp_inst", df[["isin", "symbol", "name", "series",
                                 "sector", "industry", "first_seen", "last_seen"]])
    con.execute("""
        INSERT INTO instruments
            (isin, symbol, name, series, sector, industry, first_seen, last_seen)
        SELECT isin, symbol, name, series, sector, industry, first_seen, last_seen
        FROM tmp_inst
        ON CONFLICT (isin) DO UPDATE SET
            symbol    = excluded.symbol,
            name      = excluded.name,
            series    = excluded.series,
            sector    = COALESCE(excluded.sector, instruments.sector),
            industry  = COALESCE(excluded.industry, instruments.industry),
            first_seen = COALESCE(instruments.first_seen, excluded.first_seen),
            last_seen = excluded.last_seen
    """)
    con.unregister("tmp_inst")

    # every new instrument starts active
    con.execute("""
        INSERT INTO symbol_status (isin, status, consecutive_misses, last_success)
        SELECT i.isin, 'active', 0, NULL
        FROM instruments i
        LEFT JOIN symbol_status s ON s.isin = i.isin
        WHERE s.isin IS NULL
    """)
    return len(df)


def save_flags(con, flags: pd.DataFrame, as_of: date | None = None) -> int:
    """Store today's ASM/GSM snapshot against ISINs."""
    if flags.empty:
        return 0
    as_of = as_of or date.today()
    inst = con.execute("SELECT isin, symbol FROM instruments").df()
    merged = flags.merge(inst, on="symbol", how="inner")
    merged["date"] = as_of
    merged["price_band"] = None

    con.register("tmp_flags", merged[["date", "isin", "asm", "gsm", "price_band"]])
    con.execute("""
        INSERT INTO flags (date, isin, asm, gsm, price_band)
        SELECT date, isin, asm, gsm, price_band FROM tmp_flags
        ON CONFLICT (date, isin) DO UPDATE SET
            asm = excluded.asm, gsm = excluded.gsm
    """)
    con.unregister("tmp_flags")
    return len(merged)


# ---------------------------------------------------------------- selection

def active_universe(con, as_of: date | None = None) -> pd.DataFrame:
    """
    The symbols a scan should consider today.

    Applies: allowed series, ASM/GSM exclusion, liquidity floor, minimum price,
    minimum history. Liquidity is measured in RUPEES, not share count — 100,000
    shares of a Rs 8 stock is nothing; of a Rs 3,000 stock it is enormous.
    """
    u = CFG["universe"]
    as_of = as_of or date.today()
    series_list = "', '".join(u["series_allowed"])
    min_turnover = u["min_turnover_cr"] * 1e7  # crore -> rupees

    sql = f"""
    WITH latest_flags AS (
        SELECT isin, asm, gsm,
               ROW_NUMBER() OVER (PARTITION BY isin ORDER BY date DESC) rn
        FROM flags
    ),
    stats AS (
        SELECT isin,
               COUNT(*)                                       AS bars,
               MEDIAN(close * volume)                          AS med_turnover,
               MAX(close)                                      AS last_close
        FROM (
            SELECT isin, close, volume,
                   ROW_NUMBER() OVER (PARTITION BY isin ORDER BY date DESC) rn
            FROM bars_1d
        ) WHERE rn <= 20
        GROUP BY isin
    ),
    hist AS (
        SELECT isin, COUNT(*) AS total_bars FROM bars_1d GROUP BY isin
    )
    SELECT i.isin, i.symbol, i.name, i.sector, i.series,
           s.med_turnover, h.total_bars
    FROM instruments i
    JOIN symbol_status ss ON ss.isin = i.isin AND ss.status = 'active'
    JOIN stats s  ON s.isin = i.isin
    JOIN hist  h  ON h.isin = i.isin
    LEFT JOIN latest_flags f ON f.isin = i.isin AND f.rn = 1
    WHERE i.series IN ('{series_list}')
      AND s.med_turnover >= {min_turnover}
      AND s.last_close   >= {u['min_price']}
      AND h.total_bars   >= {u['min_bars_history']}
      {"AND COALESCE(f.asm, FALSE) = FALSE" if u['exclude_asm'] else ""}
      {"AND COALESCE(f.gsm, FALSE) = FALSE" if u['exclude_gsm'] else ""}
    ORDER BY i.symbol
    """
    return con.execute(sql).df()


def all_symbols_for_ingest(con) -> pd.DataFrame:
    """
    Everything we still fetch data for — wider than the tradeable universe.

    Delisted names are excluded from fetching but their HISTORY IS KEPT,
    because removing it would reintroduce survivorship bias into backtests.
    """
    return con.execute("""
        SELECT i.isin, i.symbol, i.first_seen
        FROM instruments i
        JOIN symbol_status s ON s.isin = i.isin
        WHERE s.status = 'active'
        ORDER BY i.symbol
    """).df()


# ---------------------------------------------------------------- cli

def run_universe(con, local_csv: str | None = None, skip_flags: bool = False) -> dict:
    """
    The full sequence, on an ALREADY-OPEN connection — callers that already
    hold one (the web UI's Refresh button) must never call connect() again;
    DuckDB is single-writer, so a second connection to the same file fails
    outright rather than queuing (see db.py's own docstring).
    """
    raw = load_local_equity_list(local_csv) if local_csv else fetch_equity_list()
    inst = normalise_equity_list(raw)
    n = upsert_instruments(con, inst)
    log.info("Instruments upserted: %d", n)

    m = 0
    if not skip_flags:
        flags = fetch_surveillance_lists()
        m = save_flags(con, flags)
        log.info("Surveillance flags stored: %d", m)

    total = con.execute("SELECT COUNT(*) FROM instruments").fetchone()[0]
    log.info("instruments table now holds %d rows", total)
    return {"instruments_upserted": n, "flags_stored": m, "instruments_total": total}


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the instrument universe.")
    ap.add_argument("--local-csv", help="path to an EQUITY_L.csv you already have")
    ap.add_argument("--skip-flags", action="store_true",
                    help="skip the ASM/GSM download")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    con = connect()
    init_schema(con)
    run_universe(con, local_csv=args.local_csv, skip_flags=args.skip_flags)
    con.close()


if __name__ == "__main__":
    main()
