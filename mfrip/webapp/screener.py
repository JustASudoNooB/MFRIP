"""Fund screener: every fund in the database in one comparable table.

Methodology, stated plainly:

- **Common valuation date.** All returns are measured as of one shared date
  (the latest NAV anywhere in the universe), so every fund's "1Y" covers the
  same year. A fund whose own NAV is more than STALE_DAYS behind that date is
  shown but its period columns are left blank rather than silently comparing
  different windows.
- **Return conventions.** 6M and 1Y are total returns over the period; 3Y and
  5Y are annualised (CAGR). A cell is blank when the fund lacks about 90% of
  the window's history (never a fabricated number).
- **Common risk window.** Volatility and max drawdown are computed over the
  trailing three years only, so a 20-year fund is not penalised for a crash a
  15-year-old fund never lived through. Blank if under ~2.75y of history.
- **vs Cat.** The fund's 3Y return minus its category's median 3Y, in
  percentage points, when the category has at least MIN_PEERS funds.
- **Alpha / Beta (3Y).** Jensen's alpha and beta against the fund's own
  category benchmark over the same trailing three years. Alpha is the
  annualised return beyond what the fund's beta and the benchmark's move would
  predict; beta is how hard the fund swings relative to that benchmark. Blank
  when the category has no cached benchmark or overlap is too short.
- **Score.** MFRIP's composite (consistency 38%, Sortino 25%, Sharpe 19%,
  drawdown resilience 18%), each factor expressed as a percentile rank within
  the category, so one outlier cannot squash everyone else's scores. Needs at
  least MIN_PEERS peers to be meaningful.

AUM, expense ratio and third-party star ratings are deliberately absent: the
free data source (mfapi.in) does not provide them, and MFRIP never displays a
number it cannot compute from real data.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from ..advisor.categorize import infer_sleeve
from ..advisor.ranking import rank_sleeve
from ..config import Config, DEFAULT_CONFIG
from ..metrics import returns as RET
from ..metrics import risk as RISK
from ..metrics.relative import beta_alpha
from ..store.nav_store import load_nav
from .benchmarks import resolve_benchmark
from .data import available_funds

SLEEVE_LABEL = {
    "largecap": "Large Cap", "flexicap": "Flexi/Multi Cap", "midcap": "Mid Cap",
    "smallcap": "Small Cap", "international": "International", "debt": "Debt",
    "gold": "Gold",
}
RETURN_COLS = ["6M", "1Y", "3Y", "5Y"]
STALE_DAYS = 21          # max lag behind the universe date before blanking
RISK_YEARS = 3.0         # common window for volatility / drawdown
RISK_MIN_YEARS = 2.75    # minimum realised span for the risk window
MIN_PEERS = 3            # smallest category we score / compare against


def _pctv(x):
    return None if x is None else round(x * 100.0, 1)


def _risk_3y(nav: pd.Series, as_of: pd.Timestamp):
    """(vol %, max drawdown %) over the trailing RISK_YEARS, or (None, None)."""
    start = as_of - pd.DateOffset(days=round(RISK_YEARS * 365.25))
    win = nav.loc[start:as_of]
    if len(win) < 2:
        return None, None
    span = (win.index[-1] - win.index[0]).days / 365.25
    if span < RISK_MIN_YEARS:
        return None, None
    rets = RET.period_returns(win, 12)
    vol = RISK.annualized_volatility(rets, 12) * 100 if len(rets) > 2 else None
    return (round(vol, 1) if vol is not None else None,
            round(RISK.max_drawdown(win) * 100, 1))


def build_screener(conn: sqlite3.Connection, config: Config = DEFAULT_CONFIG) -> pd.DataFrame:
    """One row per fund. Returns an empty frame when nothing has NAV history."""
    navs: dict[int, tuple[str, pd.Series]] = {}
    for code, name in available_funds(conn):
        nav = load_nav(conn, code)
        if nav is None or len(nav.dropna()) < 2:
            continue
        navs[code] = (name, nav.dropna().sort_index())
    if not navs:
        return pd.DataFrame()

    as_of = max(nav.index[-1] for _n, nav in navs.values())

    # composite score, percentile-based within each category (>= MIN_PEERS)
    by_sleeve: dict[str, dict[int, tuple[str, pd.Series]]] = {}
    for code, (name, nav) in navs.items():
        sl = infer_sleeve(name) or "other"
        by_sleeve.setdefault(sl, {})[code] = (name, nav)
    score: dict[int, float] = {}
    for sl, group in by_sleeve.items():
        if len(group) < MIN_PEERS:
            continue
        names = {c: nm for c, (nm, _n) in group.items()}
        series = {c: n for c, (_nm, n) in group.items()}
        for fs in rank_sleeve(names, series, config):
            score[fs.code] = fs.composite

    # one benchmark NAV per category, resolved once
    bench_nav: dict[str, pd.Series] = {}
    for sl in by_sleeve:
        bcode, _blabel = resolve_benchmark(conn, sl)
        if bcode:
            bn = load_nav(conn, bcode)
            if bn is not None and not bn.empty:
                bench_nav[sl] = bn.dropna().sort_index()
    risk_start = as_of - pd.DateOffset(days=round(RISK_YEARS * 365.25))

    rows = []
    for code, (name, nav) in navs.items():
        sl = infer_sleeve(name) or "other"
        fresh = (as_of - nav.index[-1]).days <= STALE_DAYS
        if fresh:
            r6 = _pctv(RET.trailing_cagr(nav, as_of, 0.5))
            r1 = _pctv(RET.trailing_cagr(nav, as_of, 1.0))
            r3 = _pctv(RET.trailing_cagr(nav, as_of, 3.0))
            r5 = _pctv(RET.trailing_cagr(nav, as_of, 5.0))
            vol, dd = _risk_3y(nav, as_of)
            beta = alpha = None
            bn = bench_nav.get(sl)
            if bn is not None and (as_of - bn.index[-1]).days <= STALE_DAYS:
                fr = RET.period_returns(nav.loc[risk_start:as_of], 12)
                br = RET.period_returns(bn.loc[risk_start:as_of], 12)
                joined = pd.DataFrame({"f": fr, "b": br}).dropna()
                if len(joined) >= 24:
                    b_, a_ = beta_alpha(joined["f"], joined["b"],
                                        config.rf_annual, config.periods_per_year)
                    beta, alpha = round(b_, 2), round(a_ * 100.0, 1)
        else:
            r6 = r1 = r3 = r5 = vol = dd = beta = alpha = None
        rows.append({
            "Fund": name,
            "Category": SLEEVE_LABEL.get(sl, sl.title()),
            "Yrs": round((nav.index[-1] - nav.index[0]).days / 365.25, 1),
            "6M": r6, "1Y": r1, "3Y": r3, "5Y": r5,
            "vs Cat": None,   # filled below from category medians
            "Alpha 3Y": alpha,
            "Beta 3Y": beta,
            "Vol 3Y": vol,
            "DD 3Y": dd,
            "Score": round(score[code], 0) if code in score else None,
            "_sleeve": sl,
            "_stale": not fresh,
        })
    df = pd.DataFrame(rows)

    # 3Y return relative to the category median, in percentage points
    med = (df.dropna(subset=["3Y"]).groupby("_sleeve")["3Y"]
             .agg(["median", "count"]))
    for sl, row in med.iterrows():
        if row["count"] >= MIN_PEERS:
            mask = (df["_sleeve"] == sl) & df["3Y"].notna()
            df.loc[mask, "vs Cat"] = (df.loc[mask, "3Y"] - row["median"]).round(1)

    return df.sort_values("Fund").reset_index(drop=True)


def style_screener(df: pd.DataFrame):
    """screener.in-style presentation: quiet table, green/red return text,
    a soft pastel gradient only on the Score column."""
    from matplotlib.colors import LinearSegmentedColormap
    GREEN, RED, MUTED = "#147A52", "#C2452D", "#8D8677"
    soft = LinearSegmentedColormap.from_list(
        "soft_score", ["#F3DED6", "#F0EBDD", "#DEEAE2"])

    fmt = {c: "{:+.1f}%" for c in RETURN_COLS if c in df.columns}
    if "vs Cat" in df.columns:
        fmt["vs Cat"] = "{:+.1f}pp"
    if "Alpha 3Y" in df.columns:
        fmt["Alpha 3Y"] = "{:+.1f}%"
    if "Beta 3Y" in df.columns:
        fmt["Beta 3Y"] = "{:.2f}"
    if "Vol 3Y" in df.columns:
        fmt["Vol 3Y"] = "{:.1f}%"
    if "DD 3Y" in df.columns:
        fmt["DD 3Y"] = "{:.1f}%"
    if "Score" in df.columns:
        fmt["Score"] = "{:.0f}"
    if "Yrs" in df.columns:
        fmt["Yrs"] = "{:.1f}"

    def _updown(v):
        if v is None or (isinstance(v, float) and v != v):
            return f"color:{MUTED}"
        return f"color:{GREEN};font-weight:600" if v >= 0 else f"color:{RED};font-weight:600"

    sty = df.style.format(fmt, na_rep="—")
    signed = [c for c in RETURN_COLS + ["vs Cat", "Alpha 3Y"] if c in df.columns]
    if signed:
        sty = sty.map(_updown, subset=signed)
    for quiet in ("Yrs", "Beta 3Y", "Vol 3Y", "DD 3Y"):
        if quiet in df.columns:
            sty = sty.map(lambda _v: f"color:{MUTED}", subset=[quiet])
    if "Score" in df.columns:
        sty = sty.background_gradient(cmap=soft, subset=["Score"], vmin=0, vmax=100)
    return sty


def leaders_laggards(df: pd.DataFrame, by: str = "3Y", n: int = 5):
    """Per category: (top n, bottom n) funds by a column. Skips thin categories."""
    out: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    for sl, g in df.groupby("_sleeve"):
        ranked = g.dropna(subset=[by]).sort_values(by, ascending=False)
        if len(ranked) < MIN_PEERS:
            continue
        out[sl] = (ranked.head(n), ranked.tail(n).iloc[::-1])
    return out
