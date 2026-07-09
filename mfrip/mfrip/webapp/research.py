"""Module 4, Research Report Engine.

One content layer that turns either an audited recommendation or a Lab
portfolio into a structured institutional memo (nine sections), plus an HTML
renderer. The Streamlit app renders the same `ResearchReport` natively, so the
in-app and exported versions are guaranteed identical.

Every sentence is templated from a computed number, with no free-form claims.
"""
from __future__ import annotations

import html
import sqlite3
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from ..config import ASSET_PROXIES
from ..recommend import schema
from . import portfolio_lab as PL
from .data import window_stats
from .report import (
    ACCENT, BG, BORDER, GOOD, BAD, GRID, MUTED, PANEL, TEXT,
    DEFAULT_BENCHMARK, _bt_row, _caveats, _exec_summary, _key_insights,
    _months_between, _plan_series, _verdict,
)


# --------------------------------------------------------------- data model
@dataclass
class Section:
    title: str
    paragraphs: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)


@dataclass
class ResearchReport:
    title: str
    subtitle: str
    as_of: str
    kpis: list[tuple[str, str, str]]      # (label, value, colour)
    sections: list[Section]


def _pct(x):
    return "—" if x is None or (isinstance(x, float) and x != x) else f"{x:+.1%}"


def _pct0(x):
    return "—" if x is None or (isinstance(x, float) and x != x) else f"{x:.0%}"


def _num(x):
    return "—" if x is None or (isinstance(x, float) and x != x) else f"{x:.2f}"


def _col(x):
    return GOOD if (x or 0) >= 0 else BAD


# --------------------------------------------------- recommendation report
def recommendation_report(conn, rec_id, benchmark=DEFAULT_BENCHMARK, proxies=ASSET_PROXIES):
    rec = schema.load_recommendation(conn, int(rec_id))
    d = _plan_series(conn, rec, benchmark, proxies)
    if d is None:
        return None
    d["audit"]._tier = rec.risk_profile
    a, fwd, bt = d["audit"], d["fwd"], d["backtest"]
    mo = _months_between(a.start_date, a.as_of)
    vb, vp = a.excess_vs_benchmark, a.excess_vs_blended
    alloc = (vb - vp) if (vb is not None and vp is not None) else None
    b3, b5 = _bt_row(bt, "3Y"), _bt_row(bt, "5Y")

    sections = [
        Section("Executive Summary", [_exec_summary(d)]),
        Section("Key Findings", bullets=_key_insights(d)),
        Section("Performance Overview", [
            f"The plan grew ₹{a.invested:,.0f} to ₹{a.recommended_value_now:,.0f} "
            f"({_pct(a.recommended_returns['latest'])}) over ~{mo:.0f} months. Its own "
            f"equal-weight twin returned {_pct(a.equal_weight_returns['latest'])}, so the "
            f"advisor's specific weighting "
            + ("added value." if a.weighting_added else "did not add value.")
        ] + ([
            f"Run historically, the same allocation returned {_pct(b3.plan_return)} over 3 years"
            + (f" and {_pct(b5.plan_return)} over 5 years" if b5 else "") + "."
        ] if b3 else [])),
        Section("Risk Overview", [
            f"Over the forward window the plan showed {_pct0(fwd.volatility)} annualised "
            f"volatility, a Sharpe of {_num(fwd.sharpe)}, and a maximum drawdown of "
            f"{_pct(fwd.max_drawdown)}."
        ] + ([
            f"Across the 3-year backtest, Sharpe was {_num(b3.plan_sharpe)} with a "
            f"{_pct(b3.plan_maxdd)} maximum drawdown."
        ] if b3 else [])),
        Section("Benchmark Analysis", [
            f"Against the Nifty 50 ({_pct(a.benchmark_returns['latest'])} over the window), "
            f"the plan's excess was {_pct(vb)}. But against a passive twin of the *same "
            f"allocation* built from index funds, the excess was {_pct(vp)}, the fairer "
            f"measure of fund-selection skill."
        ]),
        Section("Portfolio Attribution", [
            (f"Decomposing the {_pct(vb)} beat over the Nifty: roughly {_pct(alloc)} came "
             f"from asset allocation (holding debt/gold in a falling market) and {_pct(vp)} "
             f"from fund selection versus a passive version of the plan."
             if alloc is not None else
             "Attribution versus the passive twin is unavailable for this plan.")
        ] + [
            "Note: the selection figure still blends genuine stock-picking with a deliberate "
            "mid/small-cap tilt; isolating pure selection would need category-matched benchmarks."
        ]),
        Section("Limitations", bullets=_caveats(d)),
        Section("Final Verdict", [_verdict(d)]),
        Section("Investment Takeaways", bullets=[
            "In a falling market, it was the asset mix, not stock-picking, that drove most of the "
            "headline outperformance versus the index.",
            (f"Over multiple years the allocation showed a {_pct(b3.excess_vs_passive)} edge "
             f"over a broad passive twin, suggesting some durable value beyond the recent window."
             if b3 and b3.excess_vs_passive is not None else
             "A multi-year read is limited by available fund history."),
            "Judge advisor plans on fair, allocation-matched benchmarks over full cycles, "
            "not on raw index-beating in a single down market.",
        ]),
    ]
    kpis = [
        ("Return", _pct(a.recommended_returns["latest"]), _col(a.recommended_returns["latest"])),
        ("vs Nifty", _pct(vb), _col(vb)),
        ("vs Passive", _pct(vp), _col(vp)),
        ("Sharpe", _num(fwd.sharpe), TEXT),
        ("Max DD", _pct(fwd.max_drawdown), BAD),
    ]
    return ResearchReport(
        title=f"{a.advisor} · {rec.risk_profile}",
        subtitle=f"Recommendation audit · rec date {a.start_date} · benchmark Nifty 50",
        as_of=a.as_of, kpis=kpis, sections=sections,
    )


