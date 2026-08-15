"""api/services/refresh.py — the daily refresh pipeline and the full-rebuild job, as ordered (label, fn) steps."""

from __future__ import annotations

from typing import Callable

import features
import ingest
import universe
import validate

Step = tuple[str, Callable[[], None]]


def refresh_steps(con) -> list[Step]:
    """Universe -> Ingest -> Validate -> Features (daily incremental). Same order as web/shell.py's do_refresh()."""
    return [
        ("Universe", lambda: universe.run_universe(con)),
        ("Ingest", lambda: ingest.run_ingest(con)),
        ("Validate", lambda: validate.run_validation(con)),
        ("Features", lambda: features.build_features(con)),
    ]


def full_rebuild_steps(con) -> list[Step]:
    """1D + 1W + 1M feature rebuild, then RS rank. Same order as web/shell.py's do_full_rebuild()."""
    steps: list[Step] = [
        (f"Features ({tf})", lambda tf=tf: features.build_features(con, full=True, timeframe=tf))
        for tf in ("1d", "1w", "1m")
    ]
    steps.append(("RS rank", lambda: features.build_rs_rank(con)))
    return steps
