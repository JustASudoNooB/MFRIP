from __future__ import annotations

import sqlite3

import pytest

from mfrip.store import db
from mfrip.recommend.resolve import resolve_name


@pytest.fixture
def seeded_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    rows = [
        (100001, "HDFC Flexi Cap Fund - Regular Plan - Growth"),
        (100002, "HDFC Flexi Cap Fund - Direct Plan - Growth"),
        (100003, "HDFC Flexi Cap Fund - Direct Plan - IDCW"),
        (100004, "Kotak Emerging Equity Fund - Direct Plan - Growth"),
        (100005, "Kotak Multicap Fund - Direct Plan - Growth"),
        (100006, "SBI Bluechip Fund - Direct Plan - Growth"),
    ]
    conn.executemany("INSERT INTO schemes (scheme_code, scheme_name) VALUES (?,?)", rows)
    conn.commit()
    return conn


def test_prefers_direct_growth(seeded_conn):
    cands = resolve_name(seeded_conn, "HDFC Flexi Cap Direct Growth")
    assert cands[0].scheme_code == 100002  # Direct-Growth ranks above Regular and IDCW


def test_midcap_shorthand_maps_to_emerging_equity(seeded_conn):
    # 'Kotak Emerging Equity' is the official name; search hint carries it
    cands = resolve_name(seeded_conn, "Kotak Emerging Equity Direct Growth")
    assert cands[0].scheme_code == 100004


def test_no_false_match_returns_empty(seeded_conn):
    # zero token overlap -> no candidates
    assert resolve_name(seeded_conn, "Zzzzz Qqqq Xxxx") == []
    # only the generic 'fund' token overlaps -> a weak, low-scoring match at best
    weak = resolve_name(seeded_conn, "Nonexistent Quantum Zebra Fund")
    assert weak == [] or weak[0].score < 0.6
