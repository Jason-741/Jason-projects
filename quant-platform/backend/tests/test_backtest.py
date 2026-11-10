import numpy as np
import pandas as pd
import pytest

from app.analytics import backtest as BT
from app.analytics import signals as S


def zero_cost():
    return BT.BacktestConfig(initial_capital=100.0, rebalance="daily",
                             costs=BT.CostModel(0, 0, 0, 0, min_trade_value=0.0))


def test_buy_and_hold_single_asset_matches_price_return(prices):
    p = prices[["AAA"]]
    w = pd.DataFrame(1.0, index=p.index, columns=["AAA"])
    res = BT.run_backtest(p, w, zero_cost())
    # bought at day 1 close (one-bar lag) → equity tracks price from day 1
    expected = 100 * p["AAA"].iloc[-1] / p["AAA"].iloc[1]
    assert res.equity.iloc[-1] == pytest.approx(expected, rel=1e-9)


def test_costs_reduce_returns(prices):
    w = S.weights_trend(prices, 50)
    free = BT.run_backtest(prices, w, zero_cost())
    costly = BT.run_backtest(prices, w, BT.BacktestConfig(rebalance="daily", costs=BT.CostModel(0, 20, 20, 0)))
    assert costly.equity.iloc[-1] < free.equity.iloc[-1]
    assert costly.metrics["total_costs"] > 0


def test_fx_fee_applies_to_foreign_assets(prices):
    w = S.weights_buy_and_hold(prices)
    a = BT.run_backtest(prices, w, BT.BacktestConfig(costs=BT.CostModel(0, 0, 0, 150)))
    b = BT.run_backtest(prices, w, BT.BacktestConfig(costs=BT.CostModel(0, 0, 0, 150), foreign_assets=("AAA",)))
    assert b.metrics["total_costs"] > a.metrics["total_costs"] == 0


def test_never_uses_leverage(prices):
    w = pd.DataFrame(1.0, index=prices.index, columns=prices.columns)  # asks for 300% gross
    res = BT.run_backtest(prices, w, BT.BacktestConfig())
    assert res.weights.sum(axis=1).max() <= 1.0 + 1e-6


@pytest.mark.parametrize("name", list(S.STRATEGIES))
def test_builtin_strategies_have_no_lookahead(prices, name):
    fn, params = S.STRATEGIES[name]
    small = {**params}
    if "window" in small and name == "trend":
        small["window"] = 50
    if "lookback" in small:
        small.update(lookback=60, skip=5)
    assert BT.check_no_lookahead(fn, prices.iloc[:300], small)


def test_lookahead_detector_catches_cheating(prices):
    def cheat(p):  # uses tomorrow's return
        return (p.shift(-1) > p).astype(float) / p.shape[1]
    assert not BT.check_no_lookahead(cheat, prices.iloc[:300], {})


def test_reproducible_fingerprint(prices):
    w = S.weights_trend(prices, 50)
    a = BT.run_backtest(prices, w)
    b = BT.run_backtest(prices.copy(), w.copy())
    assert a.fingerprint == b.fingerprint and a.metrics == b.metrics
    c = BT.run_backtest(prices * 1.0001, w)
    assert c.fingerprint != a.fingerprint


def test_monthly_rebalance_trades_less_than_daily(prices):
    w = S.weights_cross_sectional_momentum(prices, top_k=1, lookback=60, skip=5)
    d = BT.run_backtest(prices, w, BT.BacktestConfig(rebalance="daily"))
    m = BT.run_backtest(prices, w, BT.BacktestConfig(rebalance="monthly"))
    assert m.metrics["n_trades"] < d.metrics["n_trades"]


def test_walk_forward_only_oos(prices):
    res = BT.walk_forward(prices, S.weights_trend, {"window": [20, 50]}, train_days=300, test_days=100,
                          config=BT.BacktestConfig(), warmup_days=60)
    assert res["configurations_tested"] == 2
    assert len(res["windows"]) == 5
    first_test = res["windows"][0]["test_start"]
    assert res["oos_returns"][0][0] >= first_test


def test_psr_bounds():
    rng = np.random.default_rng(3)
    good = pd.Series(rng.normal(0.002, 0.01, 1000))
    bad = pd.Series(rng.normal(-0.002, 0.01, 1000))
    assert BT.probabilistic_sharpe(good) > 0.95
    assert BT.probabilistic_sharpe(bad) < 0.05
    assert BT.expected_max_sharpe(100, 0.01) > BT.expected_max_sharpe(2, 0.01)


def test_rsi_bounds_and_known_value():
    up = pd.Series(np.arange(1, 40, dtype=float))
    assert S.rsi(up, 14).dropna().iloc[-1] == pytest.approx(100.0)
    rng = np.random.default_rng(1)
    r = S.rsi(pd.Series(100 + rng.normal(0, 1, 500).cumsum()), 14).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_momentum_definition():
    p = pd.Series(np.arange(1, 301, dtype=float))
    m = S.momentum(p, lookback=252, skip=21)
    assert m.iloc[-1] == pytest.approx(p.iloc[-22] / p.iloc[-253] - 1)
