"""SIP returns (XIRR) and goal projection.

Most Indians invest monthly, and SIP returns differ from lump-sum point-to-point
returns. XIRR is the money-weighted return that accounts for each instalment's
timing. Goal projection deliberately shows a RANGE across return assumptions,
never a single fake-precise number.
"""
from __future__ import annotations

import pandas as pd


def _price_on_or_after(nav: pd.Series, d: pd.Timestamp):
    sub = nav[nav.index >= d]
    return (sub.index[0], float(sub.iloc[0])) if len(sub) else (None, None)


def _xnpv(rate: float, flows: list[tuple[pd.Timestamp, float]]) -> float:
    t0 = flows[0][0]
    return sum(cf / (1.0 + rate) ** ((t - t0).days / 365.0) for t, cf in flows)


def _xirr(flows: list[tuple[pd.Timestamp, float]]) -> float | None:
    # bisection on a wide bracket (robust, no derivative needed)
    lo, hi = -0.99, 5.0
    flo, fhi = _xnpv(lo, flows), _xnpv(hi, flows)
    if flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = _xnpv(mid, flows)
        if abs(fm) < 1e-7:
            return mid
        if flo * fm < 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


def sip_xirr(nav: pd.Series, monthly_amount: float, start, end) -> dict | None:
    """Simulate a monthly SIP of `monthly_amount` and return its XIRR."""
    nav = nav.dropna()
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    sip_dates = pd.date_range(start, end, freq="MS")  # month-start instalments
    if len(sip_dates) < 2:
        return None
    units = 0.0
    flows: list[tuple[pd.Timestamp, float]] = []
    for d in sip_dates:
        pd_date, price = _price_on_or_after(nav, d)
        if price is None or price <= 0:
            continue
        units += monthly_amount / price
        flows.append((pd_date, -monthly_amount))
    if len(flows) < 2:
        return None
    last_price = float(nav.iloc[-1])
    final_value = units * last_price
    flows.append((nav.index[-1], final_value))
    invested = monthly_amount * (len(flows) - 1)
    xirr = _xirr(flows)
    return {
        "xirr": xirr, "invested": invested, "final_value": final_value,
        "gain": final_value - invested, "instalments": len(flows) - 1,
    }


def goal_projection(monthly: float, years: float,
                    rates=(0.08, 0.10, 0.12)) -> dict[float, float]:
    """Future value of a monthly SIP under several annual-return assumptions."""
    out = {}
    n = int(round(years * 12))
    for r in rates:
        mr = (1.0 + r) ** (1.0 / 12) - 1.0
        fv = monthly * (((1.0 + mr) ** n - 1.0) / mr) * (1.0 + mr)
        out[r] = fv
    return out


def required_sip(target: float, years: float, rate: float = 0.10) -> float:
    """Monthly SIP needed to reach `target` at an assumed annual return."""
    n = int(round(years * 12))
    mr = (1.0 + rate) ** (1.0 / 12) - 1.0
    return target / ((((1.0 + mr) ** n - 1.0) / mr) * (1.0 + mr))
