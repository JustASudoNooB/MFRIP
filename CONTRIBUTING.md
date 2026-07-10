# Contributing to MFRIP

Thanks for your interest. MFRIP is a personal research project, but issues and
pull requests are welcome.

## Ground rules

1. **No return prediction.** MFRIP's core principle is that future fund returns
   are not predictable from past NAVs. Contributions that add forecasting
   models, trading signals, or "top fund" predictions will not be merged. New
   analytics must quantify uncertainty or test claims out-of-sample, never
   promise outcomes.
2. **Every number must be traceable.** Anything displayed on screen must come
   from a real computation on real data, with the method documented in
   `METHODOLOGY.md`.
3. **Tests are not optional.** New logic ships with tests, and the full suite
   (`python -m pytest`) must pass. Statistical code should include a control
   test with a known answer (see the zero-volatility Monte Carlo test for the
   pattern).

## Getting started

```
pip install -r requirements.txt
python -m pytest          # 135 tests should pass
python -m streamlit run app.py
```

## Style

Plain, warm language in UI copy (no jargon walls, no em-dashes). Honest
captions: if a number has a caveat, say it next to the number.

## Reporting problems

Open a GitHub issue with a screenshot and, if it is a data question, the fund
and date range involved. "This confused me" is a completely valid issue.
