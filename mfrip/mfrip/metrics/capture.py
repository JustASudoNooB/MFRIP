"""Capture ratios and historical stress tests.

Up/down capture: of the market's gains and losses, how much did the fund catch?
A fund that captures 110% of up moves but only 80% of down moves has an
attractive risk personality. Stress tests replay named historical episodes.
"""
from __future__ import annotations

import pandas as pd

from . import risk as _risk


def _monthly_returns(nav: pd.Series) -> pd.Series:
    m = nav.resample("ME").last().dropna()
    return (m / m.shift(1) - 1.0).dropna()


def capture_ratios(fund_nav: pd.Series, bench_nav: pd.Series) -> tuple[float | None, float | None]:
    """(up_capture, down_capture) as ratios, 1.0 means it matched the market."""
    fr, br = _monthly_returns(fund_nav), _monthly_returns(bench_nav)
    idx = fr.index.intersection(br.index)
    if len(idx) < 6:
        return None, None
    fr, br = fr[idx], br[idx]
    up, dn = br > 0, br < 0
    uc = float(fr[up].mean() / br[up].mean()) if up.any() and br[up].mean() != 0 else None
    dc = float(fr[dn].mean() / br[dn].mean()) if dn.any() and br[dn].mean() != 0 else None
    return uc, dc


# named historical episodes for Indian equity (date ranges of notable moves)
STRESS_EPISODES = [
    ("COVID crash", "2020-02-19", "2020-03-23"),
    ("COVID recovery", "2020-03-24", "2020-12-31"),
    ("2022 rate-hike selloff", "2021-10-18", "2022-06-17"),
    ("2024 election-week swing", "2024-06-03", "2024-06-07"),
]


def stress_test(nav: pd.Series, episodes=STRESS_EPISODES) -> list[dict]:
    """Return and worst drawdown of the series within each named episode."""
    out = []
    for name, s, e in episodes:
        w = nav[(nav.index >= pd.Timestamp(s)) & (nav.index <= pd.Timestamp(e))].dropna()
        if len(w) < 2:
            continue
        out.append({
            "name": name, "start": str(w.index[0].date()), "end": str(w.index[-1].date()),
            "return": float(w.iloc[-1] / w.iloc[0] - 1.0),
            "drawdown": float(_risk.max_drawdown(w)),
        })
    return out
