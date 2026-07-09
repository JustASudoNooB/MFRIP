"""Recommendation domain objects + persistence."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class RecFund:
    display_name: str
    weight: float                 # fraction of total (0..1)
    asset_class: str = "equity"
    search_hint: str | None = None
    scheme_code: int | None = None
    resolved_name: str | None = None
    included: bool = True
    note: str | None = None


@dataclass
class Recommendation:
    creator: str
    advisor: str
    rec_date: str
    risk_profile: str = ""
    horizon: str = ""
    rationale: str = ""
    source_platform: str = ""
    source_url: str = ""
    total_amount: float = 1_000_000.0
    funds: list[RecFund] = field(default_factory=list)
    rec_id: int | None = None


def save_recommendation(conn: sqlite3.Connection, rec: Recommendation) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        """
        INSERT INTO recommendations
            (creator, advisor, source_platform, source_url, rec_date,
             risk_profile, horizon, rationale, total_amount, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (rec.creator, rec.advisor, rec.source_platform, rec.source_url, rec.rec_date,
         rec.risk_profile, rec.horizon, rec.rationale, rec.total_amount, now),
    )
    rec_id = int(cur.lastrowid)
    for f in rec.funds:
        conn.execute(
            """
            INSERT INTO recommendation_funds
                (rec_id, display_name, search_hint, scheme_code, resolved_name,
                 weight, asset_class, included, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rec_id, display_name) DO UPDATE SET
                search_hint=excluded.search_hint, scheme_code=excluded.scheme_code,
                resolved_name=excluded.resolved_name, weight=excluded.weight,
                asset_class=excluded.asset_class, included=excluded.included,
                note=excluded.note
            """,
            (rec_id, f.display_name, f.search_hint, f.scheme_code, f.resolved_name,
             f.weight, f.asset_class, int(f.included), f.note),
        )
    conn.commit()
    return rec_id


def load_recommendation(conn: sqlite3.Connection, rec_id: int) -> Recommendation:
    r = conn.execute("SELECT * FROM recommendations WHERE rec_id = ?", (rec_id,)).fetchone()
    if r is None:
        raise ValueError(f"No recommendation {rec_id}")
    funds = [
        RecFund(
            display_name=fr["display_name"], weight=fr["weight"],
            asset_class=fr["asset_class"], search_hint=fr["search_hint"],
            scheme_code=fr["scheme_code"], resolved_name=fr["resolved_name"],
            included=bool(fr["included"]), note=fr["note"],
        )
        for fr in conn.execute(
            "SELECT * FROM recommendation_funds WHERE rec_id = ? ORDER BY rowid", (rec_id,)
        ).fetchall()
    ]
    return Recommendation(
        rec_id=r["rec_id"], creator=r["creator"], advisor=r["advisor"],
        rec_date=r["rec_date"], risk_profile=r["risk_profile"], horizon=r["horizon"],
        rationale=r["rationale"], source_platform=r["source_platform"],
        source_url=r["source_url"], total_amount=r["total_amount"], funds=funds,
    )


def update_fund_resolution(conn, rec_id: int, display_name: str, code: int, resolved_name: str) -> None:
    conn.execute(
        "UPDATE recommendation_funds SET scheme_code=?, resolved_name=? WHERE rec_id=? AND display_name=?",
        (code, resolved_name, rec_id, display_name),
    )
    conn.commit()
