"""Category-matched benchmarks.

Judging a mid-cap fund against the Nifty 50 lets the mid-cap premium masquerade
as manager skill. This resolves the RIGHT index for a fund's category: a
mid-cap fund vs a Nifty Midcap 150 index fund, small-cap vs Nifty Smallcap 250,
flexi vs Nifty 500, so capture ratios and outperformance reflect skill, not
cap-tilt. Resolution searches the user's own scheme list (robust to code
changes) and falls back to the Nifty 50 if nothing suitable is cached.
"""
from __future__ import annotations

import sqlite3

from . import data as D

NIFTY50 = 120716

# sleeve -> (preferred direct code or None, display name, search query, is_equity)
_CATEGORY = {
    "largecap":      (NIFTY50, "Nifty 50", "nifty 50 index fund direct", True),
    "flexicap":      (147625, "Nifty 500", "nifty 500 index fund direct", True),
    "midcap":        (None, "Nifty Midcap 150", "nifty midcap 150 index fund direct", True),
    "smallcap":      (None, "Nifty Smallcap 250", "nifty smallcap 250 index fund direct", True),
    "international": (None, "Nasdaq 100", "nasdaq 100 fund direct", True),
    "debt":          (None, None, None, False),
    "gold":          (None, None, None, False),
}


def _search_index_fund(conn: sqlite3.Connection, query: str) -> int | None:
    matches = D.search_schemes(conn, query, limit=15)
    if not matches:
        return None
    # prefer names that look like an index fund, ideally a Direct plan
    idx = [(c, n) for c, n in matches if "index" in n.lower()]
    pool = idx or matches
    direct = [(c, n) for c, n in pool if "direct" in n.lower()]
    return (direct or pool)[0][0]


def resolve_benchmark(conn: sqlite3.Connection, sleeve: str | None) -> tuple[int | None, str | None]:
    """Return (benchmark_code, display_name) for a fund's sleeve. (None, None)
    means no equity benchmark applies (debt/gold). Ensures the NAV is cached."""
    spec = _CATEGORY.get(sleeve or "")
    if not spec:
        if D.ensure_nav(conn, NIFTY50):
            return NIFTY50, "Nifty 50"
        return None, None
    code, name, query, is_equity = spec
    if not is_equity:
        return None, None
    # try the preferred direct code first
    if code and D.ensure_nav(conn, code):
        return code, name
    # otherwise resolve from the user's scheme list
    if query:
        found = _search_index_fund(conn, query)
        if found and D.ensure_nav(conn, found):
            return found, name
    # fall back to the broad market
    if D.ensure_nav(conn, NIFTY50):
        return NIFTY50, "Nifty 50 (no category index cached)"
    return None, None
