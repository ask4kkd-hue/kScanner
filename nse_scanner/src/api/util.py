"""
api/util.py — DataFrame -> JSON, the one place that has to get this right.

FastAPI's default jsonable_encoder does not safely handle pd.Timestamp/NaT
or numpy scalar types (DuckDB FLOAT columns come back as numpy.float32),
so returning a raw DataFrame.to_dict("records") through an endpoint can
either throw or silently serialize NaN as the string "NaN" (invalid JSON).
This is the direct replacement for web/components.py's dataframe_grid()
stringification helper, used the same way: called at the API boundary,
never inside business logic.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _jsonable_scalar(v):
    if v is None:
        return None
    if isinstance(v, (pd.Timestamp,)):
        if pd.isna(v):
            return None
        return v.strftime("%Y-%m-%d") if v.time() == pd.Timestamp.min.time() else v.isoformat()
    if isinstance(v, np.datetime64):
        return _jsonable_scalar(pd.Timestamp(v))
    if hasattr(v, "isoformat") and not isinstance(v, str):
        return v.isoformat()
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def jsonable_df(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> list[dict] with every value guaranteed JSON-safe."""
    if df is None or df.empty:
        return []
    records = df.to_dict("records")
    return [{k: _jsonable_scalar(v) for k, v in row.items()} for row in records]


def jsonable_dict(d: dict) -> dict:
    """Same sanitizing pass for a plain dict (e.g. table_counts(), advisor.position_status())."""
    return {k: _jsonable_scalar(v) if not isinstance(v, dict) else jsonable_dict(v)
           for k, v in d.items()}
