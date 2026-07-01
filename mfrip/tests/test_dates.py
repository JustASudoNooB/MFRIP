from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mfrip.webapp import data as D


def _nav(start, periods=600, drift=0.0003):
    ix = pd.date_range(start, periods=periods, freq="D")
    vals = 100 * np.cumprod(1 + np.full(periods, drift))
    return pd.Series(vals, index=ix)


def test_inception_is_first_date():
    nav = _nav("2019-05-01")
    assert D.inception(nav) == pd.Timestamp("2019-05-01")


def test_inception_empty():
    assert D.inception(pd.Series(dtype=float)) is None


def test_stats_between_range():
    nav = _nav("2020-01-01", periods=900)
    s = D.stats_between(nav, "2020-06-01", "2021-06-01")
    assert s.start >= "2020-06-01" and s.end <= "2021-06-01"
    assert s.total_return > 0  # positive drift
    assert s.n_days > 100


def test_stats_between_too_short():
    nav = _nav("2020-01-01")
    with pytest.raises(ValueError):
        D.stats_between(nav, "2020-01-01", "2020-01-01")


def test_growth_between_starts_at_base():
    nav = _nav("2020-01-01", periods=800)
    g = D.growth_between(nav, "2020-03-01", "2021-03-01", base=100_000)
    assert abs(g.iloc[0] - 100_000) < 1e-6
    assert g.index[0] >= pd.Timestamp("2020-03-01")
