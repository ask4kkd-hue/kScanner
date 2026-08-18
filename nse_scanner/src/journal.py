"""
journal.py — trade journal.

THE POINT OF THIS MODULE
------------------------
Every entry links back to the signal_id that produced it. That join is what
lets you answer "which preset actually makes money" — a question you cannot
answer from a spreadsheet that lives apart from your screener.

MAE and MFE are computed AUTOMATICALLY from bars_1d. You already own the price
history, so there is no reason to type them in:
  - MAE (worst drawdown while held) tells you if your stop is too tight
  - MFE (best unrealised gain) tells you if you are exiting too early
Together they are the two most useful numbers in any journal, and almost
nobody computes them.

R-multiple, not rupees, is the primary unit. It makes every trade comparable
regardless of position size.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from db import connect

log = logging.getLogger("journal")


# =====================================================================
# WRITE
# =====================================================================

def open_trade(con, symbol: str, entry_date: date, entry_price: float,
               qty: int, stop_price: float, target_price: float | None = None,
               preset_name: str = "", signal_id: str = "",
               thesis: str = "") -> int:
    """Record a new position."""
    isin = con.execute("SELECT isin FROM instruments WHERE symbol = ?",
                       [symbol]).fetchone()
    isin = isin[0] if isin else None
    tid = con.execute("SELECT nextval('trade_id_seq')").fetchone()[0]

    con.execute("""
        INSERT INTO trades (trade_id, signal_id, isin, symbol, preset_name,
                            entry_date, entry_price, qty, stop_price, target_price,
                            thesis, status)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,'open')
    """, [tid, signal_id, isin, symbol, preset_name, entry_date, entry_price,
          qty, stop_price, target_price, thesis])

    snapshot_features(con, tid, isin, entry_date)
    return tid


def snapshot_features(con, trade_id: int, isin: str | None, on: date) -> int:
    """
    Freeze the feature vector at entry.

    Six months from now you will want to ask "do my winners have higher
    delivery % than my losers?" — answerable only if you captured it at the
    time. Doing it later means using today's values, which is meaningless.
    """
    if not isin:
        return 0
    row = con.execute("""
        SELECT adr_pct20, atr14, adx14, rsi14, rvol, deliv_pct_sma20,
               dist_sma200_pct, rs_rank_pct, sma_compression, turnover_sma20
        FROM features_1d WHERE isin = ? AND date <= ? ORDER BY date DESC LIMIT 1
    """, [isin, on]).df()
    if row.empty:
        return 0
    n = 0
    for col in row.columns:
        v = row.iloc[0][col]
        if v is not None and not (isinstance(v, float) and np.isnan(v)):
            con.execute("INSERT INTO trade_snapshot VALUES (?,?,?)",
                        [trade_id, col, float(v)])
            n += 1
    return n


def remaining_qty(con, trade_id: int) -> int:
    """
    Original qty minus every partial exit booked against this trade so far.

    A CLOSED trade is always 0, regardless of the arithmetic — close_trade()
    settles the final leg directly on `trades` rather than inserting one more
    trade_partials row for itself, so the qty-minus-partials formula alone
    would still show leftover qty after a full close.
    """
    row = con.execute("""
        SELECT t.status, t.qty - COALESCE(
            (SELECT SUM(qty) FROM trade_partials WHERE trade_id = t.trade_id), 0)
        FROM trades t WHERE t.trade_id = ?
    """, [trade_id]).fetchone()
    if row is None:
        raise ValueError(f"No trade {trade_id}")
    status, remaining = row
    return 0 if status == "closed" else int(remaining)


def partial_close(con, trade_id: int, exit_date: date, exit_price: float,
                  qty: int, exit_reason: str, note: str = "",
                  costs: float = 0.0) -> dict:
    """
    Book a partial exit: sell part of an open position, keep the rest running.

    Exiting exactly the remaining qty is a FULL close and must go through
    close_trade() instead — enforced here so the two paths never overlap and
    a position can't end up "open" with zero qty left.
    """
    t = con.execute("SELECT status FROM trades WHERE trade_id = ?", [trade_id]).fetchone()
    if t is None:
        raise ValueError(f"No trade {trade_id}")
    if t[0] != "open":
        raise ValueError(f"Trade {trade_id} is not open.")

    remaining = remaining_qty(con, trade_id)
    if not (0 < qty < remaining):
        raise ValueError(
            f"qty must be between 1 and {remaining - 1} (remaining qty is {remaining}; "
            f"to exit all of it, close the position instead).")

    entry_price = con.execute(
        "SELECT entry_price FROM trades WHERE trade_id = ?", [trade_id]).fetchone()[0]
    gross = (exit_price - entry_price) * qty
    net = gross - costs

    partial_id = con.execute("SELECT nextval('trade_partial_id_seq')").fetchone()[0]
    con.execute("""
        INSERT INTO trade_partials
            (partial_id, trade_id, exit_date, exit_price, qty, exit_reason,
             gross_pnl, costs, net_pnl, note)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, [partial_id, trade_id, exit_date, exit_price, qty, exit_reason,
          gross, costs, net, note])

    return {"partial_id": partial_id, "trade_id": trade_id, "qty": qty,
            "net_pnl": net, "remaining_qty": remaining - qty}


