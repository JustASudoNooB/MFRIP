"""Tests for the fund screener: methodology, comparability guards, styling."""
import numpy as np
import pandas as pd

from mfrip.store import db as DB
from mfrip.webapp import screener as SCR


def _add_fund(conn, code, name, nav: pd.Series):
    conn.execute("INSERT INTO schemes (scheme_code, scheme_name) VALUES (?,?)", (code, name))
    conn.executemany("INSERT INTO nav (scheme_code, date, nav) VALUES (?,?,?)",
                     [(code, d.strftime("%Y-%m-%d"), float(v)) for d, v in nav.items()])


def _walk(dates, mu, sd, seed):
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.cumprod(1 + rng.normal(mu, sd, len(dates))), index=dates)


def _mini_db(n_per=4, seed=0, end="2024-06-28"):
    conn = DB.connect(":memory:")
    DB.init_db(conn)
    dates = pd.bdate_range("2018-01-01", end)
    code = 1000
    for sname in ("Large Cap", "Mid Cap"):
        q = np.linspace(-1, 1, n_per)
        for i in range(n_per):
            _add_fund(conn, code, f"Synthetic {sname} Fund {i+1}",
                      _walk(dates, 0.0005 + 0.0003 * q[i], 0.01, seed * 100 + code))
            code += 1
    conn.commit()
    return conn


def test_screener_shape_and_columns():
    df = SCR.build_screener(_mini_db())
    assert len(df) == 8
    for col in ["Fund", "Category", "Yrs", "6M", "1Y", "3Y", "5Y",
                "vs Cat", "Vol 3Y", "DD 3Y", "Score"]:
        assert col in df.columns


def test_percentile_score_is_outlier_robust():
    # With min-max scaling, adding one catastrophic fund squashes everyone
    # else toward the top. With percentile ranks, existing funds keep spread.
    conn = _mini_db(n_per=5)
    before = SCR.build_screener(conn).set_index("Fund")["Score"]
    dates = pd.bdate_range("2018-01-01", "2024-06-28")
    crash = pd.Series(np.linspace(100.0, 3.0, len(dates)), index=dates)  # -97%
    _add_fund(conn, 9999, "Synthetic Large Cap Fund 99", crash)
    conn.commit()
    after = SCR.build_screener(conn).set_index("Fund")["Score"]
    assert after["Synthetic Large Cap Fund 99"] <= 15          # outlier lands at the bottom
    common = [f for f in before.index if "Large Cap" in f]
    spread_before = before[common].max() - before[common].min()
    spread_after = after[common].max() - after[common].min()
    assert spread_after >= 0.6 * spread_before                 # peers not squashed together


def test_stale_fund_blanks_period_columns():
    conn = _mini_db(n_per=3)
    stale_dates = pd.bdate_range("2018-01-01", "2024-03-28")   # ends ~3 months early
    _add_fund(conn, 5000, "Synthetic Large Cap Fund 77", _walk(stale_dates, 0.0005, 0.01, 7))
    conn.commit()
    df = SCR.build_screener(conn).set_index("Fund")
    row = df.loc["Synthetic Large Cap Fund 77"]
    assert bool(row["_stale"]) is True
    for c in ["6M", "1Y", "3Y", "5Y", "Vol 3Y", "DD 3Y"]:
        assert pd.isna(row[c])                                 # blank, not misleading
    fresh = df.drop(index="Synthetic Large Cap Fund 77")
    assert fresh["1Y"].notna().all()


