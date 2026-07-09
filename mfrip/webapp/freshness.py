"""Keeps cached NAVs current on a running server.

The deployed app ships with a snapshot database. This module checks how old
that snapshot is and, when it has fallen behind, re-downloads NAV history for
the cached funds from mfapi.in. It is deliberately conservative and honest:

- **Staleness threshold.** Indian funds publish NAVs on business days, so a
  gap of a weekend (2-3 days) is normal. Data counts as stale only when the
  newest NAV anywhere is more than MAX_AGE_DAYS behind today.
- **Fail fast, never block.** Each fund gets one quick attempt (no long retry
  backoff). If the source is unreachable the app still opens with the data it
  has, and the UI says so plainly instead of pretending.
- **Once a day.** The app wraps refresh_if_stale in a per-day cache, so one
  visitor pays the update cost and everyone else that day gets it free.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

import pandas as pd

MAX_AGE_DAYS = 4  # a long weekend is fine; beyond this we call it stale


def latest_nav_date(conn: sqlite3.Connection):
    """Newest NAV date anywhere in the database, or None if empty."""
    row = conn.execute("SELECT MAX(date) FROM nav").fetchone()
    return pd.Timestamp(row[0]) if row and row[0] else None


def cached_codes(conn: sqlite3.Connection) -> list[int]:
    """Scheme codes that have any NAV history cached."""
    rows = conn.execute("SELECT DISTINCT scheme_code FROM nav").fetchall()
    return [int(r[0]) for r in rows]


def is_stale(conn: sqlite3.Connection, max_age_days: int = MAX_AGE_DAYS,
             today: dt.date | None = None) -> bool:
    latest = latest_nav_date(conn)
    if latest is None:
        return False  # nothing cached yet; bootstrap owns that case
    today = today or dt.date.today()
    return (today - latest.date()).days > max_age_days


def refresh_navs(conn: sqlite3.Connection, codes: list[int]) -> dict:
    """Re-download NAV history for `codes`. One fast attempt per fund.

    Returns {"attempted", "updated", "failed", "latest"}. Never raises for a
    single fund's failure; the app must open regardless.
    """
    from ..ingest import ingest_nav
    updated = failed = 0
    for code in codes:
        try:
            rows = ingest_nav(conn, int(code), force=True, retries=1)
            if rows > 0:
                updated += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    return {"attempted": len(codes), "updated": updated, "failed": failed,
            "latest": latest_nav_date(conn)}


def refresh_if_stale(conn: sqlite3.Connection, max_age_days: int = MAX_AGE_DAYS,
                     today: dt.date | None = None) -> dict:
    """Refresh all cached funds when the snapshot is stale; otherwise no-op.

    Returns a summary either way, with "ran" telling the app whether anything
    was attempted (so it knows whether to clear its own caches).
    """
    if not is_stale(conn, max_age_days, today=today):
        return {"ran": False, "attempted": 0, "updated": 0, "failed": 0,
                "latest": latest_nav_date(conn)}
    out = refresh_navs(conn, cached_codes(conn))
    out["ran"] = True
    return out
