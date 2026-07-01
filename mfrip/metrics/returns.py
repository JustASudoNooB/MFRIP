"""Return computations.

Two distinct things, deliberately kept separate:
  * period returns  -> the input to risk stats (vol, Sharpe, beta...)
  * trailing CAGR   -> point-to-point annualised growth over a fixed window

Both honour an `as_of` cut: nothing after `as_of` is ever read. That cut is
the foundation of the whole platform's anti-lookahead guarantee.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def cut(nav: pd.Series, as_of: pd.Timestamp) -> pd.Series:
    """Truncate a NAV series to data available on/before `as_of`.

    This is THE integrity primitive. Every metric routes through it, so a
    snapshot dated T is provably independent of any NAV observed after T.
    """
    as_of = pd.Timestamp(as_of)
    return nav[nav.index <= as_of]


def period_returns(nav: pd.Series, periods_per_year: int = 12) -> pd.Series:
    """Simple returns at the chosen frequency.

    Monthly (12) resamples to month-end NAV first. Daily (252) uses the raw
    series. Monthly is preferred for risk stats: it dodges stale-NAV daily
    autocorrelation that otherwise understates vol / inflates Sharpe.
    """
    nav = nav.dropna()
    if periods_per_year == 12:
        sampled = nav.resample("ME").last().dropna()
    elif periods_per_year == 252:
        sampled = nav
    else:
        raise ValueError("periods_per_year must be 12 (monthly) or 252 (daily)")
    return sampled.pct_change().dropna()


def trailing_cagr(
    nav: pd.Series,
    as_of: pd.Timestamp,
    years: float,
    min_coverage: float = 0.9,
) -> float | None:
    """Annualised growth over the trailing `years` ending at `as_of`.

    Returns None (never a fabricated number) when realised history covers
    less than `min_coverage` of the requested window. For windows <= 1y the
    figure is the absolute (non-annualised) period return, which is the
    standard convention for sub-year horizons.
    """
    nav = cut(nav, as_of).dropna()
    if len(nav) < 2:
        return None

    end_date = nav.index[-1]
    end_val = float(nav.iloc[-1])

    target_start = end_date - pd.DateOffset(days=round(years * 365.25))
    window = nav[nav.index <= target_start]
    if window.empty:
        return None

    start_date = window.index[-1]
    start_val = float(window.iloc[-1])
    if start_val <= 0:
        return None

    elapsed_years = (end_date - start_date).days / 365.25
    if elapsed_years < years * min_coverage:
        return None

    growth = end_val / start_val
    if years <= 1.0:
        return growth - 1.0
    return growth ** (1.0 / elapsed_years) - 1.0


def calendar_year_returns(nav: pd.Series, as_of: pd.Timestamp | None = None):
    """Year-on-year (calendar-year) returns for a NAV series.

    Each year's return is that year's closing NAV over the prior year's closing
    NAV (standard Dec-to-Dec). The first year in the data is measured from the
    fund's inception NAV to that year's close, so it is partial if the fund
    started after January; the final year is partial if the data ends before
    December. Returns a list of (year, return, is_partial), oldest first.
    """
    nav = nav.dropna().sort_index()
    if as_of is not None:
        nav = cut(nav, as_of)
    if len(nav) < 2:
        return []
    year_end = nav.resample("YE").last().dropna()
    out: list[tuple[int, float, bool]] = []
    prev = None
    first_month = nav.index[0].month
    for ts, val in year_end.items():
        year = int(ts.year)
        val = float(val)
        if prev is None:
            base = float(nav.iloc[0])          # inception
            partial = first_month > 1
        else:
            base = prev
            partial = False
        if base > 0:
            out.append((year, val / base - 1.0, partial))
        prev = val
    if out and nav.index[-1].month < 12:       # data ends mid-year
        y, r, _ = out[-1]
        out[-1] = (y, r, True)
    return out
