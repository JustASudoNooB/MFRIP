from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mfrip.metrics import relative


def _mk(rets, start="2018-01-31"):
    return pd.Series(rets, index=pd.date_range(start, periods=len(rets), freq="ME"))


def test_beta_of_series_against_itself_is_one():
    rng = np.random.default_rng(1)
    b = _mk(rng.normal(0.01, 0.04, 60))
    beta, alpha = relative.beta_alpha(b, b, rf_annual=0.065, periods_per_year=12)
    assert beta == pytest.approx(1.0)
    assert alpha == pytest.approx(0.0, abs=1e-9)


def test_beta_of_leveraged_series_is_two():
    rng = np.random.default_rng(2)
    b = _mk(rng.normal(0.01, 0.04, 60))
    fund = 2.0 * b  # pure 2x exposure, no idiosyncratic noise
    beta, _ = relative.beta_alpha(fund, b, rf_annual=0.065, periods_per_year=12)
    assert beta == pytest.approx(2.0)


def test_capture_ratios_against_self_are_one():
    rng = np.random.default_rng(4)
    b = _mk(rng.normal(0.008, 0.05, 80))
    up, down = relative.capture_ratios(b, b)
    assert up == pytest.approx(1.0, abs=1e-6)
    assert down == pytest.approx(1.0, abs=1e-6)


def test_tracking_error_zero_against_self():
    rng = np.random.default_rng(5)
    b = _mk(rng.normal(0.01, 0.04, 60))
    assert relative.tracking_error(b, b, 12) == pytest.approx(0.0, abs=1e-12)


def test_noisy_fund_beta_in_expected_range(noisy_nav, benchmark_nav):
    from mfrip.metrics import returns
    fr = returns.period_returns(noisy_nav, 12)
    br = returns.period_returns(benchmark_nav, 12)
    beta, _ = relative.beta_alpha(fr, br, 0.065, 12)
    # constructed with ~1.3 daily beta; monthly estimate should be near it
    assert 1.0 < beta < 1.6
