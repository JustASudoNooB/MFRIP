from __future__ import annotations

import os

import numpy as np
import pandas as pd

from mfrip.metrics import analytics as A


def _nav(ann, vol, start="2017-01-01", end="2026-06-19", seed=0):
    ix = pd.date_range(start, end, freq="D")
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.cumprod(1 + rng.normal((1 + ann) ** (1 / 365) - 1, vol / np.sqrt(365), len(ix))), index=ix)


def test_rolling_returns_shape():
    r = A.rolling_returns(_nav(0.12, 0.18), 3)
    assert r["count"] > 0
    assert r["worst"] <= r["avg"] <= r["best"]
    assert 0 <= r["pct_positive"] <= 1


def test_rolling_returns_beat_benchmark():
    r = A.rolling_returns(_nav(0.15, 0.18, seed=1), 1, benchmark=_nav(0.08, 0.15, seed=2))
    assert r["pct_beat_benchmark"] is None or 0 <= r["pct_beat_benchmark"] <= 1


def test_rolling_returns_too_short():
    assert A.rolling_returns(_nav(0.1, 0.15, start="2025-01-01"), 5) is None


def test_capture_directionality():
    ix = pd.date_range("2018-01-01", "2026-06-19", freq="ME")
    rng = np.random.default_rng(3)
    br = rng.normal(0.009, 0.045, len(ix))
    bench = pd.Series(100 * np.cumprod(1 + br), index=ix)
    aggressive = pd.Series(100 * np.cumprod(1 + 1.2 * br + 0.001), index=ix)
    defensive = pd.Series(100 * np.cumprod(1 + 0.7 * br + 0.0005), index=ix)
    ua, da = A.capture_ratios(aggressive, bench)
    ud, dd = A.capture_ratios(defensive, bench)
    assert ua > 110 and ud < 90          # aggressive captures more upside than defensive
    assert da > dd                        # aggressive captures more downside too


def test_sip_xirr_positive_for_rising_fund():
    s = A.sip_xirr(_nav(0.14, 0.16), 10_000)
    assert s is not None and s["xirr"] > 0
    assert s["invested"] == 10_000 * s["months"]


def test_stress_table_covers_episodes():
    rows = A.stress_table(_nav(0.1, 0.2))
    names = [r[0] for r in rows]
    assert "COVID crash" in names and "2022 rate-hike drawdown" in names
    for _, ret, mdd in rows:
        assert mdd <= 0  # drawdown is non-positive


def test_category_benchmark_resolves():
    import sqlite3
    from mfrip.store import db
    from mfrip.webapp.data import category_benchmark
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    for code, name in [(1, "Motilal Oswal Nifty Midcap 150 Index Fund - Direct Growth"),
                       (2, "UTI Nifty 50 Index Fund - Direct Growth")]:
        conn.execute("INSERT INTO schemes(scheme_code,scheme_name) VALUES(?,?)", (code, name))
    conn.commit()
    assert category_benchmark(conn, "midcap") == 1      # matches the midcap 150 index
    assert category_benchmark(conn, "largecap") == 2    # matches nifty 50 index
    assert category_benchmark(conn, "gold", fallback=99) == 99  # no gold fund → fallback
