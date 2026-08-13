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
