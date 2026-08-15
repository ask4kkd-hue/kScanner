"""
api/services/scan.py — port of web/pages/scan.py's run-once/filter-in-memory flow.

CHIPS come straight from config.yaml (filter_chips), never hardcoded here — the same
config-driven rule the rest of this project follows.
"""

from __future__ import annotations

import re

import pandas as pd

from backtest import _eval_condition
from config import CFG, resolve_preset, save_preset as _save_preset
from scan import scan as run_scan_fn

from api.services import scan_cache

CHIPS = CFG["filter_chips"]
CHIP_BY_ID = {c["id"]: c for c in CHIPS}

_GRID_COLUMNS = ["symbol", "trigger_price", "l1_price", "l2_price", "neckline",
                "depth_pct", "stop_suggested", "target_suggested",
                "bottom_at_sma", "sma_stack", "rs_rank_pct"]


def _chip_column(expr: str) -> str:
    """The leftmost identifier in a chip's expr — matches a chip to a preset
    condition on the same column, for pre-selecting chips."""
    m = re.match(r"\s*([a-zA-Z_][a-zA-Z0-9_]*)", expr)
    return m.group(1) if m else ""


def presets() -> list[str]:
    return list(CFG["presets"].keys())


def preselected_chip_ids(preset_name: str) -> list[str]:
    """Best-effort: a chip is pre-selected if the preset filters the same
    column, matched by name — not by exact operator/threshold, since chips
    carry their own independent default values."""
    conditions = resolve_preset(CFG, preset_name).get("conditions", [])
    cond_cols = {_chip_column(c) for c in conditions}
    return [c["id"] for c in CHIPS if _chip_column(c["expr"]) in cond_cols]


def run_scan(con, preset_name: str) -> tuple[str, int]:
    """Raises RuntimeError if the stale-data guard trips (ignore_stale=True here,
    same as the NiceGUI original — the Scan screen is a deliberate manual action,
    not the <2s Today landing page, so the guard doesn't need to block it)."""
    df = run_scan_fn(con, preset_name, ignore_stale=True, apply_preset=False)
    scan_id = scan_cache.store(df)
    return scan_id, len(df)


def filter_scan(scan_id: str, chips: dict[str, dict]) -> dict | None:
    df = scan_cache.get(scan_id)
    if df is None:
        return None

    filtered = df
    for chip in CHIPS:
        cs = chips.get(chip["id"])
        if not cs or not cs.get("active"):
            continue
        expr = chip["expr"]
        if "{v}" in expr:
            expr = expr.replace("{v}", str(cs.get("value")))
        mask = filtered.apply(lambda row: _eval_condition(row, expr), axis=1)
        filtered = filtered[mask]

    cols = [c for c in _GRID_COLUMNS if c in filtered.columns]
    rows = filtered[cols].round(2).to_dict("records") if not filtered.empty else []

    distribution: dict[str, int] = {}
    if not filtered.empty and "bottom_at_sma" in filtered.columns:
        distribution = filtered["bottom_at_sma"].value_counts().to_dict()

    return {
        "count": len(filtered), "total": len(df), "rows": rows,
        "bottom_at_sma_distribution": distribution,
    }


def save_preset(name: str, conditions: list[str]) -> None:
    _save_preset(name, conditions)


def scan_symbols(scan_id: str) -> list[str] | None:
    df = scan_cache.get(scan_id)
    return df["symbol"].tolist() if df is not None else None
