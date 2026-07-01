"""Resolve a slide fund name to a scheme code using the LOCAL scheme master.

No network: it searches the schemes table you already populated with
`sync-schemes`. Indian fund names are messy ('Kotak Mid Cap' is officially
'Kotak Emerging Equity Fund'), so this returns ranked candidates and the
loader/user confirms. Preference order baked into scoring:
  Direct plan > Regular,  Growth > IDCW/Dividend.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# common slide-shorthand -> tokens that actually appear in scheme names
_NORMALISE = {
    "mid": "mid", "midcap": "mid", "smallcap": "small", "largecap": "large",
    "multicap": "multi", "flexicap": "flexi", "g": "gsec", "gsec": "gsec",
    "pru": "prudential", "robo": "robeco",
}

# generic words that should not count as a real name match on their own
_STOP = {
    "fund", "plan", "direct", "regular", "growth", "option", "scheme",
    "india", "the", "of", "and", "idcw", "payout", "reinvestment",
}


def _tokens(name: str) -> list[str]:
    raw = _TOKEN_RE.findall(name.lower())
    return [_NORMALISE.get(t, t) for t in raw]


def _meaningful(tokens: set[str]) -> set[str]:
    m = tokens - _STOP
    return m if m else tokens  # fall back if a query is all generic words


@dataclass
class Candidate:
    scheme_code: int
    scheme_name: str
    score: float


def resolve_name(
    conn: sqlite3.Connection,
    query: str,
    prefer_direct: bool = True,
    prefer_growth: bool = True,
    limit: int = 5,
) -> list[Candidate]:
    q_all = set(_tokens(query))
    q_tokens = _meaningful(q_all)
    if not q_tokens:
        return []

    rows = conn.execute("SELECT scheme_code, scheme_name FROM schemes").fetchall()
    scored: list[Candidate] = []
    for r in rows:
        name = r["scheme_name"]
        n_meaningful = _meaningful(set(_tokens(name)))
        overlap = q_tokens & n_meaningful
        if not overlap:
            continue  # no real (non-generic) overlap -> not a match
        # coverage of the query's meaningful tokens, lightly penalise extra noise
        base = len(overlap) / len(q_tokens) - 0.02 * len(n_meaningful - q_tokens)

        low = name.lower()
        bonus = 0.0
        if prefer_direct and "direct" in low:
            bonus += 0.15
        if prefer_growth:
            if "growth" in low:
                bonus += 0.10
            if "idcw" in low or "payout" in low or "reinvest" in low:
                bonus -= 0.30
        score = base + bonus

        scored.append(Candidate(int(r["scheme_code"]), name, round(score, 4)))

    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:limit]