def close_trade(con, trade_id: int, exit_date: date, exit_price: float,
                exit_reason: str, followed_plan: bool = True,
                review_note: str = "", costs: float = 0.0) -> dict:
    """
    Close whatever qty remains open (the whole position, if it was never
    partially exited) and compute every derived stat, including MAE/MFE.

    If earlier partial exits already booked part of this trade, the stored
    net_pnl/gross_pnl/costs become the WHOLE TRADE's totals — every partial
    leg's net_pnl plus this final leg's — and r_multiple becomes the
    qty-weighted average R across every leg, so a closed trade's numbers
    describe the full position's outcome, not just the last slice sold.
    """
    t = con.execute("SELECT * FROM trades WHERE trade_id = ?", [trade_id]).df()
    if t.empty:
        raise ValueError(f"No trade {trade_id}")
    t = t.iloc[0]

    close_qty = remaining_qty(con, trade_id)
    if close_qty <= 0:
        raise ValueError(f"Trade {trade_id} has no remaining qty to close.")

    gross = (exit_price - t["entry_price"]) * close_qty
    net = gross - costs
    risk = t["entry_price"] - t["stop_price"]
    r = (exit_price - t["entry_price"]) / risk if risk > 0 else np.nan
    hold = (pd.to_datetime(exit_date) - pd.to_datetime(t["entry_date"])).days

    mae, mfe = compute_mae_mfe(con, t["isin"], t["entry_date"], exit_date,
                               t["entry_price"])

    partials = con.execute("""
        SELECT qty, exit_price, gross_pnl, costs, net_pnl
        FROM trade_partials WHERE trade_id = ?
    """, [trade_id]).df()

    total_gross, total_costs, total_net = gross, costs, net
    legs_r = [(r, close_qty)]
    if not partials.empty:
        total_gross += partials["gross_pnl"].sum()
        total_costs += partials["costs"].sum()
        total_net += partials["net_pnl"].sum()
        for _, prow in partials.iterrows():
            leg_r = (prow["exit_price"] - t["entry_price"]) / risk if risk > 0 else np.nan
            legs_r.append((leg_r, prow["qty"]))

    total_qty = sum(q for _, q in legs_r)
    blended_r = (sum(rr * q for rr, q in legs_r) / total_qty
                if risk > 0 and total_qty else np.nan)

    con.execute("""
        UPDATE trades SET
            exit_date=?, exit_price=?, exit_reason=?,
            gross_pnl=?, costs=?, net_pnl=?, r_multiple=?, holding_days=?,
            mae_pct=?, mfe_pct=?, followed_plan=?, review_note=?, status='closed'
        WHERE trade_id=?
    """, [exit_date, exit_price, exit_reason, total_gross, total_costs, total_net,
          blended_r, hold, mae, mfe, followed_plan, review_note, trade_id])

    return {"trade_id": trade_id, "net_pnl": total_net, "r_multiple": blended_r,
            "holding_days": hold, "mae_pct": mae, "mfe_pct": mfe}


