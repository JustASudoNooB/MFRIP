"""Ingestion: the only place the network source meets the local cache.

Functions here are thin orchestration. They run in an open-network
environment (your machine), not in test fixtures. The metrics engine never
imports this module, so metric correctness is testable without a network.
"""
from __future__ import annotations

import sqlite3
import time

import requests

from .config import Config, DEFAULT_CONFIG
from .sources import mfapi
from .store import db, nav_store


def open_store(config: Config = DEFAULT_CONFIG) -> sqlite3.Connection:
    conn = db.connect(config.db_path)
    db.init_db(conn)
    return conn


def sync_scheme_master(conn: sqlite3.Connection, session: requests.Session | None = None) -> int:
    schemes = mfapi.fetch_scheme_list(session=session)
    return nav_store.upsert_scheme_list(conn, schemes)


def ingest_nav(
    conn: sqlite3.Connection,
    scheme_code: int,
    session: requests.Session | None = None,
    force: bool = False,
    retries: int = 4,
    backoff: float = 1.0,
) -> int:
    """Download and cache one scheme's NAV history.

    Retries on empty/failed responses (mfapi intermittently returns nothing
    under load), backing off a little longer each attempt. Skips if already
    cached unless force.
    """
    if not force and nav_store.has_nav(conn, scheme_code):
        return 0
    for attempt in range(max(1, retries)):
        try:
            meta, series = mfapi.fetch_nav_history(scheme_code, session=session)
        except Exception:
            meta, series = {}, []
        if series:
            if meta:
                nav_store.update_scheme_meta(conn, scheme_code, meta)
            return nav_store.upsert_nav(conn, scheme_code, series)
        if attempt < retries - 1:
            time.sleep(backoff * (attempt + 1))
    return 0


def ingest_many(
    conn: sqlite3.Connection,
    scheme_codes: list[int],
    sleep: float = 0.3,
    force: bool = False,
) -> dict[int, int]:
    """Bulk ingest with a polite delay between calls."""
    session = requests.Session()
    results: dict[int, int] = {}
    for code in scheme_codes:
        results[code] = ingest_nav(conn, code, session=session, force=force)
        time.sleep(sleep)
    return results
