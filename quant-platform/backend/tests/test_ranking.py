import pandas as pd
import pytest

from app.analytics import backtest as BT
from app.analytics import ranking


def test_rank_orders_and_reports_coverage():
    rows = [{"symbol": s, "factors": f} for s, f in [
        ("A", {"mom_12_1": 0.5, "ret_6m": 0.3, "vs_sma200": 0.2, "vol_1y": 0.2, "mdd_3y": 0.1, "sharpe_3y": 1.5,
               "roe": 0.2, "operating_margin": 0.3, "fcf_margin": 0.2, "net_debt_to_ebitda": 0.5, "revenue_growth": 0.1}),
        ("B", {"mom_12_1": 0.1, "ret_6m": 0.0, "vs_sma200": 0.0, "vol_1y": 0.3, "mdd_3y": 0.3, "sharpe_3y": 0.5,
               "roe": 0.05, "operating_margin": 0.1, "fcf_margin": 0.0, "net_debt_to_ebitda": 3.0, "revenue_growth": -0.1}),
        ("C", {"mom_12_1": -0.2, "ret_6m": -0.1, "vs_sma200": -0.1, "vol_1y": 0.5, "mdd_3y": 0.5, "sharpe_3y": -0.2}),
        ("D", {"bars": 10}),
    ]]
    out = ranking.rank(rows)
    assert [r["symbol"] for r in out[:3]] == ["A", "B", "C"]
    assert out[0]["score"] == pytest.approx(1.0)
    assert "quality" not in out[2]["coverage"]          # ETF-like row scored on price groups only
    assert out[-1]["score"] is None and "rank" not in out[-1]


def test_composite_has_no_lookahead(prices):
    assert BT.check_no_lookahead(ranking.weights_composite, prices.iloc[:600], {"top_k": 1, "lookback": 120, "skip": 10})
