from __future__ import annotations

from mfrip.advisor import (
    DebtLoad, DrawdownReaction, EmergencyFund, Employment, Experience,
    ExistingHolding, Goal, InvestorProfile, assess_risk, evaluate_constraints,
)


def _young_aggressive():
    return InvestorProfile(
        age=26, employment=Employment.SALARIED_STABLE, horizon_years=20,
        emergency_fund=EmergencyFund.SIX_PLUS, debt=DebtLoad.NONE,
        drawdown_reaction=DrawdownReaction.INCREASE_SIP, experience=Experience.INTERMEDIATE,
    )


def _near_retiree_cautious():
    return InvestorProfile(
        age=60, employment=Employment.RETIRED, horizon_years=3,
        emergency_fund=EmergencyFund.SIX_PLUS, debt=DebtLoad.NONE,
        drawdown_reaction=DrawdownReaction.WAIT, experience=Experience.BEGINNER,
    )


# ---- risk assessment
def test_young_aggressive_scores_high():
    ra = assess_risk(_young_aggressive())
    assert ra.bucket == "Aggressive" and ra.score >= 70


def test_near_retiree_scores_low():
    ra = assess_risk(_near_retiree_cautious())
    assert ra.bucket in ("Conservative", "Moderate") and ra.score < 70


def test_tolerance_binds_when_panicky():
    # high capacity (young, long horizon, stable) but would sell everything on a drop
    p = _young_aggressive()
    p.drawdown_reaction = DrawdownReaction.SELL_ALL
    ra = assess_risk(p)
    assert ra.binding == "tolerance"
    assert ra.score <= ra.capacity  # willingness pulls the score down


def test_capacity_binds_when_short_horizon():
    p = _young_aggressive()
    p.horizon_years = 1
    p.emergency_fund = EmergencyFund.NONE
    ra = assess_risk(p)
    assert ra.binding == "capacity"


# ---- constraints
def test_no_emergency_fund_is_blocker():
    p = _young_aggressive()
    p.emergency_fund = EmergencyFund.NONE
    rep = evaluate_constraints(p)
    assert rep.has_blockers
    assert any("emergency" in c.title.lower() for c in rep.blockers)
    assert rep.max_equity <= 0.30


def test_high_interest_debt_is_blocker():
    p = _young_aggressive()
    p.debt = DebtLoad.HIGH
    rep = evaluate_constraints(p)
    assert any("debt" in c.title.lower() for c in rep.blockers)


def test_short_horizon_caps_equity():
    p = _young_aggressive()
    p.horizon_years = 2
    rep = evaluate_constraints(p)
    assert rep.max_equity <= 0.35


def test_long_horizon_no_equity_cap():
    rep = evaluate_constraints(_young_aggressive())
    assert rep.max_equity == 1.0
    assert not rep.has_blockers


def test_midcap_concentration_avoided():
    p = _young_aggressive()
    p.existing_holdings = [ExistingHolding("midcap", 0.6), ExistingHolding("largecap", 0.4)]
    rep = evaluate_constraints(p)
    assert "midcap" in rep.avoid_sleeves
    assert rep.existing_by_sleeve["midcap"] == 0.6


# ---- Layer 3 allocation
def test_allocation_sums_to_one_and_caps_equity():
    from mfrip.advisor import assess_risk, evaluate_constraints
    from mfrip.advisor.allocation import target_allocation
    p = _young_aggressive()
    p.horizon_years = 2  # should cap equity at 0.35
    ra = assess_risk(p)
    rep = evaluate_constraints(p)
    alloc = target_allocation(ra, rep)
    assert abs(sum(alloc.weights.values()) - 1.0) < 1e-6
    assert alloc.equity <= 0.35 + 1e-9


def test_allocation_avoids_concentrated_sleeve():
    from mfrip.advisor import assess_risk, evaluate_constraints, ExistingHolding
    from mfrip.advisor.allocation import target_allocation
    p = _young_aggressive()
    p.existing_holdings = [ExistingHolding("midcap", 0.6)]
    ra = assess_risk(p)
    rep = evaluate_constraints(p)
    alloc = target_allocation(ra, rep)
    assert alloc.weights.get("midcap", 0) == 0


