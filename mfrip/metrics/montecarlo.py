"""Monte Carlo goal simulation for a monthly SIP.

The honest way to look forward. Instead of a single assumed return, we take the
fund's OWN historical monthly returns and simulate thousands of possible futures,
then report the spread of outcomes as a probability fan (10th to 90th percentile
of the corpus over time). It is forward-looking and uses real parameters, but it
quantifies uncertainty rather than pretending to predict a number.

Two methods are offered:
  - "bootstrap" (default): each simulated month resamples an ACTUAL historical
    monthly return (with replacement). Non-parametric, so it inherits the fund's
    real distribution including fat tails and crashes. Treats months as
    independent, so multi-year streaks (volatility clustering) are not modelled.
  - "normal": draws monthly log-returns from a Normal fitted to history
    (geometric Brownian motion). Smooth and can extrapolate beyond the historical
    range, but assumes normality, which understates real tail risk.

The SIP convention matches metrics.sip.goal_projection exactly: each month the
instalment is added and then grows for the full month (annuity due). With zero
volatility, the simulated median equals the deterministic future value.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_PERCENTILES = (10, 25, 50, 75, 90)
MIN_MONTHS = 12  # need a meaningful return history to simulate from


def monthly_returns(nav: pd.Series) -> np.ndarray:
    """Month-end-sampled simple monthly returns from a NAV series."""
    nav = nav.dropna()
    m = nav.resample("ME").last().dropna()
    return m.pct_change().dropna().to_numpy(dtype=float)


def historical_params(nav: pd.Series) -> dict | None:
    """Estimate the monthly/annualised return and volatility from history."""
    r = monthly_returns(nav)
    if len(r) < MIN_MONTHS:
        return None
    mu_m = float(np.mean(r))
    sd_m = float(np.std(r, ddof=1))
    return {
        "returns": r,
        "n_months": int(len(r)),
        "mean_monthly": mu_m,
        "sd_monthly": sd_m,
        "ann_return": float((1.0 + mu_m) ** 12 - 1.0),
        "ann_vol": float(sd_m * np.sqrt(12.0)),
    }


def simulate_sip(nav: pd.Series, monthly: float, years: float,
                 n_sims: int = 5000, method: str = "bootstrap",
                 target: float | None = None, seed: int | None = 42,
                 percentiles=DEFAULT_PERCENTILES) -> dict:
    """Simulate a monthly SIP forward and summarise the distribution of outcomes.

    Returns a dict with the percentile bands over time, the terminal
    distribution, and (if `target` given) the probability of reaching it.
    """
    if monthly <= 0:
        raise ValueError("Monthly amount must be positive.")
    params = historical_params(nav)
    if params is None:
        raise ValueError(
            f"Need at least {MIN_MONTHS} months of history to simulate; "
            "this fund has too little.")
    months = int(round(years * 12))
    if months < 1:
        raise ValueError("Horizon must be at least one month.")

    r = params["returns"]
    rng = np.random.default_rng(seed)

    if method == "bootstrap":
        R = rng.choice(r, size=(n_sims, months), replace=True)
    elif method == "normal":
        logr = np.log1p(r)
        mu, sd = float(logr.mean()), float(logr.std(ddof=1))
        R = np.expm1(rng.normal(mu, sd, size=(n_sims, months)))
    else:
        raise ValueError("method must be 'bootstrap' or 'normal'")

    # annuity-due SIP recursion, vectorised across simulations
    paths = np.empty((n_sims, months + 1), dtype=float)
    paths[:, 0] = 0.0
    corpus = np.zeros(n_sims, dtype=float)
    for t in range(months):
        corpus = (corpus + monthly) * (1.0 + R[:, t])
        paths[:, t + 1] = corpus

    invested = monthly * np.arange(months + 1, dtype=float)
    bands = {int(p): np.percentile(paths, p, axis=0) for p in percentiles}
    terminal = paths[:, -1]
    terminal_pct = {int(p): float(np.percentile(terminal, p)) for p in percentiles}
    total_invested = float(monthly * months)

    out = {
        "months": months,
        "years": float(years),
        "monthly": float(monthly),
        "n_sims": int(n_sims),
        "method": method,
        "time_years": np.arange(months + 1) / 12.0,
        "invested": invested,
        "bands": bands,                 # percentile -> corpus array over time
        "terminal": terminal,           # full terminal distribution
        "terminal_pct": terminal_pct,   # percentile -> terminal corpus
        "total_invested": total_invested,
        "median_multiple": (terminal_pct[50] / total_invested) if total_invested else None,
        "ann_return": params["ann_return"],
        "ann_vol": params["ann_vol"],
        "n_months_history": params["n_months"],
    }
    if target is not None and target > 0:
        out["target"] = float(target)
        out["prob_target"] = float(np.mean(terminal >= target))
        # first year where the median path crosses the target (or None)
        med = bands[50]
        hit = np.where(med >= target)[0]
        out["median_hits_year"] = float(hit[0] / 12.0) if len(hit) else None
    return out


def required_monthly_for_confidence(nav: pd.Series, target: float, years: float,
                                    confidence: float = 0.5, n_sims: int = 2000,
                                    method: str = "bootstrap", seed: int = 42) -> float | None:
    """Monthly SIP so that `confidence` fraction of simulations reach `target`.

    Found by scaling: corpus is linear in the monthly amount for a fixed set of
    return paths, so we simulate once at ₹1/month, read the terminal percentile
    at (1 - confidence), and scale. Returns None if that percentile is non-positive.
    """
    if not (0.0 < confidence < 1.0):
        raise ValueError("confidence must be between 0 and 1.")
    sim = simulate_sip(nav, monthly=1.0, years=years, n_sims=n_sims,
                       method=method, seed=seed, percentiles=(int(round((1 - confidence) * 100)),))
    p = int(round((1 - confidence) * 100))
    corpus_per_rupee = sim["terminal_pct"][p]
    if corpus_per_rupee <= 0:
        return None
    return float(target / corpus_per_rupee)
