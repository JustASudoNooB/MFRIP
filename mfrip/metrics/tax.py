"""Post-tax redemption outcomes under Indian capital-gains rules.

Applied to the Monte Carlo terminal corpus: what would you actually keep if
you redeemed everything at the end of the horizon? Vectorised over the full
simulated distribution, so post-tax percentiles are honestly derived path by
path rather than by taxing a single average.

Rules encoded (Finance (No.2) Act 2024 regime, unchanged by Budget 2025):
- **Equity-oriented funds** (large/flexi/mid/small-cap and other >=65% equity):
  long-term gains (units held over 12 months) taxed at 12.5% on the amount
  above the Rs 1,25,000 per-year exemption.
- **Debt funds** (specified funds, purchased after April 2023): all gains
  taxed at the investor's income-tax slab rate, regardless of holding period.
- **Other funds** (gold, international, hybrids below the equity threshold):
  held beyond 24 months, gains taxed at 12.5% with no exemption; shorter
  holdings at slab.

Stated simplifications, shown to the user on screen:
- Assumes full redemption at the end of the horizon with all units qualifying
  as long-term (a SIP's final months of instalments would really be
  short-term; for multi-year horizons this slightly understates the tax).
- Excludes surcharge and the 4% health-and-education cess.
- The Rs 1.25L exemption is applied once, as if the whole redemption falls in
  one financial year with no other equity gains.
Tax law changes; this reflects the rules as encoded on the date in the app
header and is educational, not tax advice.
"""
from __future__ import annotations

import numpy as np

EQUITY_LTCG_RATE = 0.125
EQUITY_LTCG_EXEMPTION = 125_000.0
OTHER_LTCG_RATE = 0.125
OTHER_LTCG_MIN_YEARS = 2.0

EQUITY_SLEEVES = {"largecap", "flexicap", "midcap", "smallcap"}


def asset_class_for_sleeve(sleeve: str | None) -> str:
    """Map an inferred category to its tax treatment bucket."""
    if sleeve in EQUITY_SLEEVES:
        return "equity"
    if sleeve == "debt":
        return "debt"
    return "other"          # gold, international, hybrids, unknown


def post_tax_terminal(terminal, invested: float, asset_class: str,
                      horizon_years: float, slab: float = 0.30):
    """After-tax redemption value for each simulated terminal corpus.

    `terminal` may be a scalar or a numpy array; the result matches. Losses
    are never taxed (and loss set-off against other income is out of scope).
    """
    t = np.asarray(terminal, dtype=float)
    gains = np.maximum(t - float(invested), 0.0)
    if asset_class == "equity":
        taxable = np.maximum(gains - EQUITY_LTCG_EXEMPTION, 0.0)
        tax = EQUITY_LTCG_RATE * taxable
    elif asset_class == "debt":
        tax = float(slab) * gains
    elif asset_class == "other":
        rate = OTHER_LTCG_RATE if horizon_years >= OTHER_LTCG_MIN_YEARS else float(slab)
        tax = rate * gains
    else:
        raise ValueError(f"Unknown asset class: {asset_class!r}")
    out = t - tax
    return float(out) if np.isscalar(terminal) else out


def apply_to_sim(sim: dict, asset_class: str, slab: float = 0.30) -> dict:
    """Post-tax summary of a simulate_sip result: percentiles, multiple, and
    (when a target was set) the probability of reaching it AFTER tax."""
    invested = sim["total_invested"]
    post = post_tax_terminal(sim["terminal"], invested, asset_class,
                             sim["years"], slab)
    pct = {p: float(np.percentile(post, p)) for p in (10, 25, 50, 75, 90)}
    out = {
        "terminal_pct": pct,
        "median_multiple": (pct[50] / invested) if invested else None,
        "effective_tax_median": 1.0 - (pct[50] / float(np.percentile(sim["terminal"], 50)))
        if np.percentile(sim["terminal"], 50) > 0 else 0.0,
    }
    if sim.get("target"):
        out["prob_target"] = float(np.mean(post >= sim["target"]))
    return out
