"""Walk-forward (out-of-sample) validation of the fund-ranking methodology.

The honest question a serious reviewer asks: the engine ranks funds on past data,
but do those rankings actually hold up on data the ranking never saw? This tests
exactly that. For each cutoff date we rank funds using only history up to that
date (in-sample), then measure how those same funds actually behaved afterwards
(out-of-sample), and check whether the ranking lined up with what followed.

What it tests, and does not:
  - It tests whether the composite score is INFORMATIVE about the future, by rank
    correlation between the in-sample score and each realised out-of-sample metric,
    repeated across several time windows (walk-forward) so it is not one lucky split.
  - It does NOT, and cannot, predict which single fund will win. The useful finding
    is usually that the ranking tracks future RISK behaviour (consistency, drawdowns)
    better than future RETURNS, which is exactly why the engine weights consistency
    and downside protection rather than chasing past returns.

Honest limits: only funds that survived the whole window are testable (survivorship
bias), the universe is whatever NAVs are cached, and small samples mean wide error
bars, so a permutation p-value is reported alongside every pooled correlation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .advisor.ranking import rank_sleeve, _rolling_consistency
from .config import DEFAULT_CONFIG, Config

# OOS metrics and whether a higher value is "better" (for the top-minus-bottom spread)
OOS_METRICS = {
    "oos_sharpe": True,
    "oos_sortino": True,
    "oos_cagr": True,
    "oos_consistency": True,
    "oos_max_drawdown": True,   # less negative is larger, so higher is better
    "oos_volatility": False,    # lower volatility is better
}
RETURN_METRICS = ("oos_sharpe", "oos_sortino", "oos_cagr")
RISK_METRICS = ("oos_consistency", "oos_max_drawdown", "oos_volatility")


def _spearman(a, b) -> tuple[float, int]:
    s = pd.DataFrame({"a": np.asarray(a, float), "b": np.asarray(b, float)}).dropna()
    if len(s) < 3 or s["a"].nunique() < 2 or s["b"].nunique() < 2:
        return float("nan"), len(s)
    # Spearman = Pearson correlation of the ranks (average ranks for ties).
    # Computed this way deliberately: pandas' method="spearman" imports scipy
    # under the hood, and this project runs without scipy. Verified identical
    # to scipy's spearmanr to 1e-12, including tied values.
    ra = s["a"].rank(method="average")
    rb = s["b"].rank(method="average")
    return float(ra.corr(rb)), len(s)


def _perm_pvalue(a, b, n_perm: int = 2000, seed: int = 0) -> float:
    """Two-sided permutation p-value for a Spearman correlation (no scipy needed)."""
    df = pd.DataFrame({"a": np.asarray(a, float), "b": np.asarray(b, float)}).dropna()
    if len(df) < 4 or df["a"].nunique() < 2 or df["b"].nunique() < 2:
        return float("nan")
    ar = df["a"].rank().to_numpy()
    br = df["b"].rank().to_numpy()
    obs = abs(np.corrcoef(ar, br)[0, 1])
    rng = np.random.default_rng(seed)
    perm = br.copy()
    count = 0
    for _ in range(n_perm):
        rng.shuffle(perm)
        if abs(np.corrcoef(ar, perm)[0, 1]) >= obs - 1e-12:
            count += 1
    return float((count + 1) / (n_perm + 1))


def _oos_metrics(nav: pd.Series, start, end, min_days: int = 120,
                 config: Config = DEFAULT_CONFIG) -> dict | None:
    """Realised metrics over the out-of-sample window [start, end]."""
    from .webapp.data import stats_between
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    try:
        st = stats_between(nav, start, end, config)
    except ValueError:
        return None
    if st.n_days < min_days:
        return None
    seg = nav[(nav.index >= start) & (nav.index <= end)]
    cons = _rolling_consistency(seg, (end - start).days / 365.25)
    return {
        "oos_cagr": st.cagr, "oos_sharpe": st.sharpe, "oos_sortino": st.sortino,
        "oos_max_drawdown": st.max_drawdown, "oos_volatility": st.volatility,
        "oos_consistency": cons if cons is not None else float("nan"),
    }


def evaluate_window(funds: dict, cutoff, lookback_years: int = 3,
                    horizon_years: int = 2, min_funds: int = 5,
                    config: Config = DEFAULT_CONFIG) -> dict | None:
    """One train/test split at `cutoff`. funds: code -> (name, nav).

    In-sample = [cutoff - lookback, cutoff]; out-of-sample = [cutoff, cutoff + horizon].
    Returns per-fund (score, oos metrics), rank correlations, and top-minus-bottom spread.
    """
    cutoff = pd.Timestamp(cutoff)
    is_start = cutoff - pd.DateOffset(years=lookback_years)
    oos_end = cutoff + pd.DateOffset(years=horizon_years)

    names, is_series = {}, {}
    for code, (name, nav) in funds.items():
        nav = nav.dropna()
        nav_is = nav[nav.index <= cutoff]
        if len(nav_is) >= 60 and len(nav_is) and nav_is.index[0] <= is_start:
            names[code] = name
            is_series[code] = nav_is[nav_is.index >= is_start]
    if len(names) < min_funds:
        return None

    scores = rank_sleeve(names, is_series, config)
    score_by_code = {s.code: s.composite for s in scores}

    rows = []
    for code, (name, nav) in funds.items():
        if code not in score_by_code:
            continue
        oos = _oos_metrics(nav.dropna(), cutoff, oos_end, config=config)
        if oos is None:
            continue
        rows.append({"code": code, "name": name, "score": score_by_code[code], **oos})
    if len(rows) < min_funds:
        return None

    df = pd.DataFrame(rows)
    corr = {m: _spearman(df["score"], df[m])[0] for m in OOS_METRICS}

    ds = df.sort_values("score", ascending=False).reset_index(drop=True)
    half = len(ds) // 2
    top, bot = ds.iloc[:half], ds.iloc[len(ds) - half:]
    spread = {m: float(top[m].mean() - bot[m].mean()) for m in OOS_METRICS}

    return {
        "cutoff": str(cutoff.date()), "n": len(df), "df": df,
        "corr": corr, "spread": spread,
        "is_window": (str(is_start.date()), str(cutoff.date())),
        "oos_window": (str(cutoff.date()), str(oos_end.date())),
    }


def feasible_cutoffs(funds: dict, lookback_years: int = 3, horizon_years: int = 2,
                     step_years: int = 1) -> list[pd.Timestamp]:
    """Yearly cutoff dates for which both windows fit inside the data coverage."""
    starts = [v[1].dropna().index[0] for v in funds.values() if len(v[1].dropna())]
    ends = [v[1].dropna().index[-1] for v in funds.values() if len(v[1].dropna())]
    if not starts:
        return []
    earliest = min(starts) + pd.DateOffset(years=lookback_years)
    latest = max(ends) - pd.DateOffset(years=horizon_years)
    if earliest > latest:
        return []
    cuts, c = [], pd.Timestamp(year=earliest.year + 1, month=1, day=1)
    while c <= latest:
        cuts.append(c)
        c = c + pd.DateOffset(years=step_years)
    return cuts


def walk_forward(funds: dict, cutoffs=None, lookback_years: int = 3,
                 horizon_years: int = 2, min_funds: int = 5,
                 config: Config = DEFAULT_CONFIG) -> dict | None:
    """Run evaluate_window across several cutoffs and aggregate the evidence."""
    if cutoffs is None:
        cutoffs = feasible_cutoffs(funds, lookback_years, horizon_years)
    windows = []
    for c in cutoffs:
        w = evaluate_window(funds, c, lookback_years, horizon_years, min_funds, config)
        if w is not None:
            windows.append(w)
    if not windows:
        return None

    pooled = pd.concat([w["df"] for w in windows], ignore_index=True)
    pooled_corr = {}
    for m in OOS_METRICS:
        rho, n = _spearman(pooled["score"], pooled[m])
        pooled_corr[m] = {"rho": rho, "n": n, "p": _perm_pvalue(pooled["score"], pooled[m])}

    avg_corr = {m: float(np.nanmean([w["corr"][m] for w in windows])) for m in OOS_METRICS}
    avg_spread = {m: float(np.nanmean([w["spread"][m] for w in windows])) for m in OOS_METRICS}
    # hit rate: share of windows where the top half beat the bottom half
    hit = {m: float(np.mean([(w["spread"][m] > 0) == OOS_METRICS[m] for w in windows]))
           for m in OOS_METRICS}

    return {
        "windows": windows, "n_windows": len(windows), "pooled": pooled,
        "pooled_corr": pooled_corr, "avg_corr": avg_corr, "avg_spread": avg_spread,
        "hit_rate": hit, "lookback_years": lookback_years, "horizon_years": horizon_years,
        "return_corr": float(np.nanmean([pooled_corr[m]["rho"] for m in RETURN_METRICS])),
        "risk_corr": float(np.nanmean([
            pooled_corr["oos_consistency"]["rho"],
            pooled_corr["oos_max_drawdown"]["rho"],
            -pooled_corr["oos_volatility"]["rho"],  # flip so higher = better risk persistence
        ])),
    }


# --------------------------------------------------------------------------
# orchestration over the cached universe
# --------------------------------------------------------------------------
EQUITY_SLEEVES = {"largecap", "flexicap", "midcap", "smallcap", "international"}


def load_universe(conn, min_history_years: float = 5.0, equity_only: bool = True) -> dict:
    """All cached funds with enough history. Returns code -> (name, sleeve, nav)."""
    from .webapp.data import available_funds
    from .store.nav_store import load_nav
    from .advisor.categorize import infer_sleeve
    out = {}
    for code, name in available_funds(conn):
        nav = load_nav(conn, code).dropna()
        if len(nav) < 60:
            continue
        if (nav.index[-1] - nav.index[0]).days / 365.25 < min_history_years:
            continue
        sleeve = infer_sleeve(name)
        if equity_only and sleeve not in EQUITY_SLEEVES:
            continue
        out[code] = (name, sleeve, nav)
    return out


def run_validation(conn, lookback_years: int = 3, horizon_years: int = 2,
                   step_years: int = 1, min_sleeve: int = 5,
                   config: Config = DEFAULT_CONFIG) -> dict | None:
    """Validate over the cached equity universe: one pooled run plus per-sleeve runs."""
    uni = load_universe(conn, min_history_years=lookback_years + horizon_years, equity_only=True)
    if len(uni) < min_sleeve:
        return None

    all_funds = {c: (n, nav) for c, (n, _, nav) in uni.items()}
    overall = walk_forward(all_funds, None, lookback_years, horizon_years, min_sleeve, config)

    by_sleeve = {}
    groups: dict[str, dict] = {}
    for c, (n, sl, nav) in uni.items():
        groups.setdefault(sl, {})[c] = (n, nav)
    for sl, funds in groups.items():
        if len(funds) < min_sleeve:
            continue
        wf = walk_forward(funds, None, lookback_years, horizon_years, min_sleeve, config)
        if wf is not None:
            by_sleeve[sl] = wf

    return {
        "overall": overall, "by_sleeve": by_sleeve,
        "n_funds": len(uni), "lookback_years": lookback_years, "horizon_years": horizon_years,
    }
