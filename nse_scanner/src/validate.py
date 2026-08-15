"""
validate.py — reconcile yfinance against the official NSE bhavcopy.

WHY ONLY THE NEWEST BAR
-----------------------
Bhavcopy is UNADJUSTED. yfinance is split-adjusted. Compare them across a
split and everything mismatches for reasons that are not errors.

So we compare only the most recent bar(s): no corporate action has occurred
since, therefore the two sources MUST agree. Any disagreement is a real
problem, not an adjustment artefact.

THE HIGH-VALUE CATCH
--------------------
When bhavcopy shows a stock trading normally and yfinance shows a 40% gap on
the same day, Yahoo missed a bonus issue. That is yfinance's most common NSE
failure and it manufactures textbook fake W-bottoms — a false second low far
below the first, followed by a "recovery" that is pure data artefact.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

from config import CFG
from db import connect, init_schema
from ingest import download_bhavcopy, last_trading_day

log = logging.getLogger("validate")


def reconcile_day(con, d: date) -> pd.DataFrame:
    """Compare stored close vs bhavcopy close for one date."""
    bh = download_bhavcopy(d)
    if bh is None or bh.empty:
        log.warning("No bhavcopy available for %s — cannot validate", d)
        return pd.DataFrame()

    stored = con.execute(
        "SELECT b.isin, b.symbol, b.close AS yf_close FROM bars_1d b WHERE b.date = ?",
        [d],
    ).df()
    if stored.empty:
        log.warning("No stored bars for %s", d)
        return pd.DataFrame()

    bh = bh[bh["series"].isin(CFG["universe"]["series_allowed"])]
    m = stored.merge(bh[["symbol", "bhav_close"]], on="symbol", how="inner")
    m["date"] = d
    m["pct_diff"] = (m["yf_close"] / m["bhav_close"] - 1.0) * 100.0
    tol = CFG["validation"]["tolerance_pct"]
    m["passed"] = m["pct_diff"].abs() <= tol
    return m[["date", "isin", "symbol", "yf_close", "bhav_close", "pct_diff", "passed"]]


def store_results(con, res: pd.DataFrame) -> int:
    if res.empty:
        return 0
    con.register("tmp_val", res)
    con.execute("INSERT INTO validation_log SELECT * FROM tmp_val")
    con.unregister("tmp_val")
    return len(res)


def suspected_corporate_actions(res: pd.DataFrame, min_gap_pct: float = 15.0) -> pd.DataFrame:
    """
    Large disagreements are almost always a missed bonus/split in yfinance,
    not a tick error. Surface them separately so they get looked at.
    """
    if res.empty:
        return res
    bad = res[res["pct_diff"].abs() >= min_gap_pct].copy()
    if bad.empty:
        return bad
    bad["implied_ratio"] = bad["bhav_close"] / bad["yf_close"]
    return bad.sort_values("pct_diff", key=abs, ascending=False)


def data_is_stale(con) -> tuple[bool, date | None, date | None]:
    """
    THE GUARD THAT PROTECTS REAL MONEY.

    Manual operation means one day you will scan on four-day-old data and act
    on a stale signal. scan.py refuses to run when this returns True.
    """
    latest_bar = con.execute("SELECT MAX(date) FROM bars_1d").fetchone()[0]
    latest_cal = last_trading_day(con)
    if latest_bar is None or latest_cal is None:
        return True, latest_bar, latest_cal
    return (latest_bar < latest_cal), latest_bar, latest_cal


def run_validation(con, days_back: int = 1) -> dict:
    dates = con.execute("""
        SELECT DISTINCT date FROM bars_1d ORDER BY date DESC LIMIT ?
    """, [days_back]).df()

    total, failures = 0, 0
    flagged = []
    for d in pd.to_datetime(dates["date"]).dt.date:
        res = reconcile_day(con, d)
        if res.empty:
            continue
        store_results(con, res)
        total += len(res)
        failures += int((~res["passed"]).sum())
        ca = suspected_corporate_actions(res)
        if len(ca):
            flagged.append(ca)

    if flagged:
        allca = pd.concat(flagged)
        log.error("SUSPECTED MISSED CORPORATE ACTIONS (%d):", len(allca))
        for _, r in allca.head(20).iterrows():
            log.error("  %-12s  yf=%.2f  bhav=%.2f  diff=%.1f%%  implied ratio ~%.2f",
                      r["symbol"], r["yf_close"], r["bhav_close"],
                      r["pct_diff"], r["implied_ratio"])

    rate = (failures / total * 100.0) if total else 0.0
    log.info("Validated %d rows, %d failures (%.2f%%)", total, failures, rate)
    return {"checked": total, "failures": failures, "failure_rate_pct": rate}


def main() -> None:
    ap = argparse.ArgumentParser(description="Reconcile stored prices against bhavcopy.")
    ap.add_argument("--days", type=int, default=1,
                    help="how many recent trading days to check (default 1)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    con = connect()
    init_schema(con)

    stale, bar, cal = data_is_stale(con)
    log.info("Latest stored bar: %s | Latest trading day: %s | stale=%s", bar, cal, stale)

    res = run_validation(con, days_back=args.days)
    if res["failure_rate_pct"] > 0.5:
        log.error("Failure rate above 0.5%% — investigate before trusting any scan.")
    con.close()


if __name__ == "__main__":
    main()
