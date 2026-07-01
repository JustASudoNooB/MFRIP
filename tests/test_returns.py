from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mfrip.metrics import returns
from tests.conftest import make_nav, daily_growth_for_annual


def test_cut_excludes_future():
    nav = make_nav(100.0, 0.0003, 1000)
    as_of = nav.index[500]
    cut = returns.cut(nav, as_of)
    assert cut.index.max() == as_of
    assert len(cut) == 501


def test_trailing_cagr_recovers_known_rate(flat_growth_nav):
    as_of = flat_growth_nav.index[-1]
    cagr_3y = returns.trailing_cagr(flat_growth_nav, as_of, 3.0)
    assert cagr_3y == pytest.approx(0.12, abs=1e-3)
    cagr_5y = returns.trailing_cagr(flat_growth_nav, as_of, 5.0)
    assert cagr_5y == pytest.approx(0.12, abs=1e-3)


def test_trailing_cagr_short_window_is_absolute(flat_growth_nav):
    as_of = flat_growth_nav.index[-1]
    r_1y = returns.trailing_cagr(flat_growth_nav, as_of, 1.0)
    # one year of 12% annualised compounding ~= 12% absolute
    assert r_1y == pytest.approx(0.12, abs=2e-3)


def test_trailing_cagr_insufficient_history_returns_none():
    g = daily_growth_for_annual(0.10)
    nav = make_nav(100.0, g, n_days=400)  # ~1.1y of history
    as_of = nav.index[-1]
    assert returns.trailing_cagr(nav, as_of, 5.0) is None  # cannot fabricate 5Y
    assert returns.trailing_cagr(nav, as_of, 1.0) is not None


def test_period_returns_monthly_count(flat_growth_nav):
    rets = returns.period_returns(flat_growth_nav, periods_per_year=12)
    # ~6 years -> ~71 monthly returns
    assert 69 <= len(rets) <= 73
    assert (rets > 0).all()  # monotonic growth -> all positive
