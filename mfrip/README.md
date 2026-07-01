# MFRIP: Mutual Fund Research and Intelligence Platform

**An explainable suitability and research tool for Indian mutual funds.**
MFRIP does not predict which fund will win, that is not knowable, and any tool
claiming it should be distrusted. Instead it answers a more honest and more
useful question: *is this fund, or this portfolio, built sensibly and suited to
you?*, and it shows its full working so you can verify rather than trust.

> Educational tool, not investment advice. Past performance does not predict future returns.

---

## What it does

- **Explore a fund**: returns, risk, the *distribution* of every rolling 1/3/5-year return, up/down capture vs the fund's **own category index**, behaviour in past market shocks, a SIP/XIRR calculator, and a **Monte Carlo goal planner** that simulates thousands of possible futures and shows the probability fan of outcomes.
- **Compare funds**: head-to-head over a common window with a period-by-period "who led and why".
- **Portfolio Lab**: build and compare portfolios side by side: growth, risk, allocation, and a fund-correlation heatmap.
- **Research**: audit whether an advisor's past recommendations actually beat a fair benchmark; generate research memos; save portfolios; rank your portfolio against advised plans on a leaderboard; and run a **walk-forward validation** that checks, out-of-sample, whether the engine's own ranking actually predicts future risk and return.
- **Advisor**: enter the funds you hold and get a verdict, a Portfolio Health Score, plain-language strengths/weaknesses, allocation gaps, specific add/trim suggestions, and a head-to-head backtest of your mix vs a suggested one.

A **Start here** tab orients first-time users, and a **🎓 Beginner mode** toggle adds plain-language explanations under every metric and score.

## How it works (one paragraph)

NAV history is pulled from the free [mfapi.in](https://www.mfapi.in/) and cached
in SQLite, with strict **point-in-time, no-lookahead** discipline, a fund is
only ever judged on data that existed at the time. On top of that sit a tested
analytics engine (rolling returns, capture ratios, stress tests, SIP/XIRR, risk
metrics) and a transparent **six-layer suitability engine** (profile →
constraints → allocation → fund ranking → construction → validation) that ends
in a **Portfolio Health Score**. Every output is computed from real numbers and
every recommendation is templated from those numbers, nothing is a black box.
See [METHODOLOGY.md](METHODOLOGY.md) for the full detail.

## Honest limitations

- **No return prediction.** MFRIP judges suitability and quality, never future performance.
- **No expense ratio or AUM** in the free data source, so fund ranking uses only NAV-derived factors and the scoring weights are renormalised to say so.
- **Holdings overlap is approximated** by return correlation ("these funds move together"), because the actual stock-level holdings aren't available.
- **The data source is free and public**, so it can occasionally lag or briefly return an incomplete list.

---

## Run it locally

Requires Python 3.10+.

```bash
pip install -r requirements.txt

# one-time data setup
python -m mfrip.cli sync-schemes               # download the fund master list
python -m mfrip.cli load-all recommendations   # load the advised plans
python -m mfrip.cli fetch-all                  # download NAVs for those plans + benchmark

# launch
python -m streamlit run app.py
```

Then open the URL it prints (usually http://localhost:8501).

> On Windows, if your username contains a space, use `python -m streamlit run app.py` (not the bare `streamlit` launcher).

## Deploy it publicly (Streamlit Community Cloud, free)

1. Push this repo to GitHub.
2. At [share.streamlit.io](https://share.streamlit.io), create an app pointing at `app.py`.
3. On first load the app **bootstraps itself**: it detects the empty database and downloads the scheme list, advised plans, and their NAVs automatically (takes ~a minute, shown with a progress panel).

**Faster, more reliable startup (recommended):** Streamlit Cloud's filesystem is
ephemeral and is wiped on restart, so the bootstrap re-runs after periods of
inactivity. To make startup instant and avoid depending on the data source being
responsive, build the database locally (the three CLI commands above) and commit
it:

```bash
git add -f mfrip_data.db
git commit -m "Add seed database for instant startup"
```

(The default `.gitignore` excludes `mfrip_data.db`; the `-f` flag overrides that
intentionally. Note: saved portfolios created on the live site won't persist
across restarts on the free tier, a platform limitation, not a bug.)

---

## Testing

```bash
pip install pytest
python -m pytest -q
```

118 tests cover the financial math (including XIRR validated against a flat-NAV
control and capture ratios against known aggressive/defensive cases), the
suitability engine, point-in-time reconstruction, benchmark resolution, and the
portfolio/leaderboard logic.

## Tech stack

Python · Streamlit · pandas · NumPy · Plotly · SQLite · mfapi.in (data)

## Project layout

```
app.py                    Streamlit UI (six tabs)
mfrip/
  config.py               risk-free rate, benchmark, asset proxies
  ingest.py               scheme master + NAV download (retry/backoff)
  store/                  SQLite layer: nav_store, saved portfolios
  metrics/                returns, risk, rolling, capture, sip, relative
  portfolio/              point-in-time reconstruction, audit, backtest
  advisor/                six-layer suitability engine + glossary
  webapp/                 charts, portfolio_lab, research, benchmarks,
                          leaderboard, bootstrap, data access
  recommend/              recommendation schema + YAML loader
  cli.py                  command-line tools
recommendations/          advised plans (YAML)
tests/                    118 tests
```
