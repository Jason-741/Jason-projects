from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics import backtest as BT
from ..analytics import dcf as D
from ..analytics import montecarlo as MC
from ..analytics import optimize as O
from ..analytics import risk as RK
from ..analytics import signals as S
from ..analytics import stress as ST
from ..db import get_db
from ..models import BacktestRun
from ..security.auth import current_user
from ..services.market_data import find_security, price_frame
from .common import jsonable, price_matrix

router = APIRouter(prefix="/api", tags=["analytics"], dependencies=[Depends(current_user)])


# ---------------------------------------------------------------- valuation

class DCFBody(BaseModel):
    base_revenue: float
    revenue_growth: list[float] = Field(min_length=1, max_length=30)
    ebit_margin: list[float] | float
    tax_rate: float = Field(ge=0, le=0.6)
    wacc: float = Field(gt=0, lt=0.5)
    net_debt: float
    diluted_shares: float = Field(gt=0)
    da_pct_revenue: float = 0.0
    capex_pct_revenue: float = 0.0
    nwc_pct_revenue: float = 0.0
    terminal_method: str = "gordon"
    terminal_growth: float = 0.02
    exit_ev_ebitda: float | None = None
    mid_year: bool = True
    market_price: float | None = None
    scenarios: dict[str, dict] | None = None
    sensitivity_waccs: list[float] | None = None
    sensitivity_growths: list[float] | None = None


@router.post("/valuation/dcf")
def dcf(body: DCFBody):
    extra = {"market_price", "scenarios", "sensitivity_waccs", "sensitivity_growths"}
    inp = D.DCFInputs(**body.model_dump(exclude=extra))
    try:
        res = D.run_dcf(inp)
        out = {"result": res.as_dict(), "inputs": body.model_dump(exclude=extra),
               "label": "ESTIMATE conditional on the assumptions above — not an objectively known value"}
        waccs = body.sensitivity_waccs or [round(inp.wacc + d, 4) for d in (-0.02, -0.01, 0, 0.01, 0.02)]
        growths = body.sensitivity_growths or [round(inp.terminal_growth + d, 4) for d in (-0.01, -0.005, 0, 0.005, 0.01)]
        out["sensitivity"] = D.sensitivity(inp, waccs, growths)
        if body.scenarios:
            out["scenarios"] = D.scenarios(inp, body.scenarios)
            vals = [v["value_per_share"] for v in out["scenarios"].values()]
            out["valuation_range"] = {"low": min(vals), "high": max(vals)}
        if body.market_price:
            out["market_price"] = body.market_price
            out["margin_of_safety"] = D.margin_of_safety(res.value_per_share, body.market_price)
            out["reverse_dcf"] = D.reverse_dcf(inp, body.market_price)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return jsonable(out)


class WACCBody(BaseModel):
    risk_free: float
    beta: float
    equity_risk_premium: float
    size_premium: float = 0.0
    equity_value: float
    debt_value: float
    pre_tax_cost_of_debt: float
    tax_rate: float


@router.post("/valuation/wacc")
def wacc(b: WACCBody):
    ke = D.capm_cost_of_equity(b.risk_free, b.beta, b.equity_risk_premium, b.size_premium)
    return {"cost_of_equity": ke, "wacc": D.wacc(b.equity_value, b.debt_value, ke, b.pre_tax_cost_of_debt, b.tax_rate),
            "method": "CAPM cost of equity; market-value weights; after-tax cost of debt"}


class MineBody(BaseModel):
    annual_production: float = Field(gt=0)
    mine_life_years: int = Field(gt=0, le=60)
    commodity_price: float = Field(gt=0)
    aisc: float = Field(ge=0)
    initial_capex: float = Field(ge=0)
    discount_rate: float = 0.08
    tax_rate: float = 0.27
    royalty_rate: float = 0.0
    ramp_up: list[float] = [1.0]
    construction_delay_years: int = 0
    closure_cost: float = 0.0


@router.post("/valuation/mine")
def mine(b: MineBody):
    m = ST.MineInputs(**b.model_dump())
    return jsonable({"base": ST.mine_npv(m), "sensitivity": ST.mine_sensitivity(m),
                     "note": "simplified single-asset model; no depreciation tax shield, working capital or financing"})


# ---------------------------------------------------------------- signals & backtests

@router.get("/quant/signals/{symbol}")
def signals(symbol: str, start: date | None = None, db: Session = Depends(get_db)):
    sec = find_security(db, symbol)
    if not sec:
        raise HTTPException(404, "symbol not found")
    df = price_frame(db, sec.id, start)
    if len(df) < 30:
        raise HTTPException(422, "need at least 30 stored bars")
    px = df["adj_close"].fillna(df["close"]).astype(float)
    out = pd.DataFrame({"close": px, "sma50": S.sma(px, 50), "sma200": S.sma(px, 200), "rsi14": S.rsi(px, 14),
                        "z20": S.zscore(px, 20), "mom_12_1": S.momentum(px), "vol20": S.realized_vol(px, 20),
                        "rel_volume": S.volume_confirmation(df["volume"].astype(float))})
    bb = S.bollinger(px)
    out = out.join(bb)
    last = out.iloc[-1].to_dict()
    return jsonable({"symbol": sec.symbol, "latest": last, "as_of": str(out.index[-1]),
                     "series": [{"date": str(i), **r} for i, r in out.tail(500).iterrows()],
                     "note": "signals are descriptive indicators, not recommendations"})


