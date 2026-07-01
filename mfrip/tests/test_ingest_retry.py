from __future__ import annotations

import sqlite3
from unittest import mock

from mfrip import ingest
from mfrip.store import db


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.init_db(c)
    return c


def test_retry_then_success():
    conn = _conn()
    # first two calls return empty, third returns data
    from datetime import date
    calls = [({}, []), ({}, []), ({"scheme_name": "X"}, [(date(2025, 1, 1), 10.0)])]
    with mock.patch("mfrip.ingest.mfapi.fetch_nav_history", side_effect=calls), \
         mock.patch("mfrip.ingest.time.sleep"):
        n = ingest.ingest_nav(conn, 111, retries=4, backoff=0)
    assert n == 1  # eventually cached one row


def test_gives_up_after_retries():
    conn = _conn()
    with mock.patch("mfrip.ingest.mfapi.fetch_nav_history", return_value=({}, [])), \
         mock.patch("mfrip.ingest.time.sleep"):
        n = ingest.ingest_nav(conn, 222, retries=3, backoff=0)
    assert n == 0  # nothing cached, but no crash


def test_skips_if_already_cached():
    conn = _conn()
    from datetime import date
    from mfrip.store import nav_store
    nav_store.upsert_nav(conn, 333, [(date(2025, 1, 1), 5.0)])
    with mock.patch("mfrip.ingest.mfapi.fetch_nav_history") as m:
        n = ingest.ingest_nav(conn, 333)
    assert n == 0
    m.assert_not_called()  # cached -> no network
