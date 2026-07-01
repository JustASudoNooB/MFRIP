from __future__ import annotations

import numpy as np
import pandas as pd

from mfrip.metrics import capture, rolling, sip


def _growth(ann, vol, start="2018-01-01", end="2026-06-19", seed=1):
    ix = pd.date_range(start, end, freq="D")
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.cumprod(1 + rng.normal((1 + ann) ** (1 / 365) - 1,
                     vol / np.sqrt(365), len(ix))), index=ix)


def test_rolling_window_count_and_keys():
    r = rolling.rolling_returns(_growth(0.12, 0.16), 3)
    assert r and r["count"] > 0 and r["worst"] <= r["avg"] <= r["best"]


def test_rolling_returns_none_when_too_short():
    assert rolling.rolling_returns(_growth(0.1, 0.15, end="2018-08-01"), 5) is None


def test_rolling_outperformance_range():
    p = rolling.rolling_outperformance(_growth(0.15, 0.18, seed=1), _growth(0.10, 0.15, seed=2), 3)
    assert p is None or 0.0 <= p <= 1.0


def test_capture_aggressive_vs_defensive():
    ix = pd.date_range("2018-01-01", "2026-06-19", freq="ME")
    rng = np.random.default_rng(7)
    br = rng.normal(0.009, 0.04, len(ix))
    bench = pd.Series(100 * np.cumprod(1 + br), index=ix)
    aggr = pd.Series(100 * np.cumprod(1 + 1.2 * br + rng.normal(0, 0.004, len(ix))), index=ix)
    defn = pd.Series(100 * np.cumprod(1 + np.where(br < 0, 0.7 * br, 0.9 * br)), index=ix)
    ua, da = capture.capture_ratios(aggr, bench)
    ud, dd = capture.capture_ratios(defn, bench)
    assert ua > 1.0 and da > 1.0 and dd < da


def test_stress_test_returns_episodes():
    for r in capture.stress_test(_growth(0.12, 0.18)):
        assert {"name", "return", "drawdown", "start", "end"} <= set(r)


def test_sip_xirr_flat_is_zero():
    ix = pd.date_range("2018-01-01", "2026-06-19", freq="D")
    r = sip.sip_xirr(pd.Series(100.0, index=ix), 10000, "2018-01-01", "2026-06-19")
    assert r and abs(r["xirr"]) < 0.01


def test_sip_xirr_positive_on_growth():
    r = sip.sip_xirr(_growth(0.14, 0.18), 10000, "2018-01-01", "2026-06-19")
    assert r and r["xirr"] > 0 and r["final_value"] > r["invested"]


def test_goal_projection_monotonic_in_rate():
    g = sip.goal_projection(10000, 15)
    assert [g[r] for r in sorted(g)] == sorted(g.values())


def test_required_sip_reaches_target():
    monthly = sip.required_sip(1_00_00_000, 15, 0.10)
    fv = sip.goal_projection(monthly, 15, rates=(0.10,))[0.10]
    assert abs(fv - 1_00_00_000) / 1_00_00_000 < 0.02
