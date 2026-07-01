"""Deterministic fixtures.

Where possible the expected metric is hand-computable so the assertion is
exact, not a tolerance hand-wave.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def make_nav(start_value: float, daily_growth: float, n_days: int, start="2015-01-01") -> pd.Series:
    """Strictly compounding NAV: nav_i = start * (1+g)^i on a daily calendar."""
    idx = pd.date_range(start=start, periods=n_days, freq="D")
    vals = start_value * (1.0 + daily_growth) ** np.arange(n_days)
    return pd.Series(vals, index=idx, name="fund")


def daily_growth_for_annual(annual: float) -> float:
    return (1.0 + annual) ** (1.0 / 365.25) - 1.0


@pytest.fixture
def flat_growth_nav() -> pd.Series:
    # exactly 12% annualised, zero volatility, monotonically increasing
    g = daily_growth_for_annual(0.12)
    return make_nav(100.0, g, n_days=365 * 6)


@pytest.fixture
def benchmark_nav() -> pd.Series:
    rng = np.random.default_rng(7)
    idx = pd.date_range("2015-01-01", periods=365 * 6, freq="D")
    daily = rng.normal(0.0004, 0.008, size=len(idx))  # ~10%/yr drift, realistic vol
    nav = 100.0 * np.cumprod(1.0 + daily)
    return pd.Series(nav, index=idx, name="bench")


@pytest.fixture
def noisy_nav(benchmark_nav) -> pd.Series:
    # fund = beta 1.3 exposure to benchmark daily returns + idiosyncratic noise
    rng = np.random.default_rng(11)
    bench_ret = benchmark_nav.pct_change().dropna()
    idio = rng.normal(0.0001, 0.004, size=len(bench_ret))
    fund_ret = 1.3 * bench_ret.to_numpy() + idio
    nav = 100.0 * np.cumprod(1.0 + np.concatenate([[0.0], fund_ret]))
    return pd.Series(nav, index=benchmark_nav.index, name="fund")
