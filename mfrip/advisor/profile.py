"""Layer 1, Investor Profile and risk assessment.

The engine begins with the investor, not the funds. This module captures a rich
profile and turns it into a transparent risk score.

Design choice: the headline risk score is the *minimum* of risk CAPACITY (ability
to take risk: horizon, age, job stability, emergency fund, debt) and risk
TOLERANCE (willingness: behavioural reaction, experience). You should take no
more risk than the lesser of your ability and your willingness. Both sub-scores
and every component are exposed for explainability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Employment(str, Enum):
    SALARIED_STABLE = "salaried_stable"        # govt / PSU / tenured
    SALARIED_PRIVATE = "salaried_private"
    SELF_EMPLOYED = "self_employed"
    BUSINESS = "business_owner"
    RETIRED = "retired"
    STUDENT = "student"
    UNEMPLOYED = "between_jobs"


class Goal(str, Enum):
    RETIREMENT = "retirement"
    HOUSE = "house"
    WEDDING = "wedding"
    EDUCATION = "education"
    PASSIVE_INCOME = "passive_income"
    WEALTH = "wealth_creation"
    EMERGENCY = "emergency_corpus"


class DrawdownReaction(str, Enum):
    """If a 10L portfolio fell to 7L, what would you do?"""
    SELL_ALL = "sell_everything"
    WAIT = "hold_and_wait"
    INVEST_MORE = "invest_more"
    INCREASE_SIP = "increase_sip"


class Experience(str, Enum):
    NONE = "none"
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    EXPERIENCED = "experienced"


class EmergencyFund(str, Enum):
    NONE = "none"
    UPTO_3M = "up_to_3_months"
    THREE_TO_6M = "three_to_six_months"
    SIX_PLUS = "six_months_plus"


class DebtLoad(str, Enum):
    NONE = "none"
    LOW = "low"                # low-interest, manageable (e.g. home loan)
    MODERATE = "moderate"
    HIGH = "high_interest"     # credit cards / personal loans


# canonical equity sleeves used across the advisor
SLEEVES = ["largecap", "flexicap", "midcap", "smallcap", "international", "debt", "gold"]


@dataclass
class ExistingHolding:
    sleeve: str            # one of SLEEVES
    weight: float          # fraction (0..1) of the investor's existing portfolio


@dataclass
class InvestorProfile:
    # demographics
    age: int = 30
    country: str = "India"
    employment: Employment = Employment.SALARIED_PRIVATE
    monthly_income: float | None = None
    monthly_savings: float | None = None
    tax_bracket: float | None = None        # marginal rate e.g. 0.30
    # financial behaviour
    emergency_fund: EmergencyFund = EmergencyFund.NONE
    debt: DebtLoad = DebtLoad.NONE
    existing_holdings: list[ExistingHolding] = field(default_factory=list)
    # goals & horizon
    goals: list[Goal] = field(default_factory=list)
    horizon_years: float = 5.0
    # behaviour & experience
    drawdown_reaction: DrawdownReaction = DrawdownReaction.WAIT
    experience: Experience = Experience.BEGINNER


# ---------------------------------------------------------------- scoring tables
def _piecewise(x: float, pts: list[tuple[float, float]]) -> float:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            t = (x - xs[i - 1]) / (xs[i] - xs[i - 1])
            return ys[i - 1] + t * (ys[i] - ys[i - 1])
    return ys[-1]


_HORIZON = [(1, 8), (2, 22), (3, 38), (5, 60), (8, 78), (15, 92), (25, 100)]
_AGE = [(22, 100), (30, 92), (40, 75), (50, 55), (58, 38), (65, 22), (72, 10)]
_EMPLOYMENT = {
    Employment.SALARIED_STABLE: 100, Employment.SALARIED_PRIVATE: 78,
    Employment.SELF_EMPLOYED: 58, Employment.BUSINESS: 58,
    Employment.RETIRED: 35, Employment.STUDENT: 45, Employment.UNEMPLOYED: 12,
}
_EMERGENCY = {
    EmergencyFund.SIX_PLUS: 100, EmergencyFund.THREE_TO_6M: 62,
    EmergencyFund.UPTO_3M: 30, EmergencyFund.NONE: 8,
}
_DEBT = {DebtLoad.NONE: 100, DebtLoad.LOW: 80, DebtLoad.MODERATE: 50, DebtLoad.HIGH: 12}
_REACTION = {
    DrawdownReaction.SELL_ALL: 10, DrawdownReaction.WAIT: 52,
    DrawdownReaction.INVEST_MORE: 88, DrawdownReaction.INCREASE_SIP: 100,
}
_EXPERIENCE = {
    Experience.NONE: 35, Experience.BEGINNER: 52,
    Experience.INTERMEDIATE: 75, Experience.EXPERIENCED: 95,
}


@dataclass
class RiskAssessment:
    capacity: float           # 0..100 ability to take risk
    tolerance: float          # 0..100 willingness to take risk
    score: float              # min(capacity, tolerance)
    bucket: str               # Conservative | Moderate | Aggressive
    binding: str              # which sub-score bound the result
    breakdown: dict[str, float]


def assess_risk(p: InvestorProfile) -> RiskAssessment:
    h = _piecewise(p.horizon_years, _HORIZON)
    a = _piecewise(p.age, _AGE)
    e = _EMPLOYMENT[p.employment]
    ef = _EMERGENCY[p.emergency_fund]
    d = _DEBT[p.debt]
    capacity = 0.40 * h + 0.20 * a + 0.15 * e + 0.15 * ef + 0.10 * d

    r = _REACTION[p.drawdown_reaction]
    x = _EXPERIENCE[p.experience]
    tolerance = 0.70 * r + 0.30 * x

    score = min(capacity, tolerance)
    binding = "capacity" if capacity <= tolerance else "tolerance"
    bucket = "Aggressive" if score >= 70 else "Moderate" if score >= 40 else "Conservative"
    return RiskAssessment(
        capacity=round(capacity, 1), tolerance=round(tolerance, 1),
        score=round(score, 1), bucket=bucket, binding=binding,
        breakdown={
            "horizon": round(h, 1), "age": round(a, 1), "employment": float(e),
            "emergency_fund": float(ef), "debt": float(d),
            "reaction": float(r), "experience": float(x),
        },
    )


def assessment_reasons(p: InvestorProfile, ra: RiskAssessment) -> list[str]:
    """Plain-language drivers of the score, for the explainability layer."""
    out = []
    b = ra.breakdown
    out.append(f"A {p.horizon_years:.0f}-year horizon gives a time-capacity score of {b['horizon']:.0f}/100.")
    if ra.binding == "tolerance":
        out.append(f"Your willingness to take risk ({ra.tolerance:.0f}) is lower than your ability "
                   f"({ra.capacity:.0f}), so it sets the profile. We don't push you past your comfort.")
    else:
        out.append(f"Your ability to take risk ({ra.capacity:.0f}) is the limit here "
                   f"(willingness {ra.tolerance:.0f}); the plan respects that ceiling.")
    if b["emergency_fund"] < 40:
        out.append("A thin emergency fund lowers capacity. A cash buffer comes before market risk.")
    if b["debt"] < 40:
        out.append("High-interest debt lowers capacity. Clearing it is a guaranteed return.")
    return out