_EDITABLE_FIELDS = {"entry_date", "entry_price", "qty", "stop_price", "target_price", "thesis"}


def update_trade(con, trade_id: int, **fields) -> None:
    """
    Edit an OPEN position's entry-side details — correcting a fat-fingered
    entry price, adjusting a stop, updating the thesis. Exit-side fields
    (exit_price, exit_reason, ...) go through close_trade() instead; this
    is deliberately restricted to _EDITABLE_FIELDS so a caller can't use it
    to sneak a trade into 'closed' or overwrite the computed P&L columns.
    """
    patch = {k: v for k, v in fields.items() if k in _EDITABLE_FIELDS and v is not None}
    if not patch:
        return
    exists = con.execute("SELECT 1 FROM trades WHERE trade_id = ?", [trade_id]).fetchone()
    if not exists:
        raise ValueError(f"No trade {trade_id}")
    set_clause = ", ".join(f"{k} = ?" for k in patch)
    con.execute(f"UPDATE trades SET {set_clause} WHERE trade_id = ?",
               [*patch.values(), trade_id])


def delete_trade(con, trade_id: int) -> None:
    """
    Remove a trade entirely, including its feature snapshot and tags.

    For correcting a MISTAKEN entry (wrong symbol, fat-fingered qty caught
    before it matters) — not for exiting a real position, which should go
    through close_trade() instead so the history (and the P&L it produced)
    is kept, not erased.
    """
    con.execute("DELETE FROM trade_tags WHERE trade_id = ?", [trade_id])
    con.execute("DELETE FROM trade_snapshot WHERE trade_id = ?", [trade_id])
    con.execute("DELETE FROM trade_partials WHERE trade_id = ?", [trade_id])
    con.execute("DELETE FROM trades WHERE trade_id = ?", [trade_id])


def compute_mae_mfe(con, isin: str, entry_date, exit_date,
                    entry_price: float) -> tuple[float, float]:
    """Worst and best excursion while the position was held — from bars_1d."""
    df = con.execute("""
        SELECT high, low FROM bars_1d
        WHERE isin = ? AND date >= ? AND date <= ? ORDER BY date
    """, [isin, entry_date, exit_date]).df()
    if df.empty or not entry_price:
        return float("nan"), float("nan")
    mae = (df["low"].min() / entry_price - 1.0) * 100.0
    mfe = (df["high"].max() / entry_price - 1.0) * 100.0
    return float(mae), float(mfe)


def add_tags(con, trade_id: int, tags: list[str]) -> int:
    """
    Behavioural tags: chased_entry, moved_stop, revenge_trade, oversized,
    exited_early. Grouping P&L by tag makes your leaks announce themselves.
    """
    for tag in tags:
        con.execute("INSERT INTO trade_tags VALUES (?,?)", [trade_id, tag])
    return len(tags)


def log_missed(con, signal_id: str, scan_date: date, symbol: str,
               skip_reason: str) -> None:
    """
    Signals you SAW and skipped.

    Tracking these exposes selection bias — most traders skip their best
    setups. hypothetical_r is filled in later by update_missed_outcomes().
    """
    isin = con.execute("SELECT isin FROM instruments WHERE symbol = ?",
                       [symbol]).fetchone()
    con.execute("INSERT INTO missed_trades VALUES (?,?,?,?,?,NULL)",
                [signal_id, scan_date, isin[0] if isin else None,
                 symbol, skip_reason])


# =====================================================================
# ANALYTICS
# =====================================================================