def test_risk_window_ignores_old_crash():
    # A fund that crashed 5 years ago but has been calm for the last 3 years
    # must NOT show the old crash in its 3Y drawdown column.
    conn = DB.connect(":memory:"); DB.init_db(conn)
    dates = pd.bdate_range("2017-01-02", "2024-06-28")
    n = len(dates)
    crash_end = int(n * 0.25)                                  # crash in the first quarter
    vals = np.empty(n)
    vals[:crash_end] = np.linspace(100, 55, crash_end)         # -45% early crash
    vals[crash_end:] = 55 * np.cumprod(1 + np.full(n - crash_end, 0.0004))
    _add_fund(conn, 1, "Synthetic Large Cap Fund 1", pd.Series(vals, index=dates))
    for i, seed in enumerate((2, 3)):
        _add_fund(conn, 2 + i, f"Synthetic Large Cap Fund {2+i}", _walk(dates, 0.0004, 0.008, seed))
    conn.commit()
    df = SCR.build_screener(conn).set_index("Fund")
    assert df.loc["Synthetic Large Cap Fund 1", "DD 3Y"] > -12.0   # calm recent window


def test_vs_cat_median_is_centred():
    df = SCR.build_screener(_mini_db(n_per=5))
    for _sl, g in df.groupby("_sleeve"):
        v = g["vs Cat"].dropna()
        assert len(v) >= 3
        assert abs(v.median()) < 1e-6                          # median fund sits at 0


def test_small_category_gets_no_score():
    conn = _mini_db(n_per=4)
    dates = pd.bdate_range("2018-01-01", "2024-06-28")
    _add_fund(conn, 7000, "Synthetic Gold Fund 1", _walk(dates, 0.0003, 0.005, 11))
    _add_fund(conn, 7001, "Synthetic Gold Fund 2", _walk(dates, 0.0003, 0.005, 12))
    conn.commit()
    df = SCR.build_screener(conn).set_index("Fund")
    assert pd.isna(df.loc["Synthetic Gold Fund 1", "Score"])   # only 2 peers < MIN_PEERS
    assert df.loc["Synthetic Large Cap Fund 1", "Score"] is not None


def test_leaders_laggards_orders_by_return():
    df = SCR.build_screener(_mini_db(n_per=5))
    ll = SCR.leaders_laggards(df, by="3Y", n=3)
    assert set(ll) == {"largecap", "midcap"}
    for _sl, (top, bottom) in ll.items():
        assert top["3Y"].iloc[0] >= bottom["3Y"].iloc[0]


def test_style_screener_runs():
    df = SCR.build_screener(_mini_db()).drop(columns=["_sleeve", "_stale"])
    html = SCR.style_screener(df).to_html()
    assert "color:" in html and "background-color" in html


def test_empty_db_returns_empty_frame():
    conn = DB.connect(":memory:")
    DB.init_db(conn)
    assert SCR.build_screener(conn).empty


def test_screener_alpha_beta_benchmark_self_control():
    # A category's own benchmark fund must show beta ~1.00 and alpha ~0.0
    conn = DB.connect(":memory:"); DB.init_db(conn)
    import datetime as dt
    end = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    dates = pd.bdate_range("2019-01-02", end)
    rng = np.random.default_rng(9)
    bench = pd.Series(100 * np.cumprod(1 + rng.normal(0.0005, 0.009, len(dates))), index=dates)
    _add_fund(conn, 120716, "UTI Nifty 50 Index Fund - Direct Plan - Growth", bench)
    for i, seed in enumerate((21, 22, 23)):
        _add_fund(conn, 200 + i, f"Active Large Cap Fund {i+1} - Direct Growth",
                  _walk(dates, 0.00055, 0.01, seed))
    conn.commit()
    df = SCR.build_screener(conn).set_index("Fund")
    row = df.loc["UTI Nifty 50 Index Fund - Direct Plan - Growth"]
    assert row["Beta 3Y"] == 1.0
    assert abs(row["Alpha 3Y"]) < 0.05          # zero to rounding
    # active funds get real numbers too
    assert df.loc["Active Large Cap Fund 1 - Direct Growth", "Beta 3Y"] is not None


def test_one_line_read_is_templated_and_honest():
    from mfrip.webapp.verdict import one_line_read
    r = one_line_read(alpha=0.031, beta=1.2, up_capture=1.0, down_capture=1.2)
    assert "3%" in r and "beta 1.20" in r and "not a promise" in r
    assert one_line_read().startswith("Not enough")
