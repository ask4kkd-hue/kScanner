"""
web/pages/holdings.py — open positions (trades WHERE status='open').

Manual entry only, per v2_instructions.md — no broker fetch, no CSV import.
Each position's numbers (days_held, current P&L, MAE/MFE) come from a single
advisor.position_status() call, so what the card shows and what the advisor's
reasons cite are always the same numbers, never recomputed twice differently.

open_entry_dialog() is exported so watchlist.py's "Promote to holding" can
reuse the exact same form instead of duplicating it.
"""

from __future__ import annotations

from datetime import date

from nicegui import ui

import advisor
import components as comp
import journal as jr
import theme

BEHAVIOUR_TAGS = ["chased_entry", "moved_stop", "revenge_trade",
                 "oversized", "exited_early"]


def _symbols(con) -> list[str]:
    return con.execute(
        "SELECT DISTINCT symbol FROM instruments ORDER BY symbol"
    ).df()["symbol"].tolist()


def _latest_close(con, isin: str) -> float | None:
    row = con.execute("""
        SELECT close FROM bars_1d WHERE isin = ? ORDER BY date DESC LIMIT 1
    """, [isin]).fetchone()
    return float(row[0]) if row else None


def open_entry_dialog(con, on_saved, *, prefill_symbol: str | None = None) -> None:
    """Shared position-entry form. on_saved() is called after a trade opens."""
    symbols = _symbols(con)
    with ui.dialog() as dialog, ui.card().classes("gap-2"):
        ui.label("New position").classes("text-base font-semibold")
        sym_sel = ui.select(symbols, value=prefill_symbol or (symbols[0] if symbols else None),
                            with_input=True, label="Symbol").classes("w-64")
        with ui.row().classes("gap-2"):
            entry_date_in = ui.input("Entry date", value=date.today().isoformat()) \
                .classes("w-32")
            entry_price_in = ui.number("Entry price", min=0, step=0.05).classes("w-32")
            qty_in = ui.number("Qty", min=1, value=1, precision=0).classes("w-24")
        with ui.row().classes("gap-2"):
            stop_in = ui.number("Stop price", min=0, step=0.05).classes("w-32")
            target_in = ui.number("Target price", min=0, step=0.05).classes("w-32")
        preset_in = ui.input("Preset name (optional)").classes("w-64")
        thesis_in = ui.textarea("Thesis").classes("w-64")

        def save():
            if not sym_sel.value or not entry_price_in.value or not stop_in.value:
                ui.notify("Symbol, entry price and stop price are required.", type="warning")
                return
            try:
                jr.open_trade(
                    con, sym_sel.value,
                    date.fromisoformat(entry_date_in.value), float(entry_price_in.value),
                    int(qty_in.value or 1), float(stop_in.value),
                    target_price=float(target_in.value) if target_in.value else None,
                    preset_name=preset_in.value or "", thesis=thesis_in.value or "",
                )
            except Exception as exc:
                ui.notify(f"Could not open position: {exc}", type="negative")
                return
            dialog.close()
            ui.notify(f"Opened {sym_sel.value}.", type="positive")
            on_saved()

        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Open position", on_click=save).props("unelevated no-caps")
    dialog.open()


def _open_close_dialog(con, trade_id: int, symbol: str, on_saved) -> None:
    with ui.dialog() as dialog, ui.card().classes("gap-2"):
        ui.label(f"Close {symbol}").classes("text-base font-semibold")
        exit_date_in = ui.input("Exit date", value=date.today().isoformat()).classes("w-32")
        exit_price_in = ui.number("Exit price", min=0, step=0.05).classes("w-32")
        reason_in = ui.select(["target", "stop", "time_stop", "discretionary"],
                              value="discretionary", label="Exit reason").classes("w-48")
        followed_in = ui.checkbox("Followed the plan", value=True)
        tags_in = ui.select(BEHAVIOUR_TAGS, multiple=True, label="Behaviour tags") \
            .classes("w-64").props("use-chips dense")
        note_in = ui.textarea("Review note").classes("w-64")

        def save():
            if not exit_price_in.value:
                ui.notify("Exit price is required.", type="warning")
                return
            try:
                jr.close_trade(con, trade_id, date.fromisoformat(exit_date_in.value),
                               float(exit_price_in.value), reason_in.value,
                               followed_plan=followed_in.value, review_note=note_in.value or "")
                if tags_in.value:
                    jr.add_tags(con, trade_id, tags_in.value)
            except Exception as exc:
                ui.notify(f"Could not close position: {exc}", type="negative")
                return
            dialog.close()
            ui.notify(f"Closed {symbol}.", type="positive")
            on_saved()

        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Close position", on_click=save).props("unelevated no-caps color=negative")
    dialog.open()


