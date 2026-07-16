"""Tests for the seed-universe builder and the correlation common-window fix."""
import numpy as np
import pandas as pd

import mfrip.ingest as ING
from mfrip import universe as U
from mfrip.store import db as DB
from mfrip.webapp import portfolio_lab as PL


def _master_db():
    conn = DB.connect(":memory:")
    DB.init_db(conn)
    rows = []
    code = 100000
    for amc in ("Alpha", "Beta", "Gamma", "Delta"):
        for cat in ("Large Cap", "Flexi Cap", "Mid Cap", "Small Cap", "Gilt", "Gold ETF FoF"):
            rows.append((code, f"{amc} {cat} Fund - Direct Plan - Growth")); code += 1
            rows.append((code, f"{amc} {cat} Fund - Regular Plan - Growth")); code += 1
            rows.append((code, f"{amc} {cat} Fund - Direct Plan - IDCW")); code += 1
            rows.append((code, f"{amc} {cat} Fund - Direct Plan - Growth - Bonus Option")); code += 1
    conn.executemany("INSERT INTO schemes (scheme_code, scheme_name) VALUES (?,?)", rows)
    conn.commit()
    return conn


def test_eligibility_filters_share_classes():
    assert U._eligible("X Large Cap Fund - Direct Plan - Growth")
    assert not U._eligible("X Large Cap Fund - Regular Plan - Growth")
    assert not U._eligible("X Large Cap Fund - Direct Plan - IDCW")
    assert not U._eligible("X Fund - Direct Plan - Growth - Bonus Option")
    assert not U._eligible("X Fund - Direct Plan - Dividend Payout")


def test_select_universe_caps_and_determinism():
    conn = _master_db()
    a = U.select_universe(conn, target=20, seed=42)
    b = U.select_universe(conn, target=20, seed=42)
    assert a == b                                              # deterministic
    flat = [c for lst in a.values() for c, _n in lst]
    assert len(flat) == len(set(flat))                         # no duplicates
    for sl, lst in a.items():
        for _c, name in lst:
            assert U._eligible(name)


def test_build_universe_fetches_and_prunes(monkeypatch):
    conn = _master_db()
    fetched = []

    def fake_ingest(c, code, session=None, force=False, retries=1):
        fetched.append(code)
        # most funds get fresh history; every 7th is a dormant plan
        end = "2020-01-31" if code % 7 == 0 else "2026-07-10"
        dates = pd.bdate_range("2018-01-01", end)
        c.executemany("INSERT OR REPLACE INTO nav (scheme_code, date, nav) VALUES (?,?,?)",
                      [(code, d.strftime("%Y-%m-%d"), 100.0 + i * 0.01)
                       for i, d in enumerate(dates)])
        return len(dates)

    monkeypatch.setattr(ING, "ingest_nav", fake_ingest)
    out = U.build_universe(conn, target=24, delay=0.0, log=lambda *a, **k: None)
    assert out["downloaded"] == len(fetched) > 0
    assert out["failed"] == 0
    assert out["dropped_stale"] >= 1                           # dormant plans pruned
    # nothing stale remains cached
    latest = conn.execute("SELECT MAX(date) FROM nav").fetchone()[0]
    worst = conn.execute(
        "SELECT MIN(d) FROM (SELECT MAX(date) AS d FROM nav GROUP BY scheme_code)").fetchone()[0]
    assert (pd.Timestamp(latest) - pd.Timestamp(worst)).days <= U.STALE_CUTOFF_DAYS
    # resumable: a second run downloads nothing new
    n_before = len(fetched)
    U.build_universe(conn, target=24, delay=0.0, log=lambda *a, **k: None)
    assert len(fetched) == n_before + out["dropped_stale"]     # only re-tries pruned ones


def test_correlation_excludes_stale_and_reports():
    conn = DB.connect(":memory:"); DB.init_db(conn)
    rng = np.random.default_rng(3)

    def add(code, name, start, end):
        dates = pd.bdate_range(start, end)
        nav = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, len(dates)))
        conn.execute("INSERT INTO schemes (scheme_code, scheme_name) VALUES (?,?)", (code, name))
        conn.executemany("INSERT INTO nav (scheme_code, date, nav) VALUES (?,?,?)",
                         [(code, d.strftime("%Y-%m-%d"), float(v)) for d, v in zip(dates, nav)])

    add(1, "Fresh A", "2019-01-01", "2026-07-10")
    add(2, "Fresh B", "2019-01-01", "2026-07-10")
    add(3, "Stale Bonus Plan", "2015-01-01", "2021-03-31")
    conn.commit()
    names = {1: "Fresh A", 2: "Fresh B", 3: "Stale Bonus Plan"}
    cm = PL.correlation_matrix(conn, [1, 2, 3], names, 3.0)
    assert cm is not None
    assert list(cm.columns) == ["Fresh A", "Fresh B"]          # stale fund out
    assert "Stale Bonus Plan" in cm.attrs["excluded"]
    assert not cm.isna().any().any()                           # never a blank grid
