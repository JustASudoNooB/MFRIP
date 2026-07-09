"""Persistence: write scheme master / NAV to SQLite, load NAV as a pandas Series.

The load functions are the boundary between raw storage and the metrics
engine. A loaded NAV is a float Series indexed by a sorted DatetimeIndex,
de-duplicated on date. That is the only shape the metrics engine accepts.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

import pandas as pd


# --------------------------------------------------------------------------
# scheme master
# --------------------------------------------------------------------------
def upsert_scheme_list(conn: sqlite3.Connection, schemes: list[dict]) -> int:
    """Insert/refresh the universe list (code + name only, from /mf)."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = [
        (int(s["schemeCode"]), str(s["schemeName"]), now)
        for s in schemes
        if "schemeCode" in s and "schemeName" in s
    ]
    conn.executemany(
        """
        INSERT INTO schemes (scheme_code, scheme_name, fetched_at)
        VALUES (?, ?, ?)
        ON CONFLICT(scheme_code) DO UPDATE SET
            scheme_name = excluded.scheme_name,
            fetched_at  = excluded.fetched_at
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def update_scheme_meta(conn: sqlite3.Connection, scheme_code: int, meta: dict) -> None:
    """Enrich a scheme row with the richer metadata returned alongside NAVs."""
    conn.execute(
        """
        INSERT INTO schemes (scheme_code, scheme_name, amc, scheme_type,
                             scheme_category, isin_growth, fetched_at)
        VALUES (:code, :name, :amc, :stype, :scat, :isin, :now)
        ON CONFLICT(scheme_code) DO UPDATE SET
            scheme_name     = COALESCE(excluded.scheme_name, schemes.scheme_name),
            amc             = COALESCE(excluded.amc, schemes.amc),
            scheme_type     = COALESCE(excluded.scheme_type, schemes.scheme_type),
            scheme_category = COALESCE(excluded.scheme_category, schemes.scheme_category),
            isin_growth     = COALESCE(excluded.isin_growth, schemes.isin_growth),
            fetched_at      = excluded.fetched_at
        """,
        {
            "code": scheme_code,
            "name": meta.get("scheme_name"),
            "amc": meta.get("fund_house"),
            "stype": meta.get("scheme_type"),
            "scat": meta.get("scheme_category"),
            "isin": meta.get("isin_growth"),
            "now": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    conn.commit()


# --------------------------------------------------------------------------
# NAV
# --------------------------------------------------------------------------
def upsert_nav(conn: sqlite3.Connection, scheme_code: int, series: list[tuple[date, float]]) -> int:
    rows = [(int(scheme_code), d.isoformat(), float(v)) for d, v in series]
    conn.executemany(
        """
        INSERT INTO nav (scheme_code, date, nav) VALUES (?, ?, ?)
        ON CONFLICT(scheme_code, date) DO UPDATE SET nav = excluded.nav
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def load_nav(conn: sqlite3.Connection, scheme_code: int) -> pd.Series:
    """Load a cached NAV series as a float Series on a sorted DatetimeIndex.

    Uses the raw SQLite cursor rather than pandas.read_sql_query: the latter's
    parameter binding fails on some pandas builds (e.g. 3.0) with a SQLite
    'bad parameter or other API misuse' error.
    """
    rows = conn.execute(
        "SELECT date, nav FROM nav WHERE scheme_code = ? ORDER BY date",
        (int(scheme_code),),
    ).fetchall()
    if not rows:
        return pd.Series(dtype=float, name=str(scheme_code))
    idx = pd.DatetimeIndex(pd.to_datetime([r[0] for r in rows]))
    vals = [float(r[1]) for r in rows]
    s = pd.Series(vals, index=idx, name=str(scheme_code))
    return s[~s.index.duplicated(keep="last")].sort_index()


def has_nav(conn: sqlite3.Connection, scheme_code: int) -> bool:
    cur = conn.execute("SELECT 1 FROM nav WHERE scheme_code = ? LIMIT 1", (int(scheme_code),))
    return cur.fetchone() is not None
