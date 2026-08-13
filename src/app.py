"""
app.py — Streamlit UI.

Design note: the first thing on screen is the data-health strip, not the
signal list. Accuracy is the stated priority of this project, so the
interface makes data trustworthiness impossible to ignore rather than
burying it in a settings page. If the strip is red, nothing below it
should be traded.

Run with:   streamlit run app.py
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as pgo
import streamlit as st
from plotly.subplots import make_subplots

import indicators as ind
import journal as jr
import patterns as pat
from backtest import analyse_curves, marginal_contribution, run_backtest, sweep
from config import CFG, load_config, resolve_preset
from db import connect, init_schema, table_counts
from scan import regime_state, scan, store_signals
from validate import data_is_stale

st.set_page_config(page_title="NSE Scanner", layout="wide",
                   initial_sidebar_state="expanded")

ACCENT = CFG["ui"]["theme_accent"]

st.markdown(f"""
<style>
  html, body, [class*="css"] {{ font-feature-settings: "tnum" 1, "cv05" 1; }}
  .stApp {{ background: #0F1211; }}
  h1, h2, h3 {{ letter-spacing: -0.015em; font-weight: 600; }}
  .health {{
      display:flex; gap:0; border:1px solid #232928; border-radius:6px;
      overflow:hidden; margin-bottom:1.25rem; font-family:ui-monospace,
      "JetBrains Mono","SF Mono",Menlo,monospace; font-size:0.78rem;
  }}
  .health div {{ padding:0.55rem 0.9rem; border-right:1px solid #232928;
                 color:#8B9694; }}
  .health div:last-child {{ border-right:none; }}
  .health b {{ color:#E4E9E7; font-weight:500; }}
  .ok  {{ border-left:3px solid {ACCENT} !important; }}
  .bad {{ border-left:3px solid #C4553B !important; }}
  .stDataFrame {{ font-variant-numeric: tabular-nums; }}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_con():
    con = connect()
    init_schema(con)
    return con


con = get_con().cursor()


# ---------------------------------------------------------------- health strip

def health_strip() -> bool:
    stale, latest_bar, latest_cal = data_is_stale(con)
    counts = table_counts(con)

    fails = con.execute("""
        SELECT COUNT(*) FROM validation_log
        WHERE passed = FALSE AND date >= CURRENT_DATE - INTERVAL 7 DAY
    """).fetchone()[0]

    cls = "bad" if stale else "ok"
    st.markdown(
        f"""<div class="health {cls}">
        <div>latest bar <b>{latest_bar or '—'}</b></div>
        <div>last trading day <b>{latest_cal or '—'}</b></div>
        <div>status <b>{'STALE — run ingest' if stale else 'current'}</b></div>
        <div>bars <b>{counts.get('bars_1d') or 0:,}</b></div>
        <div>features <b>{counts.get('features_1d') or 0:,}</b></div>
        <div>validation fails (7d) <b>{fails}</b></div>
        </div>""",
        unsafe_allow_html=True,
    )
    return stale


st.title("NSE Scanner")
is_stale = health_strip()

tab_scan, tab_chart, tab_bt, tab_journal, tab_data = st.tabs(
    ["Scan", "Chart", "Backtest", "Journal", "Data"]
)


# =====================================================================
# SCAN
# =====================================================================
with tab_scan:
    left, right = st.columns([1, 3])

    with left:
        st.subheader("Preset")
        preset_names = list(CFG["presets"].keys())
        preset = st.selectbox("Which combination", preset_names,
                              index=preset_names.index("w_baseline")
                              if "w_baseline" in preset_names else 0)

        resolved = resolve_preset(CFG, preset)
        st.caption("Conditions applied")
        if resolved.get("conditions"):
            for c in resolved["conditions"]:
                st.code(c, language=None)
        else:
            st.caption("None — this is the unfiltered control.")

        st.divider()
        st.subheader("Optional filters")
        use_rs = st.toggle("Relative strength", CFG["filters"]["use_relative_strength"])
        rs_min = st.slider("Minimum RS rank (percentile)", 0, 100,
                           CFG["filters"]["rs_rank_min_pct"], disabled=not use_rs)
        use_regime = st.toggle("Regime filter", CFG["filters"]["use_regime_filter"])

        CFG["filters"]["use_relative_strength"] = use_rs
        CFG["filters"]["rs_rank_min_pct"] = rs_min
        CFG["filters"]["use_regime_filter"] = use_regime

        st.caption(f"Market regime: **{regime_state(con, date.today())}**")

        ignore_stale = st.checkbox("Scan anyway on stale data", value=False,
                                   help="The guard exists so you do not act on "
                                        "signals that are no longer true.")
        go = st.button("Run scan", type="primary", use_container_width=True)

    with right:
        if go:
            try:
                with st.spinner("Scanning…"):
                    df = scan(con, preset, ignore_stale=ignore_stale)
                    store_signals(con, df)
                st.session_state["signals"] = df
            except RuntimeError as exc:
                st.error(str(exc))

        df = st.session_state.get("signals")
        if df is not None and not df.empty:
            st.subheader(f"{len(df)} signals")
            show = df[["symbol", "trigger_price", "l1_price", "l2_price",
                       "neckline", "depth_pct", "separation",
                       "stop_suggested", "target_suggested",
                       "bottom_at_sma", "sma_stack"]].copy()
            st.dataframe(show, use_container_width=True, hide_index=True,
                         height=520)

            st.download_button(
                "Download CSV", show.to_csv(index=False).encode(),
                f"signals_{preset}_{date.today():%Y%m%d}.csv", "text/csv")

            st.caption("Where the second bottom formed")
            st.bar_chart(df["bottom_at_sma"].value_counts())
        elif df is not None:
            st.info("No signals for this preset today.")
        else:
            st.caption("Pick a preset and run a scan.")


# =====================================================================
# CHART
# =====================================================================
with tab_chart:
    symbols = con.execute(
        "SELECT DISTINCT symbol FROM instruments ORDER BY symbol").df()
    if symbols.empty:
        st.info("No instruments loaded yet. Run universe.py first.")
    else:
        c1, c2, c3 = st.columns([2, 1, 1])
        sym = c1.selectbox("Symbol", symbols["symbol"])
        bars = c2.number_input("Bars", 100, 2000, CFG["ui"]["chart_lookback_bars"])
        overlays = c3.multiselect("Overlays",
                                  ["sma10", "sma20", "sma50", "sma100", "sma200"],
                                  ["sma50", "sma200"])

        isin = con.execute("SELECT isin FROM instruments WHERE symbol = ?",
                           [sym]).fetchone()
        if isin:
            d = con.execute("""
                SELECT b.date, b.open, b.high, b.low, b.close, b.volume, b.vwap,
                       f.sma10, f.sma20, f.sma50, f.sma100, f.sma200, f.atr14
                FROM bars_1d b
                LEFT JOIN features_1d f ON f.isin=b.isin AND f.date=b.date
                WHERE b.isin = ? ORDER BY b.date DESC LIMIT ?
            """, [isin[0], int(bars)]).df().sort_values("date").reset_index(drop=True)

            if d.empty:
                st.info("No bars for this symbol yet.")
            else:
                c4, c5 = st.columns([2, 1])
                anchor = c4.selectbox(
                    "Anchor VWAP at",
                    ["(none)", "52-week low", "52-week high", "last W first low"])
                show_w = c5.checkbox("Mark last W L1 / L2", value=True)

                atr_s = d["atr14"].fillna(ind.atr(d["high"], d["low"], d["close"]))
                active = None
                if show_w or anchor == "last W first low":
                    pcfg = CFG["pattern"]
                    candidates = pat.find_w_patterns(
                        d, atr_s,
                        zigzag_pct=pcfg["zigzag_pct"],
                        min_separation=pcfg["min_separation"],
                        max_separation=pcfg["max_separation"],
                        require_undercut=pcfg["require_undercut"],
                        min_depth_pct=pcfg["min_depth_pct"],
                        exclude_locked_bars=pcfg["exclude_locked_bars"],
                        confirm_max_wait=pcfg["entry_max_wait"],
                    )
                    # find_w_patterns only returns already-confirmed W's (L1
                    # reclaimed after L2), so the chart just needs the most
                    # recent one chronologically.
                    active = candidates[-1] if candidates else None

                fig = make_subplots(
                    rows=2, cols=1, shared_xaxes=True,
                    row_heights=[0.75, 0.25], vertical_spacing=0.03,
                )

                # up/down colors validated for CVD-safety (dataviz skill) —
                # TradingView's own defaults, not decorative choices.
                UP, DOWN = "#26a69a", "#ef5350"

                fig.add_trace(pgo.Candlestick(
                    x=d["date"], open=d["open"], high=d["high"],
                    low=d["low"], close=d["close"], name=sym,
                    increasing_line_color=UP, increasing_fillcolor=UP,
                    decreasing_line_color=DOWN, decreasing_fillcolor=DOWN,
                    line_width=1,
                ), row=1, col=1)

                # fixed per-entity colors (never cycled/reassigned by selection)
                overlay_colors = {
                    "sma10": "#3987e5", "sma20": "#d95926", "sma50": "#c98500",
                    "sma100": "#d55181", "sma200": "#9085e9",
                }
                for col in overlays:
                    fig.add_trace(pgo.Scatter(
                        x=d["date"], y=d[col], name=col.upper(), mode="lines",
                        line=dict(color=overlay_colors.get(col, "#c3c2b7"), width=1.4),
                    ), row=1, col=1)

                if anchor != "(none)" and d["vwap"].notna().any():
                    if anchor == "52-week low":
                        pos = int(d["low"].tail(252).idxmin())
                    elif anchor == "52-week high":
                        pos = int(d["high"].tail(252).idxmax())
                    else:
                        pos = active.l1_pos if active else 0
                    av, _up, _dn = ind.anchored_vwap(
                        d["vwap"].fillna(d["close"]), d["volume"], pos)
                    fig.add_trace(pgo.Scatter(
                        x=d["date"], y=av, name="AVWAP", mode="lines",
                        line=dict(color="#199e70", width=1.4, dash="dash"),
                    ), row=1, col=1)

                if show_w:
                    if active:
                        last_date = d["date"].iloc[-1]
                        for label, pos, price in (
                            ("L1", active.l1_pos, active.l1_price),
                            ("L2", active.l2_pos, active.l2_price),
                        ):
                            pivot_date = d["date"].iloc[pos]
                            # a ray from the actual pivot bar to now — not a
                            # full-width line — so it's unambiguous which
                            # candle is L1 and which is L2.
                            fig.add_shape(
                                type="line", x0=pivot_date, x1=last_date,
                                y0=price, y1=price, xref="x", yref="y",
                                line=dict(color="#c3c2b7", width=1, dash="dash"),
                                opacity=0.85, row=1, col=1,
                            )
                            fig.add_trace(pgo.Scatter(
                                x=[pivot_date], y=[price], mode="markers+text",
                                marker=dict(symbol="diamond", size=9,
                                           color="#E4E9E7",
                                           line=dict(color="#0F1211", width=1)),
                                text=[label], textposition="top center",
                                textfont=dict(color="#E4E9E7", size=11),
                                name=label, showlegend=False, hoverinfo="skip",
                            ), row=1, col=1)
                    else:
                        st.caption("No triggered W-pattern in the visible window.")

                vol_colors = np.where(d["close"] >= d["open"], UP, DOWN)
                fig.add_trace(pgo.Bar(
                    x=d["date"], y=d["volume"], name="Volume",
                    marker_color=vol_colors, marker_line_width=0, opacity=0.5,
                ), row=2, col=1)

                fig.update_layout(
                    height=560,
                    margin=dict(l=10, r=10, t=10, b=10),
                    paper_bgcolor="#0F1211",
                    plot_bgcolor="#0F1211",
                    font_color="#E4E9E7",
                    xaxis_rangeslider_visible=False,
                    hovermode="x unified",
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=1.01,
                               xanchor="left", x=0),
                )
                fig.update_xaxes(showgrid=True, gridcolor="#232928",
                                 showspikes=True, spikemode="across",
                                 spikesnap="cursor", spikecolor="#8B9694",
                                 spikethickness=1)
                fig.update_yaxes(showgrid=True, gridcolor="#232928", row=1, col=1)
                fig.update_yaxes(showgrid=False, row=2, col=1)

                st.plotly_chart(fig, width="stretch")


# =====================================================================
# BACKTEST
# =====================================================================
with tab_bt:
    st.subheader("W-pattern study")
    st.caption("Run the unfiltered control first. Without a baseline number "
               "you cannot tell whether a filter helped, hurt, or did nothing.")

    mode = st.radio("Mode", ["Single run", "Entry × exit sweep",
                             "Marginal contribution of SMA filters"],
                    horizontal=True)

    c1, c2, c3, c4 = st.columns(4)
    bp = c1.selectbox("Preset", list(CFG["presets"].keys()), key="btp")
    be = c2.selectbox("Entry", CFG["backtest"]["entry_variants"], index=1)
    bx = c3.selectbox("Exit", CFG["backtest"]["exit_variants"])
    samp = c4.selectbox("Sample", ["in", "out"],
                        help="Tune on 'in' only. Look at 'out' once, at the end.")
    limit = st.number_input("Limit symbols (0 = all)", 0, 5000, 0,
                            help="Use a small number for a quick trial run.")

    if st.button("Run backtest", type="primary"):
        lim = int(limit) or None
        with st.spinner("Replaying history…"):
            if mode == "Single run":
                rid = run_backtest(con, bp, be, bx, sample=samp, limit_symbols=lim)
                st.session_state["last_run"] = rid
            elif mode == "Entry × exit sweep":
                st.session_state["sweep"] = sweep(con, bp, samp, lim)
            else:
                st.session_state["marginal"] = marginal_contribution(
                    con, "w_baseline",
                    ["w_sma200_trend", "w_sma200_rising", "w_sma50_trend",
                     "w_golden", "w_stacked", "w_delivery", "w_full"],
                    be, bx, lim)

    minimum = CFG["backtest"]["min_trades_for_conclusion"]

    if "marginal" in st.session_state:
        m = st.session_state["marginal"]
        st.subheader("Does each filter actually add anything?")
        st.dataframe(m[["preset", "trades", "win_rate", "expectancy_r",
                        "delta_expectancy", "trade_retention_pct",
                        "enough_trades"]],
                     use_container_width=True, hide_index=True)
        st.caption(f"A filter that lifts expectancy but cuts trades below "
                   f"{minimum} has found a coincidence, not an edge.")

    if "sweep" in st.session_state:
        s = st.session_state["sweep"]
        st.subheader("Entry × exit grid")
        st.dataframe(s[["entry", "exit", "trades", "win_rate", "expectancy_r",
                        "profit_factor", "median_hold_days", "max_dd_pct"]],
                     use_container_width=True, hide_index=True)
        st.caption("Sorted by expectancy — check the trade count before "
                   "believing the top row.")

    if "last_run" in st.session_state:
        rid = st.session_state["last_run"]
        m = con.execute("SELECT * FROM backtest_metrics WHERE run_id = ?",
                        [rid]).df()
        if not m.empty:
            r = m.iloc[0]
            k = st.columns(6)
            k[0].metric("Trades", f"{int(r['trades'])}")
            k[1].metric("Win rate", f"{r['win_rate']:.1f}%")
            k[2].metric("Expectancy", f"{r['expectancy_r']:.3f} R")
            k[3].metric("Profit factor", f"{r['profit_factor']:.2f}")
            k[4].metric("Max DD", f"{r['max_dd_pct']:.1f}%")
            k[5].metric("Median hold", f"{r['median_hold_days']:.0f} d")

            if r["trades"] < minimum:
                st.warning(f"Only {int(r['trades'])} trades — below the "
                           f"{minimum} threshold. This is noise, not a result.")

        st.subheader("Holding period, measured")
        curves = analyse_curves(con, rid)
        if not curves.empty:
            cc1, cc2 = st.columns(2)
            with cc1:
                st.caption("Median MFE by day — where this flattens is your "
                           "natural holding period")
                st.line_chart(curves.set_index("day_n")[["median_mfe", "p75_mfe"]])
            with cc2:
                st.caption("Survival — % of trades still above entry")
                st.line_chart(curves.set_index("day_n")[["pct_positive"]])

            st.caption("Marginal gain from holding one more day — when this "
                       "reaches zero, the edge is spent")
            st.bar_chart(curves.set_index("day_n")[["marginal_mfe"]])

            if "p85_mae_win" in curves:
                st.caption("Stop candidate: the drawdown 85% of eventual "
                           "winners never exceeded")
                st.line_chart(curves.set_index("day_n")[["p85_mae_win"]])

            st.dataframe(curves, use_container_width=True, hide_index=True)


# =====================================================================
# JOURNAL
# =====================================================================
with tab_journal:
    jc1, jc2 = st.columns([1, 2])

    with jc1:
        st.subheader("Log a trade")
        with st.form("open_trade"):
            syms = con.execute(
                "SELECT DISTINCT symbol FROM instruments ORDER BY symbol").df()
            s = st.selectbox("Symbol", syms["symbol"] if not syms.empty else [])
            ed = st.date_input("Entry date", date.today())
            ep = st.number_input("Entry price", min_value=0.0, step=0.05)
            qt = st.number_input("Quantity", min_value=1, step=1)
            sp = st.number_input("Stop", min_value=0.0, step=0.05)
            tp = st.number_input("Target", min_value=0.0, step=0.05)
            pn = st.selectbox("Preset that fired", list(CFG["presets"].keys()))
            th = st.text_area("Thesis", height=80)
            if st.form_submit_button("Save", type="primary"):
                tid = jr.open_trade(con, s, ed, ep, int(qt), sp, tp, pn,
                                    thesis=th)
                st.success(f"Trade #{tid} logged.")

        st.divider()
        st.subheader("Close a trade")
        open_t = con.execute(
            "SELECT trade_id, symbol, entry_date, entry_price FROM trades "
            "WHERE status='open' ORDER BY entry_date DESC").df()
        if open_t.empty:
            st.caption("No open positions.")
        else:
            with st.form("close_trade"):
                tid = st.selectbox(
                    "Position", open_t["trade_id"],
                    format_func=lambda i: f"#{i} "
                    f"{open_t.set_index('trade_id').loc[i, 'symbol']}")
                xd = st.date_input("Exit date", date.today())
                xp = st.number_input("Exit price", min_value=0.0, step=0.05)
                xr = st.selectbox("Exit reason",
                                  ["target_hit", "stop_hit", "time_stop",
                                   "trailed_out", "discretionary_exit"])
                fp = st.checkbox("I followed my plan", value=True)
                nt = st.text_area("Review note", height=70)
                tags = st.multiselect(
                    "Behaviour tags",
                    ["chased_entry", "moved_stop", "revenge_trade",
                     "oversized", "exited_early", "held_through_earnings"])
                if st.form_submit_button("Close", type="primary"):
                    res = jr.close_trade(con, int(tid), xd, xp, xr, fp, nt)
                    if tags:
                        jr.add_tags(con, int(tid), tags)
                    st.success(f"Closed. R = {res['r_multiple']:.2f}, "
                               f"MAE {res['mae_pct']:.1f}%, "
                               f"MFE {res['mfe_pct']:.1f}%")

    with jc2:
        s = jr.summary(con)
        if s.get("trades", 0) == 0:
            st.info("No closed trades yet.")
        else:
            k = st.columns(5)
            k[0].metric("Trades", s["trades"])
            k[1].metric("Win rate", f"{s['win_rate']:.1f}%")
            k[2].metric("Expectancy", f"{s['expectancy_r']:.3f} R")
            k[3].metric("Median hold", f"{s['median_hold_days']:.0f} d")
            k[4].metric("Median MAE", f"{s['median_mae']:.1f}%")

            eq = jr.equity_curve(con)
            if not eq.empty:
                st.caption("Equity curve")
                st.line_chart(eq.set_index("exit_date")[["cum_pnl"]])

            st.caption("Did following the plan pay?")
            st.dataframe(jr.adherence_report(con), use_container_width=True,
                         hide_index=True)

            st.caption("Which preset earns its place")
            st.dataframe(jr.preset_attribution(con), use_container_width=True,
                         hide_index=True)

            tags_df = jr.tag_analysis(con)
            if not tags_df.empty:
                st.caption("Where the leaks are")
                st.dataframe(tags_df, use_container_width=True, hide_index=True)

            metric = st.selectbox("Do winners differ on…",
                                  ["deliv_pct_sma20", "adr_pct20", "adx14",
                                   "rs_rank_pct", "dist_sma200_pct"])
            sa = jr.snapshot_analysis(con, metric)
            if not sa.empty:
                st.dataframe(sa, use_container_width=True, hide_index=True)

            pn2 = st.selectbox("Compare live vs backtest for preset",
                               list(CFG["presets"].keys()), key="cmp")
            cmp_df = jr.compare_with_backtest(con, pn2)
            if not cmp_df.empty:
                st.caption("Backtest says what the logic can do. The journal "
                           "says what you did. The gap is where the money is.")
                st.dataframe(cmp_df, use_container_width=True, hide_index=True)


# =====================================================================
# DATA
# =====================================================================
with tab_data:
    st.subheader("Table sizes")
    st.dataframe(pd.DataFrame(table_counts(con).items(),
                              columns=["table", "rows"]),
                 use_container_width=True, hide_index=True)

    st.subheader("Validation failures (last 30 days)")
    v = con.execute("""
        SELECT date, symbol, yf_close, bhav_close, pct_diff
        FROM validation_log
        WHERE passed = FALSE AND date >= CURRENT_DATE - INTERVAL 30 DAY
        ORDER BY ABS(pct_diff) DESC LIMIT 200
    """).df()
    if v.empty:
        st.success("No mismatches against the official bhavcopy.")
    else:
        st.dataframe(v, use_container_width=True, hide_index=True)
        big = v[v["pct_diff"].abs() >= 15]
        if not big.empty:
            st.error(f"{len(big)} rows differ by 15%+ — these are almost "
                     "certainly corporate actions yfinance missed. They "
                     "manufacture fake W-bottoms. Investigate before trading "
                     "those symbols.")

    st.subheader("Recent ingest runs")
    st.dataframe(con.execute(
        "SELECT * FROM ingest_log ORDER BY run_ts DESC LIMIT 20").df(),
        use_container_width=True, hide_index=True)

    st.subheader("Symbols with residual gaps")
    st.caption("These failed to fill even after the anti-join retried them.")
    st.dataframe(con.execute("""
        SELECT i.symbol, s.status, s.consecutive_misses, s.last_success
        FROM symbol_status s JOIN instruments i ON i.isin = s.isin
        WHERE s.consecutive_misses > 0
        ORDER BY s.consecutive_misses DESC LIMIT 100
    """).df(), use_container_width=True, hide_index=True)
