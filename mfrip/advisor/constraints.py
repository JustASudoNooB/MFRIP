"""Layer 2, Constraints Engine.

Before any fund is chosen, enforce the rules a good adviser would. This is the
layer most retail tools skip, and it's what stops the engine from recommending
equity to someone with no emergency fund or piling more mid-cap onto a portfolio
already concentrated in it.

Outputs structured effects (equity cap, sleeves to avoid) that Layer 3
(allocation) consumes, plus human-readable constraints and pre-investment
blockers.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .profile import DebtLoad, EmergencyFund, Goal, InvestorProfile


@dataclass
class Constraint:
    severity: str   # "blocker" | "cap" | "advice" | "info"
    title: str
    detail: str


@dataclass
class ConstraintReport:
    constraints: list[Constraint]
    max_equity: float                       # 0..1 hard ceiling on equity
    avoid_sleeves: set[str] = field(default_factory=set)
    existing_by_sleeve: dict[str, float] = field(default_factory=dict)
    blockers: list[Constraint] = field(default_factory=list)

    @property
    def has_blockers(self) -> bool:
        return bool(self.blockers)


def _horizon_equity_cap(years: float) -> float:
    if years < 1:
        return 0.10
    if years < 2:
        return 0.20
    if years < 3:
        return 0.35
    if years < 5:
        return 0.60
    if years < 7:
        return 0.80
    return 1.00


def evaluate_constraints(p: InvestorProfile) -> ConstraintReport:
    cons: list[Constraint] = []
    blockers: list[Constraint] = []
    avoid: set[str] = set()
    caps: list[float] = [1.0]

    # 1) horizon caps equity
    hc = _horizon_equity_cap(p.horizon_years)
    caps.append(hc)
    if hc < 1.0:
        cons.append(Constraint(
            "cap", "Horizon limits equity",
            f"With a {p.horizon_years:.0f}-year horizon, equity is capped at {hc:.0%} so a market "
            f"fall doesn't catch you needing the money at the wrong time."))

    # 2) emergency fund is a pre-investment blocker
    if p.emergency_fund in (EmergencyFund.NONE, EmergencyFund.UPTO_3M):
        c = Constraint(
            "blocker", "Build an emergency fund first",
            "You have under 3 months of expenses set aside. Before investing in volatile assets, "
            "park 6 months of expenses in a liquid fund or savings account. That's your safety net.")
        cons.append(c)
        blockers.append(c)
        caps.append(0.30)

    # 3) high-interest debt is a pre-investment blocker
    if p.debt == DebtLoad.HIGH:
        c = Constraint(
            "blocker", "Clear high-interest debt first",
            "High-interest debt (credit cards, personal loans) usually costs more than funds earn. "
            "Paying it off is a guaranteed, risk-free return, so prioritise it before equity.")
        cons.append(c)
        blockers.append(c)
        caps.append(0.40)
    elif p.debt == DebtLoad.MODERATE:
        cons.append(Constraint(
            "advice", "Keep equity measured while in debt",
            "You carry moderate debt; a more measured equity allocation is prudent until it eases."))

    # 4) existing concentration → avoid stacking the same sleeve
    by_sleeve: dict[str, float] = {}
    for h in p.existing_holdings:
        by_sleeve[h.sleeve] = by_sleeve.get(h.sleeve, 0.0) + h.weight
    for sleeve, w in by_sleeve.items():
        if w >= 0.5 and sleeve in ("midcap", "smallcap", "international"):
            avoid.add(sleeve)
            cons.append(Constraint(
                "cap", f"Already concentrated in {sleeve}",
                f"Your existing portfolio is {w:.0%} {sleeve}. New picks will skip {sleeve} to cut "
                f"concentration risk."))
        elif w >= 0.6:
            cons.append(Constraint(
                "advice", f"High existing {sleeve} weight",
                f"You already hold {w:.0%} in {sleeve}; new picks will lean elsewhere to diversify."))

    # 5) savings-rate nudge
    if p.monthly_income and p.monthly_savings is not None and p.monthly_income > 0:
        rate = p.monthly_savings / p.monthly_income
        if rate < 0.10:
            cons.append(Constraint(
                "advice", "Low savings rate",
                f"You're saving about {rate:.0%} of income. Small increases compound a lot over "
                f"{p.horizon_years:.0f} years."))

    # 6) goal/horizon sanity
    if Goal.RETIREMENT in p.goals and p.horizon_years < 5:
        cons.append(Constraint(
            "info", "Short horizon tagged to retirement",
            "Retirement is set with a short horizon. If it's actually further off, raise the horizon "
            "for a more growth-oriented mix."))

    return ConstraintReport(
        constraints=cons, max_equity=min(caps), avoid_sleeves=avoid,
        existing_by_sleeve=by_sleeve, blockers=blockers,
    )
