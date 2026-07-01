"""Tests for the walk-forward validation engine.

We validate the validator with synthetic funds. A latent 'quality' q drives each
fund's drift (and mildly its volatility). If q persists across the cutoff, the
engine must detect a strong positive rank correlation between the in-sample score
and out-of-sample behaviour; if the post-cutoff period uses an independent q, the
correlation at the aligned cutoff must be ~zero. Thresholds are averaged over
several seeds so the tests are robust rather than dependent on one lucky draw.
"""
import numpy as np
import pandas as pd
import pytest

from mfrip import validation as V

CUTOFF = "2019-06-30"  # aligned with the regime change below


def _make_funds(n_funds=30, seed=0, persistent=True,
                start="2014-01-01", end="2022-06-30", cutoff=CUTOFF):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, end)
    pre = np.asarray(dates <= pd.Timestamp(cutoff))
    q = np.linspace(-1, 1, n_funds)
    rng.shuffle(q)
    q2 = q.copy() if persistent else rng.permutation(q)
    funds = {}
    for i in range(n_funds):
        ma, sa = 0.0003 + 0.0007 * q[i], max(0.009 - 0.002 * q[i], 0.004)
        mb, sb = 0.0003 + 0.0007 * q2[i], max(0.009 - 0.002 * q2[i], 0.004)
        r = np.where(pre, rng.normal(ma, sa, len(dates)), rng.normal(mb, sb, len(dates)))
        funds[1000 + i] = (f"Fund {i:02d}", pd.Series(100.0 * np.cumprod(1.0 + r), index=dates))
    return funds


def _mean_window_corr(persistent, metric, seeds=range(6)):
    vals = []
    for s in seeds:
        w = V.evaluate_window(_make_funds(seed=s, persistent=persistent), CUTOFF, 3, 2)
        if w is not None:
            vals.append(w["corr"][metric])
    return float(np.mean(vals))


def test_feasible_cutoffs_within_coverage():
    cuts = V.feasible_cutoffs(_make_funds(seed=1), lookback_years=3, horizon_years=2)
    assert len(cuts) >= 2
    for c in cuts:
        assert c >= pd.Timestamp("2017-01-01")
        assert c <= pd.Timestamp("2020-06-30")


def test_evaluate_window_structure():
    w = V.evaluate_window(_make_funds(seed=2), CUTOFF, lookback_years=3, horizon_years=2)
    assert w is not None and w["n"] >= 20
    assert {"score", "oos_sharpe", "oos_consistency", "oos_max_drawdown"} <= set(w["df"].columns)
    assert set(w["corr"]) == set(V.OOS_METRICS)
    assert set(w["spread"]) == set(V.OOS_METRICS)


def test_detects_persistence_across_metrics():
    assert _mean_window_corr(True, "oos_sharpe") > 0.5
    assert _mean_window_corr(True, "oos_consistency") > 0.4
    assert _mean_window_corr(True, "oos_max_drawdown") > 0.5
    assert _mean_window_corr(True, "oos_volatility") < -0.4


def test_detects_no_persistence_at_aligned_cutoff():
    assert abs(_mean_window_corr(False, "oos_sharpe")) < 0.2
    assert abs(_mean_window_corr(False, "oos_consistency")) < 0.2


def test_persistence_is_clearly_discriminated():
    assert _mean_window_corr(True, "oos_sharpe") - _mean_window_corr(False, "oos_sharpe") > 0.4


def test_top_half_beats_bottom_half_when_persistent():
    w = V.evaluate_window(_make_funds(seed=3), CUTOFF, 3, 2)
    assert w["spread"]["oos_sharpe"] > 0
    assert w["spread"]["oos_max_drawdown"] > 0


def test_walk_forward_aggregates_and_is_significant_when_persistent():
    wf = V.walk_forward(_make_funds(seed=5, persistent=True), lookback_years=3, horizon_years=2)
    assert wf is not None and wf["n_windows"] >= 2
    pc = wf["pooled_corr"]["oos_sharpe"]
    assert set(pc) == {"rho", "n", "p"}
    assert pc["rho"] > 0.4
    assert pc["p"] < 0.05
    assert wf["return_corr"] > 0.3 and wf["risk_corr"] > 0.3
    assert 0.0 <= wf["hit_rate"]["oos_sharpe"] <= 1.0


def test_walk_forward_signal_much_weaker_when_random():
    rc = V.walk_forward(_make_funds(seed=0, persistent=False), lookback_years=3, horizon_years=2)
    assert rc["return_corr"] < 0.3 and rc["risk_corr"] < 0.3


def test_permutation_pvalue_bounds():
    a = np.arange(30.0)
    b = a + np.random.default_rng(0).normal(0, 5, 30)
    p = V._perm_pvalue(a, b, n_perm=500)
    assert 0.0 < p <= 1.0
    assert V._perm_pvalue(a, a, n_perm=500) < 0.05


def test_insufficient_funds_returns_none():
    assert V.evaluate_window(_make_funds(n_funds=3, seed=7), CUTOFF, 3, 2, min_funds=5) is None
