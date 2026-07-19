"""Hand-computed control tests for the capital-gains tax model."""
import numpy as np
import pytest

from mfrip.metrics import tax as T


def test_equity_ltcg_hand_computed():
    # invested 10L, redeemed 15L: gains 5L, taxable 3.75L, tax 46,875
    assert T.post_tax_terminal(1_500_000, 1_000_000, "equity", 10) == \
        pytest.approx(1_500_000 - 46_875)


def test_equity_exemption_shields_small_gains():
    # gains of 1L sit under the 1.25L exemption: zero tax
    assert T.post_tax_terminal(1_100_000, 1_000_000, "equity", 10) == 1_100_000
    # exactly at the exemption boundary: still zero
    assert T.post_tax_terminal(1_125_000, 1_000_000, "equity", 10) == 1_125_000


def test_debt_taxed_at_slab_regardless_of_horizon():
    # gains 5L at 30% slab: tax 1.5L, even over a 10-year horizon
    assert T.post_tax_terminal(1_500_000, 1_000_000, "debt", 10, slab=0.30) == \
        pytest.approx(1_350_000)


def test_other_long_vs_short_horizon():
    long = T.post_tax_terminal(1_500_000, 1_000_000, "other", 3, slab=0.30)
    short = T.post_tax_terminal(1_500_000, 1_000_000, "other", 1, slab=0.30)
    assert long == pytest.approx(1_500_000 - 0.125 * 500_000)
    assert short == pytest.approx(1_500_000 - 0.30 * 500_000)
    assert long > short


def test_losses_are_never_taxed():
    assert T.post_tax_terminal(800_000, 1_000_000, "equity", 10) == 800_000
    assert T.post_tax_terminal(800_000, 1_000_000, "debt", 10) == 800_000


def test_vectorised_matches_scalar():
    arr = np.array([800_000.0, 1_100_000.0, 1_500_000.0, 3_000_000.0])
    vec = T.post_tax_terminal(arr, 1_000_000, "equity", 10)
    for a, v in zip(arr, vec):
        assert v == pytest.approx(T.post_tax_terminal(float(a), 1_000_000, "equity", 10))
    assert (vec <= arr).all()                       # tax never adds money


def test_apply_to_sim_posttax_probability():
    from mfrip.metrics import montecarlo as MC
    import pandas as pd
    rng = np.random.default_rng(6)
    nav = pd.Series(100 * np.cumprod(1 + rng.normal(0.009, 0.04, 119)),
                    index=pd.date_range("2010-01-31", periods=119, freq="ME"))
    sim = MC.simulate_sip(nav, 10_000, 10, n_sims=2000, seed=6, target=2_500_000)
    post = T.apply_to_sim(sim, "equity")
    assert post["terminal_pct"][50] <= sim["terminal_pct"][50]   # tax only reduces
    assert post["prob_target"] <= sim["prob_target"]             # goal is harder after tax
    assert 0.0 <= post["effective_tax_median"] < 0.2


def test_sleeve_mapping():
    assert T.asset_class_for_sleeve("midcap") == "equity"
    assert T.asset_class_for_sleeve("debt") == "debt"
    assert T.asset_class_for_sleeve("gold") == "other"
    assert T.asset_class_for_sleeve(None) == "other"
