"""Infer a fund's sleeve from its scheme name.

mfapi gives names, not clean SEBI categories, so we keyword-match. Order matters
(check small/mid before large; debt keywords before generic). Honest about its
limits, ambiguous names return None and are simply not used as candidates.
"""
from __future__ import annotations

import re

# checked top-to-bottom; first hit wins
_RULES: list[tuple[str, list[str]]] = [
    ("gold", ["gold", "silver etf fof", "precious metal"]),
    ("debt", ["liquid", "overnight", "money market", "ultra short", "low duration",
              "short duration", "short term", "medium duration", "long duration",
              "corporate bond", "banking and psu", "banking & psu", "credit risk",
              "dynamic bond", "gilt", "g-sec", "gsec", "government securities",
              "sdl", "bond fund", "debt", "income fund", "floater", "psu debt"]),
    ("international", ["international", "global", "us equity", "u.s. equity", "nasdaq",
                       "s&p 500", "emerging market", "china", "greater china", "overseas",
                       "world", "fang", "developed market"]),
    ("smallcap", ["small cap", "smallcap", "small-cap"]),
    ("midcap", ["mid cap", "midcap", "mid-cap", "midc300", "emerging equit"]),
    ("largecap", ["large cap", "largecap", "large-cap", "bluechip", "blue chip", "top 100",
                  "nifty 50", "nifty50", "sensex", "nifty next 50", "large cap index"]),
    ("flexicap", ["flexi cap", "flexicap", "flexi-cap", "multi cap", "multicap", "multi-cap",
                  "focused", "elss", "tax saver", "long term equity", "large & mid",
                  "large and mid", "value fund", "contra", "dividend yield",
                  "nifty 500", "multi asset"]),
]

_HYBRID = ["hybrid", "balanced", "asset allocation", "equity savings", "arbitrage",
           "conservative hybrid", "aggressive hybrid", "dynamic asset"]


def infer_sleeve(name: str) -> str | None:
    s = " " + re.sub(r"\s+", " ", name.lower()) + " "
    # hybrids are deliberately not slotted into a single equity sleeve
    if any(k in s for k in _HYBRID) and not any(k in s for k in ("nifty 50", "index")):
        return None
    for sleeve, keys in _RULES:
        if any(k in s for k in keys):
            return sleeve
    # plain index funds without a cap qualifier → treat as largecap proxy
    if "index" in s or "nifty" in s:
        return "largecap"
    return None
