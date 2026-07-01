from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mfrip.portfolio.reconstruct import reconstruct
from mfrip.portfolio.audit import run_audit


def _series(values, start="2025-11-08"):
    idx = pd.date_range(start, periods=len(values), freq="D")
    return pd.Series(values, index=idx, dtype=float)


def test_reconstruct_equal_weight_known():
    # fund 1 doubles (100->200), fund 2 flat (100). Equal weight 1L.
    n = 100
    f1 = _series(np.linspace(100, 200, n))
    f2 = _series(np.full(n, 100.0))
    rec = reconstruct({1: f1, 2: f2}, {1: 0.5, 2: 0.5}, "2025-11-08", amount=100000)
    # 50k each: f1 -> 100k, f2 -> 50k => 150k, +50%
    assert rec.value.iloc[-1] == pytest.approx(150000, rel=1e-6)
    assert rec.excluded_weight == pytest.approx(0.0)


def test_reconstruct_renormalises_excluded():
    f1 = _series(np.full(50, 100.0))
    # only 0.7 of weight priceable -> excluded 0.3, f1 gets full amount
    rec = reconstruct({1: f1}, {1: 0.7}, "2025-11-08", amount=100000)
    assert rec.excluded_weight == pytest.approx(0.3)
    assert rec.invested == pytest.approx(70000)
    assert rec.value.iloc[0] == pytest.approx(100000)  # full amount deployed into priced sleeve


def test_audit_detects_outperformance():
    n = 120
    fund = _series(np.linspace(100, 130, n))   # +30%
    bench = _series(np.linspace(100, 110, n))  # +10%
    res = run_audit({1: fund}, {1: 1.0}, bench, start="2025-11-08", amount=100000)
    assert res.beat_benchmark is True
    assert res.excess_vs_benchmark == pytest.approx(0.20, abs=1e-6)
    assert res.recommended_returns["latest"] == pytest.approx(0.30, abs=1e-6)


def test_audit_horizons_none_when_not_reached():
    fund = _series(np.linspace(100, 105, 40))   # only ~40 days
    bench = _series(np.linspace(100, 102, 40))
    res = run_audit({1: fund}, {1: 1.0}, bench, start="2025-11-08")
    assert res.recommended_returns["1M"] is not None
    assert res.recommended_returns["6M"] is None  # 6 months not elapsed
