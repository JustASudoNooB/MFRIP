"""mfapi.in client.

Free, open, no-auth REST API for Indian mutual fund NAVs.
  GET /mf                      -> [{schemeCode, schemeName}, ...]
  GET /mf/search?q=...         -> [{schemeCode, schemeName}, ...]
  GET /mf/{code}               -> {meta:{...}, data:[{date:"DD-MM-YYYY", nav:"..."}], status}

This module does no caching and no DB work; it just returns clean Python
objects. Caching is the store layer's job. Network calls only happen here.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import requests

BASE_URL = "https://api.mfapi.in/mf"
_TIMEOUT = 30


def _get_session(session: requests.Session | None) -> requests.Session:
    return session if session is not None else requests.Session()


def fetch_scheme_list(session: requests.Session | None = None) -> list[dict[str, Any]]:
    """Full universe of schemes as [{'schemeCode': int, 'schemeName': str}, ...]."""
    s = _get_session(session)
    resp = s.get(BASE_URL, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def search_schemes(query: str, session: requests.Session | None = None) -> list[dict[str, Any]]:
    """Resolve a free-text name to candidate scheme codes.

    mfapi scheme names are verbose ('HDFC Top 100 Fund - Direct Plan - Growth'),
    so a recommendation that just says 'HDFC Top 100' must be disambiguated.
    """
    s = _get_session(session)
    resp = s.get(f"{BASE_URL}/search", params={"q": query}, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_nav_history(
    scheme_code: int | str, session: requests.Session | None = None
) -> tuple[dict[str, Any], list[tuple[date, float]]]:
    """Return (meta, [(date, nav), ...]) sorted ascending by date.

    Non-positive / unparseable NAV rows are dropped. NAV for growth-option
    funds is already total-return (distributions reinvested), so no
    adjustment is needed downstream.
    """
    s = _get_session(session)
    resp = s.get(f"{BASE_URL}/{scheme_code}", timeout=_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()

    meta = payload.get("meta", {}) or {}
    rows = payload.get("data", []) or []

    parsed: list[tuple[date, float]] = []
    for row in rows:
        try:
            d = datetime.strptime(row["date"], "%d-%m-%Y").date()
            nav = float(row["nav"])
        except (KeyError, ValueError, TypeError):
            continue
        if nav > 0:
            parsed.append((d, nav))

    parsed.sort(key=lambda t: t[0])
    return meta, parsed