class BacktestBody(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=40)
    strategy: str = "trend"
    params: dict = {}
    start: date | None = None
    end: date | None = None
    benchmark: str | None = None
    initial_capital: float = 100.0
    rebalance: str = "monthly"
    commission: float = 0.0
    half_spread_bps: float = 5.0
    slippage_bps: float = 5.0
    fx_fee_bps: float = 150.0
    foreign_assets: list[str] = []
    risk_free_annual: float = 0.0
    oos_fraction: float = Field(0.3, ge=0, le=0.8)
    save: bool = True


def _cfg(b: BacktestBody) -> BT.BacktestConfig:
    return BT.BacktestConfig(initial_capital=b.initial_capital, rebalance=b.rebalance,
                             costs=BT.CostModel(b.commission, b.half_spread_bps, b.slippage_bps, b.fx_fee_bps),
                             foreign_assets=tuple(s.upper() for s in b.foreign_assets), risk_free_annual=b.risk_free_annual)


def _strategy(name):
    if name not in S.STRATEGIES:
        raise HTTPException(422, f"unknown strategy; choose from {sorted(S.STRATEGIES)}")
    return S.STRATEGIES[name]


@router.post("/backtest/run")
def run_backtest(b: BacktestBody, db: Session = Depends(get_db)):
    fn, defaults = _strategy(b.strategy)
    params = {**defaults, **b.params}
    prices, notes = price_matrix(db, b.symbols, b.start, b.end)
    if len(prices) < 60:
        raise HTTPException(422, f"only {len(prices)} common dates; need >= 60")
    bench = None
    if b.benchmark:
        bm, _ = price_matrix(db, [b.benchmark], b.start, b.end)
        bench = bm.iloc[:, 0].reindex(prices.index).ffill()
    cfg = _cfg(b)
    full = BT.run_backtest(prices, fn(prices, **params), cfg, bench)
    bh = BT.run_backtest(prices, S.weights_buy_and_hold(prices), cfg, bench)
    ins, oos = BT.split_in_out_of_sample(prices, b.oos_fraction) if b.oos_fraction > 0 else (prices, None)
    split = {}
    if oos is not None and len(oos) > 30:
        # OOS evaluated with full history available for indicator warm-up, counting only OOS returns
        oos_r = full.returns[full.returns.index >= oos.index[0]]
        ins_r = full.returns[full.returns.index < oos.index[0]]
        split = {"in_sample": RK.summary(ins_r, risk_free_annual=b.risk_free_annual),
                 "out_of_sample": RK.summary(oos_r, risk_free_annual=b.risk_free_annual),
                 "oos_start": str(oos.index[0].date()),
                 "note": "parameters were NOT fitted here, so this split only checks stability across periods"}
    lookahead_ok = BT.check_no_lookahead(fn, prices, params)
    out = {"metrics": full.metrics, "buy_and_hold_metrics": bh.metrics, "split": split,
           "equity_curve": [(str(i.date()), v) for i, v in full.equity.items()],
           "buy_and_hold_curve": [(str(i.date()), v) for i, v in bh.equity.items()],
           "trades": full.trades[-200:], "closed_positions": full.closed_positions[-200:],
           "fingerprint": full.fingerprint, "config": {**b.model_dump(), "params": params}, "notes": notes,
           "lookahead_check_passed": lookahead_ok,
           "psr_vs_zero": BT.probabilistic_sharpe(full.returns),
           "disclaimer": "Historical simulation. Not evidence of future profitability."}
    if b.save:
        run = BacktestRun(config=jsonable(out["config"]), data_fingerprint=full.fingerprint, metrics=jsonable(full.metrics),
                          equity_curve=jsonable(out["equity_curve"][::5]))
        db.add(run)
        db.commit()
        out["run_id"] = run.id
    return jsonable(out)


class WalkForwardBody(BacktestBody):
    param_grid: dict[str, list] = {"window": [100, 150, 200]}
    train_days: int = 756
    test_days: int = 252


@router.post("/backtest/walk-forward")
def walk_forward(b: WalkForwardBody, db: Session = Depends(get_db)):
    fn, _ = _strategy(b.strategy)
    prices, notes = price_matrix(db, b.symbols, b.start, b.end)
    res = BT.walk_forward(prices, fn, b.param_grid, b.train_days, b.test_days, _cfg(b))
    if "error" in res:
        raise HTTPException(422, res["error"])
    res["notes"] = notes
    return jsonable(res)


