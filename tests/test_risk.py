from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mfrip.metrics import returns, risk


def test_max_drawdown_exact():
    nav = pd.Series(
        [100.0, 120.0, 90.0, 150.0],
        index=pd.date_range("2020-01-01", periods=4, freq="ME"),
    )
    # peak 120 -> trough 90 => -25%
    assert risk.max_drawdown(nav) == pytest.approx(-0.25)


def test_monotonic_series_has_zero_drawdown(flat_growth_nav):
    assert risk.max_drawdown(flat_growth_nav) == pytest.approx(0.0, abs=1e-12)


def test_zero_volatility_constant_returns():
    rets = pd.Series([0.01] * 24)
    assert risk.annualized_volatility(rets, 12) == pytest.approx(0.0, abs=1e-12)
    # zero vol -> Sharpe undefined
    assert np.isnan(risk.sharpe_ratio(rets, 0.05, 12))


def test_annualized_volatility_known():
    # alternating +/-0.1, sample std = sqrt(0.04/3) ; annualised * sqrt(12)
    rets = pd.Series([0.1, -0.1] * 12)
    expected = np.sqrt(0.04 / (len(rets) - 1) * (len(rets))) * 0  # placeholder, recompute below
    sample_std = rets.std(ddof=1)
    assert risk.annualized_volatility(rets, 12) == pytest.approx(sample_std * np.sqrt(12))


def test_sharpe_positive_when_excess_positive():
    rng = np.random.default_rng(3)
    rets = pd.Series(rng.normal(0.02, 0.03, 60))  # ~24%/yr, well above rf
    assert risk.sharpe_ratio(rets, 0.065, 12) > 0


def test_sortino_undefined_without_downside():
    # all returns above the per-period risk-free target -> no shortfall
    rets = pd.Series([0.05] * 36)
    assert np.isnan(risk.sortino_ratio(rets, 0.065, 12))


def test_sortino_finite_with_downside():
    rets = pd.Series([0.05, -0.04] * 18)
    s = risk.sortino_ratio(rets, 0.065, 12)
    assert np.isfinite(s)


def test_calmar_basic():
    assert risk.calmar_ratio(0.15, -0.30) == pytest.approx(0.5)
    assert np.isnan(risk.calmar_ratio(0.15, 0.0))


def test_annualized_return_doubling():
    # 12 monthly returns that compound to exactly 2x over 1 year -> 100% CAGR
    g = 2.0 ** (1.0 / 12) - 1.0
    rets = pd.Series([g] * 12)
    assert risk.annualized_return(rets, 12) == pytest.approx(1.0, abs=1e-9)
