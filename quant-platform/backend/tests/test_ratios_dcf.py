import math

import pytest

from app.analytics import dcf as D
from app.analytics import ratios as R

STMT = {"revenue": 1000.0, "cost_of_revenue": 600.0, "operating_income": 200.0, "d_and_a": 50.0, "net_income": 120.0,
        "pretax_income": 160.0, "income_tax": 40.0, "interest_expense": 20.0, "cash": 100.0, "long_term_debt": 300.0,
        "short_term_debt": 50.0, "current_assets": 400.0, "inventory": 100.0, "current_liabilities": 200.0,
        "equity": 500.0, "total_assets": 1200.0, "operating_cash_flow": 180.0, "capex": -80.0, "dividends_paid": -40.0,
        "eps_diluted": 1.2}
PRIOR = {**STMT, "revenue": 800.0, "equity": 400.0, "total_assets": 1000.0, "net_income": 100.0}


def test_statement_ratios_hand_checked():
    m = R.statement_ratios(STMT, PRIOR)
    assert m["gross_margin"].value == pytest.approx(0.40)
    assert m["ebitda_margin"].value == pytest.approx(0.25)          # (200+50)/1000
    assert m["operating_margin"].value == pytest.approx(0.20)
    assert m["fcf_margin"].value == pytest.approx(0.10)             # (180-80)/1000
    assert m["current_ratio"].value == pytest.approx(2.0)
    assert m["quick_ratio"].value == pytest.approx(1.5)             # (400-100)/200
    assert m["debt_to_equity"].value == pytest.approx(0.70)         # 350/500
    assert m["net_debt_to_ebitda"].value == pytest.approx(1.0)      # 250/250
    assert m["interest_coverage"].value == pytest.approx(10.0)
    assert m["roe"].value == pytest.approx(120 / 450)               # avg equity
    assert m["roa"].value == pytest.approx(120 / 1100)
    assert m["roic"].value == pytest.approx(200 * 0.75 / 750)       # tax 25%, IC = 500+350-100
    assert m["dividend_coverage"].value == pytest.approx(2.5)
    assert m["revenue_growth"].value == pytest.approx(0.25)


def test_missing_inputs_are_reported_not_imputed():
    m = R.statement_ratios({"revenue": 100.0})
    assert m["gross_margin"].value is None and "gross_profit" in m["gross_margin"].missing
    neg = R.statement_ratios({**STMT, "equity": -10.0})
    assert neg["debt_to_equity"].value is None and "not meaningful" in neg["debt_to_equity"].note


def test_multiples():
    m = R.valuation_multiples(price=12.0, shares=100.0, s=STMT, eps_growth_pct=10)
    assert m["market_cap"].value == 1200
    assert m["enterprise_value"].value == 1450                      # 1200 + 350 - 100
    assert m["pe"].value == pytest.approx(10.0)
    assert m["ev_ebitda"].value == pytest.approx(5.8)
    assert m["pb"].value == pytest.approx(2.4)
    assert m["fcf_yield"].value == pytest.approx(100 / 1200)
    assert m["peg"].value == pytest.approx(1.0)


def base_inputs(**kw):
    d = dict(base_revenue=100.0, revenue_growth=[0.10, 0.10], ebit_margin=0.20, tax_rate=0.25, wacc=0.10, net_debt=20.0,
             diluted_shares=10.0, da_pct_revenue=0.05, capex_pct_revenue=0.05, nwc_pct_revenue=0.10, terminal_growth=0.02,
             mid_year=False)
    d.update(kw)
    return D.DCFInputs(**d)


def test_dcf_hand_computed():
    # Year 1: rev 110, EBIT 22, NOPAT 16.5, D&A 5.5, capex 5.5, dNWC 1.0 -> FCFF 15.5
    # Year 2: rev 121, EBIT 24.2, NOPAT 18.15, D&A=capex 6.05, dNWC 1.1 -> FCFF 17.05
    r = D.run_dcf(base_inputs())
    assert r.years[0]["fcff"] == pytest.approx(15.5)
    assert r.years[1]["fcff"] == pytest.approx(17.05)
    pv = 15.5 / 1.1 + 17.05 / 1.1 ** 2
    tv = 17.05 * 1.02 / 0.08
    ev = pv + tv / 1.1 ** 2
    assert r.pv_forecast == pytest.approx(pv)
    assert r.terminal_value == pytest.approx(tv)
    assert r.enterprise_value == pytest.approx(ev)
    assert r.value_per_share == pytest.approx((ev - 20) / 10)
    assert any("terminal value" in w for w in r.warnings)  # TV share > 75% is flagged


def test_dcf_guards():
    with pytest.raises(ValueError):
        D.run_dcf(base_inputs(terminal_growth=0.10))
    with pytest.raises(ValueError):
        D.run_dcf(base_inputs(diluted_shares=0))


def test_reverse_dcf_recovers_growth():
    inp = base_inputs(revenue_growth=[0.07] * 5)
    price = D.run_dcf(inp).value_per_share
    out = D.reverse_dcf(base_inputs(revenue_growth=[0.0] * 5), price)
    assert out["implied_growth"] == pytest.approx(0.07, abs=1e-5)


def test_sensitivity_and_scenarios():
    inp = base_inputs()
    s = D.sensitivity(inp, [0.08, 0.10], [0.02, 0.09])
    assert s["value_per_share"][0][1] is None          # g >= wacc → undefined
    assert s["value_per_share"][0][0] > s["value_per_share"][1][0]  # lower WACC → higher value
    sc = D.scenarios(inp, {"bear": {"ebit_margin": 0.15}, "base": {}, "bull": {"ebit_margin": 0.25}})
    assert sc["bear"]["value_per_share"] < sc["base"]["value_per_share"] < sc["bull"]["value_per_share"]


def test_wacc():
    ke = D.capm_cost_of_equity(0.04, 1.2, 0.05)
    assert ke == pytest.approx(0.10)
    assert D.wacc(600, 400, ke, 0.06, 0.25) == pytest.approx(0.6 * 0.10 + 0.4 * 0.045)
    assert math.isnan(D.margin_of_safety(-1, 10))
    assert D.margin_of_safety(20, 15) == pytest.approx(0.25)
