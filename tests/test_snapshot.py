from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mfrip.config import Config
from mfrip.metrics.snapshot import build_snapshot
from tests.conftest import make_nav, daily_growth_for_annual


def test_snapshot_basic_shape(flat_growth_nav, benchmark_nav):
    as_of = flat_growth_nav.index[-1]
    snap = build_snapshot(flat_growth_nav, as_of, benchmark=benchmark_nav, scheme_code="TEST")
    d = snap.to_dict()
    assert d["scheme_code"] == "TEST"
    assert d["annualized_return"] == pytest.approx(0.12, abs=2e-3)
    assert "3Y" in d["trailing_cagr"]
    assert d["beta"] is not None


def test_point_in_time_immune_to_future_data(noisy_nav, benchmark_nav):
    """THE integrity test.

    A snapshot dated T must be byte-identical whether or not the NAV series
    contains data after T. We compute a snapshot at T, then append an absurd
    future spike and recompute at the same T. Any difference => lookahead leak.
    """
    as_of = noisy_nav.index[len(noisy_nav) // 2]

    snap_before = build_snapshot(noisy_nav, as_of, benchmark=benchmark_nav, scheme_code="X")

    # contaminate the future with a wild +500% spike and a crash
    future_idx = pd.date_range(noisy_nav.index[-1] + pd.Timedelta(days=1), periods=100, freq="D")
    future_vals = np.concatenate([
        np.full(50, noisy_nav.iloc[-1] * 6.0),
        np.full(50, noisy_nav.iloc[-1] * 0.1),
    ])
    contaminated = pd.concat([noisy_nav, pd.Series(future_vals, index=future_idx)])
    contaminated_bench = pd.concat([
        benchmark_nav,
        pd.Series(np.full(100, benchmark_nav.iloc[-1] * 3.0), index=future_idx),
    ])

    snap_after = build_snapshot(contaminated, as_of, benchmark=contaminated_bench, scheme_code="X")

    assert snap_before.to_dict() == snap_after.to_dict()


def test_snapshot_requires_minimum_history():
    g = daily_growth_for_annual(0.10)
    nav = make_nav(100.0, g, n_days=1)
    with pytest.raises(ValueError):
        build_snapshot(nav, nav.index[-1])


def test_long_windows_are_none_for_young_fund():
    g = daily_growth_for_annual(0.10)
    nav = make_nav(100.0, g, n_days=400)  # ~1.1y old
    snap = build_snapshot(nav, nav.index[-1])
    assert snap.trailing_cagr["5Y"] is None
    assert snap.trailing_cagr["10Y"] is None
    assert snap.trailing_cagr["1Y"] is not None


def test_config_is_recorded(flat_growth_nav):
    cfg = Config(rf_annual=0.07, risk_lookback_years=5.0)
    snap = build_snapshot(flat_growth_nav, flat_growth_nav.index[-1], config=cfg)
    assert snap.config_used["rf_annual"] == 0.07
    assert snap.config_used["risk_lookback_years"] == 5.0
