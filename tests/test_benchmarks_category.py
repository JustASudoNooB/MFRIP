from __future__ import annotations
import os
import numpy as np, pandas as pd
from mfrip import ingest
from mfrip.store import nav_store
from mfrip.webapp import benchmarks as BM


def _clean():
    for f in ("mfrip_data.db", "mfrip_data.db-wal", "mfrip_data.db-shm"):
        if os.path.exists(f):
            os.remove(f)


def _add(conn, code, name):
    ix = pd.date_range("2020-01-01", "2026-06-19", freq="D")
    nav = 100 * np.cumprod(1 + np.random.default_rng(code % 97).normal(0.0003, 0.01, len(ix)))
    nav_store.upsert_nav(conn, code, [(d.date(), float(v)) for d, v in zip(ix, nav)])
    conn.execute("INSERT OR REPLACE INTO schemes(scheme_code,scheme_name) VALUES(?,?)", (code, name))


def test_category_benchmarks_resolve():
    try:
        conn = ingest.open_store()
        _add(conn, 120716, "UTI Nifty 50 Index Fund - Direct Plan - Growth")
        _add(conn, 147625, "Motilal Oswal Nifty 500 Index Fund - Direct Plan - Growth")
        _add(conn, 200001, "Motilal Oswal Nifty Midcap 150 Index Fund - Direct Plan - Growth")
        _add(conn, 200002, "Nippon India Nifty Smallcap 250 Index Fund - Direct Plan - Growth")
        conn.commit()
        assert BM.resolve_benchmark(conn, "largecap")[0] == 120716
        assert BM.resolve_benchmark(conn, "flexicap")[0] == 147625
        assert BM.resolve_benchmark(conn, "midcap")[0] == 200001
        assert BM.resolve_benchmark(conn, "smallcap")[0] == 200002
        # debt/gold get no equity benchmark
        assert BM.resolve_benchmark(conn, "debt") == (None, None)
        assert BM.resolve_benchmark(conn, "gold") == (None, None)
    finally:
        _clean()


def test_benchmark_falls_back_to_nifty_when_no_category_index():
    try:
        conn = ingest.open_store()
        _add(conn, 120716, "UTI Nifty 50 Index Fund - Direct Plan - Growth")
        conn.commit()
        # no midcap index cached → fall back to Nifty 50
        code, name = BM.resolve_benchmark(conn, "midcap")
        assert code == 120716
    finally:
        _clean()
