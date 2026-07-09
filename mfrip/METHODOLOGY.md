# MFRIP Methodology

This document explains *what* MFRIP computes and *why*, the design choices, the
formulas, the assumptions, and the limits. The guiding principle throughout:
**MFRIP is a suitability and research engine, not a forecasting engine.** It
never predicts returns. It judges whether something is built well and suits a
given investor, and it shows its working.

---

## 1. Data and point-in-time discipline

- **Source.** NAV history from [mfapi.in](https://www.mfapi.in/) (free, no key), cached in SQLite.
- **No-lookahead.** Every metric is computed only from data available at the relevant date. When a portfolio is reconstructed, each fund contributes only from the first date *all* its constituents have data, so no series is silently back-filled or forward-filled with hindsight. This is enforced in the reconstruction layer and protected by tests.
- **Risk-free rate.** A single, auditable assumption (6.5% annual) used for Sharpe/Sortino, defined in `config.py`.

**Freshness.** The deployed app ships with a snapshot database and keeps itself current: on startup it checks the newest NAV date and, when that has fallen more than a few days behind (a long weekend is normal, so the threshold is 4 days), it re-downloads the cached funds' histories from mfapi.in, at most once per day per running server. The header always states 'data to <date>'; when the source is unreachable the app opens with what it has and says so on screen rather than failing or hiding the staleness.

## 2. Core risk and return metrics

All computed from the NAV series (which is already net of fund expenses):

- **CAGR**: geometric annualised return over the window.
- **Volatility**: annualised standard deviation of periodic returns.
- **Sharpe**: (annualised return − risk-free) / annualised volatility.
- **Sortino**: same numerator, but the denominator counts only downside deviation (the volatility that actually hurts).
- **Maximum drawdown**: the largest peak-to-trough decline.
- **Calmar**: CAGR / |max drawdown|.
- **Beta / alpha**: sensitivity to, and excess return over, a benchmark.

## 3. Rolling-return analysis

A single point-to-point "5-year return" can be a lucky window. MFRIP instead
reports the **distribution** of every rolling window:

- For each of the 1, 3 and 5-year horizons: best, worst, average, median, and the share of windows that were positive, computed on a monthly-sampled NAV series.
- **Rolling outperformance**: the share of rolling windows in which the fund beat its benchmark.

The visual (a dumbbell from worst to best with the average marked) makes the key
fact obvious: the longer the holding period, the narrower the range of outcomes.

## 4. Capture ratios

Of the market's moves, how much did the fund catch?

- **Up-capture** = mean fund return in months the benchmark rose ÷ mean benchmark return in those months.
- **Down-capture** = the same for months the benchmark fell.

A fund that captures more upside than downside (up-capture > down-capture) has an
attractive risk personality. Validated against synthetic aggressive (β≈1.2) and
defensive funds, which produce ≈120%/120% and ≈90%/70% respectively.

## 5. Historical stress tests

The fund's return and worst drawdown within named historical episodes, the
COVID crash (Feb–Mar 2020), the COVID recovery, the 2022 rate-hike selloff, and
the 2024 election-week swing. Episodes that predate a fund's inception are
skipped rather than fabricated.

## 6. SIP returns (XIRR) and goal projection

- **SIP XIRR.** Most Indians invest monthly, and monthly returns differ from lump-sum point-to-point returns. MFRIP simulates a monthly SIP and solves for the money-weighted return (XIRR) via bisection on the net-present-value function. Validated against a flat-NAV control (which must return ≈0%).
- **Goal projection (Monte Carlo).** Rather than a single assumed return, the goal planner runs a Monte Carlo simulation (see §6a) and shows the *probability fan* of outcomes. A required-SIP calculator inverts this ("to reach ₹X with a 50% / 75% chance you'd need ₹Y/month").

## 6a. Monte Carlo goal simulation

The honest way to look forward. Instead of pretending to know a future return, the
simulation estimates the fund's own monthly return distribution from history and
plays out thousands of possible futures for a monthly SIP, then reports the spread
of outcomes. It is forward-looking and uses real parameters, but it quantifies
**uncertainty** rather than predicting a number.

- **Parameters.** Month-end NAVs give a series of monthly returns; from these we take the mean and standard deviation (and report the annualised equivalents shown in the app, so the inputs are transparent). At least 12 months of history is required.
- **Two methods.** *Bootstrap* (default) resamples actual historical monthly returns with replacement, so each simulated path inherits the fund's real distribution including fat tails and crashes; it treats months as independent, so multi-year streaks (volatility clustering) are not modelled. *Normal* draws monthly log-returns from a fitted Gaussian (geometric Brownian motion); it is smoother and can extrapolate beyond the historical range, but assumes normality, which understates real tail risk. The app names these plainly and explains the trade-off.
- **SIP convention.** Each simulated month the instalment is added and then grows for the full month (annuity due), identical to the deterministic SIP formula. This is verified by a control test: with zero volatility the simulated median equals the closed-form future value exactly.
- **Outputs.** Percentile bands (10th / 25th / 50th / 75th / 90th) of the corpus over time form the fan; the terminal distribution gives the unlucky / typical / lucky corpus; and if a goal is set, the probability of reaching it is the fraction of simulations that finish at or above it. Because corpus is linear in the monthly amount for a fixed set of return paths, the "required SIP for a given confidence" is found by simulating once at ₹1/month and scaling.
- **Honest framing.** Everything is labelled as a range of scenarios drawn from the past, assuming the future resembles it (which it may not). The 90th percentile is not a promise and the 10th is not a floor; costs, taxes, and strategy drift are excluded.

## 7. Category-matched benchmarks

Judging a mid-cap fund against the Nifty 50 lets the mid/small-cap premium
masquerade as manager skill. MFRIP resolves the **right** index for a fund's
category, mid-cap vs Nifty Midcap 150, small-cap vs Nifty Smallcap 250, flexi
vs Nifty 500, large-cap vs Nifty 50, so capture and outperformance reflect
skill, not cap-tilt. The category index is resolved from the user's own scheme
list (robust to fund-code changes) and falls back to the Nifty 50 if no suitable
index is cached. Debt and gold funds skip equity comparison entirely, because
comparing them to a stock index is meaningless.

---

## 8. The six-layer suitability engine

A recommendation is produced by six explicit layers, each of which can be
inspected:

**Layer 1: Investor profile.** From age, horizon, employment stability,
emergency fund, debt load, drawdown reaction and experience, MFRIP computes a
**risk capacity** (how much risk you can afford) and a **risk tolerance** (how
much you can stomach). The risk score is the **minimum** of the two, standard
doctrine, because the binding constraint governs. The score maps to
Conservative / Moderate / Aggressive, and the engine reports *which* of capacity
or tolerance was binding.

**Layer 2: Constraints.** Hard rules that override the score: no equity until an
emergency fund exists; clear high-interest debt first; an equity ceiling tied to
horizon (short horizons cap equity regardless of appetite); and concentration
limits on sleeves the investor is already heavy in. These produce blockers and a
maximum equity allocation.

**Layer 3: Strategic allocation.** The risk score maps to a target equity/debt/
gold split, *clamped* by the Layer-2 ceiling, with the equity portion split
across large/flexi/mid/small/international by risk bucket. Allocation can never
violate a hard rule.

**Layer 4: Fund ranking.** Within each sleeve, funds are scored on a composite
(see §9) and ranked cross-sectionally against their true peers.

**Layer 5: Construction.** The top-ranked fund per sleeve is assigned the
sleeve's target weight; fund-to-fund correlation is checked for redundancy.

**Layer 6: Validation.** The assembled portfolio is run back through the
analytics engine and scored with a Portfolio Health Score (§10). The whole
output carries a **recommendation confidence** (§11) and per-fund "why this
fund" reasoning.

## 9. Fund-ranking composite

A composite score, **not** a return ranking, deliberately weighted toward
consistency and downside protection, as a long-term investor should be. The
canonical model weights seven factors; expense ratio and AUM are **not** in the
free data source, so the score is **renormalised** onto the four NAV-computable
factors and says so:

| Factor | Weight | What it rewards |
|---|---|---|
| Rolling consistency | 0.38 | positive returns across rolling windows |
| Sortino | 0.25 | downside-adjusted return |
| Sharpe | 0.19 | risk-adjusted return |
| Max drawdown | 0.18 | shallower worst-case falls |

Each factor is expressed as a **percentile rank within the sleeve's candidate
set** (best = 100, worst = 0, ties share the average rank), so a fund is judged
against its true peers, then combined. Percentile ranks were chosen over min-max
scaling deliberately: one extreme fund can stretch a min-max scale and squash
every other fund's scores together, while ranks are robust to outliers. This is
also how Value Research and Morningstar place a fund within its category. A
confidence figure scales
with history length and penalises very high volatility.

## 9a. Walk-forward validation of the ranking

A ranking is only worth trusting if it holds up on data it never saw. The
validation engine measures this directly, the way a quant desk backtests a
factor.

- **Method.** Step back to a past cutoff date; rank the funds using only NAV history up to that date (a lookback window, 3 years by default); then look forward over the next horizon (2 years by default) and compute what each fund actually delivered (out-of-sample CAGR, Sharpe, Sortino, rolling consistency, max drawdown, volatility). Slide the cutoff forward year by year to get several independent train/test windows, and pool them.
- **Score.** For each out-of-sample metric we compute the Spearman rank correlation between the in-sample composite score and the realised outcome, pooled across all funds and windows. A two-sided **permutation test** (labels shuffled many times, no distribution assumed) gives a p-value. The app summarises this as two numbers: *return persistence* (mean rank correlation across Sharpe, Sortino, CAGR) and *risk persistence* (across consistency, drawdown and, sign-flipped, volatility).
- **What honest results look like.** Risk characteristics (consistency, drawdowns, volatility) tend to persist out-of-sample more strongly than raw returns, so a truthful tool usually shows higher risk persistence than return persistence. That is a feature, not a defect: it is exactly why the composite ranks on risk-adjusted behaviour rather than chasing past performance. When the signal is weak, the app says so plainly rather than hiding it.
- **Validated against ground truth.** The engine is itself tested on synthetic funds with a known latent quality: when quality persists across the cutoff it must recover a strong positive correlation, and when post-cutoff quality is randomised the correlation at the aligned cutoff must collapse to near zero. Both hold (see §14).
- **Honest framing.** This tests whether the ranking is *informative and consistent*, not whether any individual fund will outperform. Survivorship and the limits of the free data source (§1, §13) still apply.

## 9b. The screener

The screener puts every fund in the database into one comparable table. Its
rules are strict about comparability, because a table that mixes measurement
windows is quietly misleading:

- **Common valuation date.** All period returns are measured to one shared date (the latest NAV anywhere in the universe). A fund whose own NAV is more than 21 days behind that date is listed, but its period columns are left blank rather than silently compared over a different window.
- **Return conventions.** 6M and 1Y are total returns over the period; 3Y and 5Y are annualised. A cell is blank when the fund lacks about 90% of the requested window (never a fabricated number).
- **Common risk window.** Volatility and worst drawdown cover the same trailing three years for every fund, so a 20-year fund is not penalised for a crash a younger fund never lived through. Blank below roughly 2.75 years of history.
- **vs Cat.** The fund's 3Y return minus its category's median 3Y, in percentage points, shown only when the category has at least 3 funds.
- **Score.** The §9 composite (percentile-based within category). Categories with fewer than 3 funds are not scored, because a percentile among two funds is nearly meaningless.

Fund size (AUM), expense ratio, and third-party star ratings are not in the free
data source, so the screener shows only what it can compute from NAV and says so
on screen.

## 10. Portfolio Health Score (0–100)

A weighted blend of six sub-scores, each computed from the actual holdings:

| Sub-score | Weight | Measures |
|---|---|---|
| Diversification | 0.22 | low average correlation between holdings |
| Risk match | 0.20 | realised volatility vs the band expected for the profile |
| Consistency | 0.18 | average rolling-window consistency of the holdings |
| Downside protection | 0.20 | portfolio max drawdown |
| Concentration | 0.13 | how spread the weights are (penalises >35% single positions) |
| Liquidity | 0.07 | open-ended funds (assumed liquid) |

It rates how well a portfolio is *built and suited*, never whether it will rise.

## 11. Recommendation confidence

Confidence is in the **suitability** of the recommendation, explicitly **not** in
future returns. It rises with data quality (history length), historical
consistency, diversification, and how cleanly the portfolio matches the target
allocation; it is reduced when sleeves can't be filled from the cached universe.

---

## 12. Why rules, not machine learning

A return-predicting ML model is the wrong tool here, for reasons that are
methodological, not preferential:

- **No ground truth.** There is no reliable label for "the fund that will outperform"; training toward past returns just fits noise.
- **Traceability.** Every number here is traceable to a computed quantity; a black box cannot be audited or defended, which is exactly what a suitability tool must be.
- **Overfitting.** With a few thousand funds and regime-dependent markets, a flexible model overfits the past it was shown.

So MFRIP is a **transparent, rules-based suitability engine**. "Correct" means
*appropriate and well-justified for this investor*, not *guaranteed to win*.

## 13. Limitations (restated plainly)

- No expense ratio or AUM in the data → ranking uses NAV-derived factors only, weights renormalised accordingly.
- Holdings overlap is proxied by return correlation ("moves together"), not actual shared stocks.
- The free data source can lag or briefly return partial lists.
- Synthetic test data behaves differently from real funds (e.g. independent random series show low correlation and muted stress); real fund data behaves as expected.
- Everything is educational, not investment advice.

## 14. Testing

135 tests, including: the no-lookahead integrity test; XIRR against a flat-NAV
control; capture ratios against known aggressive/defensive funds; goal-projection
monotonicity; suitability-engine constraints (e.g. an all-equity portfolio with
no emergency fund must be blocked); category-benchmark resolution and fallback;
leaderboard ranking; the Monte Carlo control test (zero volatility reproduces the
closed-form SIP value exactly); and the walk-forward validator against synthetic
funds with known persistence (it must detect a strong positive correlation when
quality persists and near-zero when post-cutoff quality is randomised).
