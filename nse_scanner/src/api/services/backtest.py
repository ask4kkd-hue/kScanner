"""api/services/backtest.py — port of web/pages/backtest.py's three run modes."""

from __future__ import annotations

from backtest import analyse_curves, marginal_contribution, recent_signals_report, run_backtest, sweep
from config import CFG

from api.util import jsonable_df

MIN_TRADES = CFG["backtest"]["min_trades_for_conclusion"]

# Same hardcoded candidate list web/pages/backtest.py's Marginal contribution
# mode used — kept as-is, not upgraded to "all presets" in this port.
MARGINAL_CANDIDATES = [
    "w_sma200_trend", "w_sma200_rising", "w_sma50_trend",
    "w_golden", "w_stacked", "w_delivery", "w_full",
]


def config() -> dict:
    return {
        "presets": list(CFG["presets"].keys()),
        "entry_variants": CFG["backtest"]["entry_variants"],
        "exit_variants": CFG["backtest"]["exit_variants"],
        "min_trades_for_conclusion": MIN_TRADES,
    }


def run_single(con, preset_name: str, entry_variant: str, exit_variant: str,
               sample: str, limit_symbols: int | None, label: str = "") -> str:
    return run_backtest(con, preset_name, entry_variant, exit_variant,
                        sample=sample, limit_symbols=limit_symbols, label=label)


def get_run(con, run_id: str) -> dict:
    m = con.execute("SELECT * FROM backtest_metrics WHERE run_id = ?", [run_id]).df()
    metrics = jsonable_df(m)[0] if not m.empty else None
    curves = jsonable_df(analyse_curves(con, run_id))
    return {"metrics": metrics, "curves": curves, "min_trades_for_conclusion": MIN_TRADES}


def run_sweep(con, preset_name: str, sample: str, limit_symbols: int | None) -> list[dict]:
    return jsonable_df(sweep(con, preset_name, sample, limit_symbols))


def run_marginal(con, entry_variant: str, exit_variant: str,
                 limit_symbols: int | None) -> list[dict]:
    return jsonable_df(marginal_contribution(
        con, "w_baseline", MARGINAL_CANDIDATES, entry_variant, exit_variant, limit_symbols))


def run_recent(con, preset_name: str, entry_variant: str, exit_variant: str,
               days_back: int, limit_symbols: int | None) -> dict:
    result = recent_signals_report(con, preset_name, entry_variant, exit_variant,
                                   days_back, limit_symbols)
    return {
        "run_id": result["run_id"],
        "days_back": result["days_back"],
        "trades": jsonable_df(result["trades"]),
        "summary": result["summary"],
    }