def render(con, state: dict) -> None:
    comp.page_title("Holdings")

    body = ui.column().classes("w-full gap-2")

    def refresh() -> None:
        jr.update_open_trades(con)
        body.clear()
        open_trades = con.execute("""
            SELECT trade_id, isin, symbol, entry_date, entry_price, qty,
                  stop_price, target_price, preset_name
            FROM trades WHERE status = 'open' ORDER BY entry_date
        """).df()

        with body:
            ui.button("+ New position", on_click=lambda: open_entry_dialog(con, refresh)) \
                .props("unelevated no-caps").style(f"background:{theme.ACCENT}; color:white;")

            if open_trades.empty:
                ui.label("No open positions.").classes("text-sm mt-2")
                return

            rows = []
            for _, t in open_trades.iterrows():
                s = advisor.position_status(con, int(t["trade_id"]))
                close = _latest_close(con, t["isin"])
                pnl_rupees = ((close - t["entry_price"]) * t["qty"]
                              if close is not None else None)
                risk = t["entry_price"] - t["stop_price"]
                r_mult = ((close - t["entry_price"]) / risk
                         if close is not None and risk > 0 else None)
                rows.append((t, s, close, pnl_rupees, r_mult))

            order = {"REVIEW": 0, "WATCH": 1, "HOLD": 2}
            rows.sort(key=lambda x: order.get(x[1]["status"], 3))

            total_pnl = sum(r[3] for r in rows if r[3] is not None)
            at_risk = sum(1 for r in rows if r[1]["status"] in ("WATCH", "REVIEW"))

            with ui.row().classes("w-full gap-6 text-sm"):
                ui.label(f"Total open P&L: ₹{total_pnl:,.0f}").classes("font-semibold")
                ui.label(f"At risk: {at_risk} of {len(rows)}").classes("font-semibold")

            for t, s, close, pnl_rupees, r_mult in rows:
                with ui.card().classes("w-full").style(
                        f"background:{theme.SURFACE}; border:1px solid {theme.BORDER};"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.row().classes("items-center gap-3"):
                            ui.label(t["symbol"]).classes("text-base font-bold")
                            comp.status_badge(s["status"])
                        with ui.row().classes("items-center gap-4 text-sm font-mono"):
                            ui.label(f"₹{pnl_rupees:,.0f}" if pnl_rupees is not None else "—").style(
                                f"color:{theme.ACCENT if (pnl_rupees or 0) >= 0 else theme.CRITICAL}")
                            ui.label(f"{r_mult:.2f}R" if r_mult is not None else "—")
                            ui.button(icon="close", on_click=lambda tid=int(t["trade_id"]), sym=t["symbol"]:
                                      _open_close_dialog(con, tid, sym, refresh)) \
                                .props("flat dense round size=sm")

                    m = s["metrics"]
                    with ui.row().classes("w-full gap-6 text-xs mt-1").style(
                            f"color:{theme.TEXT_MUTED}"):
                        ui.label(f"entry {t['entry_date']} @ {t['entry_price']:.2f} x {int(t['qty'])}")
                        ui.label(f"close {close:.2f}" if close is not None else "close —")
                        ui.label(f"day {m.get('days_held', '—')}")
                        mae = m.get("mae_pct")
                        mfe = m.get("mfe_pct")
                        ui.label(f"MAE {mae:.1f}%" if mae == mae else "MAE —")
                        ui.label(f"MFE {mfe:.1f}%" if mfe == mfe else "MFE —")

                    with ui.column().classes("gap-0 mt-1"):
                        for reason in s["reasons"]:
                            ui.label(f"· {reason}").classes("text-xs").style(
                                f"color:{theme.TEXT_MUTED}")

    refresh()
