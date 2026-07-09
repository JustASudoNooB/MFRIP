"""Central configuration.

All assumptions that affect a number live here so they are explicit and
auditable. Nothing in the metrics engine hard-codes a rate or a window.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DB_PATH = Path("mfrip_data.db")


@dataclass(frozen=True)
class Config:
    # INR risk-free proxy (annual, decimal). Roughly a T-bill / overnight rate.
    # Override per-study; it materially moves Sharpe/Sortino, so it is explicit.
    rf_annual: float = 0.065

    # Return frequency for risk-adjusted stats. Monthly is the professional
    # default (Morningstar convention) and avoids the stale-NAV daily
    # autocorrelation problem that inflates Sharpe for debt funds.
    periods_per_year: int = 12  # 12 = monthly, 252 = daily

    # Lookback window (years) used for vol / Sharpe / Sortino / beta / alpha.
    risk_lookback_years: float = 3.0

    # Trailing CAGR windows reported in a snapshot (years).
    trailing_windows_years: tuple[float, ...] = (0.5, 1.0, 3.0, 5.0, 10.0)

    # A trailing window is reported only if realised history covers at least
    # this fraction of it; otherwise the metric is None (never fabricated).
    min_window_coverage: float = 0.9

    db_path: Path = field(default_factory=lambda: DEFAULT_DB_PATH)


DEFAULT_CONFIG = Config()

# Passive index-fund proxies for building a "same allocation, done passively"
# benchmark. Codes chosen to be ones already commonly cached:
#   equity -> UTI Nifty 50 Index (Direct-Growth)
#   debt   -> HDFC Nifty G-Sec Jul 2031 Index (a govt-bond proxy)
#   gold   -> Nippon India Gold Savings
# Override via the CLI if you prefer broader proxies (e.g. a Nifty 500 fund).
ASSET_PROXIES: dict[str, int] = {
    "equity": 120716,
    "debt": 150847,
    "gold": 118663,
}
HYBRID_SPLIT = (0.65, 0.35)  # how a 'hybrid' sleeve maps to (equity, debt) proxies
