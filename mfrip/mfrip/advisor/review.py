"""Portfolio review, the investor brings their OWN portfolio.

Flow: enter your funds -> we judge whether it suits you and how healthy it is ->
we recommend specific fixes. Everything is computed from the actual holdings,
so the verdict is dynamic, not scripted.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from ..config import DEFAULT_CONFIG, Config
from ..webapp import data as D
from .allocation import target_allocation
from .categorize import infer_sleeve
from .constraints import evaluate_constraints
from .profile import InvestorProfile, assess_risk
from .ranking import rank_sleeve
from .recommend import HealthScore, validate_portfolio, _SLEEVE_LABEL


@dataclass
class GapAction:
    sleeve: str
    target: float
    actual: float
    action: str          # "add" | "trim" | "ok"
    detail: str
    suggested_fund: tuple[int, str] | None = None


@dataclass
class SwitchIdea:
    held_code: int
    held_name: str
    sleeve: str
    better_code: int
    better_name: str
    reason: str


@dataclass
class PortfolioReview:
    risk_bucket: str
    risk_score: float
    health: HealthScore | None
    stats: object | None
    actual_allocation: dict[str, float]
    target_allocation: dict[str, float]
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    gaps: list[GapAction] = field(default_factory=list)
    switches: list[SwitchIdea] = field(default_factory=list)
    overlaps: list[str] = field(default_factory=list)
    uncategorized: list[str] = field(default_factory=list)


def review_portfolio(conn: sqlite3.Connection, profile: InvestorProfile,
                     holdings: list[tuple[int, float]], name_by_code: dict[int, str],
                     config: Config = DEFAULT_CONFIG, benchmark_code: int = 120716) -> PortfolioReview:
    """holdings: [(code, weight)] (any positive scale; normalised internally)."""
    ra = assess_risk(profile)
    cons = evaluate_constraints(profile)
    target = target_allocation(ra, cons)

    tot = sum(w for _, w in holdings) or 1.0
    frac = [(c, w / tot) for c, w in holdings]

    # actual allocation by sleeve
    actual: dict[str, float] = {}
    uncategorized: list[str] = []
    sleeve_of: dict[int, str] = {}
    for c, w in frac:
        s = infer_sleeve(name_by_code.get(c, str(c)))
        if s is None:
            uncategorized.append(name_by_code.get(c, str(c)))
            continue
        sleeve_of[c] = s
        actual[s] = actual.get(s, 0.0) + w

    stats, health, overlaps, corr = validate_portfolio(
        conn, frac, name_by_code, ra.bucket, cons.has_blockers, config, benchmark_code)

    # strengths / weaknesses, all from computed numbers
    strengths, weaknesses = [], []
    maxw = max((w for _, w in frac), default=0)
    n = len(frac)
    if health:
        p = health.parts
        if p["Diversification"] >= 70:
            strengths.append(f"Well diversified (diversification score {p['Diversification']:.0f}/100), "
                             f"your funds don't all move together.")
        else:
            weaknesses.append(f"Limited diversification ({p['Diversification']:.0f}/100), your funds "
                              f"move quite similarly, so they cushion each other less.")
        if p["Risk match"] >= 75:
            strengths.append(f"Risk level fits your {ra.bucket.lower()} profile (risk-match {p['Risk match']:.0f}/100).")
        else:
            weaknesses.append(f"Risk level is off for a {ra.bucket.lower()} profile "
                              f"(risk-match {p['Risk match']:.0f}/100), see the allocation gaps below.")
        if p["Downside protection"] < 60 and stats:
            weaknesses.append(f"Deep drawdowns: the worst fall was {stats.max_drawdown:.0%}.")
        elif stats:
            strengths.append(f"Controlled drawdowns (worst fall {stats.max_drawdown:.0%}).")
    if maxw > 0.45:
        weaknesses.append(f"Concentrated: your largest fund is {maxw:.0%} of the portfolio; "
                          f"a single fund carrying that much adds risk.")
    if n == 1:
        weaknesses.append("Single-fund portfolio, so there's no diversification across funds at all.")
    elif n > 12:
        weaknesses.append(f"{n} funds is a lot. Beyond about 8 you mostly add overlap, not diversification.")
    if stats and stats.sharpe >= 1.0:
        strengths.append(f"Strong risk-adjusted return so far (Sharpe {stats.sharpe:.2f}).")

    # gap analysis vs target allocation
    gaps: list[GapAction] = []
    sleeves = set(target.weights) | set(actual)
    for s in sorted(sleeves, key=lambda x: -target.weights.get(x, 0)):
        tw = target.weights.get(s, 0.0)
        aw = actual.get(s, 0.0)
        diff = aw - tw
        if diff > 0.08:
            gaps.append(GapAction(s, tw, aw, "trim",
                f"You hold {aw:.0%} in {_SLEEVE_LABEL.get(s, s)} vs a target of {tw:.0%}. That's overweight, so consider trimming."))
        elif diff < -0.08:
            # suggest the best cached fund to fill the underweight sleeve
            sugg = None
            pool = {c: nm for c, nm in D.available_funds(conn) if infer_sleeve(nm) == s}
            if pool:
                series = {c: D.load_nav(conn, c) for c in pool}
                ranked = rank_sleeve(pool, series, config)
                if ranked:
                    sugg = (ranked[0].code, ranked[0].name)
            gaps.append(GapAction(s, tw, aw, "add",
                f"You hold {aw:.0%} in {_SLEEVE_LABEL.get(s, s)} vs a target of {tw:.0%}. That's underweight, so consider adding.",
                suggested_fund=sugg))
        else:
            gaps.append(GapAction(s, tw, aw, "ok",
                f"{_SLEEVE_LABEL.get(s, s)} is roughly on target ({aw:.0%} vs {tw:.0%})."))

    # switch ideas: is a held fund clearly beaten by a cached alternative in its sleeve?
    switches: list[SwitchIdea] = []
    for c, s in sleeve_of.items():
        pool = {cc: nm for cc, nm in D.available_funds(conn) if infer_sleeve(nm) == s}
        if len(pool) < 2 or c not in pool:
            continue
        series = {cc: D.load_nav(conn, cc) for cc in pool}
        ranked = rank_sleeve(pool, series, config)
        order = {fs.code: i for i, fs in enumerate(ranked)}
        if c in order and ranked:
            top = ranked[0]
            held_rank = order[c]
            held_score = next((fs.composite for fs in ranked if fs.code == c), None)
            if top.code != c and held_rank >= 1 and held_score is not None and (top.composite - held_score) >= 20:
                switches.append(SwitchIdea(
                    held_code=c, held_name=name_by_code.get(c, str(c)), sleeve=s,
                    better_code=top.code, better_name=top.name,
                    reason=f"In {_SLEEVE_LABEL.get(s, s)}, {top.name.split(' - ')[0]} scores "
                           f"{top.composite:.0f} vs your {held_score:.0f} on consistency and downside control."))

    return PortfolioReview(
        risk_bucket=ra.bucket, risk_score=ra.score, health=health, stats=stats,
        actual_allocation=actual, target_allocation=target.weights,
        strengths=strengths, weaknesses=weaknesses, gaps=gaps, switches=switches,
        overlaps=overlaps, uncategorized=uncategorized,
    )
