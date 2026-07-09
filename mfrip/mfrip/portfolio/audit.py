"""Forward audit of a reconstructed portfolio.

Races three portfolios built from the SAME funds and start date:
  * Recommended  - the advisor's weights
  * Equal-weight - same funds, equal weights (did the weighting add anything?)
  * Benchmark    - 100% in a passive index fund (did active beat passive?)

Returns realised numbers at fixed horizons. This is forward-looking by
design: unlike the Phase-1 snapshot, the whole point here is to use what
actually happened after the recommendation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .reconstruct import reconstruct


def _return_to(value: pd.Series, target: pd.Timestamp) -> float | None:
    v = value[value.index <= target]
    if len(v) < 1:
        return None
    return float(v.iloc[-1] / value.iloc[0] - 1.0)


def _horizon_table(value: pd.Series) -> dict[str, float | None]:
    start = value.index[0]
    out: dict[str, float | None] = {}
    for label, months in [("1M", 1), ("3M", 3), ("6M", 6), ("12M", 12)]:
        target = start + pd.DateOffset(months=months)
        if target > value.index[-1] + pd.Timedelta(days=3):
            out[label] = None  # horizon not reached yet
        else:
            out[label] = _return_to(value, target)
    out["latest"] = float(value.iloc[-1] / value.iloc[0] - 1.0)
    return out


@dataclass
class AuditResult:
    rec_id: int | None
    advisor: str
    start_date: str
    as_of: str
    amount: float
    invested: float
    excluded_weight: float
    recommended_value_now: float
    recommended_returns: dict
    equal_weight_returns: dict
    benchmark_returns: dict
    beat_benchmark: bool
    excess_vs_benchmark: float
    weighting_added: bool             # recommended beat its own equal-weight twin
    blended_return: float | None = None       # passive-twin (same allocation) return
    excess_vs_blended: float | None = None     # fund-selection skill vs passive twin
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def run_audit(
    nav_by_code: dict[int, pd.Series],
    weights: dict[int, float],
    benchmark_nav: pd.Series,
    start: str,
    amount: float = 1_000_000.0,
    rec_id: int | None = None,
    advisor: str = "",
    blended_value: pd.Series | None = None,
) -> AuditResult:
    rec = reconstruct(nav_by_code, weights, start, amount)
    start_ts = rec.start_date

    eq_weights = {c: 1.0 for c in weights}
    eqw = reconstruct(nav_by_code, eq_weights, start, amount)

    bench = reconstruct({-1: benchmark_nav}, {-1: 1.0}, start, amount)

    rec_ret = _horizon_table(rec.value)
    eqw_ret = _horizon_table(eqw.value)
    bench_ret = _horizon_table(bench.value)

    excess = rec_ret["latest"] - bench_ret["latest"]
    notes = []
    if rec.excluded_weight > 0:
        notes.append(
            f"{rec.excluded_weight:.0%} of the plan (un-priceable assets like FDs/"
            f"direct bonds) was excluded; returns reflect the priced portion only."
        )

    blended_return = excess_vs_blended = None
    if blended_value is not None and len(blended_value) > 1:
        bl = blended_value[blended_value.index >= start_ts]
        if len(bl) > 1:
            blended_return = float(bl.iloc[-1] / bl.iloc[0] - 1.0)
            excess_vs_blended = float(rec_ret["latest"] - blended_return)

    return AuditResult(
        rec_id=rec_id,
        advisor=advisor,
        start_date=str(start_ts.date()),
        as_of=str(rec.value.index[-1].date()),
        amount=amount,
        invested=rec.invested,
        excluded_weight=rec.excluded_weight,
        recommended_value_now=float(rec.value.iloc[-1]),
        recommended_returns=rec_ret,
        equal_weight_returns=eqw_ret,
        benchmark_returns=bench_ret,
        beat_benchmark=bool(excess > 0),
        excess_vs_benchmark=float(excess),
        weighting_added=bool(rec_ret["latest"] > eqw_ret["latest"]),
        blended_return=blended_return,
        excess_vs_blended=excess_vs_blended,
        notes=notes,
    )
