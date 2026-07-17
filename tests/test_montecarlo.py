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


# ---- calendar-year (year-on-year) returns
def _cy_nav(start, end, monthly_rate=0.0):
    import pandas as pd, numpy as np
    idx = pd.date_range(start, end, freq="B")
    if monthly_rate == 0.0:
        vals = np.full(len(idx), 100.0)
    else:
        dr = (1 + monthly_rate) ** (1 / 21) - 1
        vals = 100.0 * np.cumprod(np.full(len(idx), 1 + dr))
    return pd.Series(vals, index=idx)


def test_calendar_year_flat_is_zero():
    from mfrip.metrics.returns import calendar_year_returns
    nav = _cy_nav("2020-01-01", "2022-12-31", 0.0)
    cy = calendar_year_returns(nav)
    assert [y for y, r, p in cy] == [2020, 2021, 2022]
    for y, r, p in cy:
        assert abs(r) < 1e-9
        assert p is False  # full years, not partial


def test_calendar_year_marks_partial_years():
    from mfrip.metrics.returns import calendar_year_returns
    nav = _cy_nav("2019-06-03", "2024-03-28", 0.0)
    cy = calendar_year_returns(nav)
    years = [y for y, r, p in cy]
    partial = {y: p for y, r, p in cy}
    assert years[0] == 2019 and partial[2019] is True    # starts mid-year
    assert years[-1] == 2024 and partial[2024] is True   # ends mid-year
    assert partial[2021] is False                        # full year


def test_calendar_year_full_year_value():
    from mfrip.metrics.returns import calendar_year_returns
    import pandas as pd, numpy as np
    # NAV doubles across 2021 exactly (Dec-2020 to Dec-2021)
    idx = pd.date_range("2020-12-31", "2021-12-31", freq="D")
    vals = np.linspace(100.0, 200.0, len(idx))
    cy = calendar_year_returns(pd.Series(vals, index=idx))
    got = {y: r for y, r, p in cy}
    assert got[2021] == pytest.approx(1.0, rel=1e-6)     # +100%


def test_required_monthly_high_confidence_works_and_costs_more():
    # Regression: confidence=0.75 asks the simulator for the 25th percentile
    # only; the median field must still work (this used to KeyError on 50).
    nav = _random_nav(seed=12)
    m50 = MC.required_monthly_for_confidence(nav, 1_000_000, 10, confidence=0.50, seed=5)
    m75 = MC.required_monthly_for_confidence(nav, 1_000_000, 10, confidence=0.75, seed=5)
    assert m50 is not None and m75 is not None
    assert m75 > m50                      # higher confidence must cost more per month


def test_custom_percentiles_still_report_median():
    nav = _random_nav(seed=13)
    sim = MC.simulate_sip(nav, 5_000, 8, n_sims=500, seed=3,
                          target=1_000.0, percentiles=(25,))
    assert sim["median_multiple"] is not None and sim["median_multiple"] > 0
    assert sim["median_hits_year"] is not None   # bands.get(50) fallback path
    assert 25 in sim["terminal_pct"]


def test_custom_percentiles_never_break_median_stats():
    # Regression: required_monthly_for_confidence asks for a single custom
    # percentile (e.g. 25th for 75% confidence); the simulator must still
    # produce its median-based summary stats instead of raising KeyError.
    nav = _random_nav(seed=12)
    sim = MC.simulate_sip(nav, 5_000, 10, n_sims=800, seed=12,
                          percentiles=(25,), target=1_000_000)
    assert sim["median_multiple"] is not None and sim["median_multiple"] > 0
    assert "median_hits_year" in sim            # computed even without a 50th band
    assert 25 in sim["terminal_pct"] and 50 not in sim["terminal_pct"]


def test_required_monthly_75_percent_confidence():
    nav = _random_nav(seed=13)
    m50 = MC.required_monthly_for_confidence(nav, 2_000_000, 10, 0.50, seed=13)
    m75 = MC.required_monthly_for_confidence(nav, 2_000_000, 10, 0.75, seed=13)
    assert m50 and m75 and m75 >= m50           # higher confidence costs more


def test_sample_paths_span_outcome_range():
    nav = _random_nav(seed=14)
    sim = MC.simulate_sip(nav, 5_000, 10, n_sims=2000, seed=14)
    sp = sim["sample_paths"]
    assert sp.shape == (100, sim["months"] + 1)
    # deterministic with the seed
    sim2 = MC.simulate_sip(nav, 5_000, 10, n_sims=2000, seed=14)
    assert (sp == sim2["sample_paths"]).all()
    # sampled evenly across outcomes: first ends at the worst, last at the best
    finals = sp[:, -1]
    assert finals[0] == sim["terminal"].min()
    assert finals[-1] == sim["terminal"].max()
    assert (np.diff(finals) >= 0).all()          # ordered worst to best
    assert (sp[:, 0] == 0).all()                 # every future starts at zero


def test_sample_paths_span_the_outcome_range():
    nav = _random_nav(seed=14)
    sim = MC.simulate_sip(nav, 5_000, 10, n_sims=2000, seed=14)
    sp, rank = sim["sample_paths"], sim["sample_rank"]
    assert sp.shape == (100, sim["months"] + 1)
    assert rank[0] == 0.0 and rank[-1] == 1.0
    # sample spans the whole distribution, from unluckiest to luckiest future
    assert sp[:, -1].min() == sim["terminal"].min()
    assert sp[:, -1].max() == sim["terminal"].max()
    # and outcome-sorted, so rank really is the outcome percentile
    assert (np.diff(sp[:, -1]) >= 0).all()


def test_fan_chart_draws_coloured_journeys():
    from mfrip.webapp import charts as C
    nav = _random_nav(seed=15)
    sim = MC.simulate_sip(nav, 5_000, 10, n_sims=1000, seed=15)
    h = C.montecarlo_fan(sim).to_html(include_plotlyjs=False)
    for label in ("Unlucky journeys", "Middling journeys", "Lucky journeys"):
        assert label in h
    assert "rgba(194,69,45" in h and "rgba(20,122,82" in h   # red + green journey inks
