"""Historical backtest: how would this allocation have behaved over the last
1 / 3 / 5 years, across bull and bear stretches?

The forward audit only sees the ~7 months since the recommendation. This runs
the SAME allocation backward over longer windows (using each fund's real
history) so you can see regime behaviour. Funds without enough history for a
window are dropped and the dropped fraction reported, never back-filled.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import pandas as pd

from ..config import ASSET_PROXIES, DEFAULT_CONFIG, Config
from ..store import nav_store
from . import benchmark as bmk
from .reconstruct import reconstruct
from ..webapp.data import window_stats  # reuse the windowed stats helper


@dataclass
class BacktestRow:
    window: str
    start: str
    plan_return: float
    plan_vol: float
    plan_sharpe: float
    plan_maxdd: float
    passive_return: float | None
    excess_vs_passive: float | None
    dropped_weight: float   # plan weight dropped for lack of history in window


def _eligible(conn, rec, window_start: pd.Timestamp):
    """Funds with NAV history reaching back to window_start; renormalised."""
    nav_by_code, weights, kept = {}, {}, 0.0
    total = 0.0
    for f in rec.funds:
        if not (f.included and f.scheme_code):
            continue
        total += f.weight
        s = nav_store.load_nav(conn, f.scheme_code)
        if s.empty or s.index[0] > window_start:
            continue
        nav_by_code[f.scheme_code] = s
        weights[f.scheme_code] = weights.get(f.scheme_code, 0.0) + f.weight
        kept += f.weight
    dropped = 1.0 - (kept / total) if total > 0 else 1.0
    return nav_by_code, weights, dropped


def backtest(
    conn: sqlite3.Connection,
    rec,
    windows_years=(1.0, 3.0, 5.0),
    proxies=ASSET_PROXIES,
    config: Config = DEFAULT_CONFIG,
    amount: float = 1_000_000.0,
) -> list[BacktestRow]:
    # end date = latest date common to the plan's funds
    last_dates = [
        nav_store.load_nav(conn, f.scheme_code).index[-1]
        for f in rec.funds
        if f.included and f.scheme_code and not nav_store.load_nav(conn, f.scheme_code).empty
    ]
    if not last_dates:
        return []
    end = min(last_dates)

    # map scheme_code -> asset_class for surviving-sleeve benchmark
    ac_by_code = {f.scheme_code: f.asset_class for f in rec.funds if f.scheme_code}

    rows: list[BacktestRow] = []
    for y in windows_years:
        start = end - pd.DateOffset(days=round(y * 365.25))
        nav_by_code, weights, dropped = _eligible(conn, rec, start)
        if not weights:
            continue
        plan = reconstruct(nav_by_code, weights, start, amount)
        plan_stats = window_stats(plan.value, lookback_years=None, config=config)

        # passive twin matched to the SURVIVING sleeve only (same-sleeve, fair)
        surviving_aw: dict[str, float] = {}
        wtot = sum(weights.values())
        for code, w in weights.items():
            ac = ac_by_code.get(code, "equity")
            surviving_aw[ac] = surviving_aw.get(ac, 0.0) + w / wtot
        bench = bmk.build_blended_from_weights(conn, surviving_aw, start, amount, proxies)

        passive_ret = excess = None
        if bench is not None and len(bench.value) > 1:
            passive_ret = float(bench.value.iloc[-1] / bench.value.iloc[0] - 1.0)
            excess = plan_stats.total_return - passive_ret

        rows.append(BacktestRow(
            window=f"{int(y)}Y",
            start=str(plan.value.index[0].date()),
            plan_return=plan_stats.total_return,
            plan_vol=plan_stats.volatility,
            plan_sharpe=plan_stats.sharpe,
            plan_maxdd=plan_stats.max_drawdown,
            passive_return=passive_ret,
            excess_vs_passive=excess,
            dropped_weight=dropped,
        ))
    return rows
