from datetime import datetime, timezone

import pytest

from app.models import Transaction
from app.portfolio import ledger
from app.portfolio.importers import parse_csv
from app.portfolio.risk_limits import check_trade


def tx(day, t, **kw):
    return Transaction(id=day, ts=datetime(2026, 1, day, tzinfo=timezone.utc), tx_type=t, origin="manual", **kw)


def test_acb_cra_method_usd_position():
    txs = [
        tx(1, "deposit", amount=1000, currency="CAD"),
        tx(2, "buy", symbol="FCX", quantity=10, price=10, fees=1, currency="USD", fx_rate_to_base=1.30),
        tx(3, "buy", symbol="FCX", quantity=10, price=12, fees=1, currency="USD", fx_rate_to_base=1.35),
        tx(4, "sell", symbol="FCX", quantity=5, price=15, fees=1, currency="USD", fx_rate_to_base=1.40),
    ]
    st = ledger.build_ledger(txs, "CAD")
    acb_total = 101 * 1.30 + 121 * 1.35            # 131.30 + 163.35 = 294.65
    sold = acb_total * 5 / 20
    gain = (5 * 15 - 1) * 1.40 - sold
    ev = st.realized_events[0]
    assert ev["acb_sold_base"] == pytest.approx(sold)
    assert ev["gain_base"] == pytest.approx(gain)
    pos = st.positions["FCX"]
    assert pos.quantity == pytest.approx(15)
    assert pos.acb_base == pytest.approx(acb_total - sold)
    assert st.cash["USD"] == pytest.approx(-101 - 121 + 74)   # USD cash not funded via FX in this toy example
    assert st.cash["CAD"] == pytest.approx(1000)


def test_split_and_dividend():
    txs = [tx(1, "buy", symbol="X", quantity=10, price=20, currency="CAD"),
           tx(2, "split", symbol="X", quantity=2.0, currency="CAD"),
           tx(3, "dividend", symbol="X", amount=5, fees=0.75, currency="CAD")]
    st = ledger.build_ledger(txs)
    assert st.positions["X"].quantity == 20 and st.positions["X"].acb_base == 200
    assert st.positions["X"].dividends_base == pytest.approx(4.25)


def test_valuation_and_missing_price_flag():
    txs = [tx(1, "deposit", amount=100), tx(2, "buy", symbol="XEQT", quantity=2, price=30), tx(3, "buy", symbol="ZZZ", quantity=1, price=10)]
    st = ledger.build_ledger(txs)
    v = ledger.valuation(st, {"XEQT": 33.0}, {})
    assert v["cash_base"] == pytest.approx(30)
    assert v["missing_prices"] == ["ZZZ"]
    xeqt = [p for p in v["positions"] if p["symbol"] == "XEQT"][0]
    assert xeqt["unrealized_pnl_base"] == pytest.approx(6.0)


def test_missing_fx_rate_is_flagged():
    st = ledger.build_ledger([tx(1, "buy", symbol="FCX", quantity=1, price=40, currency="USD")])
    assert not st.positions["FCX"].acb_complete
    assert st.warnings


def test_generic_csv_import_and_dedupe():
    text = ("date,type,symbol,quantity,price,currency,fees,fx_rate_to_base,amount,counter_currency,counter_amount,reference,note\n"
            "2026-01-05,deposit,,,,CAD,,,100,,,,\n"
            "2026-01-06,buy,xeqt,2.5,32.10,CAD,0,,,,,,\n"
            "2026-01-07,buy,BAD,0,1,CAD,0,,,,,,\n")
    r = parse_csv(text)
    assert r.format == "generic" and len(r.rows) == 2 and len(r.errors) == 1
    assert r.rows[1].symbol == "XEQT" and r.rows[1].amount == pytest.approx(80.25)
    r2 = parse_csv(text)
    assert [x.external_ref for x in r.rows] == [x.external_ref for x in r2.rows]


def test_wealthsimple_activity_best_effort():
    text = ("date,transaction,description,amount,balance,currency\n"
            "2026-02-02,CONT,Contribution,100.00,100.00,CAD\n"
            "2026-02-03,BUY,\"VFV - Vanguard S&P 500 Index ETF: Bought 0.5000 shares (executed at 2026-02-03)\",-70.00,30.00,CAD\n"
            "2026-02-10,DIV,\"VFV - Vanguard S&P 500 Index ETF: Cash dividend distribution\",0.12,30.12,CAD\n"
            "2026-02-11,LOAN,Something informational,0,30.12,CAD\n")
    r = parse_csv(text)
    assert r.format == "wealthsimple_activity"
    types = [x.tx_type for x in r.rows]
    assert types == ["deposit", "buy", "dividend"]
    assert r.rows[1].price == pytest.approx(140.0) and r.rows[1].quantity == 0.5
    assert len(r.skipped) == 1


def test_risk_limits_flag_breaches():
    rc = check_trade(side="buy", trade_value_base=60, symbol="FCX", sector="Natural Resources", portfolio_value_base=100,
                     cash_base=100, current_weights={}, sector_weights={}, avg_daily_dollar_volume=5e8)
    assert not rc["passed"]
    failed = {c["check"] for c in rc["checks"] if not c["passed"]}
    assert "max_position_weight" in failed and "max_loss_contribution" in failed
    ok = check_trade(side="buy", trade_value_base=30, symbol="FCX", sector="Natural Resources", portfolio_value_base=100,
                     cash_base=100, current_weights={}, sector_weights={}, avg_daily_dollar_volume=5e8)
    assert ok["passed"]
    lev = check_trade(side="buy", trade_value_base=30, symbol="FCX", sector="X", portfolio_value_base=100, cash_base=10,
                      current_weights={}, sector_weights={}, avg_daily_dollar_volume=5e8)
    assert any(c["check"] == "no_leverage" and not c["passed"] for c in lev["checks"])