# ---- category inference
def test_categorize_sleeves():
    from mfrip.advisor.categorize import infer_sleeve
    assert infer_sleeve("SBI Small Cap Fund - Direct Growth") == "smallcap"
    assert infer_sleeve("Kotak Emerging Equity Mid Cap Fund") == "midcap"
    assert infer_sleeve("HDFC Large Cap Fund - Direct Growth") == "largecap"
    assert infer_sleeve("Parag Parikh Flexi Cap Fund") == "flexicap"
    assert infer_sleeve("SBI Gilt Fund - Direct Growth") == "debt"
    assert infer_sleeve("Nippon India Gold Savings Fund") == "gold"
    assert infer_sleeve("Motilal Oswal Nasdaq 100 International") == "international"
    assert infer_sleeve("HDFC Balanced Advantage Fund") is None  # hybrid → not slotted


# ---- end-to-end recommend
def _seed_universe(conn):
    import numpy as np, pandas as pd
    from mfrip.store import nav_store
    rng = np.random.default_rng(0)
    def mk(code, name, ann, vol):
        ix = pd.date_range("2018-01-01", "2026-06-19", freq="D")
        nav = 100 * np.cumprod(1 + rng.normal((1 + ann) ** (1 / 365) - 1, vol / np.sqrt(365), len(ix)))
        nav_store.upsert_nav(conn, code, [(x.date(), float(v)) for x, v in zip(ix, nav)])
        conn.execute("INSERT OR REPLACE INTO schemes(scheme_code,scheme_name) VALUES(?,?)", (code, name))
    for c, n, a, v in [
        (120716, "UTI Nifty 50 Index Fund - Direct Growth", 0.12, 0.15),
        (2001, "HDFC Large Cap Fund - Direct Growth", 0.13, 0.16),
        (2002, "Parag Parikh Flexi Cap Fund - Direct Growth", 0.16, 0.16),
        (2003, "Kotak Mid Cap Fund - Direct Growth", 0.18, 0.21),
        (2004, "SBI Small Cap Fund - Direct Growth", 0.20, 0.26),
        (2005, "SBI Gilt Fund - Direct Growth", 0.07, 0.04),
        (2006, "Nippon India Gold Savings Fund - Direct Growth", 0.10, 0.12),
    ]:
        mk(c, n, a, v)
    conn.commit()


def test_recommend_end_to_end():
    from mfrip import ingest
    from mfrip.advisor import InvestorProfile, Employment, EmergencyFund, Experience
    from mfrip.advisor.recommend import recommend
    import os
    try:
        conn = ingest.open_store()
        _seed_universe(conn)
        p = InvestorProfile(age=30, horizon_years=12, employment=Employment.SALARIED_PRIVATE,
                            emergency_fund=EmergencyFund.SIX_PLUS, experience=Experience.INTERMEDIATE)
        rec = recommend(conn, p, benchmark_code=120716)
        assert rec.picks, "should pick at least one fund"
        assert rec.health is not None and 0 <= rec.health.overall <= 100
        assert all(0 <= pk.weight <= 1 for pk in rec.picks)
        assert abs(sum(pk.weight for pk in rec.picks) - 1.0) < 1e-6
    finally:
        for f in ("mfrip_data.db", "mfrip_data.db-wal", "mfrip_data.db-shm"):
            if os.path.exists(f):
                os.remove(f)


def test_review_flags_concentration_and_gaps():
    from mfrip import ingest
    from mfrip.advisor import InvestorProfile, Employment, EmergencyFund, Experience
    from mfrip.advisor.review import review_portfolio
    import os
    try:
        conn = ingest.open_store()
        _seed_universe(conn)
        p = InvestorProfile(age=35, horizon_years=10, employment=Employment.SALARIED_PRIVATE,
                            emergency_fund=EmergencyFund.SIX_PLUS, experience=Experience.BEGINNER)
        names = {2003: "Kotak Mid Cap Fund - Direct Growth", 2004: "SBI Small Cap Fund - Direct Growth"}
        rv = review_portfolio(conn, p, [(2003, 80.0), (2004, 20.0)], names)
        assert rv.health is not None
        # all equity, no debt → should flag debt as underweight ('add')
        assert any(g.sleeve == "debt" and g.action == "add" for g in rv.gaps)
        # 80% in one fund → concentration weakness
        assert any("oncentrat" in w for w in rv.weaknesses)
        assert "midcap" in rv.actual_allocation
    finally:
        for f in ("mfrip_data.db", "mfrip_data.db-wal", "mfrip_data.db-shm"):
            if os.path.exists(f):
                os.remove(f)
