"""Seed-universe builder: grow the cached fund set to a broad, curated universe.

The screener can only compare funds whose NAV history is cached. This module
selects a representative universe from the full scheme master (37,000+ names)
and bulk-downloads their histories, so the deployed database ships with
hundreds of comparable funds instead of a handful.

Curation rules, stated plainly:
- Direct plans, Growth option only: one clean share class per fund, no
  regular-plan double counting, no IDCW/dividend/bonus variants (those have
  distorted NAV paths and several are discontinued).
- Spread across categories using the same sleeve inference the advisor uses,
  with per-sleeve caps scaled to the requested target.
- Deterministic selection (seeded shuffle within each sleeve), so two people
  running the same command get the same universe.
- After fetching, funds whose newest NAV is more than STALE_CUTOFF_DAYS old
  (discontinued or dormant plans) are dropped from the cache rather than left
  to sit blank in the screener.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta

import numpy as np

from .advisor.categorize import infer_sleeve

EXCLUDE_TOKENS = ("idcw", "dividend", "bonus", "segregated", "regular plan",
                  "- regular", "(regular", "payout", "reinvestment")
REQUIRE_TOKENS = ("direct", "growth")
STALE_CUTOFF_DAYS = 45

# relative weight of each category in the universe (scaled to --target)
SLEEVE_WEIGHTS = {
    "largecap": 0.14, "flexicap": 0.16, "midcap": 0.12, "smallcap": 0.12,
    "international": 0.08, "debt": 0.22, "gold": 0.03, "other": 0.13,
}


def _eligible(name: str) -> bool:
    low = name.lower()
    if any(tok in low for tok in EXCLUDE_TOKENS):
        return False
    return all(tok in low for tok in REQUIRE_TOKENS)


def select_universe(conn: sqlite3.Connection, target: int = 500,
                    seed: int = 42) -> dict[str, list[tuple[int, str]]]:
    """Pick up to `target` scheme codes from the master, grouped by sleeve.

    Already-cached funds count toward each sleeve's cap (they are kept, not
    duplicated), so re-running with a bigger target only ADDS funds.
    """
    rows = conn.execute("SELECT scheme_code, scheme_name FROM schemes").fetchall()
    cached = {int(r[0]) for r in
              conn.execute("SELECT DISTINCT scheme_code FROM nav").fetchall()}

    by_sleeve: dict[str, list[tuple[int, str]]] = {}
    for code, name in rows:
        if not _eligible(name):
            continue
        sl = infer_sleeve(name) or "other"
        by_sleeve.setdefault(sl, []).append((int(code), name))

    rng = np.random.default_rng(seed)
    picks: dict[str, list[tuple[int, str]]] = {}
    for sl, weight in SLEEVE_WEIGHTS.items():
        pool = by_sleeve.get(sl, [])
        cap = max(3, round(target * weight))
        already = [p for p in pool if p[0] in cached]
        fresh_pool = [p for p in pool if p[0] not in cached]
        order = rng.permutation(len(fresh_pool))
        chosen = already[:cap]
        for i in order:
            if len(chosen) >= cap:
                break
            chosen.append(fresh_pool[int(i)])
        if chosen:
            picks[sl] = chosen
    return picks


def build_universe(conn: sqlite3.Connection, target: int = 500, seed: int = 42,
                   delay: float = 0.15, log=print) -> dict:
    """Fetch NAV history for the selected universe. Resumable and polite.

    Already-cached funds are skipped, so an interrupted run continues where it
    stopped. A small delay between downloads keeps the free API happy.
    """
    import requests

    from .ingest import ingest_nav

    picks = select_universe(conn, target=target, seed=seed)
    todo = [(code, name, sl) for sl, lst in picks.items() for code, name in lst]
    cached = {int(r[0]) for r in
              conn.execute("SELECT DISTINCT scheme_code FROM nav").fetchall()}
    fetch_list = [(c, n, s) for c, n, s in todo if c not in cached]

    log(f"Universe: {len(todo)} funds selected across {len(picks)} categories; "
        f"{len(todo) - len(fetch_list)} already cached, {len(fetch_list)} to download.")

    session = requests.Session()
    ok = failed = 0
    for i, (code, name, _sl) in enumerate(fetch_list, 1):
        try:
            ingest_nav(conn, code, session=session, retries=2)
            ok += 1
        except Exception:
            failed += 1
        if i % 20 == 0 or i == len(fetch_list):
            log(f"  {i}/{len(fetch_list)} downloaded ({failed} failed so far)")
        time.sleep(delay)

    dropped = prune_stale(conn, log=log)
    conn.commit()
    total = conn.execute("SELECT COUNT(DISTINCT scheme_code) FROM nav").fetchone()[0]
    return {"selected": len(todo), "downloaded": ok, "failed": failed,
            "dropped_stale": dropped, "total_cached": int(total)}


def prune_stale(conn: sqlite3.Connection, cutoff_days: int = STALE_CUTOFF_DAYS,
                log=print) -> int:
    """Remove funds whose newest NAV is ancient: discontinued or dormant plans.

    They cannot be compared to anything current, and each one shows up as a
    row of blanks in the screener, so the honest move is not to carry them.
    """
    latest = conn.execute("SELECT MAX(date) FROM nav").fetchone()[0]
    if not latest:
        return 0
    cut = (datetime.strptime(latest, "%Y-%m-%d") - timedelta(days=cutoff_days)
           ).strftime("%Y-%m-%d")
    stale = [int(r[0]) for r in conn.execute(
        "SELECT scheme_code, MAX(date) AS d FROM nav GROUP BY scheme_code HAVING d < ?",
        (cut,)).fetchall()]
    for code in stale:
        conn.execute("DELETE FROM nav WHERE scheme_code = ?", (code,))
    if stale:
        log(f"Dropped {len(stale)} stale/discontinued fund(s) from the cache.")
    return len(stale)
