"""Layer 4, Fund ranking.

A composite score, NOT a return ranking. Weighted toward consistency and
downside protection, exactly as a long-term investor should. All factors come
from NAV (so they're net of fees already); expense ratio and AUM aren't in our
data, so the doc's 7-factor model is renormalised to the 4 we can compute
honestly. Scoring is cross-sectional: each factor is normalised WITHIN the
sleeve's candidate set, so a fund is judged against its true peers.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..config import DEFAULT_CONFIG, Config
from .profile import RiskAssessment

# renormalised from the spec's 30/20/15/15 (consistency/sortino/sharpe/drawdown)
_WEIGHTS = {"consistency": 0.38, "sortino": 0.25, "sharpe": 0.19, "drawdown": 0.18}


@dataclass
class FundScore:
    code: int
    name: str
    composite: float                 # 0..100 within-sleeve
    confidence: float                # 0..100 data-quality / history
    years: float
    factors: dict[str, float] = field(default_factory=dict)   # raw factor values
    stats: object = None             # WindowStats over the eval window


def _rolling_consistency(nav: pd.Series, window_years: float) -> float | None:
    """Fraction of rolling 1-year windows with a positive return."""
    m = nav.resample("ME").last().dropna()
    if len(m) < 18:
        return None
    roll = m / m.shift(12) - 1.0
    roll = roll.dropna()
    if roll.empty:
        return None
    return float((roll > 0).mean())


def _eval(nav: pd.Series, config: Config):
    from ..webapp.data import window_stats
    nav = nav.dropna()
    if len(nav) < 60:
        return None
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    lookback = min(5.0, years)
    try:
        st = window_stats(nav, lookback, config)
    except ValueError:
        return None
    cons = _rolling_consistency(nav, lookback)
    if cons is None:
        cons = 0.5  # neutral if too little history for rolling windows
    return years, st, cons


def _confidence(years: float, st) -> float:
    base = 40 if years < 1 else 60 if years < 3 else 80 if years < 5 else 92
    # penalise very high volatility (less reliable signal)
    if st.volatility and st.volatility > 0.28:
        base -= 8
    return float(max(20, min(98, base)))


def _norm(vals: list[float], higher_better=True) -> list[float]:
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-12:
        return [0.5] * len(vals)
    out = [(v - lo) / (hi - lo) for v in vals]
    return out if higher_better else [1 - o for o in out]


def rank_sleeve(navs: dict[int, str], nav_series: dict[int, pd.Series],
                config: Config = DEFAULT_CONFIG) -> list[FundScore]:
    """navs: code->name; nav_series: code->NAV. Returns FundScores, best first."""
    raw = []
    for code, name in navs.items():
        ev = _eval(nav_series.get(code, pd.Series(dtype=float)), config)
        if ev is None:
            continue
        years, st, cons = ev
        raw.append((code, name, years, st, cons))
    if not raw:
        return []

    cons_n = _norm([r[4] for r in raw], True)
    sort_n = _norm([r[3].sortino for r in raw], True)
    shar_n = _norm([r[3].sharpe for r in raw], True)
    dd_n = _norm([r[3].max_drawdown for r in raw], True)  # less negative is larger → better

    scores = []
    for i, (code, name, years, st, cons) in enumerate(raw):
        composite = 100 * (
            _WEIGHTS["consistency"] * cons_n[i] + _WEIGHTS["sortino"] * sort_n[i] +
            _WEIGHTS["sharpe"] * shar_n[i] + _WEIGHTS["drawdown"] * dd_n[i]
        )
        scores.append(FundScore(
            code=code, name=name, composite=round(composite, 1),
            confidence=_confidence(years, st), years=round(years, 1),
            factors={"consistency": round(cons, 3), "sortino": round(st.sortino, 2),
                     "sharpe": round(st.sharpe, 2), "max_drawdown": round(st.max_drawdown, 3)},
            stats=st,
        ))
    scores.sort(key=lambda s: s.composite, reverse=True)
    return scores
