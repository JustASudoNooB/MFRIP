from __future__ import annotations

import sqlite3
from datetime import date
from unittest import mock

from mfrip import ingest
from mfrip.store import db, nav_store
from mfrip.webapp import data as D


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.init_db(c)
    for code, name in [
        (122639, "Parag Parikh Flexi Cap Fund - Direct Plan - Growth"),
        (120716, "UTI Nifty 50 Index Fund - Direct Plan - Growth"),
        (999001, "Some Fund - Regular Plan - IDCW"),
    ]:
        c.execute("INSERT INTO schemes(scheme_code,scheme_name) VALUES(?,?)", (code, name))
    c.commit()
    return c


def test_search_multiword_and():
    conn = _conn()
    res = D.search_schemes(conn, "parag flexi")
    assert len(res) == 1 and res[0][0] == 122639


def test_search_includes_variants():
    conn = _conn()
    assert any("IDCW" in n for _, n in D.search_schemes(conn, "idcw"))


def test_search_empty_query():
    conn = _conn()
    assert D.search_schemes(conn, "   ") == []


def test_count_schemes():
    assert D.count_schemes(_conn()) == 3


def test_ensure_nav_fetches_then_caches():
    conn = _conn()
    series = [(date(2025, 1, 1), 10.0), (date(2025, 1, 2), 10.1)]
    with mock.patch("mfrip.ingest.mfapi.fetch_nav_history", return_value=({}, series)), \
         mock.patch("mfrip.ingest.time.sleep"):
        assert D.ensure_nav(conn, 122639) is True
    # cached now → no network on second call
    with mock.patch("mfrip.ingest.mfapi.fetch_nav_history",
                    side_effect=AssertionError("should not hit network")):
        assert D.ensure_nav(conn, 122639) is True
