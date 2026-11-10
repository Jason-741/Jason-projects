import numpy as np
import pandas as pd
import pytest

from app.analytics import montecarlo as MC
from app.analytics import optimize as O
from app.analytics import risk as RK
from app.analytics import stress as ST


def test_max_drawdown_known_path():
    prices = pd.Series([100, 120, 90, 95, 130, 104])
    r = prices.pct_change().dropna()
    assert RK.max_drawdown(r) == pytest.approx(0.25)    # 120 -> 90


def test_historical_var_cvar_known_sample():
    r = pd.Series(np.arange(-50, 50) / 1000.0)       # -5.0% .. +4.9%, 100 obs
    q = np.quantile(r, 0.05)
    assert RK.historical_var(r, 0.95) == pytest.approx(-q)
    assert RK.historical_cvar(r, 0.95) == pytest.approx(-r[r <= q].mean())
    assert RK.historical_cvar(r, 0.95) >= RK.historical_var(r, 0.95)


def test_parametric_var_matches_formula():
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.001, 0.02, 5000))
    expected = -(r.mean() - 1.6448536269514722 * r.std(ddof=1))
    assert RK.parametric_var(r, 0.95) == pytest.approx(expected)


def test_sharpe_sortino_cagr():
    r = pd.Series([0.01, -0.005, 0.02, 0.0, -0.01] * 60)
    assert RK.sharpe_ratio(r) == pytest.approx(r.mean() / r.std(ddof=1) * np.sqrt(252))
    assert RK.annualized_return(r) == pytest.approx((1 + r).prod() ** (252 / len(r)) - 1)
    dd = np.sqrt((np.minimum(r, 0) ** 2).mean())
    assert RK.sortino_ratio(r) == pytest.approx(r.mean() / dd * np.sqrt(252))


def test_beta_and_risk_contributions(prices):
    rets = RK.to_returns(prices)
    assert RK.beta(2 * rets["AAA"], rets["AAA"]) == pytest.approx(2.0)
    w = {"AAA": 0.5, "BBB": 0.3, "CCC": 0.2}
    rc = RK.risk_contributions(rets, w)
    port_vol = RK.annualized_volatility(RK.portfolio_returns(rets, w))
    assert rc["risk_contribution"].sum() == pytest.approx(port_vol, rel=1e-6)
    assert rc["pct_of_risk"].sum() == pytest.approx(1.0)


def test_concentration():
    c = RK.concentration({"a": 0.5, "b": 0.5})
    assert c["hhi"] == pytest.approx(0.5) and c["effective_n"] == pytest.approx(2)


def test_min_variance_two_uncorrelated_assets():
    cov = pd.DataFrame([[0.04, 0.0], [0.0, 0.01]], index=["x", "y"], columns=["x", "y"])
    w = O.min_variance(cov)
    assert w["x"] == pytest.approx(0.01 / 0.05, abs=1e-4)
    rp = O.risk_parity(cov)
    assert rp["x"] == pytest.approx(1 / 3, abs=1e-3)     # inverse-vol when uncorrelated: 1/.2 : 1/.1
    capped = O.min_variance(cov, max_weight=0.7)
    assert max(capped.values()) <= 0.7 + 1e-9
    with pytest.raises(ValueError):
        O.min_variance(cov, max_weight=0.4)


def test_risk_parity_equalizes_contributions(prices):
    rets = RK.to_returns(prices)
    cov = O.covariance(rets, shrinkage=0.0)
    w = O.risk_parity(cov)
    W = np.array([w[c] for c in cov.columns])
    rc = W * (cov.to_numpy() @ W)
    assert np.allclose(rc / rc.sum(), 1 / 3, atol=1e-3)


def test_monte_carlo_is_reproducible(prices):
    rets = RK.to_returns(prices)
    a = MC.simulate(rets, {"AAA": 1.0}, n_paths=300, horizon=60, seed=1)
    b = MC.simulate(rets, {"AAA": 1.0}, n_paths=300, horizon=60, seed=1)
    assert a["terminal_return_percentiles"] == b["terminal_return_percentiles"]
    assert 0 <= a["prob_loss"] <= 1
    assert a["terminal_return_percentiles"]["5"] < a["terminal_return_percentiles"]["95"]


def test_stress_fx_and_factor():
    pos = [ST.StressPosition("FCX", 50, "USD", beta_equity=1.2, factor_betas={"copper": 1.5}),
           ST.StressPosition("XIC", 50, "CAD", beta_equity=1.0)]
    out = ST.run_stress(pos, {"t": {"equity": -0.10, "factors": {"copper": -0.20}, "fx_usdcad": -0.10}})["t"]
    fcx = (1 - 0.12 - 0.30) * 0.90 - 1
    assert out["positions"][0]["return"] == pytest.approx(fcx)
    assert out["portfolio_return"] == pytest.approx((50 * fcx + 50 * -0.10) / 100)


def test_mine_npv_hand_checked():
    m = ST.MineInputs(annual_production=100, mine_life_years=2, commodity_price=10, aisc=6, initial_capex=500,
                      discount_rate=0.10, tax_rate=0.0)
    out = ST.mine_npv(m)
    assert out["npv"] == pytest.approx(-500 + 400 / 1.1 + 400 / 1.21)
    # IRR solves 400x^2 + 400x - 500 = 0 with x = 1/(1+r)
    x = (-400 + (400 ** 2 + 4 * 400 * 500) ** 0.5) / 800
    assert out["irr"] == pytest.approx(1 / x - 1, abs=1e-6)
    assert out["payback_year"] == 2
