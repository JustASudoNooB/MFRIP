"""Turn an allocation into a rupee portfolio value tracked through time.

Buy units at the recommendation date, then mark to market every day using
cached NAVs. Excluded funds (FDs, direct bonds the engine can't price) are
dropped and the remaining weights renormalised to 100%; the dropped fraction
is reported so the audit stays honest about what it did and didn't cover.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Reconstruction:
    value: pd.Series                 # portfolio rupee value over time
    start_date: pd.Timestamp
    invested: float                  # rupees actually deployed (priced funds only)
    excluded_weight: float           # fraction of the plan we could not price
    weights_used: dict[int, float]   # renormalised, scheme_code -> weight


def _renormalise(weights: dict[int, float]) -> tuple[dict[int, float], float]:
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("No priceable weight in portfolio")
    excluded = max(0.0, 1.0 - total)
    return {c: w / total for c, w in weights.items()}, excluded


def reconstruct(
    nav_by_code: dict[int, pd.Series],
    weights: dict[int, float],
    start: str | pd.Timestamp,
    amount: float = 1_000_000.0,
) -> Reconstruction:
    start = pd.Timestamp(start)
    frame = pd.DataFrame({c: s for c, s in nav_by_code.items() if c in weights})
    frame = frame.sort_index()
    frame = frame[frame.index >= start].ffill().dropna()
    if frame.empty:
        raise ValueError(f"No overlapping NAV data on/after {start.date()}")

    w_norm, excluded = _renormalise({c: weights[c] for c in frame.columns})
    entry = frame.iloc[0]
    units = {c: (w_norm[c] * amount) / float(entry[c]) for c in frame.columns}
    value = sum(frame[c] * units[c] for c in frame.columns)
    value.name = "portfolio_value"

    return Reconstruction(
        value=value,
        start_date=frame.index[0],
        invested=float(amount * (1.0 - excluded)),
        excluded_weight=excluded,
        weights_used=w_norm,
    )
