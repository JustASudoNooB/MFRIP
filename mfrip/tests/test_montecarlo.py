"""Tests for the Monte Carlo SIP goal simulation."""
import numpy as np
import pandas as pd
import pytest

from mfrip.metrics import montecarlo as MC
from mfrip.metrics.sip import goal_projection


def _const_growth_nav(monthly_rate=0.01, n_months=60, start="2015-01-31"):
    idx = pd.date_range(start, periods=n_months, freq="ME")
    return pd.Series(100.0 * (1.0 + monthly_rate) ** np.arange(n_months), index=idx)


def _random_nav(seed=0, n_months=120, mu=0.009, sd=0.04, start="2010-01-31"):
    rng = np.random.default_rng(seed)
    r = rng.normal(mu, sd, n_months - 1)
    nav = 100.0 * np.cumprod(np.concatenate([[1.0], 1.0 + r]))
    idx = pd.date_range(start, periods=n_months, freq="ME")
    return pd.Series(nav, index=idx)


def test_zero_vol_matches_deterministic():
    # With a constant monthly return, every bootstrapped path is identical,
    # so the simulated corpus must equal the closed-form annuity-due SIP value.
    nav = _const_growth_nav(0.01, 60)
    monthly, years = 10_000.0, 5.0
    sim = MC.simulate_sip(nav, monthly, years, n_sims=500, method="bootstrap", seed=1)
    n = 60
    mr = 0.01
    fv = monthly * (((1 + mr) ** n - 1) / mr) * (1 + mr)
    assert sim["terminal_pct"][50] == pytest.approx(fv, rel=1e-9)
    # zero spread: all percentiles equal
    assert sim["terminal_pct"][10] == pytest.approx(sim["terminal_pct"][90], rel=1e-9)


def test_zero_vol_agrees_with_goal_projection():
    # annual return implied by 1%/month, fed through goal_projection, should match
    nav = _const_growth_nav(0.01, 72)
    monthly, years = 5_000.0, 6.0
    ann = (1.01) ** 12 - 1.0
    det = goal_projection(monthly, years, rates=(ann,))[ann]
    sim = MC.simulate_sip(nav, monthly, years, n_sims=300, seed=2)
    assert sim["terminal_pct"][50] == pytest.approx(det, rel=1e-6)


def test_percentiles_are_ordered():
    nav = _random_nav(seed=3)
    sim = MC.simulate_sip(nav, 5_000, 10, n_sims=4000, seed=3)
    tp = sim["terminal_pct"]
    assert tp[10] <= tp[25] <= tp[50] <= tp[75] <= tp[90]
    # and the bands are ordered at every point in time
    assert np.all(sim["bands"][10] <= sim["bands"][50])
    assert np.all(sim["bands"][50] <= sim["bands"][90])


def test_bands_start_at_zero_and_grow():
    nav = _random_nav(seed=4)
    sim = MC.simulate_sip(nav, 5_000, 8, n_sims=2000, seed=4)
    for p in (10, 50, 90):
        assert sim["bands"][p][0] == 0.0
    # invested line is linear and ends at total invested
    assert sim["invested"][-1] == pytest.approx(sim["total_invested"])
    assert sim["invested"][-1] == pytest.approx(5_000 * sim["months"])


def test_seed_is_deterministic():
    nav = _random_nav(seed=5)
    a = MC.simulate_sip(nav, 3_000, 7, n_sims=1500, seed=99)
    b = MC.simulate_sip(nav, 3_000, 7, n_sims=1500, seed=99)
    assert a["terminal_pct"] == b["terminal_pct"]


def test_corpus_is_linear_in_monthly():
    # same seed -> identical return paths -> doubling the SIP doubles every outcome
    nav = _random_nav(seed=6)
    a = MC.simulate_sip(nav, 10_000, 6, n_sims=1000, seed=7)
    b = MC.simulate_sip(nav, 20_000, 6, n_sims=1000, seed=7)
    assert b["terminal_pct"][50] == pytest.approx(2 * a["terminal_pct"][50], rel=1e-9)


def test_target_probability_bounds():
    nav = _random_nav(seed=8)
    low = MC.simulate_sip(nav, 5_000, 10, n_sims=3000, seed=8, target=1.0)
    high = MC.simulate_sip(nav, 5_000, 10, n_sims=3000, seed=8, target=1e12)
    assert low["prob_target"] == pytest.approx(1.0)       # trivially reachable
    assert high["prob_target"] == pytest.approx(0.0)      # impossibly high
    mid = MC.simulate_sip(nav, 5_000, 10, n_sims=3000, seed=8,
                          target=5_000 * 120)             # ~ total invested
    assert 0.0 <= mid["prob_target"] <= 1.0


def test_normal_method_runs_and_orders():
    nav = _random_nav(seed=9)
    sim = MC.simulate_sip(nav, 5_000, 10, n_sims=3000, method="normal", seed=9)
    tp = sim["terminal_pct"]
    assert tp[10] <= tp[50] <= tp[90]
    assert sim["method"] == "normal"


def test_required_monthly_scales_with_target():
    nav = _random_nav(seed=10)
    m1 = MC.required_monthly_for_confidence(nav, target=1_000_000, years=10, confidence=0.5, seed=10)
    m2 = MC.required_monthly_for_confidence(nav, target=2_000_000, years=10, confidence=0.5, seed=10)
    assert m1 is not None and m2 is not None
    assert m2 == pytest.approx(2 * m1, rel=1e-9)


def test_insufficient_history_raises():
    nav = _const_growth_nav(0.01, 6)  # only 5 monthly returns
    with pytest.raises(ValueError):
        MC.simulate_sip(nav, 5_000, 10)


def test_nonpositive_monthly_raises():
    nav = _random_nav(seed=11)
    with pytest.raises(ValueError):
        MC.simulate_sip(nav, 0, 10)
