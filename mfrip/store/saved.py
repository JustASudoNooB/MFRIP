"""Local persistence for user-built portfolios.

Saved into the same SQLite database the rest of the app uses, so a person can
keep their portfolio and revisit or compare it later. The table is created on
demand, so existing databases need no migration.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


def _ensure(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS saved_portfolios (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            created_at TEXT NOT NULL,
            holdings   TEXT NOT NULL
        )
    """)
    conn.commit()


def save_portfolio(conn: sqlite3.Connection, name: str,
                   holdings: list[tuple[int, float, str]]) -> int:
    """holdings: list of (scheme_code, weight, name). Returns the new row id."""
    _ensure(conn)
    payload = json.dumps([{"code": int(c), "weight": float(w), "name": n} for c, w, n in holdings])
    cur = conn.execute(
        "INSERT INTO saved_portfolios(name, created_at, holdings) VALUES(?,?,?)",
        (name.strip() or "Untitled", datetime.now(timezone.utc).isoformat(timespec="seconds"), payload),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_portfolios(conn: sqlite3.Connection) -> list[dict]:
    """Newest first. Each: {id, name, created_at, holdings:[(code,weight,name)]}."""
    _ensure(conn)
    rows = conn.execute(
        "SELECT id, name, created_at, holdings FROM saved_portfolios ORDER BY id DESC"
    ).fetchall()
    out = []
    for r in rows:
        items = json.loads(r["holdings"])
        out.append({
            "id": int(r["id"]), "name": r["name"], "created_at": r["created_at"],
            "holdings": [(int(i["code"]), float(i["weight"]), i.get("name", str(i["code"]))) for i in items],
        })
    return out


def load_portfolio(conn: sqlite3.Connection, pid: int) -> dict | None:
    _ensure(conn)
    r = conn.execute(
        "SELECT id, name, created_at, holdings FROM saved_portfolios WHERE id=?", (int(pid),)
    ).fetchone()
    if not r:
        return None
    items = json.loads(r["holdings"])
    return {
        "id": int(r["id"]), "name": r["name"], "created_at": r["created_at"],
        "holdings": [(int(i["code"]), float(i["weight"]), i.get("name", str(i["code"]))) for i in items],
    }


def delete_portfolio(conn: sqlite3.Connection, pid: int) -> None:
    _ensure(conn)
    conn.execute("DELETE FROM saved_portfolios WHERE id=?", (int(pid),))
    conn.commit()
