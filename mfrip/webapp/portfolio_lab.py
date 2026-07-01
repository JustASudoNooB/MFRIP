"""Portfolio Lab analytics, build a portfolio from any funds and measure it.

Pure orchestration over the existing engine (reconstruct + metrics): no new
return/risk maths, so every number is the same one the audit engine produces.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from ..config import DEFAULT_CONFIG, Config
from ..metrics import relative as Rel
from ..metrics import returns as R
from ..metrics import risk as Risk
from ..portfolio.reconstruct import reconstruct
from .data import load_nav, window_stats


def analyze(
    conn: sqlite3.Connection,
    holdings: list[tuple[int, float]],
    lookback: float | None,
    benchmark_code: int,
    config: Config = DEFAULT_CONFIG,
    base: float = 100_000.0,
) -> dict | None:
    """holdings: [(scheme_code, weight)]. Returns metrics + growth series, or None."""
    navs: dict[int, pd.Series] = {}
    weights: dict[int, float] = {}
    for c, w in holdings:
        s = load_nav(conn, c)
        if not s.empty:
            navs[c] = s
            weights[c] = weights.get(c, 0.0) + float(w)
    if not weights or sum(weights.values()) <= 0:
        return None
    start = max(s.index[0] for s in navs.values())
    try:
        recon = reconstruct(navs, weights, start, base)
        stats = window_stats(recon.value, lookback, config)
    except ValueError:
        return None

    wstart = pd.Timestamp(stats.start)
    wval = recon.value[recon.value.index >= wstart]
    growth = (wval / float(wval.iloc[0])) * base

    beta = alpha = None
    bench = load_nav(conn, benchmark_code)
    if not bench.empty:
        pr = R.period_returns(wval, config.periods_per_year)
        br = R.period_returns(bench[bench.index >= wstart], config.periods_per_year)
        b, a = Rel.beta_alpha(pr, br, config.rf_annual, config.periods_per_year)
        beta = None if b != b else b
        alpha = None if a != a else a

    return {
        "stats": stats,
        "calmar": Risk.calmar_ratio(stats.cagr, stats.max_drawdown),
        "alpha": alpha,
        "beta": beta,
        "growth": growth,
        "excluded": recon.excluded_weight,
        "n_funds": len(navs),
    }


def correlation_matrix(
    conn: sqlite3.Connection,
    codes: list[int],
    name_by_code: dict[int, str],
    lookback: float | None,
    config: Config = DEFAULT_CONFIG,
) -> pd.DataFrame | None:
    """Correlation of monthly returns among the given funds over the window."""
    series: dict[str, pd.Series] = {}
    for c in dict.fromkeys(codes):  # de-dup, keep order
        s = load_nav(conn, c)
        if s.empty:
            continue
        try:
            ws = window_stats(s, lookback, config)
        except ValueError:
            continue
        pr = R.period_returns(s[s.index >= pd.Timestamp(ws.start)], config.periods_per_year)
        label = name_by_code.get(c, str(c))
        series[label[:22]] = pr
    if len(series) < 2:
        return None
    return pd.DataFrame(series).dropna().corr()


def explain(results: dict[str, dict]) -> list[str]:
    """Templated, data-backed comparison of the built portfolios."""
    out: list[str] = []
    named = [(n, r) for n, r in results.items() if r]
    if len(named) < 1:
        return out
    if len(named) >= 2:
        best_sharpe = max(named, key=lambda x: x[1]["stats"].sharpe)
        out.append(
            f"{best_sharpe[0]} has the strongest risk-adjusted return "
            f"(Sharpe {best_sharpe[1]['stats'].sharpe:.2f}) over this window."
        )
        best_dd = max(named, key=lambda x: x[1]["stats"].max_drawdown)  # closest to 0
        out.append(
            f"{best_dd[0]} protected capital best, with the shallowest drawdown "
            f"({best_dd[1]['stats'].max_drawdown:.1%})."
        )
        best_ret = max(named, key=lambda x: x[1]["stats"].cagr)
        out.append(
            f"{best_ret[0]} compounded fastest at {best_ret[1]['stats'].cagr:.1%} a year, "
            f"with {best_ret[1]['stats'].volatility:.0%} volatility."
        )
    for n, r in named:
        a = r["alpha"]
        if a is not None:
            verb = "added" if a >= 0 else "gave up"
            out.append(f"{n} {verb} {abs(a):.1%} annual alpha vs the benchmark "
                       f"(beta {r['beta']:.2f}).")
    return out


def portfolio_value(conn, holdings, base=100_000.0):
    """Full reconstructed value series of a portfolio (list of (code, weight))."""
    navs, weights = {}, {}
    for c, w in holdings:
        s = load_nav(conn, c)
        if not s.empty:
            navs[c] = s
            weights[c] = weights.get(c, 0.0) + float(w)
    if not weights or sum(weights.values()) <= 0:
        return None
    start = max(s.index[0] for s in navs.values())
    try:
        recon = reconstruct(navs, weights, start, base)
    except ValueError:
        return None
    return recon.value


def head_to_head(conn, holdings_a, holdings_b, config: Config = DEFAULT_CONFIG, base=100_000.0):
    """Backtest two portfolios over their MUTUAL common window. Returns
    (growth_a, growth_b, stats_a, stats_b, (start, end)) or None."""
    from .data import stats_between
    va = portfolio_value(conn, holdings_a, base)
    vb = portfolio_value(conn, holdings_b, base)
    if va is None or vb is None or va.empty or vb.empty:
        return None
    start = max(va.index[0], vb.index[0])
    end = min(va.index[-1], vb.index[-1])
    if start >= end:
        return None
    ga = va[(va.index >= start) & (va.index <= end)]
    gb = vb[(vb.index >= start) & (vb.index <= end)]
    if len(ga) < 2 or len(gb) < 2:
        return None
    ga = ga / float(ga.iloc[0]) * base
    gb = gb / float(gb.iloc[0]) * base
    try:
        sa = stats_between(va, start, end, config)
        sb = stats_between(vb, start, end, config)
    except ValueError:
        return None
    return ga, gb, sa, sb, (start, end)


def correlation_guidance(corr) -> list[str]:
    """Plain-language read of a correlation matrix: redundancy vs diversification."""
    if corr is None or len(corr) < 2:
        return []
    pairs = []
    for i in range(len(corr)):
        for j in range(i + 1, len(corr)):
            pairs.append((corr.index[i], corr.columns[j], float(corr.iat[i, j])))
    if not pairs:
        return []
    out = []
    hi = max(pairs, key=lambda p: p[2])
    lo = min(pairs, key=lambda p: p[2])
    if hi[2] >= 0.8:
        out.append(f"**{hi[0]}** and **{hi[1]}** move almost in lockstep "
                   f"(correlation {hi[2]:.2f}). Holding both adds little, since they rise and fall together, "
                   f"so you're not really spreading risk. Consider keeping just one.")
    if lo[2] <= 0.5:
        out.append(f"**{lo[0]}** and **{lo[1]}** are the most independent pair "
                   f"(correlation {lo[2]:.2f}): when one dips, the other often holds, which is exactly "
                   f"what good diversification looks like.")
    avg = sum(p[2] for p in pairs) / len(pairs)
    if avg >= 0.75:
        out.append(f"Overall your funds are highly correlated (average {avg:.2f}), so the portfolio behaves "
                   f"almost like one fund. Adding a genuinely different asset (debt, gold, or international) "
                   f"would diversify more than another similar equity fund.")
    elif avg <= 0.5:
        out.append(f"Overall correlation is low (average {avg:.2f}), so your funds complement each other nicely.")
    else:
        out.append(f"Overall correlation is moderate (average {avg:.2f}), which is reasonable, with a little room to diversify further.")
    return out
