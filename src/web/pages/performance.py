"""
web/pages/performance.py — trade-level analytics, entirely from journal.py.

Every attribution cut shows its trade count; any cut below
backtest.min_trades_for_conclusion renders greyed with "insufficient
sample" rather than as a stated finding — same rule the CLI backtest
report and CLAUDE.md's methodology section both apply.
"""

from __future__ import annotations

from nicegui import ui

import components as comp
import journal as jr
import theme
from config import CFG

MIN_TRADES = CFG["backtest"]["min_trades_for_conclusion"]


def _stat_row(df, group_col: str, label_col: str | None = None) -> None:
    """Render a grouped attribution table with insufficient-sample greying."""
    if df.empty:
        ui.label("No closed trades yet.").classes("text-sm")
        return
    for _, row in df.iterrows():
        trades = int(row["trades"])
        thin = trades < MIN_TRADES
        style = f"color:{theme.TEXT_MUTED};" if thin else ""
        label = row[label_col or group_col]
        with ui.row().classes("gap-4 text-sm").style(style):
            ui.label(str(label)).classes("w-40 font-semibold" if not thin else "w-40")
            ui.label(f"{trades} trades")
            if "avg_r" in row:
                ui.label(f"avg {row['avg_r']:.2f}R" if row["avg_r"] == row["avg_r"] else "avg —")
            if "win_rate" in row:
                ui.label(f"{row['win_rate']:.0f}% win" if row["win_rate"] == row["win_rate"] else "")
            if "net_pnl" in row:
                ui.label(f"₹{row['net_pnl']:,.0f}" if row["net_pnl"] == row["net_pnl"] else "")
            if thin:
                ui.label("insufficient sample").classes("text-xs italic")