# ------------------------------------------------------- portfolio report
def _avg_offdiag(corr: pd.DataFrame):
    if corr is None or len(corr) < 2:
        return None
    vals = [corr.iat[i, j] for i in range(len(corr)) for j in range(len(corr)) if i < j]
    return sum(vals) / len(vals) if vals else None


def portfolio_report(conn, name, holdings, lookback, period_label, benchmark_code,
                     name_by_code, bench_name="benchmark"):
    res = PL.analyze(conn, holdings, lookback, benchmark_code)
    if res is None:
        return None
    s = res["stats"]
    codes = [c for c, _ in holdings]
    corr = PL.correlation_matrix(conn, codes, name_by_code, lookback)
    avg_corr = _avg_offdiag(corr)
    tot_w = sum(w for _, w in holdings) or 1.0
    weights = {c: w / tot_w for c, w in holdings}
    top_code = max(weights, key=weights.get)

    sections = [
        Section("Executive Summary", [
            f"{name} blends {res['n_funds']} fund(s). Over the {period_label.lower()} window it "
            f"turned ₹1,00,000 into ₹{res['growth'].iloc[-1]:,.0f} ({_pct(s.total_return)}), "
            f"compounding at {_pct(s.cagr)} a year. Versus {bench_name}, it produced "
            f"{_pct(res['alpha'])} annual alpha at a beta of {_num(res['beta'])}."
        ]),
        Section("Key Findings", bullets=[
            f"Risk-adjusted return: Sharpe {_num(s.sharpe)}, Sortino {_num(s.sortino)}.",
            f"Worst peak-to-trough loss was {_pct(s.max_drawdown)} (Calmar {_num(res['calmar'])}).",
            (f"Holdings are {'well diversified' if (avg_corr or 0) < 0.5 else 'fairly correlated'} "
             f", with average pairwise correlation {_num(avg_corr)}." if avg_corr is not None
             else "Correlation needs at least two funds with overlapping history."),
            f"Largest single position: {name_by_code.get(top_code, top_code)[:40]} at "
            f"{_pct0(weights[top_code])}.",
        ]),
        Section("Performance Overview", [
            f"Total return {_pct(s.total_return)} over the window; CAGR {_pct(s.cagr)}. "
            f"₹1,00,000 became ₹{res['growth'].iloc[-1]:,.0f}."
        ]),
        Section("Risk Overview", [
            f"Annualised volatility {_pct0(s.volatility)}, Sharpe {_num(s.sharpe)}, "
            f"Sortino {_num(s.sortino)}, maximum drawdown {_pct(s.max_drawdown)}, "
            f"Calmar {_num(res['calmar'])}."
        ]),
        Section("Benchmark Analysis", [
            f"Against {bench_name}, beta is {_num(res['beta'])} and annualised alpha is "
            f"{_pct(res['alpha'])}. "
            + ("Positive alpha means the portfolio beat what its market exposure alone would predict."
               if (res['alpha'] or 0) >= 0 else
               "Negative alpha means the portfolio lagged what its market exposure alone would predict.")
        ]),
        Section("Portfolio Attribution", [
            (f"Diversification: the holdings' average pairwise correlation is {_num(avg_corr)}; "
             f"lower means each fund contributes more independent risk." if avg_corr is not None
             else "Add at least two funds with overlapping history to attribute diversification."),
            f"Concentration: the largest position is {_pct0(weights[top_code])} of the portfolio."
        ]),
        Section("Limitations", bullets=[
            f"Measured over a single {period_label.lower()} window, not a full market cycle.",
            "Alpha/beta depend on the chosen benchmark; a large-cap index flatters mid/small-cap "
            "portfolios. Use a broad index (Nifty 500) for cap-diverse holdings.",
            "Returns are gross of transaction costs, exit loads, and taxes.",
            "Funds without history covering the window are excluded; survivorship is not corrected."
            + (f" {_pct0(res['excluded'])} of weight was un-priceable and excluded."
               if res["excluded"] > 0 else ""),
        ]),
        Section("Final Verdict", [
            (f"{name} delivered "
             + ("strong" if s.sharpe >= 1 else "moderate" if s.sharpe >= 0.5 else "weak")
             + f" risk-adjusted performance (Sharpe {_num(s.sharpe)}) over this window, with "
             + ("positive" if (res['alpha'] or 0) >= 0 else "negative")
             + f" alpha of {_pct(res['alpha'])}. Read this as one window's evidence, not a "
               "full-cycle verdict.")
        ]),
        Section("Investment Takeaways", bullets=[
            "Compare portfolios on risk-adjusted terms (Sharpe/Sortino), not raw return alone.",
            "Diversification across low-correlation funds reduces drawdown without proportionally "
            "sacrificing return.",
            "Re-run across multiple windows before trusting an edge. One period can mislead.",
        ]),
    ]
    kpis = [
        ("CAGR", _pct(s.cagr), _col(s.cagr)),
        ("Sharpe", _num(s.sharpe), TEXT),
        ("Max DD", _pct(s.max_drawdown), BAD),
        ("Alpha", _pct(res["alpha"]), _col(res["alpha"])),
        ("Beta", _num(res["beta"]), TEXT),
    ]
    return ResearchReport(
        title=name,
        subtitle=f"Portfolio research · {period_label} · vs {bench_name}",
        as_of=str(res["growth"].index[-1].date()),
        kpis=kpis, sections=sections,
    )


