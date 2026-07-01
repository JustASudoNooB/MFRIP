"""The point-in-time snapshot: the single public contract of the engine.

`build_snapshot(nav, as_of, benchmark=...)` returns every return/risk metric
computable from NAV data available on or before `as_of`. By construction it
cannot see the future: the first thing it does is cut both series at `as_of`.

Honesty boundary (read this before using it in a recommendation audit):
static fund metadata available from free sources, such as expense ratio, AUM,
holdings, fund manager, is CURRENT, not point-in-time. Those fields belong
in the recommendation record with a "current, not as-of" flag, never stamped
onto this snapshot as though they were historically accurate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import pandas as pd

from ..config import Config, DEFAULT_CONFIG
from . import relative, returns, risk


@dataclass
class Snapshot:
    scheme_code: str
    as_of: str
    n_observations: int
    history_start: str | None
    history_years: float

    trailing_cagr: dict[str, float | None]   # e.g. {"6M": .., "1Y": .., "3Y": ..}
    annualized_return: float
    annualized_volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float

    # benchmark-relative (NaN/None when no benchmark supplied)
    beta: float | None = None
    alpha: float | None = None
    tracking_error: float | None = None
    information_ratio: float | None = None
    upside_capture: float | None = None
    downside_capture: float | None = None

    config_used: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _window_label(years: float) -> str:
    return f"{int(years * 12)}M" if years < 1 else f"{int(years)}Y"


def build_snapshot(
    nav: pd.Series,
    as_of: str | pd.Timestamp,
    benchmark: pd.Series | None = None,
    config: Config = DEFAULT_CONFIG,
    scheme_code: str = "",
) -> Snapshot:
    as_of = pd.Timestamp(as_of)
    ppy = config.periods_per_year

    # --- the cut: nothing past as_of survives this line ---
    nav_cut = returns.cut(nav, as_of).dropna()

    if len(nav_cut) < 2:
        raise ValueError(f"Insufficient NAV history on/before {as_of.date()}")

    # risk stats are computed over the trailing lookback window only
    lookback_start = nav_cut.index[-1] - pd.DateOffset(
        days=round(config.risk_lookback_years * 365.25)
    )
    nav_lb = nav_cut[nav_cut.index >= lookback_start]
    rets = returns.period_returns(nav_lb, ppy)

    trailing = {
        _window_label(y): returns.trailing_cagr(nav, as_of, y, config.min_window_coverage)
        for y in config.trailing_windows_years
    }

    cagr_lb = risk.annualized_return(rets, ppy)
    mdd = risk.max_drawdown(nav_lb)

    snap = Snapshot(
        scheme_code=scheme_code,
        as_of=str(as_of.date()),
        n_observations=int(len(nav_cut)),
        history_start=str(nav_cut.index[0].date()),
        history_years=round((nav_cut.index[-1] - nav_cut.index[0]).days / 365.25, 2),
        trailing_cagr=trailing,
        annualized_return=cagr_lb,
        annualized_volatility=risk.annualized_volatility(rets, ppy),
        sharpe=risk.sharpe_ratio(rets, config.rf_annual, ppy),
        sortino=risk.sortino_ratio(rets, config.rf_annual, ppy),
        max_drawdown=mdd,
        calmar=risk.calmar_ratio(cagr_lb, mdd),
        config_used={
            "rf_annual": config.rf_annual,
            "periods_per_year": ppy,
            "risk_lookback_years": config.risk_lookback_years,
        },
    )

    if benchmark is not None:
        bench_cut = returns.cut(benchmark, as_of).dropna()
        bench_lb = bench_cut[bench_cut.index >= lookback_start]
        bench_rets = returns.period_returns(bench_lb, ppy)
        beta, alpha = relative.beta_alpha(rets, bench_rets, config.rf_annual, ppy)
        up, down = relative.capture_ratios(rets, bench_rets)
        snap.beta = beta
        snap.alpha = alpha
        snap.tracking_error = relative.tracking_error(rets, bench_rets, ppy)
        snap.information_ratio = relative.information_ratio(rets, bench_rets, ppy)
        snap.upside_capture = up
        snap.downside_capture = down

    return snap