def list_closed_trades(con) -> pd.DataFrame:
    """Row-level closed trades, newest exit first -- same table/filter as
    summary() etc. below, just ungrouped. Those functions answer "how am I
    doing overall"; this answers "what actually happened, trade by trade",
    which nothing else exposes (Positions only ever lists status='open')."""
    return con.execute("""
        SELECT trade_id, symbol, preset_name, entry_date, entry_price, qty,
               exit_date, exit_price, exit_reason, net_pnl, r_multiple,
               holding_days, mae_pct, mfe_pct
        FROM trades WHERE status = 'closed' ORDER BY exit_date DESC
    """).df()


def summary(con) -> dict:
    t = con.execute("SELECT * FROM trades WHERE status = 'closed'").df()
    if t.empty:
        return {"trades": 0}

    wins = t[t["net_pnl"] > 0]
    losses = t[t["net_pnl"] <= 0]
    win_rate = len(wins) / len(t) * 100.0
    avg_win_r = wins["r_multiple"].mean() if len(wins) else 0.0
    avg_loss_r = losses["r_multiple"].mean() if len(losses) else 0.0

    gl = abs(losses["net_pnl"].sum())
    return {
        "trades": len(t),
        "win_rate": win_rate,
        "expectancy_r": (win_rate / 100) * avg_win_r + (1 - win_rate / 100) * avg_loss_r,
        "avg_win_r": avg_win_r,
        "avg_loss_r": avg_loss_r,
        "profit_factor": wins["net_pnl"].sum() / gl if gl else float("inf"),
        "net_pnl": t["net_pnl"].sum(),
        "median_hold_days": t["holding_days"].median(),
        "median_mae": t["mae_pct"].median(),
        "median_mfe": t["mfe_pct"].median(),
    }


def adherence_report(con) -> pd.DataFrame:
    """
    P&L of trades where you followed the plan vs trades where you did not.

    Usually the most uncomfortable and most useful table in the journal.
    """
    return con.execute("""
        SELECT COALESCE(followed_plan, FALSE) AS followed_plan,
               COUNT(*) AS trades,
               AVG(r_multiple) AS avg_r,
               SUM(net_pnl) AS net_pnl,
               AVG(CASE WHEN net_pnl > 0 THEN 1.0 ELSE 0.0 END) * 100 AS win_rate
        FROM trades WHERE status = 'closed'
        GROUP BY 1
    """).df()


def preset_attribution(con) -> pd.DataFrame:
    """Which preset actually makes money. Feeds straight back into config.yaml."""
    return con.execute("""
        SELECT preset_name, COUNT(*) AS trades,
               AVG(r_multiple) AS avg_r, SUM(net_pnl) AS net_pnl,
               AVG(CASE WHEN net_pnl > 0 THEN 1.0 ELSE 0.0 END) * 100 AS win_rate,
               MEDIAN(holding_days) AS median_hold
        FROM trades WHERE status = 'closed'
        GROUP BY preset_name ORDER BY avg_r DESC
    """).df()


def tag_analysis(con) -> pd.DataFrame:
    """P&L grouped by behavioural tag."""
    return con.execute("""
        SELECT g.tag, COUNT(*) AS trades,
               AVG(t.r_multiple) AS avg_r, SUM(t.net_pnl) AS net_pnl
        FROM trade_tags g JOIN trades t ON t.trade_id = g.trade_id
        WHERE t.status = 'closed'
        GROUP BY g.tag ORDER BY avg_r
    """).df()


