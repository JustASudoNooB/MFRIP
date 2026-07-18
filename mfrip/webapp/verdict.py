"""One-line reads: a plain-English sentence built only from computed numbers.

Every clause is templated from a real metric; nothing here is opinion or
prediction. The read describes character, not future performance.
"""
from __future__ import annotations


def one_line_read(*, alpha: float | None = None, beta: float | None = None,
                  up_capture: float | None = None, down_capture: float | None = None,
                  max_dd: float | None = None, beat_share: float | None = None) -> str:
    """Compose a short character read from whichever metrics are available."""
    clauses: list[str] = []
    if alpha is not None:
        if alpha >= 0.02:
            clauses.append(f"has beaten its benchmark by about {alpha:.0%}/yr after adjusting for risk")
        elif alpha <= -0.02:
            clauses.append(f"has trailed its benchmark by about {abs(alpha):.0%}/yr after adjusting for risk")
        else:
            clauses.append("has roughly matched its benchmark after adjusting for risk")
    if beta is not None:
        if beta >= 1.15:
            clauses.append(f"swings noticeably harder than its index (beta {beta:.2f})")
        elif beta <= 0.85:
            clauses.append(f"rides gentler than its index (beta {beta:.2f})")
    if down_capture is not None and up_capture is not None:
        if down_capture <= 0.85 and up_capture >= 0.9:
            clauses.append("has protected well in falls while keeping most of the rises")
        elif down_capture >= 1.1:
            clauses.append("has fallen harder than its index in bad stretches")
    if beat_share is not None and not clauses:
        clauses.append(f"beat its benchmark in {beat_share:.0%} of rolling windows")
    if not clauses:
        return "Not enough overlapping benchmark history yet for a fair one-line read."
    read = "; ".join(clauses[:2])
    return "Over the last three years, this fund " + read + ". Character, not a promise."
