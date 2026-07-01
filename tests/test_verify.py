from mfrip.cli import _review_flag


def test_flags_global_fof_in_equity():
    f = _review_flag("equity", "Kotak Global Emerging Market overseas Equity Omni FOF", "FoF Overseas")
    assert f is not None


def test_flags_us_bluechip():
    assert _review_flag("equity", "ICICI Prudential US Bluechip Equity Fund", "Equity") is not None


def test_flags_arbitrage_in_equity_slot():
    assert _review_flag("equity", "Nippon India Arbitrage Fund", "Hybrid - Arbitrage") is not None


def test_clean_equity_passes():
    assert _review_flag("equity", "Kotak Midcap Fund - Direct - Growth", "Equity - Mid Cap Fund") is None


def test_arbitrage_ok_in_debt_slot():
    # arbitrage used as a debt substitute is intended -> no flag
    assert _review_flag("debt", "ICICI Prudential Arbitrage Fund", "Hybrid - Arbitrage") is None


def test_gold_slot_needs_gold():
    assert _review_flag("gold", "Some Random Fund", "Equity") is not None
    assert _review_flag("gold", "Nippon India Gold Savings Fund", "FoF Domestic - Gold") is None