def snapshot_analysis(con, metric: str, buckets: int = 4) -> pd.DataFrame:
    """
    Do winners differ from losers on a given entry-time metric?

    e.g. snapshot_analysis(con, 'deliv_pct_sma20') answers
    'do my winners have higher delivery %?'
    """
    df = con.execute("""
        SELECT s.value, t.r_multiple, t.net_pnl
        FROM trade_snapshot s JOIN trades t ON t.trade_id = s.trade_id
        WHERE s.metric = ? AND t.status = 'closed'
    """, [metric]).df()
    if df.empty:
        return df
    df["bucket"] = pd.qcut(df["value"], min(buckets, df["value"].nunique()),
                           duplicates="drop")
    return df.groupby("bucket", observed=True).agg(
        trades=("r_multiple", "size"),
        avg_r=("r_multiple", "mean"),
        win_rate=("net_pnl", lambda s: (s > 0).mean() * 100),
    ).reset_index()


def equity_curve(con) -> pd.DataFrame:
    t = con.execute("""
        SELECT exit_date, net_pnl FROM trades
        WHERE status = 'closed' ORDER BY exit_date
    """).df()
    if t.empty:
        return t
    t["cum_pnl"] = t["net_pnl"].cumsum()
    t["peak"] = t["cum_pnl"].cummax()
    t["drawdown"] = t["cum_pnl"] - t["peak"]
    return t


def update_open_trades(con, as_of: date | None = None) -> int:
    """Refresh unrealised P&L and running MAE/MFE for open positions."""
    open_t = con.execute("SELECT * FROM trades WHERE status = 'open'").df()
    n = 0
    for _, t in open_t.iterrows():
        # A trade with no isin (open_trade() doesn't reject an unknown
        # symbol — it stores isin=NULL) reads back as NaN via pandas. Passed
        # straight through as a query parameter, DuckDB infers a DOUBLE
        # parameter type from the float NaN and tries to cast the isin
        # VARCHAR column to match, which throws for every real ISIN in the
        # table — not just a no-op for this one row.
        if pd.isna(t["isin"]):
            continue
        last = con.execute("""
            SELECT close, date FROM bars_1d WHERE isin = ?
            ORDER BY date DESC LIMIT 1
        """, [t["isin"]]).df()
        if last.empty:
            continue
        mae, mfe = compute_mae_mfe(con, t["isin"], t["entry_date"],
                                   last["date"].iloc[0], t["entry_price"])
        con.execute("UPDATE trades SET mae_pct=?, mfe_pct=? WHERE trade_id=?",
                    [mae, mfe, t["trade_id"]])
        n += 1
    return n


def compare_with_backtest(con, preset_name: str) -> pd.DataFrame:
    """
    THE LOOP THAT ACTUALLY IMPROVES YOUR TRADING.

    The backtest says what the logic can do. The journal says what you did.
    The gap is where the money is:
      backtest 45% win rate, you 32%     -> execution gap, not a logic problem
      backtest holds 7 days, you hold 3  -> you are exiting early
      backtest MAE 1.8%, yours 0.9%      -> you are stopping out on noise
    """
    live = con.execute("""
        SELECT COUNT(*) AS trades,
               AVG(CASE WHEN net_pnl > 0 THEN 1.0 ELSE 0.0 END)*100 AS win_rate,
               AVG(r_multiple) AS avg_r,
               MEDIAN(holding_days) AS median_hold,
               MEDIAN(mae_pct) AS median_mae,
               MEDIAN(mfe_pct) AS median_mfe
        FROM trades WHERE status='closed' AND preset_name = ?
    """, [preset_name]).df()

    bt = con.execute("""
        SELECT m.trades, m.win_rate, m.expectancy_r AS avg_r,
               m.median_hold_days AS median_hold,
               m.median_mae, m.median_mfe
        FROM backtest_metrics m
        JOIN backtest_runs r ON r.run_id = m.run_id
        WHERE r.preset_name = ?
        ORDER BY r.run_ts DESC LIMIT 1
    """, [preset_name]).df()

    if live.empty or bt.empty:
        return pd.DataFrame()

    live["source"] = "live"
    bt["source"] = "backtest"
    out = pd.concat([bt, live], ignore_index=True)
    return out[["source", "trades", "win_rate", "avg_r",
                "median_hold", "median_mae", "median_mfe"]]
