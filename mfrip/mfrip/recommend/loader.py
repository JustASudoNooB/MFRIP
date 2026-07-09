"""Load a recommendation from a YAML file and auto-resolve fund codes.

YAML shape (see recommendations/feroz_moderate.yaml):

    creator: Ankur Warikoo
    advisor: Feroz Aziz
    rec_date: 2025-11-08
    total_amount: 1000000
    buckets:
      - asset_class: equity
        amount: 700000
        funds: [{name: "DSP Large and Mid Cap"}, ...]   # equal-split within bucket

Weights are derived from bucket amount / total, split equally across the
funds in a bucket unless a fund specifies its own `amount`.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml

from .resolve import resolve_name
from .schema import RecFund, Recommendation


def parse_yaml(path: str | Path) -> Recommendation:
    data = yaml.safe_load(Path(path).read_text())
    total = float(data.get("total_amount", 1_000_000))

    funds: list[RecFund] = []
    for bucket in data.get("buckets", []):
        ac = bucket.get("asset_class", "equity")
        bucket_amt = float(bucket["amount"])
        items = bucket["funds"]
        # explicit per-fund amounts, else equal split of the bucket
        explicit = [float(i["amount"]) for i in items if "amount" in i]
        default_amt = (bucket_amt - sum(explicit)) / max(1, len(items) - len(explicit))
        for it in items:
            amt = float(it.get("amount", default_amt))
            funds.append(RecFund(
                display_name=it["name"],
                weight=amt / total,
                asset_class=ac,
                search_hint=it.get("search"),
                included=it.get("included", True),
                note=it.get("note"),
            ))

    return Recommendation(
        creator=data.get("creator", ""),
        advisor=data.get("advisor", ""),
        rec_date=str(data["rec_date"]),
        risk_profile=data.get("risk_profile", ""),
        horizon=data.get("horizon", ""),
        rationale=data.get("rationale", ""),
        source_platform=data.get("source_platform", ""),
        source_url=data.get("source_url", ""),
        total_amount=total,
        funds=funds,
    )


def auto_resolve(conn: sqlite3.Connection, rec: Recommendation) -> list[tuple[RecFund, list]]:
    """Attach the best candidate code to each included fund; return candidates too."""
    report = []
    for f in rec.funds:
        if not f.included:
            report.append((f, []))
            continue
        query = f.search_hint or f.display_name
        cands = resolve_name(conn, query, limit=4)
        if cands:
            f.scheme_code = cands[0].scheme_code
            f.resolved_name = cands[0].scheme_name
        report.append((f, cands))
    return report
