"""
web/shell.py — the app frame: header, health rail, left nav, content swap.

CONTENT AREA swaps by calling the active page module's render(con, state) —
no NiceGUI sub-routing, just clearing and rebuilding one container. Drawer
collapse state and the last-open page persist in ui_prefs so they survive
an app restart.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

from nicegui import ui

import components as comp
import theme
from validate import data_is_stale
from db import table_counts

_SRC_DIR = Path(__file__).resolve().parent.parent

PAGES = ["today", "scan", "chart", "watchlist", "holdings",
        "performance", "backtest", "data"]
LABELS = {"today": "Today", "scan": "Scan", "chart": "Chart",
         "watchlist": "Watchlist", "holdings": "Holdings",
         "performance": "Performance", "backtest": "Backtest", "data": "Data"}
ICONS = {"today": "today", "scan": "search", "chart": "candlestick_chart",
         "watchlist": "visibility", "holdings": "account_balance_wallet",
         "performance": "insights", "backtest": "science", "data": "storage"}

PIPELINE_STEPS = [
    ("Universe", ["universe.py"]),
    ("Ingest", ["ingest.py"]),
    ("Validate", ["validate.py", "--days", "1"]),
    ("Features", ["features.py"]),
]


def get_pref(con, key: str, default: str | None = None) -> str | None:
    row = con.execute("SELECT value FROM ui_prefs WHERE key = ?", [key]).fetchone()
    return row[0] if row else default


def set_pref(con, key: str, value: str) -> None:
    con.execute("""
        INSERT INTO ui_prefs (key, value) VALUES (?, ?)
        ON CONFLICT (key) DO UPDATE SET value = excluded.value
    """, [key, value])


def _run_step(args: list[str]) -> tuple[bool, str]:
    result = subprocess.run([sys.executable, *args], cwd=str(_SRC_DIR),
                            capture_output=True, text=True)
    tail = (result.stdout + result.stderr).strip().splitlines()
    return result.returncode == 0, "\n".join(tail[-15:])


def build(con) -> None:
    """Build the shell for one connected client's cursor `con`."""
    theme.apply()

    state: dict = {
        "page": get_pref(con, "last_page", "today") or "today",
        "drawer_mini": get_pref(con, "drawer_mini", "0") == "1",
    }

    content = ui.column().classes("w-full gap-3")

    def refresh_health(container: ui.element) -> None:
        container.clear()
        with container:
            stale, latest_bar, latest_cal = data_is_stale(con)
            counts = table_counts(con)
            fails = con.execute("""
                SELECT COUNT(*) FROM validation_log
                WHERE passed = FALSE AND date >= CURRENT_DATE - INTERVAL 7 DAY
            """).fetchone()[0]
            behind = ""
            if stale and latest_bar and latest_cal:
                gap = con.execute("""
                    SELECT COUNT(*) FROM trading_calendar
                    WHERE bhavcopy_available AND date > ? AND date <= ?
                """, [latest_bar, latest_cal]).fetchone()[0]
                behind = f" — {gap} session{'s' if gap != 1 else ''} behind"
            cls = "bad" if stale else "ok"
            ui.html(f"""
                <div class="k-health {cls}">
                <div>latest bar <b>{latest_bar or '—'}</b></div>
                <div>last trading day <b>{latest_cal or '—'}</b></div>
                <div>status <b>{('STALE' + behind) if stale else 'current'}</b></div>
                <div>bars <b>{counts.get('bars_1d') or 0:,}</b></div>
                <div>features <b>{counts.get('features_1d') or 0:,}</b></div>
                <div>validation fails (7d) <b>{fails}</b></div>
                </div>
            """)

    health_box = ui.column().classes("w-full")

    def render_page() -> None:
        content.clear()
        set_pref(con, "last_page", state["page"])
        with content:
            mod = importlib.import_module(f"pages.{state['page']}")
            mod.render(con, state)

    def go(name: str) -> None:
        state["page"] = name
        render_page()

    async def do_refresh() -> None:
        n = ui.notification(timeout=None, spinner=True, close_button=False)
        for label, args in PIPELINE_STEPS:
            n.message = f"Refreshing… {label}"
            ok, tail = await comp.run_bg(_run_step, args)
            if not ok:
                n.dismiss()
                ui.notify(f"Refresh FAILED at {label} — nothing after it ran.\n{tail}",
                          type="negative", multi_line=True, timeout=20000,
                          close_button=True)
                return
        n.dismiss()
        ui.notify("Refresh complete.", type="positive")
        refresh_health(health_box)

    async def do_full_rebuild() -> None:
        n = ui.notification("Full rebuild — features.py --full (this takes a while)…",
                            timeout=None, spinner=True, close_button=False)
        ok, tail = await comp.run_bg(_run_step, ["features.py", "--full"])
        n.dismiss()
        if ok:
            ui.notify("Full rebuild complete.", type="positive")
            refresh_health(health_box)
        else:
            ui.notify(f"Full rebuild failed.\n{tail}", type="negative",
                      multi_line=True, timeout=20000, close_button=True)

    def reset_drawings() -> None:
        sym = state.get("chart_symbol")
        tf = state.get("chart_timeframe", "1d")
        if not sym:
            ui.notify("No chart symbol selected yet.", type="warning")
            return
        row = con.execute("SELECT isin FROM instruments WHERE symbol = ?", [sym]).fetchone()
        if row:
            con.execute("DELETE FROM drawings WHERE isin = ? AND timeframe = ?",
                        [row[0], tf])
            ui.notify(f"Drawings cleared for {sym} ({tf}).")

    def open_exports() -> None:
        path = _SRC_DIR.parent / "exports"
        try:
            subprocess.Popen(["explorer", str(path)])
        except Exception:
            ui.notify(f"Exports folder: {path}")

    with ui.header().classes("items-center justify-between px-3 py-1").style(
            f"background:{theme.SURFACE}; border-bottom:1px solid {theme.BORDER};"):
        with ui.row().classes("items-center gap-2"):
            ui.button(icon="menu", on_click=lambda: drawer.toggle()) \
                .props("flat dense round color=white")
            ui.label("kSCANNER").classes("text-base font-bold").style(
                f"letter-spacing:0.04em; color:{theme.TEXT_PRIMARY}")
        with ui.row().classes("items-center gap-1"):
            ui.button("Refresh", icon="refresh", on_click=do_refresh) \
                .props("unelevated dense no-caps").style(
                    f"background:{theme.ACCENT}; color:white")
            with ui.button(icon="more_vert").props("flat dense round color=white"):
                with ui.menu():
                    ui.menu_item("Run full rebuild (features --full)", do_full_rebuild)
                    ui.menu_item("Open exports folder", open_exports)
                    ui.menu_item("Reset drawings for this symbol", reset_drawings)
                    ui.separator()
                    ui.menu_item("About", lambda: ui.notify(
                        "kSCANNER v2 — local NSE swing/position scanner. "
                        "EOD data only, no live quotes."))

    with ui.left_drawer(value=True, bordered=True).classes("gap-0").style(
            f"background:{theme.SURFACE};") as drawer:
        drawer.props(f'width={64 if state["drawer_mini"] else 180}')

        def render_nav() -> None:
            drawer.clear()
            with drawer:
                mini = state["drawer_mini"]

                def toggle_mini() -> None:
                    state["drawer_mini"] = not state["drawer_mini"]
                    set_pref(con, "drawer_mini", "1" if state["drawer_mini"] else "0")
                    drawer.props(f'width={64 if state["drawer_mini"] else 180}')
                    render_nav()

                ui.button(icon="chevron_left" if not mini else "chevron_right",
                         on_click=toggle_mini).props("flat dense round color=white")
                for name in PAGES:
                    btn = ui.button(
                        "" if mini else LABELS[name], icon=ICONS[name],
                        on_click=lambda n=name: go(n),
                    ).props("flat no-caps align=left dense color=white").classes(
                        "w-full justify-start")
                    if state["page"] == name:
                        btn.style(f"background:{theme.ACCENT}22;")

        render_nav()

    with ui.column().classes("w-full gap-3"):
        refresh_health(health_box)
        content

    render_page()
