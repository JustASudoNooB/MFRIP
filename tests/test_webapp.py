from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd
import pytest

from mfrip.store import db, nav_store
from mfrip.webapp import data as D


def _nav(values, start="2018-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="D")
    return pd.Series(values, index=idx, dtype=float)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.init_db(c)
    nav_store.upsert_scheme_list(c, [
        {"schemeCode": 1, "schemeName": "Alpha Fund - Direct - Growth"},
        {"schemeCode": 2, "schemeName": "Beta Fund - Direct - Growth"},
        {"schemeCode": 3, "schemeName": "No Data Fund"},
    ])
    rng = np.random.default_rng(0)
    a = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, 800))
    b = 100 * np.cumprod(1 + rng.normal(0.0003, 0.012, 800))
    idx = pd.date_range("2018-01-01", periods=800, freq="D")
    nav_store.upsert_nav(c, 1, [(d.date(), float(v)) for d, v in zip(idx, a)])
    nav_store.upsert_nav(c, 2, [(d.date(), float(v)) for d, v in zip(idx, b)])
    return c


def test_available_funds_only_with_nav(conn):
    funds = D.available_funds(conn)
    codes = [c for c, _ in funds]
    assert 1 in codes and 2 in codes
    assert 3 not in codes  # no NAV -> excluded


def test_window_stats_basic(conn):
    nav = D.load_nav(conn, 1)
    s = D.window_stats(nav, lookback_years=1.0)
    assert -1 < s.total_return < 5
    assert s.volatility >= 0
    assert s.max_drawdown <= 0
    assert s.n_days > 100


def test_growth_starts_at_base(conn):
    nav = D.load_nav(conn, 1)
    g = D.growth_of(nav, lookback_years=1.0, base=100_000)
    assert g.iloc[0] == pytest.approx(100_000)


def test_correlation_in_range(conn):
    c = D.correlation(D.load_nav(conn, 1), D.load_nav(conn, 2))
    assert -1.0 <= c <= 1.0


def test_explain_mentions_winner(conn):
    nav_a, nav_b = D.load_nav(conn, 1), D.load_nav(conn, 2)
    sa, sb = D.window_stats(nav_a, 2.0), D.window_stats(nav_b, 2.0)
    text = D.explain_comparison("Alpha", sa, "Beta", sb, D.correlation(nav_a, nav_b))
    assert "Alpha" in text and "Beta" in text
    assert "%" in text  # has numbers
