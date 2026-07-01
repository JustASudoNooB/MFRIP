"""SQLite schema and connection helpers.

Two tables:
  schemes : the scheme master (universe metadata)
  nav     : (scheme_code, date) -> nav, the cached price history

NAV is cached locally so the metrics engine is fully reproducible and we
never re-hit mfapi for the same series. Dates are stored ISO (YYYY-MM-DD)
so lexicographic ordering equals chronological ordering.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS schemes (
    scheme_code     INTEGER PRIMARY KEY,
    scheme_name     TEXT NOT NULL,
    amc             TEXT,
    scheme_type     TEXT,
    scheme_category TEXT,
    isin_growth     TEXT,
    fetched_at      TEXT
);

CREATE TABLE IF NOT EXISTS nav (
    scheme_code INTEGER NOT NULL,
    date        TEXT NOT NULL,       -- ISO YYYY-MM-DD
    nav         REAL NOT NULL,
    PRIMARY KEY (scheme_code, date)
);

CREATE INDEX IF NOT EXISTS idx_nav_code ON nav (scheme_code);

CREATE TABLE IF NOT EXISTS recommendations (
    rec_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    creator         TEXT,              -- who published/featured it (e.g. Warikoo)
    advisor         TEXT,              -- who actually made the call (e.g. Feroz Aziz)
    source_platform TEXT,
    source_url      TEXT,
    rec_date        TEXT NOT NULL,     -- ISO YYYY-MM-DD
    risk_profile    TEXT,
    horizon         TEXT,
    rationale       TEXT,
    total_amount    REAL,
    created_at      TEXT
);

CREATE TABLE IF NOT EXISTS recommendation_funds (
    rec_id         INTEGER NOT NULL,
    display_name   TEXT NOT NULL,      -- name as written on the slide
    search_hint    TEXT,              -- override used to resolve the scheme code
    scheme_code    INTEGER,           -- resolved code (NULL until resolved)
    resolved_name  TEXT,
    weight         REAL NOT NULL,     -- fraction of total_amount (0..1)
    asset_class    TEXT,              -- equity / debt / gold / ...
    included       INTEGER DEFAULT 1, -- 0 = excluded from reconstruction
    note           TEXT,
    PRIMARY KEY (rec_id, display_name)
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    # check_same_thread=False: Streamlit re-runs the script across worker
    # threads and reuses one cached connection; our access is read-mostly and
    # serialised per session, so this is safe here and avoids a cross-thread crash.
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
