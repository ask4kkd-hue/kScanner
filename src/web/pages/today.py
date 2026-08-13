"""
web/pages/today.py — default landing screen, end-of-day use.

Must load in under 2 seconds (v2_instructions.md). That rules out running a
live scan.scan() on page load — a real scan takes 1-2 minutes, which is why
it's a manual button on the Scan screen. "New opportunities" here instead
reads the already-persisted signals_1d table from the last actual scan run
(run_daily.bat or a manual "Run scan" click) — a plain SELECT, not a
recomputation.

Weekly/monthly opportunities check whether features_1w/features_1m have any
rows at all; if not (they don't yet — see README "Pending features"), this
says so explicitly rather than silently reporting zero signals.
"""

from __future__ import annotations

from datetime import date, timedelta

from nicegui import ui

import advisor
import components as comp
import journal as jr
import theme
import watchlist as wl
from db import table_counts
from scan import regime_state
from validate import data_is_stale


def _latest_close(con, isin: str) -> float | None:
    row = con.execute("SELECT close FROM bars_1d WHERE isin = ? ORDER BY date DESC LIMIT 1",
                      [isin]).fetchone()
    return float(row[0]) if row else None


def _tracked_symbols(con) -> set[str]:
    held = con.execute("SELECT DISTINCT symbol FROM trades WHERE status = 'open'") \
        .df()["symbol"].tolist()
    watched = con.execute("SELECT DISTINCT symbol FROM watchlist").df()["symbol"].tolist()
    return set(held) | set(watched)


def _latest_signals(con, timeframe: str, limit: int = 5):
    return con.execute("""
        WITH latest AS (SELECT MAX(scan_date) AS d FROM signals_1d WHERE timeframe = ?)
        SELECT s.symbol, s.trigger_price, s.stop_suggested, s.target_suggested,
              f.rs_rank_pct
        FROM signals_1d s
        JOIN latest ON s.scan_date = latest.d
        LEFT JOIN features_1d f ON f.isin = s.isin AND f.date = s.scan_date
        WHERE s.timeframe = ?
        ORDER BY f.rs_rank_pct DESC NULLS LAST
    """, [timeframe, timeframe]).df()


