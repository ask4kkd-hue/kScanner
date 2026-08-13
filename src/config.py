"""
config.py — loads config.yaml and exposes it as CFG.

Everything tunable lives in config.yaml. The rule from the design doc:
    thresholds live in presets, never in the database.
That way changing a threshold never triggers a feature rebuild.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml

_HERE = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("SCANNER_CONFIG", _HERE / "config.yaml"))


def load_config(path: Path | str = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    return _expand_paths(cfg)


def _expand_paths(cfg: dict) -> dict:
    root = Path(cfg["paths"]["root"]).expanduser()
    cfg["paths"] = {k: str(root / v) if k != "root" else str(root)
                    for k, v in cfg["paths"].items()}
    return cfg


def config_hash(obj: Any) -> str:
    """Stable short hash of any config subtree. Stamped onto every result row."""
    blob = json.dumps(obj, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def save_preset(name: str, conditions: list[str], *,
                path: Path | str = CONFIG_PATH,
                timeframe: str = "1d", pattern: str = "w_double_bottom") -> None:
    """
    Append a new preset to config.yaml's presets: block — a surgical text
    insert, not a full yaml.dump, so every existing comment and the hand-kept
    formatting elsewhere in the file survive untouched. Also updates the
    in-memory CFG so the new preset is usable immediately, no restart.

    This is the "Save these chips as a preset" scan-screen action from the
    v2 UI — never generates conditions itself, just persists ones already
    built from filter chips.
    """
    if name in CFG["presets"]:
        raise ValueError(f"Preset '{name}' already exists.")

    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    start = next((i for i, ln in enumerate(lines) if ln.rstrip() == "presets:"), None)
    if start is None:
        raise RuntimeError("Could not find 'presets:' block in config.yaml.")

    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].rstrip("\n")
        if stripped and not stripped[0].isspace():
            end = i
            break

    cond_lines = "".join(f'      - "{c}"\n' for c in conditions)
    block = (f"\n  {name}:\n"
            f'    timeframe: "{timeframe}"\n'
            f'    pattern: "{pattern}"\n'
            f"    conditions:\n"
            f"{cond_lines}")

    lines.insert(end, block)
    Path(path).write_text("".join(lines), encoding="utf-8")

    CFG["presets"][name] = {"timeframe": timeframe, "pattern": pattern,
                           "conditions": list(conditions), "name": name}


def resolve_preset(cfg: dict, name: str) -> dict:
    """
    Resolve a preset, following `inherits` and applying `conditions_add`
    and `overrides`. Lets you build variants without repeating yourself.
    """
    presets = cfg["presets"]
    if name not in presets:
        raise KeyError(f"Unknown preset '{name}'. Available: {sorted(presets)}")

    node = dict(presets[name])
    parent_name = node.pop("inherits", None)
    if parent_name:
        base = resolve_preset(cfg, parent_name)
        conditions = list(base.get("conditions", []))
        merged = {**base, **{k: v for k, v in node.items()
                             if k not in ("conditions_add", "overrides")}}
        conditions += list(node.get("conditions_add", []))
        merged["conditions"] = conditions
        for k, v in node.get("overrides", {}).items():
            merged[k] = v
        merged["name"] = name
        return merged

    node["name"] = name
    node.setdefault("conditions", [])
    return node


CFG = load_config()
