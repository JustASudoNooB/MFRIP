"""Layers 5 & 6, Construction, Validation, Explainability.

Assembles top-ranked funds into the target allocation, runs the result through
the existing analytics engine, checks fund-to-fund overlap (via return
correlation, our honest proxy for holdings overlap), and produces a Portfolio
Health Score (0-100) plus per-pick "why this fund" reasoning.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import pandas as pd

from ..config import DEFAULT_CONFIG, Config
from ..webapp import data as D
from ..webapp import portfolio_lab as PL
from .allocation import Allocation, target_allocation
from .categorize import infer_sleeve
from .constraints import ConstraintReport, evaluate_constraints
from .profile import InvestorProfile, RiskAssessment, assess_risk, assessment_reasons
from .ranking import FundScore, rank_sleeve

_SLEEVE_LABEL = {
    "largecap": "Large Cap", "flexicap": "Flexi / Multi Cap", "midcap": "Mid Cap",
    "smallcap": "Small Cap", "international": "International", "debt": "Debt", "gold": "Gold",
}


@dataclass
class Pick:
    sleeve: str
    code: int
    name: str
    weight: float
    confidence: float
    composite: float
    why: list[str]
    consistency_factor: float = 0.5
    alternatives: list[tuple[int, str, float]] = field(default_factory=list)


@dataclass
class HealthScore:
    overall: float
    parts: dict[str, float]


@dataclass
class Recommendation:
    risk: RiskAssessment
    risk_reasons: list[str]
    constraints: ConstraintReport
    allocation: Allocation
    picks: list[Pick]
    gaps: list[str]
    portfolio_stats: object | None
    health: HealthScore | None
    overlaps: list[str]
    confidence: float


def _why(fs: FundScore, bucket: str, horizon: float, best_cons: bool, best_dd: bool) -> list[str]:
    f = fs.factors
    w = []
    if best_cons or f["consistency"] >= 0.7:
        w.append(f"Consistent: positive in {f['consistency']:.0%} of rolling 1-year periods over {fs.years:.0f}y.")
    if best_dd or f["max_drawdown"] >= -0.25:
        w.append(f"Held up when markets fell: worst drawdown {f['max_drawdown']:.0%}.")
    if f["sharpe"] >= 0.8:
        w.append(f"Strong risk-adjusted return (Sortino {f['sortino']:.2f}, Sharpe {f['sharpe']:.2f}).")
    else:
        w.append(f"Risk-adjusted return: Sortino {f['sortino']:.2f}, Sharpe {f['sharpe']:.2f}.")
    w.append(f"Fits a {bucket} profile and ~{horizon:.0f}-year horizon.")
    return w[:4]


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def _risk_match(bucket, vol, has_blockers):
    if vol is None:
        return 70.0
    lo, hi = {"Conservative": (0.0, 0.11), "Moderate": (0.09, 0.17),
              "Aggressive": (0.14, 0.32)}[bucket]
    pen = (lo - vol) * 300 if vol < lo else (vol - hi) * 300 if vol > hi else 0
    return _clamp(100 - pen - (20 if has_blockers else 0))


def _avg_offdiag(corr):
    if corr is None or len(corr) < 2:
        return None
    vals = [corr.iat[i, j] for i in range(len(corr)) for j in range(len(corr)) if i < j]
    return sum(vals) / len(vals) if vals else None


def validate_portfolio(conn, holdings_frac, name_by_code, bucket, has_blockers,
                       config: Config = DEFAULT_CONFIG, benchmark_code: int = 120716):
    """Run a portfolio (list of (code, weight_fraction)) through the analytics
    engine and compute overlaps + a Portfolio Health Score. Used by both the
    recommender and the portfolio reviewer so they score identically."""
    from .ranking import _rolling_consistency
    codes = [c for c, _ in holdings_frac]
    res = PL.analyze(conn, [(c, w * 100) for c, w in holdings_frac], 5.0, benchmark_code)
    stats = res["stats"] if res else None
    corr = PL.correlation_matrix(conn, codes, name_by_code, 5.0)

    overlaps = []
    if corr is not None:
        for i in range(len(corr)):
            for j in range(i + 1, len(corr)):
                if corr.iat[i, j] >= 0.85:
                    overlaps.append(f"{corr.index[i]} and {corr.columns[j]} are highly correlated "
                                    f"({corr.iat[i, j]:.2f}), so they likely hold a lot of the same stocks.")

    avg_corr = _avg_offdiag(corr)
    div = _clamp(100 * (1 - avg_corr)) if avg_corr is not None else 60.0
    cons_vals = []
    for c in codes:
        cv = _rolling_consistency(D.load_nav(conn, c).dropna(), 5.0)
        if cv is not None:
            cons_vals.append(cv)
    consistency = _clamp(100 * sum(cons_vals) / len(cons_vals)) if cons_vals else 60.0
    maxw = max((w for _, w in holdings_frac), default=1.0)
    concentration = _clamp(100 * (1 - max(0, maxw - 0.35) / 0.5))
    mdd = stats.max_drawdown if stats else None
    downside = _clamp(100 * (1 - abs(mdd) / 0.5)) if mdd is not None else 60.0
    rmatch = _risk_match(bucket, stats.volatility if stats else None, has_blockers)
    parts = {
        "Diversification": round(div, 0), "Risk match": round(rmatch, 0),
        "Consistency": round(consistency, 0), "Downside protection": round(downside, 0),
        "Concentration": round(concentration, 0), "Liquidity": 100.0,
    }
    overall = (0.22 * div + 0.20 * rmatch + 0.18 * consistency +
               0.20 * downside + 0.13 * concentration + 0.07 * 100.0)
    return stats, HealthScore(overall=round(overall, 0), parts=parts), overlaps, corr


def recommend(conn: sqlite3.Connection, profile: InvestorProfile,
              config: Config = DEFAULT_CONFIG, benchmark_code: int = 120716) -> Recommendation:
    ra = assess_risk(profile)
    reasons = assessment_reasons(profile, ra)
    cons = evaluate_constraints(profile)
    alloc = target_allocation(ra, cons)

    # build candidate universe from cached funds, grouped by sleeve
    universe = D.available_funds(conn)
    by_sleeve: dict[str, dict[int, str]] = {}
    for code, name in universe:
        s = infer_sleeve(name)
        if s:
            by_sleeve.setdefault(s, {})[code] = name

    picks: list[Pick] = []
    gaps: list[str] = []
    for sleeve, weight in sorted(alloc.weights.items(), key=lambda kv: -kv[1]):
        cands = by_sleeve.get(sleeve, {})
        if not cands:
            gaps.append(_SLEEVE_LABEL.get(sleeve, sleeve))
            continue
        series = {c: D.load_nav(conn, c) for c in cands}
        ranked = rank_sleeve(cands, series, config)
        if not ranked:
            gaps.append(_SLEEVE_LABEL.get(sleeve, sleeve))
            continue
        top = ranked[0]
        best_cons = top.factors["consistency"] == max(r.factors["consistency"] for r in ranked)
        best_dd = top.factors["max_drawdown"] == max(r.factors["max_drawdown"] for r in ranked)
        picks.append(Pick(
            sleeve=sleeve, code=top.code, name=top.name, weight=weight,
            confidence=top.confidence, composite=top.composite,
            why=_why(top, ra.bucket, profile.horizon_years, best_cons, best_dd),
            consistency_factor=top.factors["consistency"],
            alternatives=[(r.code, r.name, r.composite) for r in ranked[1:3]],
        ))

    # renormalise pick weights (gaps may have dropped some)
    tot = sum(p.weight for p in picks) or 1.0
    for p in picks:
        p.weight = round(p.weight / tot, 4)

    # validate through the analytics engine
    stats = health = corr = None
    overlaps = []
    if picks:
        holdings_frac = [(p.code, p.weight) for p in picks]
        name_by = {p.code: p.name for p in picks}
        stats, health, overlaps, corr = validate_portfolio(
            conn, holdings_frac, name_by, ra.bucket, cons.has_blockers, config, benchmark_code)

    confidence = (sum(p.confidence for p in picks) / len(picks)) if picks else 0.0
    if gaps:
        confidence *= 0.85
    return Recommendation(
        risk=ra, risk_reasons=reasons, constraints=cons, allocation=alloc,
        picks=picks, gaps=gaps, portfolio_stats=stats, health=health,
        overlaps=overlaps or [], confidence=round(confidence, 0),
    )


def format_text(rec: Recommendation) -> str:
    """Plain-text rendering of a recommendation for the CLI."""
    ra = rec.risk
    L = ["=" * 62, "MFRIP INVESTOR SUITABILITY RECOMMENDATION", "=" * 62]
    L.append(f"Risk profile: {ra.bucket}  (score {ra.score}/100, capacity {ra.capacity}, "
             f"tolerance {ra.tolerance}, bound by {ra.binding})")
    for r in rec.risk_reasons:
        L.append("  - " + r)
    if rec.constraints.blockers:
        L.append("\n[!] DO THESE FIRST (before investing in equity):")
        for b in rec.constraints.blockers:
            L.append(f"   * {b.title}: {b.detail}")
    L.append("\nTARGET ALLOCATION")
    for s, w in sorted(rec.allocation.weights.items(), key=lambda kv: -kv[1]):
        L.append(f"   {_SLEEVE_LABEL.get(s, s):<18} {w:6.1%}")
    for n in rec.allocation.notes:
        L.append("   (" + n + ")")
    L.append("\nRECOMMENDED FUNDS")
    if not rec.picks:
        L.append("   (No cached funds match these sleeves, so search or fetch some in the app.)")
    for p in rec.picks:
        L.append(f"\n   [{_SLEEVE_LABEL.get(p.sleeve, p.sleeve)}]  {p.weight:.0%}  ->  {p.name}")
        L.append(f"       score {p.composite}/100 in category · confidence {p.confidence:.0f}%")
        for w in p.why:
            L.append("        - " + w)
        if p.alternatives:
            L.append("        alternatives: " + "; ".join(f"{n} ({c})" for _, n, c in p.alternatives))
    if rec.gaps:
        L.append("\n   [!] No cached fund for: " + ", ".join(rec.gaps) + ".")
    if rec.overlaps:
        L.append("\nOVERLAP CHECK")
        for o in rec.overlaps:
            L.append("   [!] " + o)
    if rec.portfolio_stats:
        s = rec.portfolio_stats
        L.append("\nVALIDATION (assembled portfolio, up to 5y)")
        L.append(f"   CAGR {s.cagr:+.1%} · vol {s.volatility:.0%} · Sharpe {s.sharpe:.2f} · "
                 f"Sortino {s.sortino:.2f} · max drawdown {s.max_drawdown:.0%}")
    if rec.health:
        L.append(f"\nPORTFOLIO HEALTH: {rec.health.overall:.0f}/100")
        for k, v in rec.health.parts.items():
            bar = "#" * int(v / 10)
            L.append(f"   {k:<22} {v:3.0f}  {bar}")
    L.append(f"\nRecommendation confidence: {rec.confidence:.0f}%")
    L.append("\nEducational tool, not investment advice. "
             "Past performance does not predict future returns.")
    return "\n".join(L)
