"""Pure data helpers for the web app.

These contain all the logic and none of the Streamlit rendering, so they can
be unit-tested headlessly. app.py imports these and only does layout/widgets.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config import DEFAULT_CONFIG, Config
from ..metrics import returns as _ret
from ..metrics import relative as _rel
from ..metrics import risk as _risk
from ..store import nav_store


def count_schemes(conn: sqlite3.Connection) -> int:
    """Total schemes in the master list (everything searchable)."""
    r = conn.execute("SELECT COUNT(*) AS n FROM schemes").fetchone()
    return int(r["n"]) if r else 0


def search_schemes(conn: sqlite3.Connection, query: str, limit: int = 40) -> list[tuple[int, str]]:
    """Search the full scheme master by name. Matches every word (AND), so
    'parag flexi' finds 'Parag Parikh Flexi Cap …'. Returns (code, name)."""
    words = [w for w in query.lower().split() if w]
    if not words:
        return []
    clause = " AND ".join(["LOWER(scheme_name) LIKE ?"] * len(words))
    params = [f"%{w}%" for w in words] + [limit]
    rows = conn.execute(
        f"SELECT scheme_code, scheme_name FROM schemes WHERE {clause} "
        f"ORDER BY LENGTH(scheme_name) LIMIT ?", params,
    ).fetchall()
    return [(r["scheme_code"], r["scheme_name"]) for r in rows]


def ensure_nav(conn: sqlite3.Connection, code: int) -> bool:
    """Return True if NAV is available; download-and-cache on demand if not."""
    if not nav_store.load_nav(conn, code).empty:
        return True
    from ..ingest import ingest_nav
    try:
        ingest_nav(conn, int(code))
    except Exception:
        return False
    return not nav_store.load_nav(conn, code).empty


# category-matched benchmark: the right yardstick separates skill from cap-tilt
_SLEEVE_BENCH_QUERY = {
    "largecap": "nifty 50 index",
    "flexicap": "nifty 500 index",
    "midcap": "nifty midcap 150 index",
    "smallcap": "nifty smallcap 250 index",
    "international": "nasdaq 100",
    "debt": "nifty g-sec index",
    "gold": "gold etf fund",
}


def category_benchmark(conn: sqlite3.Connection, sleeve: str, fallback: int = 120716) -> int:
    """Resolve the best index fund to benchmark a sleeve against (separates a
    mid-cap fund's cap-tilt from genuine skill). Falls back to Nifty 50."""
    q = _SLEEVE_BENCH_QUERY.get(sleeve)
    if q:
        for code, _ in search_schemes(conn, q, limit=5):
            return code
    return fallback


# --------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------
def available_funds(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    """Funds that actually have NAV cached, as (code, name), name-sorted."""
    rows = conn.execute(
        """
        SELECT s.scheme_code, COALESCE(s.scheme_name, CAST(s.scheme_code AS TEXT))
        FROM schemes s
        WHERE EXISTS (SELECT 1 FROM nav n WHERE n.scheme_code = s.scheme_code)
        ORDER BY 2
        """
    ).fetchall()
    if rows:
        return [(int(r[0]), str(r[1])) for r in rows]
    # fallback: codes present in nav but missing from schemes
    rows = conn.execute("SELECT DISTINCT scheme_code FROM nav ORDER BY scheme_code").fetchall()
    return [(int(r[0]), str(r[0])) for r in rows]


# --------------------------------------------------------------------------
# windowed statistics
# --------------------------------------------------------------------------
@dataclass
class WindowStats:
    start: str
    end: str
    total_return: float
    cagr: float
    volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    n_days: int


def _resolve_window(nav: pd.Series, lookback_years: float | None) -> tuple[pd.Timestamp, pd.Timestamp]:
    nav = nav.dropna()
    end = nav.index[-1]
    if lookback_years is None:
        return nav.index[0], end
    start_target = end - pd.DateOffset(days=round(lookback_years * 365.25))
    start = nav.index[nav.index >= start_target]
    return (start[0] if len(start) else nav.index[0]), end


def window_stats(
    nav: pd.Series, lookback_years: float | None = None, config: Config = DEFAULT_CONFIG
) -> WindowStats:
    start, end = _resolve_window(nav, lookback_years)
    w = nav[(nav.index >= start) & (nav.index <= end)].dropna()
    if len(w) < 2:
        raise ValueError("Not enough data in window")
    prets = _ret.period_returns(w, config.periods_per_year)
    total = float(w.iloc[-1] / w.iloc[0] - 1.0)
    return WindowStats(
        start=str(start.date()),
        end=str(end.date()),
        total_return=total,
        cagr=_risk.annualized_return(prets, config.periods_per_year),
        volatility=_risk.annualized_volatility(prets, config.periods_per_year),
        sharpe=_risk.sharpe_ratio(prets, config.rf_annual, config.periods_per_year),
        sortino=_risk.sortino_ratio(prets, config.rf_annual, config.periods_per_year),
        max_drawdown=_risk.max_drawdown(w),
        n_days=int(len(w)),
    )


def trailing_returns_table(nav: pd.Series, config: Config = DEFAULT_CONFIG) -> dict[str, float | None]:
    """Trailing CAGR/return for each standard window, None where history is short."""
    as_of = nav.dropna().index[-1]
    out: dict[str, float | None] = {}
    for y in config.trailing_windows_years:
        label = f"{int(y * 12)}M" if y < 1 else f"{int(y)}Y"
        out[label] = _ret.trailing_cagr(nav, as_of, y, config.min_window_coverage)
    return out


def growth_of(nav: pd.Series, lookback_years: float | None = None, base: float = 100_000.0) -> pd.Series:
    """Value of `base` rupees invested at the window start, marked to market."""
    start, end = _resolve_window(nav, lookback_years)
    w = nav[(nav.index >= start) & (nav.index <= end)].dropna()
    return (w / w.iloc[0]) * base


def inception(nav: pd.Series):
    """First date with NAV data, or None."""
    nav = nav.dropna()
    return nav.index[0] if len(nav) else None


def stats_between(nav: pd.Series, start, end, config: Config = DEFAULT_CONFIG) -> WindowStats:
    """WindowStats over an explicit [start, end] date range (same maths as window_stats)."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    w = nav[(nav.index >= start) & (nav.index <= end)].dropna()
    if len(w) < 2:
        raise ValueError("Not enough data in this date range")
    prets = _ret.period_returns(w, config.periods_per_year)
    return WindowStats(
        start=str(w.index[0].date()), end=str(w.index[-1].date()),
        total_return=float(w.iloc[-1] / w.iloc[0] - 1.0),
        cagr=_risk.annualized_return(prets, config.periods_per_year),
        volatility=_risk.annualized_volatility(prets, config.periods_per_year),
        sharpe=_risk.sharpe_ratio(prets, config.rf_annual, config.periods_per_year),
        sortino=_risk.sortino_ratio(prets, config.rf_annual, config.periods_per_year),
        max_drawdown=_risk.max_drawdown(w), n_days=int(len(w)),
    )


def growth_between(nav: pd.Series, start, end, base: float = 100_000.0) -> pd.Series:
    """Growth of `base` invested at `start`, marked to market through `end`."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    w = nav[(nav.index >= start) & (nav.index <= end)].dropna()
    return (w / w.iloc[0]) * base if not w.empty else w


# --------------------------------------------------------------------------
# comparison
# --------------------------------------------------------------------------
def correlation(nav_a: pd.Series, nav_b: pd.Series, periods_per_year: int = 12) -> float:
    ra = _ret.period_returns(nav_a, periods_per_year)
    rb = _ret.period_returns(nav_b, periods_per_year)
    df = pd.concat([ra.rename("a"), rb.rename("b")], axis=1).dropna()
    if len(df) < 3:
        return float("nan")
    return float(df["a"].corr(df["b"]))


def explain_comparison(name_a: str, sa: WindowStats, name_b: str, sb: WindowStats, corr: float) -> str:
    """Plain-English 'why one beat the other' from the windowed stats."""
    winner, loser = (name_a, name_b) if sa.total_return >= sb.total_return else (name_b, sa)
    win, lose = (sa, sb) if sa.total_return >= sb.total_return else (sb, sa)
    wname = name_a if sa.total_return >= sb.total_return else name_b
    lname = name_b if sa.total_return >= sb.total_return else name_a

    lines = [
        f"Over this period, **{wname}** returned {win.total_return:+.1%} versus "
        f"{lose.total_return:+.1%} for {lname}."
    ]
    if win.volatility < lose.volatility:
        lines.append(
            f"It did so with *lower* volatility ({win.volatility:.1%} vs {lose.volatility:.1%}), "
            "so it won on both return and risk, a clear edge."
        )
    else:
        lines.append(
            f"But it was *more* volatile ({win.volatility:.1%} vs {lose.volatility:.1%}), "
            "so the higher return came with a rougher ride."
        )
    if win.max_drawdown > lose.max_drawdown:  # less negative = shallower
        lines.append(
            f"Its worst drawdown was shallower ({win.max_drawdown:.1%} vs {lose.max_drawdown:.1%}), "
            "meaning less to recover from in the bad stretch."
        )
    better_sharpe = win.sharpe if win.sharpe == win.sharpe else float("-inf")
    lines.append(
        f"Risk-adjusted (Sharpe), {wname} scored {win.sharpe:.2f} against {lose.sharpe:.2f}."
    )
    if corr == corr:
        if corr > 0.85:
            lines.append(
                f"The two move very closely together (correlation {corr:.2f}), so holding both "
                "adds little diversification."
            )
        elif corr < 0.5:
            lines.append(
                f"They move quite differently (correlation {corr:.2f}), so combining them could "
                "actually smooth a portfolio."
            )
        else:
            lines.append(f"Their correlation is moderate ({corr:.2f}).")
    return " ".join(lines)


def load_nav(conn: sqlite3.Connection, code: int) -> pd.Series:
    return nav_store.load_nav(conn, code)
