from __future__ import annotations

import pytest

from mfrip.portfolio.benchmark import aggregate_asset_weights, proxy_weights
from mfrip.recommend.schema import RecFund, Recommendation


def _rec(funds):
    return Recommendation(creator="W", advisor="A", rec_date="2025-11-08", funds=funds)


def test_aggregate_renormalises_over_priced():
    rec = _rec([
        RecFund("e1", 0.35, "equity", scheme_code=1),
        RecFund("e2", 0.35, "equity", scheme_code=2),
        RecFund("d1", 0.20, "debt", scheme_code=3),
        RecFund("excl", 0.10, "debt", scheme_code=None, included=False),
    ])
    w = aggregate_asset_weights(rec)
    assert w["equity"] == pytest.approx(0.70 / 0.90)  # renormalised over priced 0.90
    assert w["debt"] == pytest.approx(0.20 / 0.90)


def test_proxy_weights_split_hybrid():
    pw = proxy_weights({"hybrid": 1.0}, hybrid_split=(0.65, 0.35))
    assert pw["equity"] == pytest.approx(0.65)
    assert pw["debt"] == pytest.approx(0.35)


def test_proxy_weights_drop_alternatives_and_renormalise():
    pw = proxy_weights({"equity": 0.8, "alternatives": 0.2})
    assert pw["equity"] == pytest.approx(1.0)  # alternatives dropped, equity renormalised
    assert "gold" not in pw


def test_proxy_weights_sum_to_one():
    pw = proxy_weights({"equity": 0.6, "debt": 0.2, "gold": 0.1, "hybrid": 0.1})
    assert sum(pw.values()) == pytest.approx(1.0)
