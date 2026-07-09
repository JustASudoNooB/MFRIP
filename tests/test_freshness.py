"""Tests for the daily NAV self-refresh mechanism."""
import datetime as dt

import pytest

import mfrip.ingest as ING
from mfrip.store import db as DB
from mfrip.webapp import freshness as FR


def _db(latest="2026-06-26", codes=(101, 102, 103)):
    conn = DB.connect(":memory:")
    DB.init_db(conn)
    for code in codes:
        conn.execute("INSERT INTO schemes (scheme_code, scheme_name) VALUES (?,?)",
                     (code, f"Fund {code}"))
        conn.executemany("INSERT INTO nav (scheme_code, date, nav) VALUES (?,?,?)",
                         [(code, "2026-06-24", 100.0), (code, latest, 101.0)])
    conn.commit()
    return conn


def test_latest_nav_date_and_cached_codes():
    conn = _db()
    assert FR.latest_nav_date(conn).date() == dt.date(2026, 6, 26)
    assert sorted(FR.cached_codes(conn)) == [101, 102, 103]
    empty = DB.connect(":memory:"); DB.init_db(empty)
    assert FR.latest_nav_date(empty) is None


def test_is_stale_boundaries():
    conn = _db(latest="2026-06-26")
    # a long weekend (up to MAX_AGE_DAYS behind) is not stale
    assert FR.is_stale(conn, today=dt.date(2026, 6, 30)) is False   # 4 days
    assert FR.is_stale(conn, today=dt.date(2026, 7, 1)) is True     # 5 days
    empty = DB.connect(":memory:"); DB.init_db(empty)
    assert FR.is_stale(empty, today=dt.date(2026, 7, 1)) is False   # bootstrap's case


def test_refresh_navs_counts_and_advances(monkeypatch):
    conn = _db()

    def fake_ingest(c, code, session=None, force=False, retries=1):
        if code == 102:
            raise RuntimeError("mfapi hiccup")
        c.execute("INSERT OR REPLACE INTO nav (scheme_code, date, nav) VALUES (?,?,?)",
                  (code, "2026-07-04", 102.0))
        return 1

    monkeypatch.setattr(ING, "ingest_nav", fake_ingest)
    out = FR.refresh_navs(conn, FR.cached_codes(conn))
    assert out["attempted"] == 3 and out["updated"] == 2 and out["failed"] == 1
    assert out["latest"].date() == dt.date(2026, 7, 4)             # data advanced


def test_refresh_if_stale_is_a_noop_when_fresh(monkeypatch):
    conn = _db(latest="2026-06-26")

    def must_not_run(*a, **k):
        raise AssertionError("refresh ran on fresh data")

    monkeypatch.setattr(ING, "ingest_nav", must_not_run)
    out = FR.refresh_if_stale(conn, today=dt.date(2026, 6, 28))
    assert out["ran"] is False and out["updated"] == 0


def test_refresh_if_stale_runs_when_stale(monkeypatch):
    conn = _db(latest="2026-06-20")
    calls = []

    def fake_ingest(c, code, session=None, force=False, retries=1):
        calls.append((code, force))
        c.execute("INSERT OR REPLACE INTO nav (scheme_code, date, nav) VALUES (?,?,?)",
                  (code, "2026-07-04", 102.0))
        return 1

    monkeypatch.setattr(ING, "ingest_nav", fake_ingest)
    out = FR.refresh_if_stale(conn, today=dt.date(2026, 7, 4))
    assert out["ran"] is True and out["updated"] == 3
    assert all(force for _c, force in calls)                       # full re-download
    # a failed source leaves the app standing: all fail, still returns a summary
    conn2 = _db(latest="2026-06-20")
    monkeypatch.setattr(ING, "ingest_nav",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    out2 = FR.refresh_if_stale(conn2, today=dt.date(2026, 7, 4))
    assert out2["ran"] is True and out2["updated"] == 0 and out2["failed"] == 3
