from __future__ import annotations

import os

import numpy as np
import pandas as pd

from mfrip import ingest
from mfrip.store import nav_store
from mfrip.webapp import portfolio_lab as PL


def _seed(conn):
    rng = np.random.default_rng(3)
    def mk(code, ann, vol, start="2018-01-01"):
        ix = pd.date_range(start, "2026-06-19", freq="D")
        nav = 100 * np.cumprod(1 + rng.normal((1 + ann) ** (1 / 365) - 1, vol / np.sqrt(365), len(ix)))
        nav_store.upsert_nav(conn, code, [(x.date(), float(v)) for x, v in zip(ix, nav)])
        conn.execute("INSERT OR REPLACE INTO schemes(scheme_code,scheme_name) VALUES(?,?)", (code, f"Fund {code}"))
    mk(1, 0.11, 0.27); mk(2, 0.10, 0.26)
    mk(3, 0.13, 0.16, start="2020-01-01")  # younger
    conn.commit()


def _clean():
    for f in ("mfrip_data.db", "mfrip_data.db-wal", "mfrip_data.db-shm"):
        if os.path.exists(f):
            os.remove(f)


def test_head_to_head_uses_common_window():
    try:
        conn = ingest.open_store()
        _seed(conn)
        # fund 3 starts 2020 → common window should start no earlier than 2020
        h = PL.head_to_head(conn, [(1, 1.0)], [(3, 1.0)])
        assert h is not None
        ga, gb, sa, sb, (s, e) = h
        assert s >= pd.Timestamp("2020-01-01")
        assert abs(ga.iloc[0] - 100_000) < 1 and abs(gb.iloc[0] - 100_000) < 1
    finally:
        _clean()


def test_head_to_head_none_when_no_overlap():
    try:
        conn = ingest.open_store()
        rng = np.random.default_rng(1)
        ix1 = pd.date_range("2015-01-01", "2018-01-01", freq="D")
        ix2 = pd.date_range("2022-01-01", "2026-01-01", freq="D")
        for code, ix in [(10, ix1), (11, ix2)]:
            nav = 100 * np.cumprod(1 + rng.normal(0.0003, 0.01, len(ix)))
            nav_store.upsert_nav(conn, code, [(x.date(), float(v)) for x, v in zip(ix, nav)])
        assert PL.head_to_head(conn, [(10, 1.0)], [(11, 1.0)]) is None
    finally:
        _clean()


def test_correlation_guidance_flags_redundancy():
    idx = pd.date_range("2020-01-01", periods=40, freq="ME")
    base = pd.Series(np.cumsum(np.random.default_rng(0).normal(0, 1, 40)), index=idx)
    df = pd.DataFrame({"A": base, "B": base * 1.0 + 0.001, "C": base[::-1].values})
    corr = df.corr()
    lines = PL.correlation_guidance(corr)
    assert any("lockstep" in ln or "almost" in ln for ln in lines)
