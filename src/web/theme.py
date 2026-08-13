"""
web/theme.py — the v2 UI's design tokens.

These are not new colors. They are exactly what app.py (v1) already used and
validated this session — dark surface, single accent, TradingView's own
candle colors (checked for colorblind-safe separation, not eyeballed), a
fixed per-SMA palette so a line's color never changes when you toggle other
overlays. v2 keeps them so the two UIs read as the same product while both
exist.
"""

from __future__ import annotations

from nicegui import ui

SURFACE = "#0F1211"
BORDER = "#232928"
TEXT_MUTED = "#8B9694"
TEXT_PRIMARY = "#E4E9E7"
ACCENT = "#2F6F62"       # HOLD / "current" / good
CRITICAL = "#C4553B"     # REVIEW / "stale" / bad
WARNING = "#D9A030"      # WATCH

CANDLE_UP = "#26a69a"
CANDLE_DOWN = "#ef5350"

# Fixed per-entity overlay colors — never cycled or reassigned by selection
# (same rule app.py's Chart tab uses): a line's color is tied to what it IS,
# not to how many other lines happen to be showing at the same time.
SMA_COLORS = {
    "sma10": "#3987e5", "sma20": "#d95926", "sma50": "#c98500",
    "sma100": "#d55181", "sma200": "#9085e9",
}
AVWAP_COLOR = "#199e70"
MARKER_COLOR = TEXT_PRIMARY
REF_LINE_COLOR = "#c3c2b7"

STATUS_COLORS = {"HOLD": ACCENT, "WATCH": WARNING, "REVIEW": CRITICAL}

_CSS = f"""
html, body {{ font-feature-settings: "tnum" 1, "cv05" 1; }}
body {{ background: {SURFACE} !important; color: {TEXT_PRIMARY}; }}
h1, h2, h3 {{ letter-spacing: -0.015em; font-weight: 600; }}

.k-health {{
    display:flex; gap:0; border:1px solid {BORDER}; border-radius:6px;
    overflow:hidden; margin-bottom:1rem; font-family:ui-monospace,
    "JetBrains Mono","SF Mono",Menlo,monospace; font-size:0.78rem;
}}
.k-health > div {{ padding:0.55rem 0.9rem; border-right:1px solid {BORDER};
                   color:{TEXT_MUTED}; }}
.k-health > div:last-child {{ border-right:none; }}
.k-health b {{ color:{TEXT_PRIMARY}; font-weight:500; }}
.k-health.ok  {{ border-left:3px solid {ACCENT} !important; }}
.k-health.bad {{ border-left:3px solid {CRITICAL} !important; }}

.k-badge {{
    display:inline-block; padding:0.15rem 0.55rem; border-radius:4px;
    font-family:ui-monospace,"JetBrains Mono","SF Mono",Menlo,monospace;
    font-size:0.72rem; font-weight:600; letter-spacing:0.02em;
}}
.k-badge-hold   {{ background:{ACCENT}22;   color:{ACCENT}; }}
.k-badge-watch  {{ background:{WARNING}22;  color:{WARNING}; }}
.k-badge-review {{ background:{CRITICAL}22; color:{CRITICAL}; }}

.nicegui-content {{ padding: 0.75rem 1.25rem; }}
"""


def apply() -> None:
    """Call once, before building the shell."""
    ui.dark_mode().enable()
    ui.colors(primary=ACCENT)
    ui.add_head_html(f"<style>{_CSS}</style>")


def status_class(status: str) -> str:
    return {"HOLD": "k-badge k-badge-hold",
           "WATCH": "k-badge k-badge-watch",
           "REVIEW": "k-badge k-badge-review"}.get(status, "k-badge")
