"""Rolling-returns analysis, the distribution of every rolling window, not one
lucky point-to-point number. Best/worst/average annualised return over each
rolling 1/3/5-year window, plus how often a fund beat its benchmark.
"""
from __future__ import annotations

import pandas as pd


def _monthly(nav: pd.Series) -> pd.Series:
    return nav.resample("ME").last().dropna()


def rolling_returns(nav: pd.Series, years: float) -> dict | None:
    """Annualised return over each rolling `years`-month window."""
    m = _monthly(nav)
    k = int(round(years * 12))
    if k < 1 or len(m) <= k:
        return None
    roll = (m / m.shift(k)) ** (1.0 / years) - 1.0
    roll = roll.dropna()
    if roll.empty:
        return None
    return {
        "best": float(roll.max()), "worst": float(roll.min()),
        "avg": float(roll.mean()), "median": float(roll.median()),
        "pct_positive": float((roll > 0).mean()), "count": int(len(roll)),
    }


def rolling_outperformance(nav: pd.Series, bench: pd.Series, years: float) -> float | None:
    """Fraction of rolling windows where the fund beat the benchmark."""
    m, b = _monthly(nav), _monthly(bench)
    idx = m.index.intersection(b.index)
    if len(idx) < 2:
        return None
    m, b = m[idx], b[idx]
    k = int(round(years * 12))
    if k < 1 or len(m) <= k:
        return None
    fr = m / m.shift(k) - 1.0
    br = b / b.shift(k) - 1.0
    d = (fr - br).dropna()
    if d.empty:
        return None
    return float((d > 0).mean())
