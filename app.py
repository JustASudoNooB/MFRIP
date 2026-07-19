"""MFRIP web app. Bloomberg-style fund & portfolio intelligence.

Run from the project root (the folder containing this file):
    python -m streamlit run app.py

Funds shown are those already in mfrip_data.db. Add more with the CLI:
    python -m mfrip.cli fetch <code>
"""
from __future__ import annotations

import os
import sqlite3
import sys

# Make the bundled `mfrip` package importable no matter how or from where this
# file is launched (for example Streamlit Cloud running it from a nested folder).
# Without this, a nested checkout can raise `ModuleNotFoundError: No module named 'mfrip'`.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
from mfrip.metrics import returns as RET
from mfrip.metrics import capture as CAP
from mfrip.metrics import relative as REL
from mfrip.metrics import tax as TAX
from mfrip.webapp.verdict import one_line_read
from mfrip.metrics import sip as SIP
from mfrip.metrics import montecarlo as MC
from mfrip import validation as VALID
from mfrip.store import saved as SAVED
from mfrip.webapp import leaderboard as LB
from mfrip.webapp import screener as SCR
from mfrip.webapp import freshness as FRESH
from mfrip.webapp import benchmarks as BM
from mfrip.advisor.categorize import infer_sleeve

st.set_page_config(page_title="MFRIP · Fund Intelligence", page_icon="▲", layout="wide")

WINDOWS = {"6 months": 0.5, "1 year": 1.0, "3 years": 3.0, "5 years": 5.0, "Max": None}

