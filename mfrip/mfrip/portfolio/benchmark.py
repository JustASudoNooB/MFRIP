"""Build a 'passive twin' of a recommendation.

Takes the plan's equity/debt/gold/hybrid weights and fills them with cheap
index-fund proxies instead of the advisor's chosen funds. Comparing the real
plan against this isolates *fund-selection skill* from the asset-allocation
decision: beating it means the picks added value beyond just the mix.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from ..config import ASSET_PROXIES, HYBRID_SPLIT
from ..store import nav_store
from .reconstruct import Reconstruction, reconstruct


def aggregate_asset_weights(rec) -> dict[str, float]:
    """Priced weight per asset class, renormalised over the priceable sleeve."""
    w: dict[str, float] = {}
    for f in rec.funds:
        if f.included and f.scheme_code:
            w[f.asset_class] = w.get(f.asset_class, 0.0) + f.weight
    total = sum(w.values())
    return {k: v / total for k, v in w.items()} if total > 0 else {}


def proxy_weights(asset_weights: dict[str, float], hybrid_split=HYBRID_SPLIT) -> dict[str, float]:
    """Collapse asset-class weights onto equity/debt/gold proxy buckets."""
    out = {"equity": 0.0, "debt": 0.0, "gold": 0.0}
    for ac, wt in asset_weights.items():
        if ac in ("equity", "debt", "gold"):
            out[ac] += wt
        elif ac == "hybrid":
            out["equity"] += wt * hybrid_split[0]
            out["debt"] += wt * hybrid_split[1]
        elif ac == "alternatives":
            continue  # no clean passive proxy -> drop and renormalise
        else:
            out["equity"] += wt
    total = sum(out.values())
    return {k: v / total for k, v in out.items() if v > 0} if total > 0 else {}


def build_blended_from_weights(
    conn: sqlite3.Connection,
    asset_weights: dict[str, float],
    start,
    amount: float,
    proxies: dict[str, int] = ASSET_PROXIES,
) -> Reconstruction | None:
    """Passive twin from an explicit asset-class weighting (already renormalised)."""
    pw = proxy_weights(asset_weights)
    nav_by_code, weights = {}, {}
    for ac, wt in pw.items():
        code = proxies.get(ac)
        if not code:
            continue
        s = nav_store.load_nav(conn, code)
        if s.empty:
            continue
        nav_by_code[code] = s
        weights[code] = weights.get(code, 0.0) + wt
    if not weights:
        return None
    return reconstruct(nav_by_code, weights, start, amount)


def build_blended_benchmark(
    conn: sqlite3.Connection,
    rec,
    start,
    amount: float,
    proxies: dict[str, int] = ASSET_PROXIES,
) -> Reconstruction | None:
    """Passive twin of the full plan allocation."""
    return build_blended_from_weights(
        conn, aggregate_asset_weights(rec), start, amount, proxies
    )
