MFRIP: Mutual Fund Research and Intelligence Platform

An explainable suitability and research tool for Indian mutual funds.

🔗 Use it live, right now: mfripfixed.streamlit.app

No installation, no signup. Works on any phone, tablet, or computer with a browser.

Show Image Show Image Show Image Show Image

MFRIP does not predict which fund will win, that is not knowable, and any tool
claiming it should be distrusted. Instead it answers a more honest and more
useful question: is this fund, or this portfolio, built sensibly and suited to
you?, and it shows its full working so you can verify rather than trust.


Educational tool, not investment advice. Past performance does not predict future returns.



New here? Two-minute tour


Open the live app and flip on 🎓 Beginner mode in the left sidebar. Every chart and score then explains itself in plain language.
Go to Explore a fund, search any Indian mutual fund by name (all 37,000+ are searchable), and scroll: returns, risk, how it behaved in past crashes, and a Monte Carlo goal planner for your SIP.
Try the Screener to compare every fund side by side, or the Advisor to enter funds you own and get an honest health check with suggestions.
The header always shows "data to <date>": the app refreshes its NAVs from mfapi.in daily, and tells you plainly if the source is ever unreachable.


Found something confusing or broken? Feedback is very welcome: open an
issue on this repo or message me directly.

A look inside

Start hereScreenerExplore a fundShow ImageShow ImageShow Image

Screenshots use a small demo dataset; open the live app to search all real Indian funds.


What it does


Self-refreshing data: the app checks its own data age on startup and, when the newest NAV has fallen more than a few days behind, re-fetches the cached funds from mfapi.in once per day, showing 'data to <date>' in the header so freshness is always visible. If the source is unreachable it opens anyway with the data it has, and says so.
Screener: every fund in one clean, comparable table: returns across 6M/1Y/3Y/5Y measured to a common date, risk over a common 3-year window, return vs the category median, and MFRIP's percentile-based quality score, with search, category filters, and leaders and laggards by 3-year return.
Explore a fund: returns, risk, the distribution of every rolling 1/3/5-year return, up/down capture vs the fund's own category index, behaviour in past market shocks, a SIP/XIRR calculator, and a Monte Carlo goal planner that simulates thousands of possible futures and shows the probability fan of outcomes.
Compare funds: head-to-head over a common window with a period-by-period "who led and why".
Portfolio Lab: build and compare portfolios side by side: growth, risk, allocation, and a fund-correlation heatmap.
Research: audit whether an advisor's past recommendations actually beat a fair benchmark; generate research memos; save portfolios; rank your portfolio against advised plans on a leaderboard; and run a walk-forward validation that checks, out-of-sample, whether the engine's own ranking actually predicts future risk and return.
Advisor: enter the funds you hold and get a verdict, a Portfolio Health Score, plain-language strengths/weaknesses, allocation gaps, specific add/trim suggestions, and a head-to-head backtest of your mix vs a suggested one.


A Start here tab orients first-time users, and a 🎓 Beginner mode toggle adds plain-language explanations under every metric and score.

How it works (one paragraph)

NAV history is pulled from the free mfapi.in and cached
in SQLite, with strict point-in-time, no-lookahead discipline, a fund is
only ever judged on data that existed at the time. On top of that sit a tested
analytics engine (rolling returns, capture ratios, stress tests, SIP/XIRR, risk
metrics) and a transparent six-layer suitability engine (profile →
constraints → allocation → fund ranking → construction → validation) that ends
in a Portfolio Health Score. Every output is computed from real numbers and
every recommendation is templated from those numbers, nothing is a black box.
See METHODOLOGY.md for the full detail.

Honest limitations


No return prediction. MFRIP judges suitability and quality, never future performance.
No expense ratio or AUM in the free data source, so fund ranking uses only NAV-derived factors and the scoring weights are renormalised to say so.
Holdings overlap is approximated by return correlation ("these funds move together"), because the actual stock-level holdings aren't available.
The data source is free and public, so it can occasionally lag or briefly return an incomplete list.



Run it locally

Requires Python 3.10+.

bashpip install -r requirements.txt

# one-time data setup
python -m mfrip.cli sync-schemes               # download the fund master list
python -m mfrip.cli load-all recommendations   # load the advised plans
python -m mfrip.cli fetch-all                  # download NAVs for those plans + benchmark

# launch
python -m streamlit run app.py

Then open the URL it prints (usually http://localhost:8501).


On Windows, if your username contains a space, use python -m streamlit run app.py (not the bare streamlit launcher).



Deploy it publicly (Streamlit Community Cloud, free)


Push this repo to GitHub.
At share.streamlit.io, create an app pointing at app.py.
On first load the app bootstraps itself: it detects the empty database and downloads the scheme list, advised plans, and their NAVs automatically (takes ~a minute, shown with a progress panel).


Faster, more reliable startup (recommended): Streamlit Cloud's filesystem is
ephemeral and is wiped on restart, so the bootstrap re-runs after periods of
inactivity. To make startup instant and avoid depending on the data source being
responsive, build the database locally (the three CLI commands above) and commit
it:

bashgit add -f mfrip_data.db
git commit -m "Add seed database for instant startup"

(The default .gitignore excludes mfrip_data.db; the -f flag overrides that
intentionally. Note: saved portfolios created on the live site won't persist
across restarts on the free tier, a platform limitation, not a bug.)


Testing

bashpip install pytest
python -m pytest -q

135 tests cover the financial math (including XIRR validated against a flat-NAV
control and capture ratios against known aggressive/defensive cases), the
suitability engine, point-in-time reconstruction, benchmark resolution, and the
portfolio/leaderboard logic.

Tech stack

Python · Streamlit · pandas · NumPy · Plotly · SQLite · mfapi.in (data)

Project layout

app.py                    Streamlit UI (seven tabs)
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
tests/                    135 tests
docs/screenshots/         README images
ARCHITECTURE.md           system map and data flow
METHODOLOGY.md            every formula and rule, stated plainly
CONTRIBUTING.md           ground rules for contributions
LICENSE                   MIT

Architecture

A full system map, the data flow diagram, and the testing philosophy live in
ARCHITECTURE.md. The finance methodology behind every number
is documented, formula by formula, in METHODOLOGY.md.

Author

Built by Akhand Raj, a dual-degree student (M.Sc. Economics + B.E.
Mechanical Engineering) at BITS Pilani Hyderabad, targeting quantitative risk
and markets roles. Feedback and questions are welcome via
GitHub issues.

License

MIT. See LICENSE.
