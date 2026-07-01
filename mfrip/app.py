"""MFRIP web app. Bloomberg-style fund & portfolio intelligence.

Run from the project root (the folder containing this file):
    python -m streamlit run app.py

Funds shown are those already in mfrip_data.db. Add more with the CLI:
    python -m mfrip.cli fetch <code>
"""
from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from mfrip.config import DEFAULT_CONFIG, ASSET_PROXIES as ASSET_PROXIES_APP
from mfrip.ingest import open_store
from mfrip.webapp import data as D
from mfrip.webapp import charts as C
from mfrip.webapp import portfolio_lab as PL
from mfrip.webapp import research as RR
from mfrip.recommend import schema as RSCHEMA
from mfrip.advisor import (InvestorProfile, Employment, EmergencyFund, DebtLoad,
                           DrawdownReaction, Experience)
from mfrip.advisor.review import review_portfolio
from mfrip.advisor.recommend import recommend as advisor_recommend
from mfrip.advisor import glossary as GLOSS
from mfrip.metrics import rolling as ROLL
from mfrip.metrics import capture as CAP
from mfrip.metrics import sip as SIP
from mfrip.metrics import montecarlo as MC
from mfrip import validation as VALID
from mfrip.store import saved as SAVED
from mfrip.webapp import leaderboard as LB
from mfrip.webapp import benchmarks as BM
from mfrip.advisor.categorize import infer_sleeve

st.set_page_config(page_title="MFRIP · Fund Intelligence", page_icon="▲", layout="wide")

WINDOWS = {"6 months": 0.5, "1 year": 1.0, "3 years": 3.0, "5 years": 5.0, "Max": None}

