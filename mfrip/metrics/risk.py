"""Absolute (single-series) risk metrics.

All functions take period returns and the annual risk-free rate, and
annualise consistently. The risk-free rate is converted geometrically to a
per-period rate so Sharpe/Sortino are internally consistent with CAGR.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _rf_per_period(rf_annual: float, periods_per_year: int) -> float:
    return (1.0 + rf_annual) ** (1.0 / periods_per_year) - 1.0


def annualized_volatility(returns: pd.Series, periods_per_year: int = 12) -> float:
    if len(returns) < 2:
        return float("nan")
    return float(returns.std(ddof=1) * np.sqrt(periods_per_year))


def annualized_return(returns: pd.Series, periods_per_year: int = 12) -> float:
    """Geometric annualised return of the period-return stream."""
    if len(returns) == 0:
        return float("nan")
    total_growth = float((1.0 + returns).prod())
    n_years = len(returns) / periods_per_year
    if n_years <= 0 or total_growth <= 0:
        return float("nan")
    return total_growth ** (1.0 / n_years) - 1.0


def sharpe_ratio(returns: pd.Series, rf_annual: float, periods_per_year: int = 12) -> float:
    if len(returns) < 2:
        return float("nan")
    rf = _rf_per_period(rf_annual, periods_per_year)
    excess = returns - rf
    ann_excess = excess.mean() * periods_per_year
    ann_vol = returns.std(ddof=1) * np.sqrt(periods_per_year)
    return float(ann_excess / ann_vol) if ann_vol > 0 else float("nan")


def sortino_ratio(returns: pd.Series, rf_annual: float, periods_per_year: int = 12) -> float:
    """Sortino with target downside deviation (Sortino & Price convention).

    Downside deviation uses the full-sample denominator: shortfalls below the
    risk-free target are squared, averaged over ALL periods, then rooted.
    """
    if len(returns) < 2:
        return float("nan")
    rf = _rf_per_period(rf_annual, periods_per_year)
    excess = returns - rf
    shortfall = np.minimum(excess, 0.0)
    downside_dev = np.sqrt((shortfall ** 2).mean()) * np.sqrt(periods_per_year)
    ann_excess = excess.mean() * periods_per_year
    return float(ann_excess / downside_dev) if downside_dev > 0 else float("nan")


def max_drawdown(nav: pd.Series) -> float:
    """Worst peak-to-trough decline of a NAV (price) series. <= 0."""
    nav = nav.dropna()
    if len(nav) < 2:
        return float("nan")
    running_peak = nav.cummax()
    drawdown = nav / running_peak - 1.0
    return float(drawdown.min())


def calmar_ratio(cagr: float | None, mdd: float) -> float:
    if cagr is None or mdd is None or np.isnan(mdd) or mdd >= 0:
        return float("nan")
    return float(cagr / abs(mdd))