@router.get("/backtest/runs")
def backtest_runs(limit: int = 30, db: Session = Depends(get_db)):
    return [{"id": r.id, "created_at": r.created_at.isoformat(), "config": r.config, "fingerprint": r.data_fingerprint,
             "metrics": r.metrics} for r in db.scalars(select(BacktestRun).order_by(BacktestRun.id.desc()).limit(limit))]


@router.get("/backtest/strategies")
def strategies():
    return {k: {"params": v[1], "doc": (v[0].__doc__ or "").strip()} for k, v in S.STRATEGIES.items()}


# ---------------------------------------------------------------- risk & construction

class PortfolioRiskBody(BaseModel):
    weights: dict[str, float]
    start: date | None = None
    end: date | None = None
    benchmark: str | None = None
    risk_free_annual: float = 0.0


@router.post("/risk/portfolio")
def portfolio_risk(b: PortfolioRiskBody, db: Session = Depends(get_db)):
    syms = list(b.weights)
    prices, notes = price_matrix(db, syms + ([b.benchmark] if b.benchmark else []), b.start, b.end)
    rets = RK.to_returns(prices)
    asset = rets[[s.upper() for s in syms]]
    w = {k.upper(): v for k, v in b.weights.items()}
    port = RK.portfolio_returns(asset, w)
    bench = rets[b.benchmark.upper()] if b.benchmark else None
    rc = RK.risk_contributions(asset, w)
    return jsonable({"summary": RK.summary(port, bench, b.risk_free_annual),
                     "risk_contributions": {i: r.to_dict() for i, r in rc.iterrows()},
                     "correlation": {i: r.to_dict() for i, r in asset.corr().iterrows()},
                     "asset_vol": {c: RK.annualized_volatility(asset[c]) for c in asset.columns},
                     "betas": {c: RK.beta(asset[c], bench) for c in asset.columns} if bench is not None else None,
                     "concentration": RK.concentration(w), "drawdown": [(str(i.date()), v) for i, v in RK.drawdown_series(port).items()][::2],
                     "notes": notes,
                     "assumptions": ["constant weights rebalanced daily", "historical VaR assumes the sample is representative",
                                     "parametric VaR assumes normal returns and understates fat tails"]})


class StressBody(BaseModel):
    positions: list[dict]
    scenarios: dict[str, dict] | None = None
    idiosyncratic: dict[str, float] | None = None


@router.post("/risk/stress")
def stress(b: StressBody):
    pos = [ST.StressPosition(**p) for p in b.positions]
    return jsonable({"results": ST.run_stress(pos, b.scenarios, idiosyncratic=b.idiosyncratic),
                     "builtin_scenarios": ST.BUILTIN_SCENARIOS,
                     "method": "first-order linear factor model; betas are estimates"})


class MCBody(BaseModel):
    weights: dict[str, float]
    start: date | None = None
    horizon_days: int = Field(252, ge=5, le=2520)
    n_paths: int = Field(5000, ge=100, le=50000)
    mean_block: int = 10
    seed: int = 42
    initial_value: float = 100.0


@router.post("/risk/montecarlo")
def montecarlo(b: MCBody, db: Session = Depends(get_db)):
    prices, notes = price_matrix(db, list(b.weights), b.start)
    rets = RK.to_returns(prices)
    try:
        res = MC.simulate(rets, {k.upper(): v for k, v in b.weights.items()}, b.initial_value, b.horizon_days, b.n_paths,
                          b.mean_block, b.seed)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    res["notes"] = notes
    return jsonable(res)


class ConstructBody(BaseModel):
    symbols: list[str] = Field(min_length=1)
    method: str = "risk_parity"
    max_weight: float = 1.0
    shrinkage: float = 0.2
    expected_returns: dict[str, float] | None = None
    start: date | None = None
    capital: float = 100.0


@router.post("/portfolio/construct")
def construct(b: ConstructBody, db: Session = Depends(get_db)):
    prices, notes = price_matrix(db, b.symbols, b.start)
    rets = RK.to_returns(prices)
    try:
        res = O.construct(rets, b.method, b.max_weight, b.shrinkage,
                          {k.upper(): v for k, v in (b.expected_returns or {}).items()} or None)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc))
    comparisons = {}
    for m in ("equal_weight", "inverse_vol", "min_variance", "risk_parity"):
        try:
            comparisons[m] = O.construct(rets, m, b.max_weight, b.shrinkage)["stats"]
        except (ValueError, RuntimeError) as exc:
            comparisons[m] = {"error": str(exc)}
    last = prices.iloc[-1]
    res["allocation"] = {s: {"weight": w, "value": w * b.capital, "price": float(last[s]),
                             "shares_fractional": w * b.capital / float(last[s])} for s, w in res["weights"].items()}
    res["comparisons"] = comparisons
    res["notes"] = notes + ["at small capital, prefer few positions; check fractional-share availability per security"]
    return jsonable(res)