# ----------------------------------------------------------------- styling
st.markdown("""
<style>
  #MainMenu, footer, header {visibility:hidden;}
  .block-container {padding-top:1.2rem; padding-bottom:2rem; max-width:1180px;}
  html, body, [class*="css"] {font-family:'Inter','Segoe UI',sans-serif;}
  /* amber top rule + header */
  .mf-top {border-top:2px solid #ffa53c; margin:-1.2rem -100vw 0; padding-top:1rem;}
  .mf-head {display:flex; align-items:baseline; gap:12px; border-bottom:1px solid #262a33;
            padding-bottom:10px; margin-bottom:6px;}
  .mf-tag {background:#ffa53c; color:#0a0c10; font-weight:700; font-size:11px;
           letter-spacing:.16em; padding:3px 8px; border-radius:2px;}
  .mf-title {color:#cdd3dc; font-size:19px; font-weight:600; letter-spacing:.02em;}
  .mf-sub {color:#6a7079; font-size:12px; font-family:monospace;}
  /* metrics → terminal tiles */
  div[data-testid="stMetric"] {background:#13161d; border:1px solid #262a33;
       border-radius:3px; padding:10px 12px;}
  div[data-testid="stMetricLabel"] p {color:#6a7079; font-size:10px !important;
       text-transform:uppercase; letter-spacing:.07em;}
  div[data-testid="stMetricValue"] {color:#cdd3dc; font-family:'SF Mono',Consolas,monospace;
       font-size:22px; font-variant-numeric:tabular-nums;}
  /* tabs */
  button[data-baseweb="tab"] {font-size:13px;}
  button[data-baseweb="tab"][aria-selected="true"] {color:#ffa53c;}
  div[data-baseweb="tab-highlight"] {background:#ffa53c;}
  h2, h3 {color:#ffa53c !important; font-size:13px !important; text-transform:uppercase;
          letter-spacing:.06em; font-weight:600;}
  .stDataFrame {border:1px solid #262a33; border-radius:3px;}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_conn() -> sqlite3.Connection:
    return open_store()


@st.cache_data
def funds(_conn):
    return D.available_funds(_conn)


def _pct(x):
    return "—" if x is None or (isinstance(x, float) and x != x) else f"{x:+.1%}"


def _num(x):
    return "—" if x is None or (isinstance(x, float) and x != x) else f"{x:.2f}"


GREEN, RED, NEUTRAL = "#33b27b", "#f0563f", "#cdd3dc"
AMBER = "#ffa53c"


def tiles_html(items, cols=4):
    """items: list of (label, value_str, colour). Returns a tile-grid HTML string."""
    cells = "".join(
        f'<div style="background:#13161d;border:1px solid #262a33;border-radius:4px;padding:9px 11px">'
        f'<div style="color:#6a7079;font-size:10px;text-transform:uppercase;letter-spacing:.06em">{lab}</div>'
        f'<div style="font-family:\'SF Mono\',Consolas,monospace;font-size:21px;color:{col};'
        f'font-variant-numeric:tabular-nums">{val}</div></div>'
        for lab, val, col in items
    )
    return (f'<div style="display:grid;grid-template-columns:repeat({cols},1fr);'
            f'gap:8px;margin:6px 0 14px">{cells}</div>')


def beginner() -> bool:
    """True when the user has Beginner mode switched on (sidebar)."""
    return bool(st.session_state.get("beginner_mode", False))


def learn(text: str, icon: str = "🎓"):
    """Render an extra plain-language explanation only in Beginner mode."""
    if beginner():
        st.info(text, icon=icon)


def task_card(emoji, title, tab, desc, when):
    return (f'<div style="background:#13161d;border:1px solid #262a33;border-left:3px solid #ffa53c;'
            f'border-radius:8px;padding:13px 15px;margin-bottom:10px">'
            f'<div style="font-size:15px;color:#ffa53c;font-weight:600">{emoji}&nbsp; {title}</div>'
            f'<div style="font-size:13px;color:#cdd3dc;margin:5px 0 6px">{desc}</div>'
            f'<div style="font-size:12px;color:#6a7079">→ open the <b style="color:#cdd3dc">{tab}</b> '
            f'tab&nbsp;·&nbsp;{when}</div></div>')


conn = get_conn()
fund_list = funds(conn)
name_by_code = {c: n for c, n in fund_list}
codes = [c for c, _ in fund_list]

n_schemes = D.count_schemes(conn)
st.markdown(
    '<div class="mf-top"></div>'
    '<div class="mf-head"><span class="mf-tag">MFRIP</span>'
    '<span class="mf-title">Fund Intelligence</span>'
    f'<span class="mf-sub">point-in-time · no-lookahead · {n_schemes:,} funds searchable · '
    f'{len(codes)} cached</span></div>',
    unsafe_allow_html=True,
)

if n_schemes == 0:
    from mfrip.webapp import bootstrap as BOOT
    st.info("First run on a fresh server, so we're setting up the fund data. This happens just once and takes about "
            "a minute.", icon="⏳")
    with st.status("Initialising MFRIP…", expanded=True) as _status:
        try:
            steps = BOOT.bootstrap(conn, progress=lambda m: _status.write(m))
            for s in steps:
                _status.write("✓ " + s)
            _status.update(label="All set, loading the app…", state="complete")
        except Exception as e:
            _status.update(label="Setup failed", state="error")
            st.error(f"Couldn't fetch the initial data from the public data source ({e}). "
                     "It may be down for a moment, so refresh to try again. If you're running "
                     "locally, run `python -m mfrip.cli sync-schemes` once, then refresh.")
            st.stop()
    funds.clear()
    st.rerun()

# ----------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("### MFRIP")
    st.toggle("🎓 Beginner mode", key="beginner_mode",
              help="Adds plain-language explanations under every metric, chart, and score, "
                   "without taking away any of the analysis.")
    if beginner():
        st.caption("Beginner mode is **on**, so you'll see 🎓 explainers throughout.")
    st.divider()
    st.caption("**New here?** Open the **Start here** tab for a 20-second tour of what each "
               "part does and where to begin.")
    st.divider()
    st.caption("MFRIP judges whether a fund or portfolio is *built well and suits you*. "
               "It does not predict returns. Educational tool, not investment advice.")


def name_of(code):
    if code in name_by_code:
        return name_by_code[code]
    r = conn.execute("SELECT scheme_name FROM schemes WHERE scheme_code=?", (code,)).fetchone()
    return r["scheme_name"] if r else str(code)


def search_pick(label, key, fallback_idx=0):
    """Search box over ALL Indian funds; falls back to cached funds before typing."""
    q = st.text_input(label, key=f"{key}_q",
                      placeholder="type 3+ letters of any Indian fund, like 'parag flexi'")
    if q and len(q.strip()) >= 3:
        matches = D.search_schemes(conn, q)
        if not matches:
            st.caption("No matching fund found.")
            return None
        d = dict(matches)
        return st.selectbox("Matches", list(d), format_func=lambda c: d[c], key=f"{key}_m")
    if codes:
        return st.selectbox("…or a cached fund", codes,
                            index=min(fallback_idx, len(codes) - 1),
                            format_func=name_of, key=f"{key}_loaded")
    return None


def weight_editor(picks, by_amount, slot):
    """Editable weight/amount table with a live total. In percent mode it shows a
    green/red 'Total: X%' and a Normalize-to-100 button. Returns the list of values."""
    wcol = "Amount ₹" if by_amount else "Weight %"
    ver = st.session_state.get(f"{slot}_ver", 0)
    default = 10000.0 if by_amount else round(100.0 / len(picks), 1)
    dfw = pd.DataFrame({"Fund": [name_of(c) for c in picks], wcol: [default] * len(picks)})
    ovr = st.session_state.pop(f"{slot}_ovr", None)
    if ovr is not None and len(ovr) == len(picks):
        dfw[wcol] = ovr
    edited = st.data_editor(
        dfw, hide_index=True, width='stretch',
        key=f"{slot}_{by_amount}_{ver}_{len(picks)}",
        column_config={
            "Fund": st.column_config.TextColumn(disabled=True),
            wcol: st.column_config.NumberColumn(min_value=0.0, step=1.0,
                  format="₹%.0f" if by_amount else "%.1f"),
        },
    )
    vals = [float(edited[wcol].iloc[j]) for j in range(len(picks))]
    total = sum(vals)
    if by_amount:
        st.markdown(f"<div style='font-size:13px;color:#9aa3ad'>Total invested: "
                    f"<b style='color:#cdd3dc'>₹{total:,.0f}</b></div>", unsafe_allow_html=True)
    else:
        ok = abs(total - 100.0) < 0.1
        msg = "" if ok else " (should add up to 100%)"
        st.markdown(f"<div style='font-size:13px;color:#9aa3ad'>Total weight: "
                    f"<b style='color:{GREEN if ok else RED}'>{total:.1f}%</b>{msg}</div>",
                    unsafe_allow_html=True)
        if not ok and total > 0 and st.button("Normalize to 100%", key=f"{slot}_norm"):
            st.session_state[f"{slot}_ovr"] = [round(v * 100.0 / total, 1) for v in vals]
            st.session_state[f"{slot}_ver"] = ver + 1
            st.rerun()
    return vals


def date_range_picker(nav_list, key, label="Date range"):
    """Date inputs constrained to the COMMON lifetime of the given NAV series.
    Returns (start_ts, end_ts, inception_note) or (None, None, note) if no overlap."""
    incs = [D.inception(n) for n in nav_list if n is not None and not n.empty]
    ends = [n.dropna().index[-1] for n in nav_list if n is not None and not n.empty]
    if not incs:
        return None, None, "No data."
    common_start = max(incs)           # later inception bounds the overlap
    common_end = min(ends)
    if common_start >= common_end:
        return None, None, "These funds have no overlapping history."
    note = (f"Common history from {common_start.date()} to {common_end.date()}"
            if len(nav_list) > 1 else f"Data from {common_start.date()}")
    c1, c2 = st.columns(2)
    s = c1.date_input("From", value=common_start.date(), min_value=common_start.date(),
                      max_value=common_end.date(), key=f"{key}_s")
    e = c2.date_input("To", value=common_end.date(), min_value=common_start.date(),
                      max_value=common_end.date(), key=f"{key}_e")
    if s >= e:
        st.caption("Start must be before end.")
        return None, None, note
    return pd.Timestamp(s), pd.Timestamp(e), note


def _short(nm):
    return nm.split(" - ")[0]


def _sub_returns(nav, start, end, n=3):
    span = (end - start) / n
    out = []
    for k in range(n):
        s, e = start + span * k, start + span * (k + 1)
        w = nav[(nav.index >= s) & (nav.index <= e)].dropna()
        out.append((s.date(), e.date(), float(w.iloc[-1] / w.iloc[0] - 1) if len(w) >= 2 else None))
    return out


def compare_verdict(na, sa, nb, sb, corr, nav_a, nav_b, start, end):
    """Templated, computed account of who led over the window and in each sub-period."""
    L = []
    w_ret = na if sa.total_return >= sb.total_return else nb
    L.append(f"- Over {sa.start} → {sa.end}, **{_short(w_ret)}** delivered the higher total return "
             f"({_pct(max(sa.total_return, sb.total_return))} vs {_pct(min(sa.total_return, sb.total_return))}).")
    w_sh = na if sa.sharpe >= sb.sharpe else nb
    L.append(f"- Risk-adjusted (Sharpe), **{_short(w_sh)}** led "
             f"({_num(max(sa.sharpe, sb.sharpe))} vs {_num(min(sa.sharpe, sb.sharpe))}).")
    safer = na if sa.max_drawdown >= sb.max_drawdown else nb
    L.append(f"- **{_short(safer)}** fell less at its worst "
             f"({_pct(max(sa.max_drawdown, sb.max_drawdown))} vs {_pct(min(sa.max_drawdown, sb.max_drawdown))} drawdown).")
    sra, srb = _sub_returns(nav_a, start, end), _sub_returns(nav_b, start, end)
    seg = ["Early", "Middle", "Late"]
    parts = []
    for k, (s, e, ra) in enumerate(sra):
        rb = srb[k][2]
        if ra is None or rb is None:
            continue
        leader = na if ra >= rb else nb
        parts.append(f"{seg[k]} ({s}→{e}): **{_short(leader)}** ({_pct(max(ra, rb))} vs {_pct(min(ra, rb))})")
    if parts:
        L.append("- Period by period: " + "; ".join(parts) + ".")
    if abs(sa.volatility - sb.volatility) > 0.02:
        mv = na if sa.volatility > sb.volatility else nb
        L.append(f"- {_short(mv)} was the more volatile "
                 f"({_pct(max(sa.volatility, sb.volatility))} vs {_pct(min(sa.volatility, sb.volatility))} annualised), "
                 f"a likely reason for its different drawdown and return profile.")
    rel = ("move closely together" if corr > 0.7 else
           "move fairly independently" if corr < 0.4 else "move somewhat together")
    div = ("so holding both adds little diversification" if corr > 0.7 else
           "so they can diversify each other" if corr < 0.4 else "so diversification is modest")
    L.append(f"- The two {rel} (correlation {_num(corr)}), {div}.")
    L.append("\n*Leadership in one window isn't predictive; these reasons are descriptive, not causal.*")
    return "\n".join(L)


def coverage_report(code_list):
    """Per-fund data ranges + the common overlap, to explain a failed blend."""
    lines, starts, ends = [], [], []
    for c in code_list:
        nav = D.load_nav(conn, c)
        nm = _short(name_of(c))
        if nav.empty:
            lines.append(f"- **{nm}**: no NAV data fetched (data source returned nothing)")
        else:
            lines.append(f"- **{nm}**: {nav.index[0].date()} → {nav.index[-1].date()}")
            starts.append(nav.index[0])
            ends.append(nav.index[-1])
    tail = ""
    if starts:
        cs, ce = max(starts), min(ends)
        if cs >= ce:
            tail = ("\n\n**No common period.** These funds' histories don't overlap, so they "
                    "can't be blended. Swap out the fund whose range ends earliest (a closed/merged "
                    "scheme, or a stale fetch), or re-pick it to fetch fresh data.")
        else:
            tail = f"\n\nThey do overlap from **{cs.date()} to {ce.date()}**, so if this still fails, re-fetch the fund with the shortest range."
    return "\n".join(lines) + tail


tab_home, tab_explore, tab_compare, tab_lab, tab_research, tab_advisor = st.tabs(
    ["START HERE", "EXPLORE A FUND", "COMPARE FUNDS", "PORTFOLIO LAB", "RESEARCH", "ADVISOR"])

# ================================================================= START HERE
with tab_home:
    st.markdown("#### Welcome to MFRIP")
    st.markdown(GLOSS.PHILOSOPHY)
    st.caption("Educational tool, not investment advice. Past performance does not predict future returns.")

    if beginner():
        st.success(
            "**🎓 Beginner mode is on.** From here on, look for the 🎓 boxes: under every chart, score, "
            "and number, you'll find a plain-language note explaining what you're looking at and how to read it. "
            "Brand new to this? Try it in three steps:\n\n"
            "1. Open **Explore a fund**, search a fund you've heard of, and read the 🎓 notes as you scroll.\n"
            "2. Open **Advisor**, type in a couple of funds you own (or might buy), and hit Analyze.\n"
            "3. Read the verdict and the suggested fixes. The 🎓 notes explain every part.",
            icon="🎓")
    else:
        st.info("New to investing? Flip on **🎓 Beginner mode** in the left sidebar. Every chart, score, and "
                "number then gets a plain-language explanation, so you can learn as you go.", icon="🎓")

    st.subheader("What would you like to do?")
    st.caption("Pick whichever fits. Each one opens in its own tab along the top.")
    cc = st.columns(2)
    for i, (emoji, title, tab, desc, when) in enumerate(GLOSS.TASK_GUIDE):
        cc[i % 2].markdown(task_card(emoji, title, tab, desc, when), unsafe_allow_html=True)

    st.subheader("How to read anything MFRIP shows you")
    st.caption("Keep these four apart and you'll never be misled by a number.")
    for label, body in GLOSS.TRUST_LAYERS:
        st.markdown(f"**{label}:** {body}")

    with st.expander("⚠️  What MFRIP can't do (the honest limits)"):
        for lim in GLOSS.LIMITATIONS:
            st.markdown(f"- {lim}")

    with st.expander("📖  Glossary: what every term really means"):
        st.markdown("**The six things we score a portfolio on**")
        for k, v in GLOSS.PARAM_HELP.items():
            st.markdown(f"- **{k}:** {v}")
        st.markdown("**Common metrics you'll see**")
        for k, v in GLOSS.METRIC_HELP.items():
            st.markdown(f"- **{k}:** {v}")

# ---------------------------------------------------------------- Explore
with tab_explore:
    code = search_pick("Search a fund", "exp")
    if code is None:
        st.stop()
    with st.spinner("Fetching NAV history…"):
        D.ensure_nav(conn, code)
    nav = D.load_nav(conn, code)
    if nav.empty:
        st.error("Couldn't fetch NAV for this fund. It may be missing on the data source.")
    else:
        start, end, note = date_range_picker([nav], "exp_dates")
        st.caption(f"📅 {note}")
        if start is None:
            st.stop()
        try:
            stats = D.stats_between(nav, start, end)
            ret_col = GREEN if (stats.total_return or 0) >= 0 else RED
            st.markdown(tiles_html([
                ("Return", _pct(stats.total_return), ret_col),
                ("Volatility", _pct(stats.volatility), NEUTRAL),
                ("Sharpe", _num(stats.sharpe), NEUTRAL),
                ("Max drawdown", _pct(stats.max_drawdown), RED),
            ]), unsafe_allow_html=True)
            learn("**Return** is the total growth over this period. **Volatility** is how bumpy the ride was: "
                  "higher means bigger swings. **Sharpe** is return earned per unit of bumpiness (above 1 is good, "
                  "above 2 is excellent). **Max drawdown** is the worst peak-to-bottom fall it ever took, the "
                  "loss you'd have had to stomach at the worst moment.")

            st.subheader(f"Growth of ₹1,00,000 · {stats.start} → {stats.end}")
            learn("This line shows what ₹1,00,000 invested at the start would be worth over time. A steady climb is what you want; a jagged path means a bumpier ride.")
            g = D.growth_between(nav, start, end, base=100_000).rename(name_of(code))
            st.plotly_chart(C.growth_chart({name_of(code): g}), width='stretch',
                            config={"displayModeBar": False})

            st.subheader("Trailing returns · annualised")
            learn("These are returns over different past periods, shown as a per-year figure ('annualised') so a 3-year and a 5-year number can be compared fairly.")
            tr = D.trailing_returns_table(nav)
            st.dataframe(
                pd.DataFrame({"Window": list(tr), "Return": [_pct(v) for v in tr.values()]}),
                hide_index=True, width='stretch',
            )
            st.caption(f"Full history from {nav.index[0].date()} · {len(nav)} NAVs · "
                       f"CAGR over range {_pct(stats.cagr)} · risk-free {DEFAULT_CONFIG.rf_annual:.1%}")

            # ---- rolling returns (kills the single-window illusion)
            st.subheader("Rolling returns · every window, not one lucky date")
            learn("Instead of a single return, this shows the whole range you might have got depending on your timing. The longer you stay invested, the narrower and safer that range becomes.")
            fund_sleeve = infer_sleeve(name_of(code))
            bench_code, bench_label = BM.resolve_benchmark(conn, fund_sleeve)
            bench_nav = D.load_nav(conn, bench_code) if bench_code else pd.Series(dtype=float)
            if bench_label and bench_code not in (None, 120716):
                st.caption(f"📐 We judge this against its **own category** index, *{bench_label}*, rather than the Nifty 50, so "
                           f"outperformance reflects stock-picking skill, not just the mid/small-cap premium.")
            beat_col = f"Beat {bench_label}" if bench_label else "Beat index"
            rows = []
            chart_rows = []
            for yrs, lab in [(1, "1-year"), (3, "3-year"), (5, "5-year")]:
                rr = ROLL.rolling_returns(nav, yrs)
                if not rr:
                    continue
                beat = ROLL.rolling_outperformance(nav, bench_nav, yrs) if not bench_nav.empty else None
                rows.append({"Window": lab, "Best": _pct(rr["best"]), "Worst": _pct(rr["worst"]),
                             "Average": _pct(rr["avg"]), "% positive": f"{rr['pct_positive']:.0%}",
                             beat_col: "—" if beat is None else f"{beat:.0%}",
                             "# windows": rr["count"]})
                chart_rows.append({"window": lab, "best": rr["best"], "worst": rr["worst"], "avg": rr["avg"]})
            if rows:
                if len(chart_rows) >= 1:
                    st.plotly_chart(C.rolling_range_chart(chart_rows), width='stretch',
                                    config={"displayModeBar": False})
                short = chart_rows[0]
                st.markdown(f"**In plain English:** depending on *when* you'd invested, this fund's "
                            f"{short['window']} return swung between **{short['worst']:+.0%}** (worst stretch) "
                            f"and **{short['best']:+.0%}** (best), averaging **{short['avg']:+.0%}**.")
                st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
                st.caption("Red = worst rolling window, green = best, amber diamond = average. The longer the "
                           "holding period, the tighter the range. That narrowing is why time in the market "
                           "matters more than timing it.")
            else:
                st.caption("Not enough history for rolling-return analysis (needs 1y+).")

            # ---- capture ratios (vs the category index)
            if not bench_nav.empty:
                uc, dc = CAP.capture_ratios(nav, bench_nav)
                if uc is not None and dc is not None:
                    st.subheader(f"Up / down capture vs {bench_label}")
                    learn("Capture compares the fund with the market. Up-capture is how much of the market's gains it grabbed; down-capture is how much of the losses it took. Catching more of the ups than the downs is the sweet spot.")
                    ccol = GREEN if uc >= 1 else NEUTRAL
                    dcol = GREEN if dc < 1 else RED
                    st.markdown(tiles_html([
                        ("Up-capture", f"{uc:.0%}", ccol),
                        ("Down-capture", f"{dc:.0%}", dcol),
                    ], cols=2), unsafe_allow_html=True)
                    if uc < 0.6 and dc < 0.6:
                        read = (f"This fund only loosely tracks {bench_label}. It caught **{uc:.0%}** of "
                                f"its gains and **{dc:.0%}** of its losses. Typical of a debt, gold, hybrid, or "
                                f"low-beta fund: calmer, but it won't fully ride rallies.")
                    elif uc >= dc:
                        read = (f"Of {bench_label}'s gains this fund caught **{uc:.0%}**, and of its losses only "
                                f"**{dc:.0%}**. Catching more of the upside than downside is the shape you want.")
                    else:
                        read = (f"This fund caught **{uc:.0%}** of {bench_label}'s gains but **{dc:.0%}** of its "
                                f"losses, so it takes more of the downside than the upside, the less flattering shape.")
                    st.caption(read)
            elif fund_sleeve in ("debt", "gold"):
                st.caption(f"No equity-index capture here, since comparing a {fund_sleeve} fund to a stock index "
                           f"isn't meaningful.")

            # ---- historical stress tests
            episodes = CAP.stress_test(nav)
            if episodes:
                st.subheader("How it held up in past stress")
                learn("The honesty check: how far this fund actually fell during real market crises. It shows what you'd have had to sit through if you'd held it back then.")
                st.plotly_chart(C.stress_chart(episodes), width='stretch',
                                config={"displayModeBar": False})
                st.caption("Return during each named market shock (hover for the worst drawdown inside the "
                           "episode). Episodes before this fund existed are skipped.")

            # ---- SIP & goal planner
            with st.expander("💰  SIP & goal planner"):
                sc = st.columns(2)
                monthly = sc[0].number_input("Monthly SIP (₹)", 500, 1000000, 10000, step=500, key="exp_sip")
                goal_years = sc[1].number_input("Goal horizon (years)", 1, 40, 15, key="exp_goalyr")
                sres = SIP.sip_xirr(nav, float(monthly), start, end)
                if sres and sres["xirr"] is not None:
                    st.markdown(tiles_html([
                        ("Invested", f"₹{sres['invested']:,.0f}", NEUTRAL),
                        ("Would be worth", f"₹{sres['final_value']:,.0f}", GREEN if sres['gain'] >= 0 else RED),
                        ("SIP return (XIRR)", f"{sres['xirr']:.1%}", GREEN if sres['xirr'] >= 0 else RED),
                    ], cols=3), unsafe_allow_html=True)
                    st.caption(f"If you'd invested ₹{monthly:,.0f}/month in this fund from {start.date()} to "
                               f"{end.date()} ({sres['instalments']} instalments). XIRR is the true "
                               f"money-weighted return, the one a monthly investor actually feels.")
                st.markdown("---")
                st.markdown(f"**Where could ₹{monthly:,.0f}/month for {goal_years:.0f} years actually end up?**")
                gc = st.columns(2)
                target = gc[0].number_input("Goal amount (₹, optional)", 0, 1_000_000_000, 0,
                                            step=100_000, key="exp_target",
                                            help="Set a target to see the simulated chance of reaching it. Leave at 0 to skip.")
                method_label = gc[1].selectbox(
                    "How to simulate", ["Resample this fund's history", "Bell-curve model"],
                    key="exp_mcmethod",
                    help="Resampling draws from the fund's actual past monthly returns, so it keeps its real "
                         "behaviour including crashes. The bell-curve model is smoother but assumes returns are "
                         "normally distributed, which tends to understate crash risk.")
                method_key = "bootstrap" if method_label.startswith("Resample") else "normal"
                try:
                    sim = MC.simulate_sip(nav, float(monthly), float(goal_years), n_sims=5000,
                                          method=method_key,
                                          target=(float(target) if target > 0 else None), seed=42)
                    learn("This is a **Monte Carlo simulation**. We took this fund's own history (about "
                          f"{sim['ann_return']:.0%}/year return with {sim['ann_vol']:.0%}/year swings) and played "
                          "out 5,000 possible futures for your SIP. The shaded fan is the range you might land in; "
                          "the middle line is the typical result. It widens over time because the further ahead "
                          "you look, the less certain things are. It is a range of scenarios, not a prediction.")
                    st.plotly_chart(C.montecarlo_fan(sim), width='stretch',
                                    config={"displayModeBar": False})
                    st.markdown(tiles_html([
                        ("Total you invest", f"₹{sim['total_invested']:,.0f}", NEUTRAL),
                        ("Unlucky · 10th pct", f"₹{sim['terminal_pct'][10]:,.0f}", RED),
                        ("Typical · median", f"₹{sim['terminal_pct'][50]:,.0f}", AMBER),
                        ("Lucky · 90th pct", f"₹{sim['terminal_pct'][90]:,.0f}", GREEN),
                    ], cols=4), unsafe_allow_html=True)
                    st.caption(f"In a typical future this turns ₹{sim['total_invested']:,.0f} invested into about "
                               f"₹{sim['terminal_pct'][50]:,.0f} ({sim['median_multiple']:.1f}x). But outcomes "
                               f"realistically range from ₹{sim['terminal_pct'][10]:,.0f} to "
                               f"₹{sim['terminal_pct'][90]:,.0f} depending on how markets behave.")
                    if target > 0:
                        prob = sim["prob_target"]
                        pcol = GREEN if prob >= 0.6 else AMBER if prob >= 0.35 else RED
                        st.markdown(
                            f"<div style='font-size:1.05rem;margin:.4rem 0'>Chance of reaching "
                            f"<b>₹{target:,.0f}</b>: <b style='color:{pcol}'>{prob:.0%}</b></div>",
                            unsafe_allow_html=True)
                        if prob >= 0.7:
                            st.caption("Comfortable: most simulated futures get there.")
                        elif prob >= 0.4:
                            st.caption("Plausible, but far from certain. Investing a little more, or giving it more "
                                       "time, would shift the odds in your favour.")
                        else:
                            st.caption("A stretch on this fund's history. You'd likely need a larger SIP, a longer "
                                       "horizon, or a higher-return (and higher-risk) fund.")
                        need50 = MC.required_monthly_for_confidence(nav, float(target), float(goal_years), 0.50, seed=42)
                        need75 = MC.required_monthly_for_confidence(nav, float(target), float(goal_years), 0.75, seed=42)
                        if need50 and need75:
                            learn(f"To reach ₹{target:,.0f} on this fund's history, you'd invest roughly "
                                  f"₹{need50:,.0f}/month for a 50/50 chance, or about ₹{need75:,.0f}/month to make "
                                  "it likely (around 75%). Higher confidence simply costs more per month.")
                    st.caption("Drawn from this fund's past monthly returns, assuming the future resembles the past "
                               "(it may not). Each month is simulated independently, so real multi-year streaks can "
                               "make the true spread a little wider. Ignores costs, taxes, and any change in the "
                               "fund's strategy. Educational, not a guarantee.")
                except ValueError as e:
                    st.info(f"Goal simulation needs a longer history for this fund. ({e})")
        except ValueError as e:
            st.error(str(e))

# ---------------------------------------------------------------- Compare
with tab_compare:
    cc = st.columns(2)
    with cc[0]:
        code_a = search_pick("Fund A", "cmp_a", fallback_idx=0)
    with cc[1]:
        code_b = search_pick("Fund B", "cmp_b", fallback_idx=1)

    if code_a is None or code_b is None:
        st.info("Search and pick two funds to compare.")
    elif code_a == code_b:
        st.info("Pick two different funds to compare.")
    else:
        with st.spinner("Fetching NAV history…"):
            D.ensure_nav(conn, code_a)
            D.ensure_nav(conn, code_b)
        nav_a, nav_b = D.load_nav(conn, code_a), D.load_nav(conn, code_b)
        ia, ib = D.inception(nav_a), D.inception(nav_b)
        if ia is not None and ib is not None:
            later = max(ia, ib)
            younger = name_of(code_a) if ia >= ib else name_of(code_b)
            st.caption(f"📅 {name_of(code_a).split(' - ')[0]} from {ia.date()} · "
                       f"{name_of(code_b).split(' - ')[0]} from {ib.date()}, "
                       f"comparable from **{later.date()}** (limited by the younger fund, {younger.split(' - ')[0]}).")
        start, end, note = date_range_picker([nav_a, nav_b], "cmp_dates")
        if start is None:
            st.warning(note)
            st.stop()
        try:
            sa = D.stats_between(nav_a, start, end)
            sb = D.stats_between(nav_b, start, end)
            corr = D.correlation(
                nav_a[(nav_a.index >= start) & (nav_a.index <= end)],
                nav_b[(nav_b.index >= start) & (nav_b.index <= end)],
            )

            left, right = st.columns(2)
            for col, nm, s in [(left, name_of(code_a), sa), (right, name_of(code_b), sb)]:
                rc = GREEN if (s.total_return or 0) >= 0 else RED
                col.markdown(f"**{nm}**")
                col.markdown(tiles_html([
                    ("Return", _pct(s.total_return), rc),
                    ("CAGR", _pct(s.cagr), rc),
                    ("Sharpe", _num(s.sharpe), NEUTRAL),
                    ("Max DD", _pct(s.max_drawdown), RED),
                ], cols=2), unsafe_allow_html=True)

            st.subheader(f"Growth of ₹1,00,000 · {sa.start} → {sa.end}")
            learn("Both funds start from the same amount, so you can see at a glance which one pulled ahead, and when.")
            ga = D.growth_between(nav_a, start, end, base=100_000).rename(name_of(code_a))
            gb = D.growth_between(nav_b, start, end, base=100_000).rename(name_of(code_b))
            st.plotly_chart(
                C.growth_chart({name_of(code_a): ga, name_of(code_b): gb}),
                width='stretch', config={"displayModeBar": False})

            st.subheader("Who led, and why")
            learn("This splits the race into stretches and explains who was winning in each, and the likely reason (more risk, a different category, and so on).")
            st.markdown(compare_verdict(name_of(code_a), sa, name_of(code_b), sb, corr,
                                        nav_a, nav_b, start, end))
        except ValueError as e:
            st.error(str(e))

# ---------------------------------------------------------------- Portfolio Lab
with tab_lab:
    st.caption("Build up to three portfolios from any funds, set allocations as percentages "
               "or rupee amounts, and compare risk-adjusted performance. Allocations auto-normalise.")
    top = st.columns([1, 1, 1, 2])
    n_pf = top[0].selectbox("Portfolios", [1, 2, 3], index=1, key="lab_n")
    lab_win = top[1].selectbox("Period", list(WINDOWS), index=2, key="lab_win")
    alloc_mode = top[2].selectbox("Allocate by", ["Percent (%)", "Amount (₹)"], key="lab_mode")

    # benchmark: only index funds make a valid yardstick for alpha/beta.
    # search the FULL scheme list so Nifty 50/500 are offered even if not cached.
    bench_matches = D.search_schemes(conn, "nifty 50 index", limit=30) or []
    bench_pool = [c for c, _ in bench_matches] or codes
    if 120716 not in bench_pool and 120716 in codes:
        bench_pool = [120716] + bench_pool
    b_default = bench_pool.index(120716) if 120716 in bench_pool else 0
    bench_code = top[3].selectbox("Benchmark (Nifty index)", bench_pool, index=b_default,
                                  format_func=name_of, key="lab_bench")
    lab_lb = WINDOWS[lab_win]
    by_amount = alloc_mode.startswith("Amount")
    wcol = "Amount ₹" if by_amount else "Weight %"

    PNAMES = ["Portfolio A", "Portfolio B", "Portfolio C"]
    builders = st.columns(int(n_pf))
    portfolios = {}
    for i in range(int(n_pf)):
        with builders[i]:
            nm = st.text_input("Name", PNAMES[i], key=f"lab_nm{i}")
            q = st.text_input("Search & add funds", key=f"lab_q{i}",
                              placeholder="type ≥3 letters, e.g. 'parag flexi'")
            sel_key = f"lab_sel{i}"
            current = st.session_state.get(sel_key, [])
            matches = D.search_schemes(conn, q) if q and len(q.strip()) >= 3 else []
            # always keep current picks in options so they persist across searches
            opt = list(dict.fromkeys(current + [m[0] for m in matches] + codes))
            picks = st.multiselect("Funds in this portfolio", opt, format_func=name_of, key=sel_key)
            if picks:
                with st.spinner("Fetching NAVs…"):
                    picks = [c for c in picks if D.ensure_nav(conn, c)]
                vals = weight_editor(picks, by_amount, slot=f"labw{i}")
                holdings = [(picks[j], vals[j]) for j in range(len(picks))]
                portfolios[nm] = holdings
                tot = sum(vals) or 1.0
                st.plotly_chart(
                    C.allocation_pie([name_of(picks[j]).split(" - ")[0][:18] for j in range(len(picks))],
                                     [v / tot for v in vals], title=nm),
                    width='stretch', config={"displayModeBar": False})

    if not portfolios:
        st.info("Pick funds for at least one portfolio to see the analysis.")
    else:
        with st.spinner("Fetching benchmark…"):
            D.ensure_nav(conn, bench_code)
        results, growth_series, all_codes = {}, {}, []
        for nm, holdings in portfolios.items():
            res = PL.analyze(conn, holdings, lab_lb, bench_code)
            results[nm] = res
            if res:
                growth_series[nm] = res["growth"].rename(nm)
                all_codes += [c for c, _ in holdings]

        valid = {n: r for n, r in results.items() if r}
        if not valid:
            st.error("Couldn't build any portfolio. Here's the data coverage of the funds you picked:")
            st.markdown(coverage_report(list(dict.fromkeys(all_codes or
                        [c for hs in portfolios.values() for c, _ in hs]))))
        else:
            # ---- metrics comparison table (portfolios as columns)
            ROWS = [
                ("CAGR", lambda r: _pct(r["stats"].cagr), True),
                ("Total return", lambda r: _pct(r["stats"].total_return), True),
                ("Volatility", lambda r: _pct(r["stats"].volatility), False),
                ("Sharpe", lambda r: _num(r["stats"].sharpe), False),
                ("Sortino", lambda r: _num(r["stats"].sortino), False),
                ("Max drawdown", lambda r: _pct(r["stats"].max_drawdown), "dd"),
                ("Calmar", lambda r: _num(r["calmar"]), False),
                ("Alpha (ann.)", lambda r: _pct(r["alpha"]), True),
                ("Beta", lambda r: _num(r["beta"]), False),
            ]
            names = list(valid)
            head = "".join(f'<th style="text-align:right">{n}</th>' for n in names)
            body = ""
            for label, fn, signed in ROWS:
                cells = ""
                for n in names:
                    r = valid[n]
                    val = fn(r)
                    col = NEUTRAL
                    if signed == "dd":
                        col = RED
                    elif signed is True:
                        raw = r["alpha"] if label.startswith("Alpha") else (
                              r["stats"].cagr if label == "CAGR" else r["stats"].total_return)
                        col = GREEN if (raw or 0) >= 0 else RED
                    cells += f'<td class="num" style="color:{col}">{val}</td>'
                body += (f'<tr><td style="color:#9aa3ad">{label}</td>{cells}</tr>')
            st.markdown(
                f'<table style="width:100%;border-collapse:collapse;font-size:13px;margin:6px 0 4px">'
                f'<thead><tr><th style="text-align:left;color:#ffa53c;font-size:10px;'
                f'text-transform:uppercase;letter-spacing:.06em;padding:6px 10px;border-bottom:1px solid #ffa53c33">Metric</th>'
                f'{head.replace("<th ", "<th class=num-h ")}</tr></thead><tbody>{body}</tbody></table>'
                '<style>.num-h{color:#ffa53c;font-size:10px;text-transform:uppercase;letter-spacing:.06em;'
                'padding:6px 10px;border-bottom:1px solid #ffa53c33;font-family:SF Mono,Consolas,monospace}'
                'tbody td{padding:6px 10px;border-bottom:1px solid #20242c}</style>',
                unsafe_allow_html=True,
            )
            for n in names:
                if results[n] and results[n]["excluded"] > 0:
                    st.caption(f"{n}: {results[n]['excluded']:.0%} excluded (un-priceable sleeve).")

            # ---- growth overlay (+ benchmark)
            st.subheader("Growth of ₹1,00,000")
            learn("Each portfolio you built starts from the same amount, with a benchmark for reference, so you can compare them directly.")
            bench_nav = D.load_nav(conn, bench_code)
            series = dict(growth_series)
            if not bench_nav.empty and growth_series:
                anchor = next(iter(growth_series.values()))
                bn = bench_nav[bench_nav.index >= anchor.index[0]]
                if len(bn) > 1:
                    series[name_of(bench_code) + " (benchmark)"] = (bn / float(bn.iloc[0])) * 100000
            st.plotly_chart(C.growth_chart(series), width='stretch',
                            config={"displayModeBar": False})

            # ---- correlation matrix
            cm = PL.correlation_matrix(conn, all_codes, name_by_code, lab_lb)
            if cm is not None and len(cm) >= 2:
                st.subheader("Correlation of holdings")
                learn("This grid shows how similarly your funds move. High numbers mean they rise and fall together (less protection); low numbers mean they balance each other out.")
                st.plotly_chart(C.correlation_heat(cm, height=min(420, 80 + 38 * len(cm))),
                                width='stretch', config={"displayModeBar": False})

            # ---- explainability
            insights = PL.explain(results)
            if insights:
                st.subheader("What the numbers say")
                learn("A plain-language summary of the comparison above, so you don't have to read the tables yourself.")
                st.markdown("\n".join(f"- {s}" for s in insights))
            st.caption("Direct-Growth, point-in-time NAVs, no lookahead. Alpha/beta vs the "
                       "chosen benchmark; risk-free assumed " f"{DEFAULT_CONFIG.rf_annual:.1%}.")

# ---------------------------------------------------------------- Research (Module 4)
def render_report(r):
    st.markdown(
        '<div class="mf-head" style="border:none;margin-bottom:2px">'
        '<span class="mf-tag" style="background:#56b6c2">RESEARCH</span>'
        f'<span class="mf-title">{r.title}</span></div>', unsafe_allow_html=True)
    st.caption(f"{r.subtitle} · as of {r.as_of}")
    st.markdown(tiles_html(list(r.kpis), cols=len(r.kpis)), unsafe_allow_html=True)
    for s in r.sections:
        st.subheader(s.title)
        for p in s.paragraphs:
            st.write(p)
        if s.bullets:
            st.markdown("\n".join(f"- {b}" for b in s.bullets))
    st.download_button("⬇  Download HTML memo", RR.render_html(r),
                       file_name=f"research_{r.title[:24].replace(' ', '_')}.html",
                       mime="text/html", key="rr_dl")


with tab_research:
    st.caption("Generate an institutional research memo: nine sections, every line built "
               "from real computed numbers, for an audited recommendation or a portfolio you build.")
    kind = st.radio("Report on", ["Audited recommendation", "A portfolio"],
                    horizontal=True, key="rr_kind")

    if kind == "Audited recommendation":
        auditable = []
        for row in conn.execute("SELECT rec_id, advisor, risk_profile FROM recommendations "
                                "ORDER BY rec_id").fetchall():
            rec = RSCHEMA.load_recommendation(conn, row["rec_id"])
            if any(f.included and f.scheme_code for f in rec.funds):
                auditable.append((row["rec_id"], f"{rec.advisor} · {rec.risk_profile}  (#{row['rec_id']})"))
        if not auditable:
            st.info("No audited recommendations in this database. Load and fetch them via the CLI first.")
        else:
            d = dict(auditable)
            rid = st.selectbox("Recommendation", list(d), format_func=lambda c: d[c], key="rr_rec")
            eq = st.checkbox("Use broad Nifty 500 proxy for the passive twin (fairer)", value=True)
            proxies = dict(ASSET_PROXIES_APP)
            if eq and 147625 in codes:
                proxies["equity"] = 147625
            with st.spinner("Building research memo…"):
                rep = RR.recommendation_report(conn, rid, proxies=proxies)
            if rep is None:
                st.error("Could not build a report: NAV data is missing for this plan.")
            else:
                render_report(rep)

    else:  # A portfolio
        rc = st.columns([1, 1, 2])
        rp_win = rc[0].selectbox("Period", list(WINDOWS), index=2, key="rr_win")
        rp_name = rc[1].text_input("Name", "My Portfolio", key="rr_nm")
        bmatch = D.search_schemes(conn, "nifty 50 index", limit=20) or []
        bpool = [c for c, _ in bmatch] or codes
        bidx = bpool.index(120716) if 120716 in bpool else 0
        rp_bench = rc[2].selectbox("Benchmark (Nifty index)", bpool, index=bidx,
                                   format_func=name_of, key="rr_bench")
        q = st.text_input("Search & add funds", key="rr_q",
                          placeholder="type ≥3 letters, e.g. 'sbi small cap'")
        current = st.session_state.get("rr_sel", [])
        matches = D.search_schemes(conn, q) if q and len(q.strip()) >= 3 else []
        opt = list(dict.fromkeys(current + [m[0] for m in matches] + codes))
        picks = st.multiselect("Funds", opt, format_func=name_of, key="rr_sel")
        if not picks:
            st.info("Add at least one fund to generate a portfolio memo.")
        else:
            with st.spinner("Fetching NAVs…"):
                picks = [c for c in picks if D.ensure_nav(conn, c)]
                D.ensure_nav(conn, rp_bench)
            vals = weight_editor(picks, by_amount=False, slot="rrw")
            holdings = [(picks[j], vals[j]) for j in range(len(picks))]
            names_map = {c: name_of(c) for c in picks}
            with st.spinner("Building research memo…"):
                rep = RR.portfolio_report(conn, rp_name, holdings, WINDOWS[rp_win], rp_win,
                                          rp_bench, names_map, bench_name=name_of(rp_bench).split(" - ")[0])
            if rep is None:
                st.error("Couldn't build this portfolio. Here's each fund's data coverage:")
                st.markdown(coverage_report([c for c, _ in holdings]))
            else:
                render_report(rep)

                # ---- save this portfolio
                st.divider()
                sv = st.columns([3, 1])
                save_name = sv[0].text_input("Save as", rp_name, key="rr_savenm",
                                             label_visibility="collapsed")
                if sv[1].button("💾  Save portfolio", key="rr_save"):
                    tot = sum(vals) or 1.0
                    SAVED.save_portfolio(conn, save_name,
                                         [(picks[j], vals[j] / tot, name_of(picks[j])) for j in range(len(picks))])
                    st.success(f"Saved “{save_name}”. See it under *My saved portfolios* below.")

                # ---- leaderboard vs advised plans
                st.subheader("How your portfolio ranks against the advised plans")
                learn("This ranks your portfolio against well-known advisor plans on the same risk-adjusted basis. A high rank means strong return for the risk you took, over this period.")
                advised = []
                for row in conn.execute("SELECT rec_id, advisor, risk_profile FROM recommendations "
                                        "ORDER BY rec_id").fetchall():
                    r = RSCHEMA.load_recommendation(conn, row["rec_id"])
                    if any(f.included and f.scheme_code for f in r.funds):
                        advised.append((row["rec_id"], f"{r.advisor} · {r.risk_profile}"))
                if not advised:
                    st.caption("No advised plans loaded in this database to compare against.")
                else:
                    with st.spinner("Ranking against the advised plans over a common 3-year window…"):
                        board = LB.leaderboard(conn, holdings, advised, lookback=3.0, benchmark_code=rp_bench)
                    if board:
                        st.dataframe(pd.DataFrame([
                            {"Rank": r["rank"], "Portfolio": r["name"], "CAGR": _pct(r["cagr"]),
                             "Volatility": _pct(r["volatility"]), "Sharpe": _num(r["sharpe"]),
                             "Max DD": _pct(r["max_drawdown"])} for r in board
                        ]), hide_index=True, width='stretch')
                        you = next((r for r in board if r["is_user"]), None)
                        if you:
                            st.caption(f"Your portfolio ranks **#{you['rank']} of {len(board)}** by Sharpe ratio "
                                       f"over the last 3 years, judged on exactly the same risk-adjusted basis as the "
                                       f"advised plans. Ranking reflects this period only, not the future.")

    # ---- saved portfolios (load / delete), shared across modes
    st.divider()
    with st.expander("📁  My saved portfolios"):
        saved_list = SAVED.list_portfolios(conn)
        if not saved_list:
            st.caption("Nothing saved yet. Build a portfolio above and hit Save.")
        else:
            for sp in saved_list:
                cols = st.columns([3, 2, 1, 1])
                cols[0].markdown(f"**{sp['name']}**  ·  {len(sp['holdings'])} funds")
                cols[1].caption(sp["created_at"][:10])
                if cols[2].button("Load", key=f"load_{sp['id']}"):
                    st.session_state["rr_sel"] = [c for c, _, _ in sp["holdings"]]
                    st.session_state["adv_loaded_note"] = sp["name"]
                    st.rerun()
                if cols[3].button("Delete", key=f"del_{sp['id']}"):
                    SAVED.delete_portfolio(conn, sp["id"])
                    st.rerun()
            if st.session_state.get("adv_loaded_note"):
                st.caption(f"Loaded “{st.session_state.pop('adv_loaded_note')}” into the portfolio builder above "
                           "(switch to *A portfolio* mode if needed).")

    # ---- Walk-forward validation (does the ranking hold up out-of-sample?)
    st.markdown("---")
    st.subheader("Does the ranking actually hold up?  ·  out-of-sample test")
    st.caption("An honest tool should be able to show whether its own ranking predicts anything. "
               "This re-runs the engine on the past and checks it against what happened next.")
    learn("**Walk-forward validation** is how you tell a real ranking from luck. We step back in "
          "time, rank funds using only the data available up to that date, then watch how those "
          "funds actually did over the NEXT couple of years, data the ranking never saw. Repeat "
          "across many dates. If the funds we rated highly genuinely did better afterwards, the "
          "ranking carries signal. We score it with rank correlation: +1 means the order held "
          "perfectly, 0 means no better than a coin toss.")
    if st.button("Run walk-forward validation", key="run_val"):
        with st.spinner("Re-ranking the past and scoring it against the future..."):
            st.session_state["val_data"] = VALID.run_validation(conn, lookback_years=3, horizon_years=2)
            st.session_state["val_ran"] = True
    if not st.session_state.get("val_ran"):
        st.caption("Click to run. It walks through several years of history fund by fund, so give "
                   "it a few seconds.")
    else:
        _res = st.session_state.get("val_data")
        _ov = _res["overall"] if _res else None
        if _res is None or _ov is None or _ov.get("n_windows", 0) == 0:
            st.warning("Not enough history yet. Validation needs at least 5 equity funds with about "
                       "5+ years of NAV data in the database. Add more recommendations, fetch their "
                       "history via the CLI, and run again.")
        else:
            st.markdown(f"Tested on **{_res['n_funds']} equity funds** across **{_ov['n_windows']} "
                        f"train/test windows** ({_res['lookback_years']}-year lookback, "
                        f"{_res['horizon_years']}-year out-of-sample horizon).")
            _mc1, _mc2 = st.columns(2)
            _mc1.metric("Risk ranking persistence (ρ)", f"{_ov['risk_corr']:+.2f}",
                        help="How well the ranking predicts future consistency, drawdowns and "
                             "volatility. Higher is better.")
            _mc2.metric("Return ranking persistence (ρ)", f"{_ov['return_corr']:+.2f}",
                        help="How well the ranking predicts future Sharpe, Sortino and CAGR. "
                             "Returns are inherently harder to foresee than risk.")
            _rc, _retc = _ov["risk_corr"], _ov["return_corr"]
            if _rc > _retc + 0.10:
                st.info("Exactly what an honest tool should show: the ranking tracks **future risk** "
                        "(consistency, drawdowns, volatility) more reliably than future returns. Risk "
                        "characteristics persist; raw return is much harder to predict, which is why "
                        "this tool ranks on risk-adjusted behaviour rather than chasing performance.")
            elif _retc > 0.20:
                st.info("The ranking shows out-of-sample signal on **both** risk and return "
                        "persistence here. That is a strong result, but still not a promise about "
                        "any single fund.")
            else:
                st.info("The out-of-sample signal is weak on this universe and horizon. That is an "
                        "honest finding, not a hidden one: past ranking does not strongly predict "
                        "the future here. The tool is about suitability and discipline, not a "
                        "crystal ball.")
            _labels = {"oos_sharpe": "Risk-adjusted (Sharpe)", "oos_sortino": "Downside (Sortino)",
                       "oos_cagr": "Return (CAGR)", "oos_consistency": "Consistency",
                       "oos_max_drawdown": "Drawdown resilience", "oos_volatility": "Low volatility"}
            _rows = []
            for _m in ["oos_sharpe", "oos_sortino", "oos_cagr", "oos_consistency",
                       "oos_max_drawdown", "oos_volatility"]:
                _pc = _ov["pooled_corr"][_m]
                _higher = VALID.OOS_METRICS[_m]
                _dir_ok = (_pc["rho"] > 0) if _higher else (_pc["rho"] < 0)
                _rows.append({
                    "What the ranking should predict": _labels[_m],
                    "Rank correlation (ρ)": round(float(_pc["rho"]), 2),
                    "p-value": round(float(_pc["p"]), 3),
                    "Holds up?": "yes" if (_pc["p"] < 0.05 and _dir_ok) else "no",
                })
            st.dataframe(pd.DataFrame(_rows), hide_index=True, width='stretch')
            st.caption("Rank correlation between our in-sample score and each realised out-of-sample "
                       "outcome, pooled across all funds and windows. The p-value is from a "
                       "permutation test (no distribution assumed); 'yes' means significant at 5% in "
                       "the expected direction. For volatility, predicting *lower* is the win.")
            st.plotly_chart(
                C.validation_scatter(_ov["pooled"], "oos_sharpe", "Out-of-sample Sharpe",
                                     rho=_ov["pooled_corr"]["oos_sharpe"]["rho"]),
                width='stretch', config={"displayModeBar": False})
            st.caption("Each dot is one fund in one window: its in-sample score (left to right) "
                       "against the Sharpe it went on to deliver. An upward tilt means higher-ranked "
                       "funds tended to do better afterwards.")
            if _res.get("by_sleeve"):
                _sl_lbl = {"largecap": "Large Cap", "flexicap": "Flexi/Multi Cap",
                           "midcap": "Mid Cap", "smallcap": "Small Cap",
                           "international": "International"}
                with st.expander("Break it down by category"):
                    _srows = []
                    for _sl, _wf in _res["by_sleeve"].items():
                        _srows.append({
                            "Category": _sl_lbl.get(_sl, _sl.title()),
                            "Windows": _wf["n_windows"],
                            "Risk ρ": round(float(_wf["risk_corr"]), 2),
                            "Return ρ": round(float(_wf["return_corr"]), 2),
                        })
                    st.dataframe(pd.DataFrame(_srows), hide_index=True, width='stretch')
                    st.caption("Validation within each category separately. Smaller groups are "
                               "noisier, so read these as directional, not precise.")
            st.caption("Validation tests whether the ranking is *informative and consistent* "
                       "out-of-sample. It is not a guarantee that any individual fund will "
                       "outperform, and a synthetic or short history will behave differently from a "
                       "full real universe.")


# ---------------------------------------------------------------- Advisor (review + recommend)
_REACTION = {"Hold and wait": DrawdownReaction.WAIT, "Invest more": DrawdownReaction.INVEST_MORE,
             "Increase my SIP": DrawdownReaction.INCREASE_SIP, "Sell everything": DrawdownReaction.SELL_ALL}
_EMERG = {"6+ months saved": EmergencyFund.SIX_PLUS, "3-6 months": EmergencyFund.THREE_TO_6M,
          "Under 3 months": EmergencyFund.UPTO_3M, "None": EmergencyFund.NONE}
_DEBT = {"None": DebtLoad.NONE, "Low (e.g. home loan)": DebtLoad.LOW,
         "Moderate": DebtLoad.MODERATE, "High-interest (cards/personal)": DebtLoad.HIGH}
_EMPLOY = {"Salaried (stable/govt)": Employment.SALARIED_STABLE, "Salaried (private)": Employment.SALARIED_PRIVATE,
           "Self-employed": Employment.SELF_EMPLOYED, "Business owner": Employment.BUSINESS,
           "Retired": Employment.RETIRED, "Student": Employment.STUDENT, "Between jobs": Employment.UNEMPLOYED}
_SLEEVE_LABEL_APP = {"largecap": "Large Cap", "flexicap": "Flexi/Multi Cap", "midcap": "Mid Cap",
                     "smallcap": "Small Cap", "international": "International", "debt": "Debt", "gold": "Gold"}


def _build_profile():
    st.markdown("**1 · About you**")
    a = st.columns(3)
    age = a[0].slider("Age", 18, 75, 30, key="adv_age")
    horizon = a[1].slider("Investment horizon (years)", 1, 30, 10, key="adv_hz")
    exp = a[2].selectbox("Experience with investing",
                         ["none", "beginner", "intermediate", "experienced"], index=1, key="adv_exp")
    b = st.columns(3)
    react = b[0].selectbox("If a ₹10L portfolio fell to ₹7L, you'd…", list(_REACTION), key="adv_rx")
    emerg = b[1].selectbox("Emergency fund", list(_EMERG), key="adv_ef")
    debt = b[2].selectbox("Debt", list(_DEBT), key="adv_debt")
    employ = st.selectbox("Employment", list(_EMPLOY), index=1, key="adv_emp")
    return InvestorProfile(
        age=age, horizon_years=float(horizon), employment=_EMPLOY[employ],
        emergency_fund=_EMERG[emerg], debt=_DEBT[debt],
        drawdown_reaction=_REACTION[react], experience=Experience(exp))


def _health_block(health, stats):
    score = health.overall
    col = GREEN if score >= 75 else "#ffa53c" if score >= 55 else RED
    st.markdown(f"<div style='font-size:13px;color:#6a7079'>PORTFOLIO HEALTH</div>"
                f"<div style='font-family:SF Mono,monospace;font-size:42px;color:{col};line-height:1'>"
                f"{score:.0f}<span style='font-size:18px;color:#6a7079'>/100</span></div>",
                unsafe_allow_html=True)
    items = []
    for k, v in health.parts.items():
        c = GREEN if v >= 75 else "#ffa53c" if v >= 50 else RED
        items.append((k, f"{v:.0f}", c))
    st.markdown(tiles_html(items, cols=3), unsafe_allow_html=True)
    learn("The **Portfolio Health Score** (0 to 100) blends six checks: diversification, risk match, consistency, "
          "downside protection, concentration, and liquidity. It rates how well your portfolio is *built and "
          "suited to you*, not whether it will go up. 75+ is strong, 55 to 74 is okay with fixable gaps, below 55 "
          "needs attention. Each tile above is one of the six, scored the same way.")
    if stats:
        st.caption(f"Validated over up to 5y: CAGR {_pct(stats.cagr)} · vol {_pct(stats.volatility)} · "
                   f"Sharpe {_num(stats.sharpe)} · max drawdown {_pct(stats.max_drawdown)}")


def _alloc_compare(actual, target):
    cols = st.columns(2)
    SLAB = {"largecap": "Large", "flexicap": "Flexi", "midcap": "Mid", "smallcap": "Small",
            "international": "Intl", "debt": "Debt", "gold": "Gold"}
    with cols[0]:
        if actual:
            st.plotly_chart(C.allocation_pie([SLAB.get(s, s) for s in actual],
                            list(actual.values()), title="Your mix"),
                            width='stretch', config={"displayModeBar": False})
    with cols[1]:
        st.plotly_chart(C.allocation_pie([SLAB.get(s, s) for s in target],
                        list(target.values()), title="Suitable target"),
                        width='stretch', config={"displayModeBar": False})


with tab_advisor:
    st.caption("Enter the funds you hold and a little about yourself. We'll judge how healthy and "
               "suitable your portfolio is, then suggest specific fixes, all drawn straight from your actual funds.")
    st.info("Educational tool, not investment advice. Past performance does not predict future returns.", icon="ℹ️")

    profile = _build_profile()

    st.markdown("**2 · Your current portfolio**")
    q = st.text_input("Search & add the funds you hold", key="adv_q",
                      placeholder="type ≥3 letters, e.g. 'sbi small cap'")
    current = st.session_state.get("adv_sel", [])
    matches = D.search_schemes(conn, q) if q and len(q.strip()) >= 3 else []
    opt = list(dict.fromkeys(current + [m[0] for m in matches] + codes))
    picks = st.multiselect("Funds you own", opt, format_func=name_of, key="adv_sel")

    if not picks:
        st.info("Add the funds you currently hold to get your portfolio reviewed.")
    else:
        with st.spinner("Fetching NAVs…"):
            picks = [c for c in picks if D.ensure_nav(conn, c)]
        vals = weight_editor(picks, by_amount=False, slot="advw")
        holdings = [(picks[j], vals[j]) for j in range(len(picks))]
        names_map = {c: name_of(c) for c in picks}

        if st.button("🔍  Analyze my portfolio", key="adv_go", type="primary"):
            st.session_state["adv_run"] = True

        if st.session_state.get("adv_run"):
            with st.spinner("Reviewing…"):
                rv = review_portfolio(conn, profile, holdings, names_map)

            st.divider()
            st.subheader(f"Verdict · you look {rv.risk_bucket.lower()} (risk score {rv.risk_score:.0f}/100)")
            if rv.health:
                _health_block(rv.health, rv.stats)
                with st.expander("📋  How we judge your portfolio, and what each score means"):
                    for line in GLOSS.scoring_intro():
                        st.markdown(line)
                    st.markdown("---")
                    for k, v in rv.health.parts.items():
                        st.markdown(f"**{k}: {v:.0f}/100** · {GLOSS.PARAM_HELP.get(k, '')}")

            vc = st.columns(2)
            with vc[0]:
                st.markdown("**What's working**")
                if rv.strengths:
                    st.markdown("\n".join(f"- {s}" for s in rv.strengths))
                else:
                    st.caption("Nothing stands out as a clear strength yet.")
            with vc[1]:
                st.markdown("**What to fix**")
                if rv.weaknesses:
                    st.markdown("\n".join(f"- {w}" for w in rv.weaknesses))
                else:
                    st.caption("No major weaknesses flagged.")

            st.subheader("Your mix vs what suits you")
            learn("The left donut is how your money is actually split across fund types; the right is the split we'd suggest for someone with your profile. The gaps between them are what the advice below fixes.")
            _alloc_compare(rv.actual_allocation, rv.target_allocation)

            st.subheader("Recommended changes")
            learn("Specific moves: which fund types to add or trim, and named funds to consider, to close the gaps shown above.")
            for g in rv.gaps:
                if g.action == "add":
                    extra = f", consider **{g.suggested_fund[1].split(' - ')[0]}**" if g.suggested_fund else ""
                    st.markdown(f"🟢 **Add** · {g.detail}{extra}")
                elif g.action == "trim":
                    st.markdown(f"🔴 **Trim** · {g.detail}")
            if rv.switches:
                st.markdown("**Possible upgrades within a category:**")
                for s in rv.switches:
                    st.markdown(f"- Swap **{s.held_name.split(' - ')[0]}** → **{s.better_name.split(' - ')[0]}**: {s.reason}")
            if rv.uncategorized:
                st.caption("Couldn't categorise (excluded from sleeve analysis): " + ", ".join(rv.uncategorized))

            # ---- how your funds correlate (diversification guidance)
            if len(picks) >= 2:
                cm = PL.correlation_matrix(conn, picks, names_map, 5.0)
                if cm is not None and len(cm) >= 2:
                    st.subheader("How your funds correlate")
                    learn("Whether your funds genuinely diversify, or just double up on the same kind of bet.")
                    st.caption("1.0 = they move identically · 0 = unrelated. Low numbers between holdings "
                               "mean real diversification.")
                    st.plotly_chart(C.correlation_heat(cm, height=min(420, 90 + 40 * len(cm))),
                                    width='stretch', config={"displayModeBar": False})
                    for line in PL.correlation_guidance(cm):
                        st.markdown(f"- {line}")

            # ---- head to head: their mix vs a suitable suggested mix, same window
            with st.spinner("Building a suitable portfolio to compare…"):
                rec = advisor_recommend(conn, profile)
            sugg_holdings = [(p.code, p.weight) for p in rec.picks]
            if sugg_holdings:
                h2h = PL.head_to_head(conn, [(picks[j], vals[j]) for j in range(len(picks))], sugg_holdings)
                st.subheader("Your portfolio vs our suggested mix")
                learn("A fair test: your current mix and our suggested one, run over the exact same past period. This is history, not a prediction of what's ahead.")
                if h2h is None:
                    st.caption("Not enough overlapping history to compare the two over a common window.")
                else:
                    ga, gb, sa, sb, (ws, we) = h2h
                    st.markdown(f"Over the period both could be measured (**{ws.date()} → {we.date()}**), "
                                f"₹1,00,000 invested in each:")
                    cmpc = st.columns(2)
                    cmpc[0].markdown(tiles_html([
                        ("Your end value", f"₹{ga.iloc[-1]:,.0f}", NEUTRAL),
                        ("Your CAGR", _pct(sa.cagr), GREEN if sa.cagr >= 0 else RED),
                        ("Your worst fall", _pct(sa.max_drawdown), RED),
                        ("Your Sharpe", _num(sa.sharpe), NEUTRAL),
                    ], cols=2), unsafe_allow_html=True)
                    cmpc[1].markdown(tiles_html([
                        ("Suggested end value", f"₹{gb.iloc[-1]:,.0f}", NEUTRAL),
                        ("Suggested CAGR", _pct(sb.cagr), GREEN if sb.cagr >= 0 else RED),
                        ("Suggested worst fall", _pct(sb.max_drawdown), RED),
                        ("Suggested Sharpe", _num(sb.sharpe), NEUTRAL),
                    ], cols=2), unsafe_allow_html=True)
                    st.plotly_chart(
                        C.growth_chart({"Your portfolio": ga.rename("Your portfolio"),
                                        "Suggested mix": gb.rename("Suggested mix")}),
                        width='stretch', config={"displayModeBar": False})
                    better_dd = "suggested" if sb.max_drawdown > sa.max_drawdown else "your"
                    better_sh = "suggested" if sb.sharpe > sa.sharpe else "your"
                    st.markdown(f"The **{better_sh}** mix earned more per unit of risk (higher Sharpe), and the "
                                f"**{better_dd}** mix fell less at its worst. "
                                "*This is how each would have behaved in the past, not a forecast. A mix "
                                "chosen by studying the past will tend to look good against that same past.*")
                    with st.expander("See the suggested portfolio's funds"):
                        for p in rec.picks:
                            st.markdown(f"- **{p.weight:.0%} {p.name.split(' - ')[0]}** "
                                        f"({_SLEEVE_LABEL_APP.get(p.sleeve, p.sleeve)}) · score {p.composite:.0f}/100")
                        if rec.gaps:
                            st.caption("No cached fund for: " + ", ".join(rec.gaps))
