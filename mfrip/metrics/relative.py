"""Benchmark-relative metrics: beta, Jensen's alpha, capture, tracking error.

Fund and benchmark return streams are aligned on their common dates before
any regression. The benchmark should be a total-return series (e.g. a Nifty
index-fund NAV), NOT a price index, or alpha is biased upward by the index's
dividend yield.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _rf_per_period(rf_annual: float, periods_per_year: int) -> float:
    return (1.0 + rf_annual) ** (1.0 / periods_per_year) - 1.0


def _align(fund: pd.Series, bench: pd.Series) -> tuple[pd.Series, pd.Series]:
    df = pd.concat([fund.rename("f"), bench.rename("b")], axis=1).dropna()
    return df["f"], df["b"]


def beta_alpha(
    fund_ret: pd.Series,
    bench_ret: pd.Series,
    rf_annual: float,
    periods_per_year: int = 12,
) -> tuple[float, float]:
    """(beta, annualised Jensen's alpha) via OLS of excess returns.

    beta  = cov(f_ex, b_ex) / var(b_ex)
    alpha = mean(f_ex) - beta * mean(b_ex), annualised by * periods_per_year
    """
    f, b = _align(fund_ret, bench_ret)
    if len(f) < 3:
        return float("nan"), float("nan")
    rf = _rf_per_period(rf_annual, periods_per_year)
    fx, bx = f - rf, b - rf
    var_b = bx.var(ddof=1)
    if var_b <= 0:
        return float("nan"), float("nan")
    beta = float(np.cov(fx, bx, ddof=1)[0, 1] / var_b)
    alpha_period = float(fx.mean() - beta * bx.mean())
    return beta, alpha_period * periods_per_year


def tracking_error(fund_ret: pd.Series, bench_ret: pd.Series, periods_per_year: int = 12) -> float:
    f, b = _align(fund_ret, bench_ret)
    if len(f) < 2:
        return float("nan")
    active = f - b
    return float(active.std(ddof=1) * np.sqrt(periods_per_year))


def information_ratio(fund_ret: pd.Series, bench_ret: pd.Series, periods_per_year: int = 12) -> float:
    f, b = _align(fund_ret, bench_ret)
    if len(f) < 2:
        return float("nan")
    active = f - b
    te = active.std(ddof=1) * np.sqrt(periods_per_year)
    ann_active = active.mean() * periods_per_year
    return float(ann_active / te) if te > 0 else float("nan")


def capture_ratios(fund_ret: pd.Series, bench_ret: pd.Series) -> tuple[float, float]:
    """(upside capture, downside capture) as ratios of geometric mean returns.

    Upside: over periods where the benchmark rose. Downside: where it fell.
    > 1 upside / < 1 downside is the desirable asymmetry.
    """
    f, b = _align(fund_ret, bench_ret)
    if len(f) < 2:
        return float("nan"), float("nan")

    def _cap(mask: pd.Series) -> float:
        fm, bm = f[mask], b[mask]
        if len(fm) == 0:
            return float("nan")
        f_g = float((1.0 + fm).prod() ** (1.0 / len(fm)) - 1.0)
        b_g = float((1.0 + bm).prod() ** (1.0 / len(bm)) - 1.0)
        return f_g / b_g if b_g != 0 else float("nan")

    return _cap(b > 0), _cap(b < 0)


def rolling_beta_alpha(fund_nav: pd.Series, bench_nav: pd.Series,
                       window_years: float = 3.0, rf_annual: float = 0.065,
                       periods_per_year: int = 12) -> pd.DataFrame:
    """Rolling beta and annualised alpha over every `window_years` window.

    One row per window end (monthly step). Shows whether outperformance is a
    consistent habit or a one-off stretch, which a single full-period alpha
    hides. Empty frame when overlap is too short.
    """
    from .returns import period_returns

    f = period_returns(fund_nav, periods_per_year)
    b = period_returns(bench_nav, periods_per_year)
    df = pd.DataFrame({"f": f, "b": b}).dropna()
    w = int(round(window_years * periods_per_year))
    if len(df) < w + 1:
        return pd.DataFrame(columns=["beta", "alpha"])
    out = []
    for end in range(w, len(df) + 1):
        chunk = df.iloc[end - w:end]
        beta, alpha = beta_alpha(chunk["f"], chunk["b"], rf_annual, periods_per_year)
        out.append((df.index[end - 1], beta, alpha))
    res = pd.DataFrame(out, columns=["date", "beta", "alpha"]).set_index("date")
    return res