# ----------------------------------------------------------------- styling
# Editorial design-studio skin: warm paper, ink type, hand-drawn accents.
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700;800&family=Manrope:wght@400;500;600;700&display=swap');
  #MainMenu, footer, header {visibility:hidden;}
  /* self-contained canvas: the light theme must hold even if config.toml is absent */
  .stApp {background:#F2EFE8 !important; color:#17150F;}
  section[data-testid="stSidebar"] {background:#EBE6DB !important;}
  section[data-testid="stSidebar"] * {color:#17150F;}
  div[data-testid="stExpander"] summary, div[data-testid="stExpander"] summary p,
  div[data-testid="stExpander"] p, .stApp label p, .stMarkdown p {color:#17150F;}
  .stApp [data-testid="stCaptionContainer"] p {color:#6B6455; font-size:13px; line-height:1.55;}
  .block-container {padding-top:1.0rem; padding-bottom:2.5rem; max-width:1180px;}
  html, body, [class*="css"] {font-family:'Manrope','Inter','Segoe UI',sans-serif; color:#17150F;}
  h1,h2,h3,h4 {font-family:'Sora','Manrope',sans-serif !important;
               letter-spacing:-0.01em; color:#17150F !important;}
  h2,h3 {font-size:16px !important; font-weight:650;}
  /* masthead: bare wordmark on paper, thin ink rule ending in a wave */
  .mf-head {display:flex; align-items:baseline; gap:14px; background:none;
            padding:6px 0 12px 0; margin-bottom:14px; position:relative;
            border-bottom:1.5px solid #17150F;}
  .mf-head::after {content:""; position:absolute; right:0; bottom:-8px;
      width:72px; height:14px; background-repeat:no-repeat;
      background-image:url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='72' height='14' viewBox='0 0 72 14'%3E%3Cpath d='M2 8 Q8 2 14 8 T26 8 T38 8 T50 8 T62 8 T74 8' fill='none' stroke='%2317150F' stroke-width='2.4' stroke-linecap='round'/%3E%3C/svg%3E");}
  .mf-tag {background:none; color:#17150F; font-family:'Sora',sans-serif;
           font-weight:800; font-size:17px; letter-spacing:.14em; padding:0;}
  .mf-title {color:#17150F; font-family:'Sora',sans-serif;
             font-size:17px; font-weight:600;}
  .mf-sub {color:#6B6455; font-size:12px;}
  /* hero */
  .mf-hero {position:relative; padding:34px 8px 30px 8px; overflow:visible;}
  .mf-hero::before {content:""; position:absolute; top:-60px; left:-90px;
      width:420px; height:340px; pointer-events:none; z-index:0;
      background:radial-gradient(closest-side, rgba(245,184,160,.38), rgba(201,184,240,.30) 55%, rgba(242,239,232,0) 75%);
      filter:blur(38px);}
  .mf-hero h1 {position:relative; z-index:1; margin:0 0 12px 0;
      font-family:'Sora',sans-serif; font-weight:700; color:#17150F;
      font-size:clamp(34px,5vw,56px); line-height:1.08; letter-spacing:-0.015em;}
  .mf-hero .squig {position:relative; white-space:nowrap;}
  .mf-hero .squig::after {content:""; position:absolute; left:0; right:0; bottom:-7px; height:10px;
      background-repeat:repeat-x;
      background-image:url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='10' viewBox='0 0 40 10'%3E%3Cpath d='M0 6 Q5 1 10 6 T20 6 T30 6 T40 6' fill='none' stroke='%2317150F' stroke-width='3' stroke-linecap='round'/%3E%3C/svg%3E");}
  .mf-hero p {position:relative; z-index:1; color:#8D8677; font-size:16px;
      margin:0 0 20px 0; max-width:560px;}
  .mf-pill {display:inline-block; background:#17150F; color:#F2EFE8 !important;
      padding:11px 24px; border-radius:999px; font-weight:600; font-size:14px;
      text-decoration:none !important; transition:transform .12s ease, box-shadow .12s ease;
      box-shadow:0 2px 8px rgba(23,21,15,.18);}
  .mf-pill:hover {transform:translateY(-2px); box-shadow:0 5px 14px rgba(23,21,15,.24);}
  /* ink statement band */
  .mf-band {position:relative; background:#17150F; color:#F2EFE8;
      border-radius:16px; padding:30px 34px; margin:8px 0 18px 0; overflow:hidden;}
  .mf-band p {position:relative; z-index:1; font-family:'Sora',sans-serif;
      font-size:clamp(16px,2vw,21px); line-height:1.65; margin:0; color:#F2EFE8;}
  .mf-band::before, .mf-band::after {content:""; position:absolute; width:220px; height:60px;
      opacity:.14; background-repeat:repeat-x;
      background-image:url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='44' height='16' viewBox='0 0 44 16'%3E%3Cpath d='M0 9 Q5.5 3 11 9 T22 9 T33 9 T44 9' fill='none' stroke='%23F2EFE8' stroke-width='2'/%3E%3C/svg%3E");}
  .mf-band::before {top:14px; right:-30px; transform:rotate(-4deg);}
  .mf-band::after {bottom:12px; left:-24px; transform:rotate(3deg);}
  /* tabs: editorial uppercase, hand-drawn underline on active */
  div[data-baseweb="tab-list"] {gap:20px; border-bottom:1px solid #E4DDD0 !important;}
  button[data-baseweb="tab"] {font-size:12px; letter-spacing:.12em; text-transform:uppercase;
      color:#8D8677; background:transparent; border-radius:0;
      padding:8px 2px 12px 2px !important; font-weight:600;}
  button[data-baseweb="tab"]:hover {color:#17150F; background:transparent;}
  button[data-baseweb="tab"][aria-selected="true"] {color:#17150F; background:transparent;
      background-image:url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='36' height='8' viewBox='0 0 36 8'%3E%3Cpath d='M1 5 Q5.5 1 10 5 T19 5 T28 5 T37 5' fill='none' stroke='%2317150F' stroke-width='2.6' stroke-linecap='round'/%3E%3C/svg%3E");
      background-repeat:repeat-x; background-position:left bottom 2px; background-size:36px 8px;}
  div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"] {display:none;}
  /* cards, tables, widgets */
  div[data-testid="stMetric"] {background:#FBF9F4; border:1px solid #E4DDD0;
       border-radius:14px; padding:10px 14px; box-shadow:0 1px 2px rgba(23,21,15,.05);}
  div[data-testid="stMetricLabel"] p {color:#8D8677; font-size:11px !important;
       text-transform:uppercase; letter-spacing:.06em;}
  div[data-testid="stMetricValue"] {color:#17150F; font-size:22px;
       font-variant-numeric:tabular-nums;}
  .stDataFrame {border:1px solid #E4DDD0; border-radius:14px;
       box-shadow:0 1px 2px rgba(23,21,15,.05);}
  div[data-testid="stExpander"] {background:#FBF9F4; border:1px solid #E4DDD0;
       border-radius:14px;}
  .stButton > button {background:#17150F; color:#F2EFE8; border:none;
       border-radius:999px; padding:.45rem 1.3rem; font-weight:600;
       transition:transform .12s ease;}
  .stButton > button:hover {transform:translateY(-1px); color:#F2EFE8; background:#2A261C;}
  section[data-testid="stSidebar"] {border-right:1px solid #E4DDD0;}
  /* phones and small screens */
  @media (max-width: 640px) {
    .block-container {padding-left:.65rem; padding-right:.65rem; padding-top:.7rem;}
    .mf-head {flex-wrap:wrap; gap:8px 10px; row-gap:4px;}
    .mf-sub {flex-basis:100%; font-size:11px; line-height:1.5;}
    .mf-title {font-size:15px;}
    .mf-hero {padding:22px 2px 20px 2px;}
    .mf-hero::before {width:280px; height:240px; left:-70px; top:-50px;}
    .mf-band {padding:22px 20px;}
    button[data-baseweb="tab"] {font-size:11px; letter-spacing:.10em;}
    div[data-baseweb="tab-list"] {overflow-x:auto; -webkit-overflow-scrolling:touch;
        scrollbar-width:none; gap:14px;}
    div[data-baseweb="tab-list"]::-webkit-scrollbar {display:none;}
    div[data-testid="stMetricValue"] {font-size:19px;}
    h2, h3 {font-size:14px !important;}
  }
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


GREEN, RED, NEUTRAL = "#147A52", "#C2452D", "#17150F"
AMBER = "#C05F0E"  # app accent (deep amber, readable on paper)


def tiles_html(items, cols=4):
    """items: list of (label, value_str, colour). Returns a tile-grid HTML string."""
    cells = "".join(
        f'<div style="background:#FBF9F4;border:1px solid #E4DDD0;'
        f'border-left:3px solid {col if col in (GREEN, RED) else "#E4DDD0"};'
        f'border-radius:14px;padding:9px 12px;box-shadow:0 1px 2px rgba(23,21,15,.05)">'
        f'<div style="color:#8D8677;font-size:11px;text-transform:uppercase;letter-spacing:.05em">{lab}</div>'
        f'<div style="font-size:21px;color:{col};'
        f'font-variant-numeric:tabular-nums">{val}</div></div>'
        for lab, val, col in items
    )
    return (f'<div style="display:grid;'
            f'grid-template-columns:repeat(auto-fit,minmax(min(150px,100%),1fr));'
            f'gap:8px;margin:6px 0 14px">{cells}</div>')


def beginner() -> bool:
    """True when the user has Beginner mode switched on (sidebar)."""
    return bool(st.session_state.get("beginner_mode", False))


def learn(text: str, icon: str = "🎓"):
    """Render an extra plain-language explanation only in Beginner mode."""
    if beginner():
        st.info(text, icon=icon)


def task_card(emoji, title, tab, desc, when):
    return (f'<div style="background:#ffffff;border:1px solid #E4DDD0;border-left:3px solid #8D8677;'
            f'border-radius:8px;padding:13px 15px;margin-bottom:10px">'
            f'<div style="font-size:15px;color:#8D8677;font-weight:600">{emoji}&nbsp; {title}</div>'
            f'<div style="font-size:13px;color:#17150F;margin:5px 0 6px">{desc}</div>'
            f'<div style="font-size:12px;color:#8D8677">→ open the <b style="color:#17150F">{tab}</b> '
            f'tab&nbsp;·&nbsp;{when}</div></div>')


conn = get_conn()
fund_list = funds(conn)
name_by_code = {c: n for c, n in fund_list}
codes = [c for c, _ in fund_list]

# ---------------------------------------------------------- daily data refresh
# Keep the shipped snapshot current: if the newest NAV has fallen more than a
# few days behind, re-fetch the cached funds once per day per running server.
# Safe before bootstrap: an empty database is never "stale", only unbuilt.
import datetime as _dt


@st.cache_resource(show_spinner=False)
def _daily_refresh(day_key: str) -> dict:
    out = FRESH.refresh_if_stale(conn)
    if out.get("updated"):
        funds.clear()
    return out


if FRESH.is_stale(conn):
    with st.spinner("Fetching the latest NAVs from mfapi.in… (happens about once a day)"):
        _fresh = _daily_refresh(str(_dt.date.today()))
else:
    _fresh = _daily_refresh(str(_dt.date.today()))
_data_to = FRESH.latest_nav_date(conn)

n_schemes = D.count_schemes(conn)
_fresh_bit = f'data to {_data_to:%d %b %Y} · ' if _data_to is not None else ''
st.markdown(
    '<div class="mf-head"><span class="mf-tag">MFRIP</span>'
    '<span class="mf-title">Fund Intelligence</span>'
    f'<span class="mf-sub">point-in-time · no-lookahead · {_fresh_bit}'
    f'{n_schemes:,} funds searchable · '
    f'{len(codes)} cached</span></div>',
    unsafe_allow_html=True,
)
if _fresh.get("ran") and _fresh.get("updated", 0) == 0 and _data_to is not None:
    st.caption(f"Tried to update fund data, but the public source (mfapi.in) wasn't reachable "
               f"just now. Showing data up to {_data_to:%d %b %Y}; it retries automatically "
               "tomorrow, or sooner if the app restarts.")

from mfrip.webapp import bootstrap as BOOT
if BOOT.needs_bootstrap(conn):
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
                    f"<b style='color:#17150F'>₹{total:,.0f}</b></div>", unsafe_allow_html=True)
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


tab_home, tab_explore, tab_screener, tab_compare, tab_lab, tab_research, tab_advisor = st.tabs(
    ["START HERE", "EXPLORE A FUND", "SCREENER", "COMPARE FUNDS", "PORTFOLIO LAB", "RESEARCH", "ADVISOR"])

# ================================================================= START HERE
with tab_home:
    st.markdown(
        '<div class="mf-hero">'
        '<h1><span class="squig">Honest</span> research for<br>mutual fund decisions.</h1>'
        '<p>No predictions, no black boxes. Every score, chart, and verdict shows its full working, '
        'so you can see exactly how we got there.</p>'
        '<a class="mf-pill" href="#pick-a-task">Pick a task ↓</a>'
        '</div>', unsafe_allow_html=True)
    _phil = GLOSS.PHILOSOPHY.replace("'", "&#39;")
    st.markdown(f'<div class="mf-band"><p>{_phil}</p></div>', unsafe_allow_html=True)
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

    st.markdown('<div id="pick-a-task"></div>', unsafe_allow_html=True)
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

            # ---- calendar-year (year-on-year) returns
            cy = RET.calendar_year_returns(nav)
            if cy:
                st.subheader("Year-on-year returns · one bar per calendar year")
                learn("This is how the fund did in each individual year (January to December), rather than as an "
                      "average. It shows consistency and the bad years, not just the smooth long-run figure. A star "
                      "next to a bar means that year is partial: the fund either started or the data ends part-way "
                      "through it.")
                st.plotly_chart(C.calendar_year_chart(cy), width='stretch',
                                config={"displayModeBar": False})
                _best = max(cy, key=lambda t: t[1])
                _worst = min(cy, key=lambda t: t[1])
                _pos = sum(1 for _, r, _p in cy if r >= 0)
                st.caption(f"Best year {_best[0]} at {_pct(_best[1])}, worst year {_worst[0]} at {_pct(_worst[1])}. "
                           f"Positive in {_pos} of {len(cy)} years. Past years are history, not a guide to future ones.")

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

                # ---- alpha & beta (vs the category index)
                _fr = RET.period_returns(nav, 12)
                _br = RET.period_returns(bench_nav, 12)
                _joined = pd.DataFrame({"f": _fr, "b": _br}).dropna().tail(36)
                if len(_joined) >= 24:
                    _beta, _alpha = REL.beta_alpha(_joined["f"], _joined["b"],
                                                   DEFAULT_CONFIG.rf_annual, 12)
                    st.subheader(f"Alpha & beta vs {bench_label} · last 3 years")
                    learn("Beta is how hard the fund swings when its benchmark moves: 1.0 means in step, "
                          "above 1 means amplified, below 1 means damped. Alpha is the extra return per year "
                          "beyond what its beta would predict, after the risk-free rate: the closest thing to "
                          "a 'manager skill' number, though luck plays a part too.")
                    _acol = GREEN if _alpha > 0.005 else RED if _alpha < -0.005 else NEUTRAL
                    st.markdown(tiles_html([
                        ("Beta", f"{_beta:.2f}", NEUTRAL),
                        ("Alpha (annualised)", f"{_alpha:+.1%}", _acol),
                    ], cols=2), unsafe_allow_html=True)
                    st.markdown("*" + one_line_read(alpha=_alpha, beta=_beta,
                                                    up_capture=uc, down_capture=dc) + "*")
                    _roll = REL.rolling_beta_alpha(nav, bench_nav, 3.0,
                                                   DEFAULT_CONFIG.rf_annual, 12)
                    if len(_roll) >= 12:
                        st.markdown("**Rolling 3-year alpha** · is the outperformance a habit?")
                        learn("One alpha number can hide a lot: a single great year can carry a decade. This "
                              "chart recomputes alpha over every rolling 3-year window, so you can see whether "
                              "beating the benchmark is consistent behaviour or a one-off stretch.")
                        st.plotly_chart(C.rolling_alpha_chart(_roll), width='stretch',
                                        config={"displayModeBar": False})
                        _pos = float((_roll["alpha"] > 0).mean())
                        st.caption(f"Alpha was positive in {_pos:.0%} of all rolling 3-year windows. "
                                   "Past habit, not a promise.")
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
                step_up_pct = st.number_input("Annual SIP step-up (%)", 0, 25, 0, key="exp_stepup",
                                              help="Raise your monthly amount by this much every year, the way "
                                                   "many people do as income grows. 0 keeps it flat.")
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
                                          target=(float(target) if target > 0 else None), seed=42,
                                          step_up=step_up_pct / 100.0)
                    if step_up_pct:
                        st.caption(f"With a {step_up_pct}% yearly step-up, your instalment grows from "
                                   f"₹{monthly:,.0f} now to ₹{monthly * (1 + step_up_pct / 100.0) ** (goal_years - 1):,.0f} "
                                   "in the final year; the totals below include that.")
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

                    # ---- what you'd actually keep, after capital-gains tax
                    _show_tax = st.toggle("Show post-tax · what you'd actually keep", key="exp_tax",
                                          help="Applies today's Indian capital-gains rules to each simulated "
                                               "outcome, as if you redeemed everything at the end.")
                    if _show_tax:
                        _ac_default = TAX.asset_class_for_sleeve(fund_sleeve)
                        _tc = st.columns(2)
                        _ac_label = _tc[0].selectbox(
                            "Tax treatment", ["Equity fund", "Debt fund (slab rate)", "Other (gold/international/hybrid)"],
                            index={"equity": 0, "debt": 1, "other": 2}[_ac_default], key="exp_tax_ac",
                            help="Auto-picked from the fund's category; override if you know better.")
                        _slab = _tc[1].selectbox("Your income-tax slab", [0.10, 0.20, 0.30],
                                                 index=2, format_func=lambda v: f"{v:.0%}", key="exp_tax_slab")
                        _ac = {"Equity fund": "equity", "Debt fund (slab rate)": "debt",
                               "Other (gold/international/hybrid)": "other"}[_ac_label]
                        _post = TAX.apply_to_sim(sim, _ac, _slab)
                        st.markdown(tiles_html([
                            ("Post-tax · unlucky 10th", f"₹{_post['terminal_pct'][10]:,.0f}", RED),
                            ("Post-tax · typical", f"₹{_post['terminal_pct'][50]:,.0f}", AMBER),
                            ("Post-tax · lucky 90th", f"₹{_post['terminal_pct'][90]:,.0f}", GREEN),
                        ], cols=3), unsafe_allow_html=True)
                        _line = (f"Tax trims the typical outcome by about {_post['effective_tax_median']:.1%}.")
                        if "prob_target" in _post and target > 0:
                            _line += (f" After tax, the chance of reaching ₹{target:,.0f} is "
                                      f"**{_post['prob_target']:.0%}** (pre-tax: {sim['prob_target']:.0%}).")
                        st.markdown(_line)
                        st.caption("Assumes full redemption at the horizon with all units long-term (a SIP's "
                                   "final months would really be short-term, so the true tax is slightly "
                                   "higher). Excludes surcharge and cess; the ₹1.25L equity exemption is "
                                   "applied once. Rules change; educational, not tax advice.")
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
                    st.caption("Each thin line is one complete simulated future, from first instalment to the "
                               "end: a sample of 100 of the 5,000 futures simulated, picked across the whole "
                               "range. Red lines ended unlucky, green ended lucky. Notice how similar they all "
                               "look in the early years; the spread is a later-years story.")
                    st.caption("Drawn from this fund's past monthly returns, assuming the future resembles the past "
                               "(it may not). Each month is simulated independently, so real multi-year streaks can "
                               "make the true spread a little wider. Ignores costs, taxes, and any change in the "
                               "fund's strategy. Educational, not a guarantee.")
                except ValueError as e:
                    st.info(f"Goal simulation needs a longer history for this fund. ({e})")
            # ---- withdrawal planner (SWP)
            with st.expander("💸  Withdrawal planner · will the money last?"):
                learn("The reverse of a SIP: you have a corpus and draw a monthly amount from it. Each month "
                      "the money grows (or falls) with the fund, then your withdrawal comes out. We simulate "
                      "5,000 futures and ask one blunt question: does the corpus survive your horizon?")
                wc = st.columns(3)
                swp_corpus = wc[0].number_input("Corpus today (₹)", 100_000, 1_000_000_000,
                                                5_000_000, step=100_000, key="exp_swp_c")
                swp_monthly = wc[1].number_input("Withdraw per month (₹)", 1_000, 10_000_000,
                                                 40_000, step=1_000, key="exp_swp_w")
                swp_years = wc[2].number_input("For how many years", 1, 50, 25, key="exp_swp_y")
                try:
                    _swp = MC.simulate_swp(nav, float(swp_corpus), float(swp_monthly),
                                           float(swp_years), n_sims=5000, seed=42)
                    st.plotly_chart(C.swp_fan(_swp), width='stretch',
                                    config={"displayModeBar": False})
                    _sp = _swp["survival_prob"]
                    _scol = GREEN if _sp >= 0.85 else AMBER if _sp >= 0.6 else RED
                    st.markdown(tiles_html([
                        ("Survives the full horizon", f"{_sp:.0%}", _scol),
                        ("Typically lasts", f"{_swp['median_lasts_years']:.1f} yrs"
                         if _swp['median_lasts_years'] < swp_years else f"{swp_years:.0f}+ yrs", NEUTRAL),
                        ("Typical corpus at the end", f"₹{_swp['median_end_corpus']:,.0f}", NEUTRAL),
                    ], cols=3), unsafe_allow_html=True)
                    _rate = swp_monthly * 12 / swp_corpus
                    st.caption(f"You are drawing {_rate:.1%} of the corpus per year. Each thin line is one "
                               "simulated future; once a line touches zero it stays there, because you cannot "
                               "withdraw from an empty account. Ignores taxes and exit loads. Educational, "
                               "not a guarantee.")
                except ValueError as e:
                    st.info(f"Withdrawal simulation needs a longer history for this fund. ({e})")

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
                f'<thead><tr><th style="text-align:left;color:#8D8677;font-size:11px;'
                f'text-transform:uppercase;letter-spacing:.06em;padding:6px 10px;border-bottom:1px solid #dbe4ff">Metric</th>'
                f'{head.replace("<th ", "<th class=num-h ")}</tr></thead><tbody>{body}</tbody></table>'
                '<style>.num-h{color:#8D8677;font-size:11px;text-transform:uppercase;letter-spacing:.06em;'
                'padding:6px 10px;border-bottom:1px solid #dbe4ff}'
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
            st.subheader("Correlation of holdings")
            if cm is not None and len(cm) >= 2:
                learn("This grid shows how similarly your funds move. High numbers mean they rise and fall together (less protection); low numbers mean they balance each other out.")
                st.plotly_chart(C.correlation_heat(cm, height=min(420, 80 + 38 * len(cm))),
                                width='stretch', config={"displayModeBar": False})
                _left_out = cm.attrs.get("excluded", [])
                if _left_out:
                    st.caption("Left out of this grid (their NAVs don't cover the same recent window, usually a "
                               "discontinued plan or a very young fund): " + ", ".join(_left_out) + ".")
            else:
                st.caption("A correlation grid needs at least two funds with overlapping recent history in this "
                           "window. Some of your picks look stale or too young; try a shorter lookback or swap "
                           "in funds with current NAVs.")

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
                st.download_button("⬇️  Download this memo (HTML · print to PDF from your browser)",
                                   data=RR.render_html(rep), file_name="mfrip_memo.html",
                                   mime="text/html", key=f"dl_{abs(hash(rep.title)) % 10**8}")

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
                st.download_button("⬇️  Download this memo (HTML · print to PDF from your browser)",
                                   data=RR.render_html(rep), file_name="mfrip_memo.html",
                                   mime="text/html", key=f"dl_{abs(hash(rep.title)) % 10**8}")

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
    col = GREEN if score >= 75 else "#f08c00" if score >= 55 else RED
    st.markdown(f"<div style='font-size:13px;color:#8D8677'>PORTFOLIO HEALTH</div>"
                f"<div style='font-family:SF Mono,monospace;font-size:42px;color:{col};line-height:1'>"
                f"{score:.0f}<span style='font-size:18px;color:#8D8677'>/100</span></div>",
                unsafe_allow_html=True)
    items = []
    for k, v in health.parts.items():
        c = GREEN if v >= 75 else "#f08c00" if v >= 50 else RED
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
                    _left_out = cm.attrs.get("excluded", [])
                    if _left_out:
                        st.caption("Left out (no overlapping recent NAVs in this window): "
                                   + ", ".join(_left_out) + ".")
                    for line in PL.correlation_guidance(cm):
                        st.markdown(f"- {line}")
                elif len(picks) >= 2:
                    st.caption("Couldn't compute a correlation grid: your funds don't share enough overlapping "
                               "recent history (often a stale or discontinued plan is the culprit).")

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


# ================================================================= SCREENER
with tab_screener:
    st.subheader("Fund screener · every fund, one comparable table")
    learn("A screener lets you scan many funds at once instead of opening them one at a time. Every fund here is "
          "measured as of the same date so the comparison is fair. 6M and 1Y are the total return over that period; "
          "3Y and 5Y are per-year (annualised). 'vs Cat' is how far the fund's 3-year return sits above or below "
          "the middle fund of its category. Risk (volatility and worst fall) is measured over the same recent "
          "3 years for everyone. The Score is where the fund ranks among its own category peers, 0 to 100, "
          "leaning toward consistency and downside protection rather than chasing last year's winner. "
          "Click any column heading to sort.")
    @st.cache_data(show_spinner=False, ttl=6 * 3600)
    def _screener_table(_key: str) -> pd.DataFrame:
        # cached so that typing in the search box doesn't recompute 500 funds;
        # the key changes when data refreshes, so results are never stale
        return SCR.build_screener(get_conn())

    with st.spinner("Measuring every fund as of a common date..."):
        _scr = _screener_table(f"{_data_to}|{len(codes)}")
    if _scr.empty:
        st.info("No funds with enough NAV history to screen yet. As more funds are added to the database they will "
                "show up here automatically.")
    else:
        _asof = None
        _f1, _f2 = st.columns([2, 1])
        _q = _f1.text_input("Search fund", "", key="scr_q",
                            placeholder="Type part of a fund name...")
        _cats = ["All categories"] + sorted(_scr["Category"].unique())
        _pick = _f2.selectbox("Category", _cats, key="scr_cat")
        _view = _scr
        if _pick != "All categories":
            _view = _view[_view["Category"] == _pick]
        if _q.strip():
            _view = _view[_view["Fund"].str.contains(_q.strip(), case=False, regex=False)]

        _med3 = _view["3Y"].dropna()
        st.markdown(tiles_html([
            ("Funds", f"{len(_view)}", NEUTRAL),
            ("Categories", f"{_view['Category'].nunique()}", NEUTRAL),
            ("Median 3Y return", f"{_med3.median():+.1f}%" if len(_med3) else "—",
             GREEN if len(_med3) and _med3.median() >= 0 else RED if len(_med3) else NEUTRAL),
            ("Scored vs peers", f"{int(_view['Score'].notna().sum())}", NEUTRAL),
        ], cols=4), unsafe_allow_html=True)

        if _view.empty:
            st.caption("Nothing matches that search in this category.")
        else:
            _compact = st.toggle("Compact columns · best on phones", key="scr_compact",
                                 help="Shows just the essentials: fund, 1Y, 3Y, vs category, and Score. "
                                      "Turn off for the full table with risk columns.")
            _show = _view.drop(columns=["_sleeve", "_stale"])
            if _compact:
                _show = _show[[c for c in ["Fund", "1Y", "3Y", "vs Cat", "Score"]
                               if c in _show.columns]]
            st.dataframe(SCR.style_screener(_show), hide_index=True, width='stretch')
            _stale_n = int(_view["_stale"].sum())
            _note = (f" {_stale_n} fund(s) have NAVs more than {SCR.STALE_DAYS} days behind the common date, so "
                     "their period columns are blank rather than compared over a different window."
                     if _stale_n else "")
            st.caption("All returns are measured to the same date. 6M and 1Y are total returns; 3Y and 5Y are "
                       "per-year. Volatility and worst drawdown cover the same trailing 3 years for every fund. "
                       "A blank cell means the fund lacks enough history for that column, never a made-up number."
                       + _note)

        st.markdown("---")
        st.subheader("Leaders & laggards · by 3-year return")
        st.caption(f"The strongest and weakest in each category over three years. Categories with fewer than "
                   f"{SCR.MIN_PEERS} funds are skipped because a handful of funds cannot be ranked meaningfully.")
        _ll = SCR.leaders_laggards(_view if _pick != "All categories" else _scr, by="3Y", n=5)
        if not _ll:
            st.caption("Not enough funds with 3-year history in any category yet to rank leaders and laggards.")
        else:
            for _sl, (_top, _bottom) in _ll.items():
                with st.expander(SCR.SLEEVE_LABEL.get(_sl, _sl.title()), expanded=(_pick != "All categories")):
                    _cols_show = [c for c in ["Fund", "3Y", "vs Cat", "Score"] if c in _top.columns]
                    _l, _r = st.columns(2)
                    _l.markdown("**Leaders**")
                    _l.dataframe(SCR.style_screener(_top[_cols_show]), hide_index=True, width='stretch')
                    _r.markdown("**Laggards**")
                    _r.dataframe(SCR.style_screener(_bottom[_cols_show]), hide_index=True, width='stretch')

        st.markdown("---")
        st.subheader("Shortlist & compare · your final contenders")
        learn("Narrowing down is the whole game. Pick up to four funds from the table above and see them "
              "side by side: same window, same yardsticks, growth of the same rupee.")
        _sl_picks = st.multiselect("Pick up to 4 funds", list(_view["Fund"]),
                                   max_selections=4, key="scr_shortlist",
                                   placeholder="Choose from the screened funds above...")
        if len(_sl_picks) >= 2:
            _sl_rows = _scr[_scr["Fund"].isin(_sl_picks)]
            st.dataframe(SCR.style_screener(_sl_rows.drop(columns=["_sleeve", "_stale"])),
                         hide_index=True, width='stretch')
            _name_to_code = {n: c for c, n in fund_list}
            _sl_navs = {}
            for _nm in _sl_picks:
                _c = _name_to_code.get(_nm)
                if _c:
                    _nv = D.load_nav(conn, _c)
                    if _nv is not None and not _nv.empty:
                        _sl_navs[_nm[:26]] = _nv
            if len(_sl_navs) >= 2:
                _common_start = max(s.dropna().index[0] for s in _sl_navs.values())
                _rebased = {k: (s.loc[_common_start:] / s.loc[_common_start:].iloc[0]) * 100_000
                            for k, s in _sl_navs.items()}
                st.markdown(f"**Growth of ₹1,00,000** · common window from {_common_start.date()}")
                st.plotly_chart(C.growth_chart(_rebased), width='stretch',
                                config={"displayModeBar": False})
            st.caption("Shortlist lives for this browser session only; it resets on refresh. "
                       "For a keeper, save it as a portfolio in the Portfolio Lab.")
        elif _sl_picks:
            st.caption("Pick at least two to compare.")

        st.caption("Fund size (AUM), expense ratio and third-party star ratings are not in the free data source, "
                   "so MFRIP shows its own computed, percentile-based score instead of pretending to have them. "
                   "Past returns are history, not a prediction. Educational, not investment advice.")