# --------------------------------------------------------------- HTML render
def render_html(r: ResearchReport) -> str:
    kpi_html = "".join(
        f'<div style="background:{PANEL};border:1px solid {BORDER};border-radius:3px;padding:10px 13px">'
        f'<div style="color:{MUTED};font-size:10px;text-transform:uppercase;letter-spacing:.07em">{html.escape(lab)}</div>'
        f'<div style="font-family:\'SF Mono\',Consolas,monospace;font-size:22px;color:{col}">{html.escape(val)}</div></div>'
        for lab, val, col in r.kpis
    )
    secs = ""
    for s in r.sections:
        paras = "".join(f"<p>{html.escape(p)}</p>" for p in s.paragraphs)
        buls = ("<ul>" + "".join(f"<li>{html.escape(b)}</li>" for b in s.bullets) + "</ul>") if s.bullets else ""
        secs += f'<section class="sec"><h2>{html.escape(s.title)}</h2>{paras}{buls}</section>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(r.title)} · Research</title><style>
  *{{box-sizing:border-box}} body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;
   color:{TEXT};background:{BG};margin:0;line-height:1.55;border-top:2px solid {ACCENT}}}
  .wrap{{max-width:880px;margin:0 auto;padding:0 20px 64px}}
  header{{border-bottom:1px solid {BORDER};padding:18px 0 12px;margin-bottom:6px}}
  .tag{{background:{ACCENT};color:{BG};font-weight:700;font-size:11px;letter-spacing:.16em;padding:3px 8px;border-radius:2px}}
  h1{{color:{TEXT};font-size:21px;margin:10px 0 2px}} .sub{{color:{MUTED};font-size:12px;font-family:monospace}}
  .kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:16px 0 6px}}
  .sec{{background:{PANEL};border:1px solid {BORDER};border-radius:4px;padding:4px 18px 12px;margin:12px 0}}
  h2{{color:{ACCENT};font-size:12px;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid {ACCENT}33;padding-bottom:6px}}
  p{{font-size:14px}} ul{{font-size:13.5px;padding-left:18px}} li{{margin:5px 0}}
  @media(max-width:640px){{.kpis{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><div class="wrap">
  <header><span class="tag">MFRIP</span><h1>{html.escape(r.title)}</h1>
  <div class="sub">{html.escape(r.subtitle)} · as of {r.as_of} · generated {date.today().isoformat()}</div></header>
  <div class="kpis">{kpi_html}</div>{secs}
  <p style="color:{MUTED};font-size:11px;margin-top:18px">Direct-Growth, point-in-time NAVs, no lookahead.
  Every figure is reproducible from the analytics engine. This is research, not investment advice.</p>
</div></body></html>"""
