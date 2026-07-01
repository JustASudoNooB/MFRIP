"""Leaderboard, how a user's portfolio stacks up against the advised plans.

Reconstructs every advised plan (the audited recommendations) and the user's
portfolio over the SAME window, then ranks them on standardised metrics. This is
the 'audit my own portfolio alongside the gurus' feature.
"""
from __future__ import annotations

import sqlite3

from ..config import DEFAULT_CONFIG, Config
from ..recommend import schema as RSCHEMA
from . import portfolio_lab as PL


def advised_holdings(conn: sqlite3.Connection, rec_id: int) -> list[tuple[int, float]]:
    rec = RSCHEMA.load_recommendation(conn, int(rec_id))
    return [(f.scheme_code, f.weight) for f in rec.funds if f.included and f.scheme_code]


def leaderboard(conn: sqlite3.Connection, user_holdings: list[tuple[int, float]],
                advised: list[tuple[int, str]], lookback: float = 3.0,
                benchmark_code: int = 120716, config: Config = DEFAULT_CONFIG) -> list[dict]:
    """advised: list of (rec_id, label). Returns ranked rows (best Sharpe first),
    each {name, is_user, cagr, volatility, sharpe, max_drawdown}."""
    rows = []
    for rid, label in advised:
        h = advised_holdings(conn, rid)
        if not h:
            continue
        res = PL.analyze(conn, h, lookback, benchmark_code, config)
        if res:
            s = res["stats"]
            rows.append({"name": label, "is_user": False, "cagr": s.cagr,
                         "volatility": s.volatility, "sharpe": s.sharpe,
                         "max_drawdown": s.max_drawdown})
    if user_holdings:
        res = PL.analyze(conn, user_holdings, lookback, benchmark_code, config)
        if res:
            s = res["stats"]
            rows.append({"name": "★ Your portfolio", "is_user": True, "cagr": s.cagr,
                         "volatility": s.volatility, "sharpe": s.sharpe,
                         "max_drawdown": s.max_drawdown})
    rows.sort(key=lambda r: (r["sharpe"] if r["sharpe"] == r["sharpe"] else -99), reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows
