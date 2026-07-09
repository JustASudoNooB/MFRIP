"""Advanced NAV analytics, how fund analysis is actually done.

All pure-NAV (so net of fees already): rolling-return distributions, up/down
capture ratios, SIP XIRR (what monthly investors really experience), and
historical stress episodes. No prediction anywhere; these describe the past
honestly.
"""
from __future__ import annotations

import pandas as pd

from ..config import DEFAULT_CONFIG, Config
from .returns import period_returns
from .risk import max_drawdown


# ------------------------------------------------------------ rolling returns
def rolling_returns(nav: pd.Series, years: float, config: Config = DEFAULT_CONFIG,
                    benchmark: pd.Series | None = None) -> dict | None:
    """Distribution of every rolling `years`-long return (annualised for >1y).
    Kills the single-window illusion: best, worst, average, % positive, and
    optionally % of windows that beat a benchmark."""
    m = nav.resample("ME").last().dropna()
    k = int(round(years * 12))
    if k < 1 or len(m) <= k:
        return None
    roll = (m / m.shift(k) - 1.0).dropna()
    if roll.empty:
        return None
    ann = (1 + roll) ** (1 / years) - 1 if years > 1 else roll
    out = {
        "window_years": years, "count": int(len(roll)),
        "best": float(ann.max()), "worst": float(ann.min()),
        "avg": float(ann.mean()), "median": float(ann.median()),
        "pct_positive": float((roll > 0).mean()),
        "pct_beat_benchmark": None,
    }
    if benchmark is not None and not benchmark.empty:
        bm = benchmark.resample("ME").last().dropna()
        broll = (bm / bm.shift(k) - 1.0)
        aligned = pd.concat([roll, broll], axis=1).dropna()
        if len(aligned) >= 3:
            out["pct_beat_benchmark"] = float((aligned.iloc[:, 0] > aligned.iloc[:, 1]).mean())
    return out


# ------------------------------------------------------------ capture ratios
def capture_ratios(fund_nav: pd.Series, bench_nav: pd.Series,
                   config: Config = DEFAULT_CONFIG) -> tuple[float, float] | None:
    """Up/down capture vs a benchmark, using monthly returns. Up-capture >100
    means the fund outpaces the benchmark when it rises; down-capture <100 means
    it falls less when the benchmark drops (good)."""
    fr = period_returns(fund_nav.resample("ME").last().dropna(), 12)
    br = period_returns(bench_nav.resample("ME").last().dropna(), 12)
    a = pd.concat([fr, br], axis=1).dropna()
    if len(a) < 6:
        return None
    f, b = a.iloc[:, 0], a.iloc[:, 1]
    up, down = b > 0, b < 0
    if up.sum() < 3 or down.sum() < 3:
        return None
    ub = (1 + b[up]).prod() - 1
    db = (1 + b[down]).prod() - 1
    if ub == 0 or db == 0:
        return None
    up_cap = ((1 + f[up]).prod() - 1) / ub * 100
    down_cap = ((1 + f[down]).prod() - 1) / db * 100
    return float(up_cap), float(down_cap)


# ------------------------------------------------------------ SIP XIRR
def _xirr(flows: list[tuple[pd.Timestamp, float]]) -> float | None:
    if len(flows) < 2:
        return None
    t0 = flows[0][0]

    def npv(r):
        return sum(cf / (1 + r) ** ((d - t0).days / 365.0) for d, cf in flows)

    lo, hi = -0.95, 5.0
    flo, fhi = npv(lo), npv(hi)
    if flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = npv(mid)
        if abs(fm) < 1e-3:
            return mid
        if flo * fm < 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


def sip_xirr(nav: pd.Series, monthly: float = 10_000.0) -> dict | None:
    """Annualised XIRR of investing `monthly` on the first NAV of each month,
    what a real SIP investor experiences, which differs from point-to-point CAGR."""
    m = nav.resample("MS").first().dropna()
    if len(m) < 6:
        return None
    units = 0.0
    flows: list[tuple[pd.Timestamp, float]] = []
    for d, p in zip(m.index, m.values):
        if p <= 0:
            continue
        units += monthly / p
        flows.append((d, -monthly))
    invested = monthly * len(flows)
    final_value = units * float(m.values[-1])
    flows.append((m.index[-1], final_value))
    rate = _xirr(flows)
    if rate is None:
        return None
    return {"xirr": float(rate), "invested": invested, "value": final_value,
            "months": len(flows) - 1}


# ------------------------------------------------------------ stress episodes
STRESS_EPISODES = [
    ("COVID crash", "2020-02-19", "2020-03-23"),
    ("COVID recovery", "2020-04-01", "2020-12-31"),
    ("2022 rate-hike drawdown", "2021-10-18", "2022-06-17"),
    ("2018 mid/small-cap fall", "2018-01-01", "2018-10-26"),
    ("2024 election-result week", "2024-06-03", "2024-06-07"),
]


def episode_performance(value: pd.Series, start: str, end: str) -> tuple[float, float] | None:
    """(total return, max drawdown) of a value/NAV series over a date episode."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    w = value[(value.index >= s) & (value.index <= e)].dropna()
    if len(w) < 2:
        return None
    return float(w.iloc[-1] / w.iloc[0] - 1.0), max_drawdown(w)


def stress_table(value: pd.Series) -> list[tuple[str, float, float]]:
    """[(episode_name, return, max_drawdown)] for every episode with data."""
    rows = []
    for name, s, e in STRESS_EPISODES:
        r = episode_performance(value, s, e)
        if r is not None:
            rows.append((name, r[0], r[1]))
    return rows
