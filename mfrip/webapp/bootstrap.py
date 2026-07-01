"""First-run bootstrap.

On a fresh server (e.g. Streamlit Community Cloud, whose filesystem starts empty
and is wiped on restart) the SQLite DB has no data. This populates the minimum
needed for the app to work: the scheme master, the bundled advised plans, and
the NAV history for those plans' funds and the benchmark, by calling the same
tested ingest functions the CLI uses. It is safe to call on every start: each
step is skipped if already done.
"""
from __future__ import annotations

import glob
import os
import sqlite3

from .. import ingest
from ..recommend import loader, schema
from ..store import nav_store

NIFTY50 = 120716


def needs_bootstrap(conn: sqlite3.Connection) -> bool:
    """True if the DB is missing the fund master OR the advised plans.

    Checking recommendations (not just schemes) matters when a partially-built
    database is deployed: it may already hold the scheme master yet have no
    advised plans loaded, in which case the audit and research features would
    show nothing until we load them.
    """
    try:
        schemes = conn.execute("SELECT COUNT(*) FROM schemes").fetchone()[0]
        recs = conn.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0]
    except sqlite3.OperationalError:
        return True
    return schemes == 0 or recs == 0


def bootstrap(conn: sqlite3.Connection, recs_dir: str = "recommendations",
              benchmark: int = NIFTY50, progress=None) -> list[str]:
    """Populate scheme master + advised plans + their NAVs. Returns step log.
    `progress` is an optional callback(str) for UI updates."""
    def say(m):
        if progress:
            progress(m)

    done: list[str] = []

    # 1) scheme master (one API call returning the full list)
    if conn.execute("SELECT COUNT(*) FROM schemes").fetchone()[0] == 0:
        say("Downloading the fund master list…")
        n = ingest.sync_scheme_master(conn)
        done.append(f"Synced {n:,} schemes")

    # 2) advised plans (bundled YAML): resolve fund codes and store
    have_recs = conn.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0]
    if have_recs == 0 and os.path.isdir(recs_dir):
        paths = sorted(glob.glob(os.path.join(recs_dir, "*.yaml")))
        if paths:
            say(f"Loading {len(paths)} advised plans…")
            for p in paths:
                rec = loader.parse_yaml(p)
                loader.auto_resolve(conn, rec)
                schema.save_recommendation(conn, rec)
            done.append(f"Loaded {len(paths)} advised plans")

    # 3) NAV history for the plans' funds + the benchmark
    codes: set[int] = {benchmark}
    for r in conn.execute("SELECT rec_id FROM recommendations").fetchall():
        rec = schema.load_recommendation(conn, r["rec_id"])
        codes.update(f.scheme_code for f in rec.funds if f.included and f.scheme_code)
    todo = [c for c in sorted(codes) if not nav_store.has_nav(conn, c)]
    if todo:
        say(f"Downloading NAV history for {len(todo)} funds (first run only)…")
        ingest.ingest_many(conn, todo, sleep=0.3)
        done.append(f"Fetched NAV history for {len(todo)} funds")

    return done
