"""Layer 3, Strategic Asset Allocation.

Risk score + constraints → a target mix across sleeves, BEFORE any fund is
chosen. The constraint engine's equity ceiling and avoid-sleeves are applied
here, so allocation can never violate a hard rule (e.g. short horizon or no
emergency fund caps equity no matter how bold the risk score).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .constraints import ConstraintReport
from .profile import RiskAssessment


@dataclass
class Allocation:
    weights: dict[str, float]                 # sleeve -> weight, sums to 1.0
    equity: float
    debt: float
    gold: float
    notes: list[str] = field(default_factory=list)


def _pw(x, pts):
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


_EQUITY = [(10, 0.15), (25, 0.30), (40, 0.50), (55, 0.65), (70, 0.78), (85, 0.88), (95, 0.92)]

# equity split within the equity sleeve, by bucket
_EQ_SPLIT = {
    "Conservative": {"largecap": 0.55, "flexicap": 0.40, "midcap": 0.05, "smallcap": 0.0, "international": 0.0},
    "Moderate":     {"largecap": 0.32, "flexicap": 0.36, "midcap": 0.18, "smallcap": 0.08, "international": 0.06},
    "Aggressive":   {"largecap": 0.20, "flexicap": 0.30, "midcap": 0.27, "smallcap": 0.18, "international": 0.05},
}


def target_allocation(ra: RiskAssessment, cons: ConstraintReport) -> Allocation:
    notes: list[str] = []
    score = ra.score

    equity_want = _pw(score, _EQUITY)
    equity = min(equity_want, cons.max_equity)
    if equity < equity_want - 1e-9:
        notes.append(f"Equity trimmed from {equity_want:.0%} to {equity:.0%} by a constraint "
                     f"(horizon, emergency fund, or debt).")

    gold = 0.10 if score < 40 else 0.075 if score < 70 else 0.05
    remaining = 1.0 - equity
    gold = min(gold, remaining)
    debt = remaining - gold

    split = dict(_EQ_SPLIT[ra.bucket])
    # honour avoid-sleeves: zero them, redistribute proportionally to the rest
    removed = 0.0
    for s in list(split):
        if s in cons.avoid_sleeves and split[s] > 0:
            removed += split[s]
            split[s] = 0.0
            notes.append(f"Skipped {s} in the equity sleeve (you're already concentrated there).")
    if removed > 0:
        live = sum(split.values())
        if live > 0:
            split = {s: w + (w / live) * removed for s, w in split.items()}

    weights = {s: round(equity * w, 4) for s, w in split.items() if equity * w > 1e-6}
    if debt > 1e-6:
        weights["debt"] = round(debt, 4)
    if gold > 1e-6:
        weights["gold"] = round(gold, 4)

    total = sum(weights.values()) or 1.0
    weights = {s: round(w / total, 4) for s, w in weights.items()}
    return Allocation(weights=weights, equity=round(equity, 4),
                      debt=round(debt, 4), gold=round(gold, 4), notes=notes)
