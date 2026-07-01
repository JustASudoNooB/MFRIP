from __future__ import annotations

import os

import numpy as np
import pandas as pd

from mfrip import ingest
from mfrip.store import nav_store, saved


def _clean():
    for f in ("mfrip_data.db", "mfrip_data.db-wal", "mfrip_data.db-shm"):
        if os.path.exists(f):
            os.remove(f)


def test_saved_portfolio_roundtrip():
    try:
        conn = ingest.open_store()
        h = [(120716, 0.6, "UTI Nifty 50"), (150847, 0.4, "HDFC Gilt")]
        pid = saved.save_portfolio(conn, "Test", h)
        assert pid > 0
        lst = saved.list_portfolios(conn)
        assert len(lst) == 1 and lst[0]["name"] == "Test"
        loaded = saved.load_portfolio(conn, pid)
        assert loaded["holdings"][0][0] == 120716
        assert abs(loaded["holdings"][0][1] - 0.6) < 1e-9
        saved.delete_portfolio(conn, pid)
        assert saved.list_portfolios(conn) == []
    finally:
        _clean()


def test_saved_table_created_on_existing_db():
    # listing before any save should auto-create the table and return []
    try:
        conn = ingest.open_store()
        assert saved.list_portfolios(conn) == []
    finally:
        _clean()


def test_leaderboard_ranks_and_marks_user():
    from mfrip.recommend import schema
    from mfrip.webapp import leaderboard as LB

    def mk(conn, code, ann, vol):
        ix = pd.date_range("2019-01-01", "2026-06-19", freq="D")
        rng = np.random.default_rng(code)
        nav = 100 * np.cumprod(1 + rng.normal((1 + ann) ** (1 / 365) - 1, vol / np.sqrt(365), len(ix)))
        nav_store.upsert_nav(conn, code, [(x.date(), float(v)) for x, v in zip(ix, nav)])

    try:
        conn = ingest.open_store()
        for c, a, v in [(120716, 0.11, 0.15), (150847, 0.06, 0.04), (500, 0.14, 0.18), (501, 0.07, 0.05)]:
            mk(conn, c, a, v)
        # a minimal advised plan saved into the DB
        from mfrip.recommend.schema import Recommendation, RecFund
        rec = Recommendation(creator="me", advisor="Test Advisor", rec_date="2023-01-01",
                             risk_profile="Moderate", funds=[
            RecFund(display_name="A", weight=0.6, scheme_code=500, included=True),
            RecFund(display_name="B", weight=0.4, scheme_code=501, included=True),
        ])
        rid = schema.save_recommendation(conn, rec)
        board = LB.leaderboard(conn, [(120716, 0.7), (150847, 0.3)], [(rid, "Test Plan")], lookback=3.0)
        assert any(r["is_user"] for r in board)
        sharpes = [r["sharpe"] for r in board]
        assert sharpes == sorted(sharpes, reverse=True)
        assert all("rank" in r for r in board)
    finally:
        _clean()
