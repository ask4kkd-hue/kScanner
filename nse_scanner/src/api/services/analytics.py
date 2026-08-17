"""api/services/analytics.py — thin HTTP-facing port of analytics.py."""

from __future__ import annotations

import analytics as an

from api.util import jsonable_df


def config() -> dict:
    return {
        "types": [
            {"id": key, **info} for key, info in an.ANALYSIS_TYPES.items()
        ]
    }


def run(con, analysis_type: str, min_pct: float, max_pct: float) -> list[dict]:
    df = an.run_analysis(con, analysis_type, min_pct=min_pct, max_pct=max_pct)
    return jsonable_df(df)