def render(con, state: dict) -> None:
    comp.page_title("Performance")

    s = jr.summary(con)
    trades = s.get("trades", 0)

    with comp.section("Overview", collapsed=False):
        if not trades:
            ui.label("No closed trades yet.").classes("text-sm")
        else:
            thin = trades < MIN_TRADES
            with ui.row().classes("gap-6 text-sm flex-wrap"):
                ui.label(f"{trades} trades")
                ui.label(f"Win rate: {s['win_rate']:.1f}%")
                ui.label(f"Expectancy: {s['expectancy_r']:.3f}R")
                ui.label(f"Profit factor: {s['profit_factor']:.2f}"
                         if s["profit_factor"] != float("inf") else "Profit factor: ∞")
                ui.label(f"Avg win: {s['avg_win_r']:.2f}R")
                ui.label(f"Avg loss: {s['avg_loss_r']:.2f}R")
                ui.label(f"Net P&L: ₹{s['net_pnl']:,.0f}")
            if thin:
                ui.label(f"Below {MIN_TRADES} trades — insufficient sample, "
                         f"read these as noise, not a conclusion.").classes(
                    "text-xs italic mt-1").style(f"color:{theme.WARNING}")

    with comp.section("Equity curve & drawdown", collapsed=False):
        curve = jr.equity_curve(con)
        if curve.empty:
            ui.label("No closed trades yet.").classes("text-sm")
        else:
            ui.echart({
                "backgroundColor": "transparent",
                "grid": {"left": 50, "right": 20, "top": 20, "bottom": 30},
                "xAxis": {"type": "category", "data": curve["exit_date"].astype(str).tolist(),
                         "axisLabel": {"color": theme.TEXT_MUTED}},
                "yAxis": {"type": "value", "axisLabel": {"color": theme.TEXT_MUTED}},
                "series": [{"type": "line", "name": "Equity", "data": curve["cum_pnl"].round(0).tolist(),
                          "smooth": True, "showSymbol": False,
                          "lineStyle": {"color": theme.ACCENT}},
                         {"type": "line", "name": "Drawdown", "data": curve["drawdown"].round(0).tolist(),
                          "smooth": True, "showSymbol": False,
                          "lineStyle": {"color": theme.CRITICAL}}],
                "legend": {"textStyle": {"color": theme.TEXT_MUTED}},
            }).classes("w-full").style("height:260px;")

    with comp.section("Attribution", collapsed=False):
        ui.label("By preset").classes("text-sm font-semibold mt-1")
        _stat_row(jr.preset_attribution(con), "preset_name")

        ui.label("By timeframe").classes("text-sm font-semibold mt-3")
        tf_df = con.execute("""
            SELECT COALESCE(timeframe, '1d') AS tf_label, COUNT(*) AS trades,
                  AVG(r_multiple) AS avg_r,
                  AVG(CASE WHEN net_pnl > 0 THEN 1.0 ELSE 0.0 END) * 100 AS win_rate,
                  SUM(net_pnl) AS net_pnl
            FROM trades WHERE status = 'closed' GROUP BY 1
        """).df()
        _stat_row(tf_df, "tf_label")

        ui.label("By sector").classes("text-sm font-semibold mt-3")
        sector_df = con.execute("""
            SELECT COALESCE(i.sector, 'unknown') AS sector, COUNT(*) AS trades,
                  AVG(t.r_multiple) AS avg_r,
                  AVG(CASE WHEN t.net_pnl > 0 THEN 1.0 ELSE 0.0 END) * 100 AS win_rate,
                  SUM(t.net_pnl) AS net_pnl
            FROM trades t LEFT JOIN instruments i ON i.isin = t.isin
            WHERE t.status = 'closed' GROUP BY 1 ORDER BY trades DESC
        """).df()
        _stat_row(sector_df, "sector")

        ui.label("By where the second bottom formed").classes("text-sm font-semibold mt-3")
        # journal.py's snapshot_features() only captures NUMERIC features_1d
        # columns at entry (adr_pct20, rsi14, ...) — bottom_at_sma is a
        # categorical classification that was never wired into the live
        # trade snapshot, and trades.signal_id isn't an actual foreign key
        # into signals_1d (which has no signal_id column to join on). This
        # cut can't be computed from the live journal as it stands, so it
        # says that rather than showing a fabricated or silently-empty table.
        ui.label("Not available for live trades — journal.py's entry snapshot "
                "doesn't capture bottom_at_sma (categorical fields aren't "
                "snapshotted, only numeric indicators). Present in the "
                "backtest's bottom_at_sma slicing instead.").classes(
            "text-xs italic").style(f"color:{theme.TEXT_MUTED}")

    with comp.section("Adherence & behaviour", collapsed=True):
        ui.label("Followed plan vs not").classes("text-sm font-semibold")
        adh = jr.adherence_report(con)
        if adh.empty:
            ui.label("No closed trades yet.").classes("text-sm")
        else:
            for _, row in adh.iterrows():
                label = "Followed plan" if row["followed_plan"] else "Did not follow plan"
                ui.label(f"{label}: {int(row['trades'])} trades, "
                        f"avg {row['avg_r']:.2f}R, {row['win_rate']:.0f}% win, "
                        f"₹{row['net_pnl']:,.0f}").classes("text-sm")

        ui.label("By behaviour tag").classes("text-sm font-semibold mt-3")
        tags = jr.tag_analysis(con)
        if tags.empty:
            ui.label("No tagged trades yet.").classes("text-sm")
        else:
            for _, row in tags.iterrows():
                ui.label(f"{row['tag']}: {int(row['trades'])} trades, "
                        f"avg {row['avg_r']:.2f}R, ₹{row['net_pnl']:,.0f}").classes("text-sm")

        ui.label("Do winners differ on…").classes("text-sm font-semibold mt-3")
        metric_sel = ui.select(
            ["deliv_pct_sma20", "adr_pct20", "adx14", "rs_rank_pct", "dist_sma200_pct"],
            value="deliv_pct_sma20").classes("w-48")
        snapshot_box = ui.column().classes("w-full mt-1")

        def show_snapshot():
            snapshot_box.clear()
            sa = jr.snapshot_analysis(con, metric_sel.value)
            with snapshot_box:
                if sa.empty:
                    ui.label("Not enough entry-snapshot data for this metric yet.").classes(
                        "text-sm")
                    return
                for _, row in sa.iterrows():
                    ui.label(f"{row['bucket']}: {int(row['trades'])} trades, "
                            f"avg {row['avg_r']:.2f}R, {row['win_rate']:.0f}% win").classes(
                        "text-sm")

        metric_sel.on_value_change(show_snapshot)
        show_snapshot()

    with comp.section("Live vs backtest", collapsed=True):
        presets_traded = con.execute("""
            SELECT DISTINCT preset_name FROM trades
            WHERE status = 'closed' AND preset_name != '' ORDER BY 1
        """).df()["preset_name"].tolist()
        if not presets_traded:
            ui.label("No closed trades with a preset name yet.").classes("text-sm")
        else:
            preset_sel = ui.select(presets_traded, value=presets_traded[0]).classes("w-48")
            table_box = ui.column().classes("w-full mt-2")

            def show_comparison():
                table_box.clear()
                cmp_df = jr.compare_with_backtest(con, preset_sel.value)
                with table_box:
                    if cmp_df.empty:
                        ui.label("No backtest run for this preset to compare against.").classes(
                            "text-sm")
                        return
                    for _, row in cmp_df.iterrows():
                        ui.label(
                            f"{row['source']}: {int(row['trades'])} trades, "
                            f"{row['win_rate']:.1f}% win, avg {row['avg_r']:.2f}R, "
                            f"median hold {row['median_hold']:.0f}d, "
                            f"median MAE {row['median_mae']:.1f}%, "
                            f"median MFE {row['median_mfe']:.1f}%"
                        ).classes("text-sm")

            preset_sel.on_value_change(show_comparison)
            show_comparison()