def render(con, state: dict) -> None:
    tracked = _tracked_symbols(con)

    # ---------------------------------------------------------- 1. STATUS
    with comp.section("Status", collapsed=False):
        stale, latest_bar, latest_cal = data_is_stale(con)
        counts = table_counts(con)
        fails = con.execute("""
            SELECT COUNT(*) FROM validation_log
            WHERE passed = FALSE AND date >= CURRENT_DATE - INTERVAL 7 DAY
        """).fetchone()[0]
        regime = regime_state(con, date.today())

        if stale and latest_bar and latest_cal:
            gap = con.execute("""
                SELECT COUNT(*) FROM trading_calendar
                WHERE bhavcopy_available AND date > ? AND date <= ?
            """, [latest_bar, latest_cal]).fetchone()[0]
            ui.label(f"Run refresh — {gap} session{'s' if gap != 1 else ''} behind").classes(
                "text-sm font-semibold").style(f"color:{theme.CRITICAL}")
        else:
            ui.label("Data current").classes("text-sm font-semibold").style(
                f"color:{theme.ACCENT}")

        with ui.row().classes("gap-6 text-xs mt-1").style(f"color:{theme.TEXT_MUTED}"):
            ui.label(f"latest bar {latest_bar or '—'}")
            ui.label(f"last trading day {latest_cal or '—'}")
            ui.label(f"validation fails (7d) {fails}")
            ui.label(f"market regime {regime}")

    # ---------------------------------------------------- 2. YOUR POSITIONS
    with comp.section("Your Positions", collapsed=False):
        jr.update_open_trades(con)
        open_trades = con.execute("""
            SELECT trade_id, isin, symbol, entry_date, entry_price, qty, stop_price
            FROM trades WHERE status = 'open'
        """).df()

        if open_trades.empty:
            ui.label("No open positions.").classes("text-sm")
        else:
            rows = []
            for _, t in open_trades.iterrows():
                s = advisor.position_status(con, int(t["trade_id"]))
                close = _latest_close(con, t["isin"])
                pnl_pct = (close / t["entry_price"] - 1.0) * 100.0 if close else None
                risk = t["entry_price"] - t["stop_price"]
                r_mult = (close - t["entry_price"]) / risk if close and risk > 0 else None
                rows.append((t, s, pnl_pct, r_mult))

            order = {"REVIEW": 0, "WATCH": 1, "HOLD": 2}
            rows.sort(key=lambda x: order.get(x[1]["status"], 3))

            total_pnl = sum((_latest_close(con, t["isin"]) or t["entry_price"]) * t["qty"]
                            - t["entry_price"] * t["qty"] for t, *_ in rows)
            at_risk = sum(1 for _, s, _, _ in rows if s["status"] in ("WATCH", "REVIEW"))

            for t, s, pnl_pct, r_mult in rows:
                exp = ui.expansion().classes("w-full").props("dense")
                with exp:
                    with exp.add_slot("header"):
                        with ui.row().classes("items-center gap-4 w-full"):
                            ui.label(t["symbol"]).classes("font-semibold w-28")
                            ui.label(f"day {s['metrics'].get('days_held', '—')}").classes(
                                "text-xs w-16").style(f"color:{theme.TEXT_MUTED}")
                            ui.label(f"{pnl_pct:+.1f}%" if pnl_pct is not None else "—").classes(
                                "text-xs w-16")
                            ui.label(f"{r_mult:+.2f}R" if r_mult is not None else "—").classes(
                                "text-xs w-16")
                            comp.status_badge(s["status"])
                    for reason in s["reasons"]:
                        ui.label(f"· {reason}").classes("text-xs").style(
                            f"color:{theme.TEXT_MUTED}")

            with ui.row().classes("gap-6 text-sm mt-2"):
                ui.label(f"Total open P&L: ₹{total_pnl:,.0f}").classes("font-semibold")
                ui.label(f"At risk: {at_risk} of {len(rows)}").classes("font-semibold")

    # ------------------------------------------------- 3. NEW OPPORTUNITIES
    with comp.section("New Opportunities", collapsed=False):
        def opportunity_block(title: str, timeframe: str, features_table: str) -> None:
            with comp.section(title, collapsed=False):
                if timeframe != "1d":
                    built = con.execute(
                        f"SELECT COUNT(*) FROM {features_table}").fetchone()[0]
                    if not built:
                        ui.label(f"Not built yet — run features.py for "
                                f"{timeframe}").classes("text-sm").style(
                            f"color:{theme.TEXT_MUTED}")
                        return

                sig = _latest_signals(con, timeframe)
                if sig.empty:
                    ui.label("No signals from the last scan.").classes("text-sm")
                    return

                new_sig = sig[~sig["symbol"].isin(tracked)]
                already = sig[sig["symbol"].isin(tracked)]
                ui.label(f"{len(sig)} signals — {len(new_sig)} new, "
                        f"{len(already)} already tracked").classes("text-xs").style(
                    f"color:{theme.TEXT_MUTED}")

                for _, row in new_sig.head(5).iterrows():
                    with ui.row().classes("gap-4 text-sm"):
                        ui.label(row["symbol"]).classes("w-28 font-semibold")
                        ui.label(f"{row['trigger_price']:.2f}").classes("w-20")
                        rs = row.get("rs_rank_pct")
                        ui.label(f"RS {rs:.0f}" if rs == rs else "RS —").classes("w-16")

                def go_to_scan():
                    state["page"] = "scan"
                    ui.notify(f"Open the Scan tab to see all {timeframe} signals.")

                ui.button(f"See all in Scan", on_click=go_to_scan) \
                    .props("dense flat no-caps size=sm")

        opportunity_block("Short term — 1D signals", "1d", "features_1d")
        opportunity_block("Medium term — 1W signals", "1w", "features_1w")
        opportunity_block("Long term — 1M signals", "1m", "features_1m")

    # -------------------------------------------------------------- 4. P&L
    with comp.section("P&L", collapsed=True):
        closed = con.execute("""
            SELECT exit_date, net_pnl FROM trades WHERE status = 'closed'
        """).df()
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        def realised_since(cutoff) -> float:
            if closed.empty:
                return 0.0
            m = closed["exit_date"] >= cutoff
            return float(closed.loc[m, "net_pnl"].sum())

        open_trades2 = con.execute("SELECT isin, entry_price, qty FROM trades WHERE status='open'").df()
        unrealised = 0.0
        for _, t in open_trades2.iterrows():
            close = _latest_close(con, t["isin"])
            if close is not None:
                unrealised += (close - t["entry_price"]) * t["qty"]

        with ui.row().classes("gap-6 text-sm"):
            ui.label(f"Today: ₹{realised_since(today):,.0f}")
            ui.label(f"This week: ₹{realised_since(week_start):,.0f}")
            ui.label(f"This month: ₹{realised_since(month_start):,.0f}")
            ui.label(f"All time: ₹{(closed['net_pnl'].sum() if not closed.empty else 0):,.0f}")
            ui.label(f"Unrealised: ₹{unrealised:,.0f}")

        curve = jr.equity_curve(con)
        if not curve.empty:
            ui.echart({
                "backgroundColor": "transparent",
                "grid": {"left": 0, "right": 0, "top": 4, "bottom": 4},
                "xAxis": {"type": "category", "show": False,
                         "data": curve["exit_date"].astype(str).tolist()},
                "yAxis": {"type": "value", "show": False},
                "series": [{"type": "line", "data": curve["cum_pnl"].round(0).tolist(),
                          "smooth": True, "showSymbol": False,
                          "lineStyle": {"color": theme.ACCENT}}],
            }).classes("w-full").style("height:60px;")

    # ---------------------------------------------- 5. WATCHLIST NEAR TRIGGER
    near_df = wl.list_with_status(con)
    near_df = near_df[near_df.get("near_trigger", False) == True] if not near_df.empty else near_df
    with comp.section(f"Watchlist Near Trigger ({len(near_df)})",
                      collapsed=near_df.empty):
        if near_df.empty:
            ui.label("Nothing near trigger.").classes("text-sm")
        else:
            for _, row in near_df.iterrows():
                with ui.row().classes("gap-4 text-sm"):
                    ui.label(row["symbol"]).classes("w-28 font-semibold")
                    ui.label(f"close {row.get('close', 0):.2f}")
                    if row.get("target_price"):
                        ui.label(f"target {row['target_price']:.2f}")
                    if row.get("neckline"):
                        ui.label(f"neckline {row['neckline']:.2f}")
