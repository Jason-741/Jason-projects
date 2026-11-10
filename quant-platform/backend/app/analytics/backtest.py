"""Long-only, share-based daily backtester with explicit costs and one-bar execution lag.

Methodology
-----------
* Signals are computed from prices up to day t and executed at day t+1's price (lag=1).
* Rebalancing happens only on schedule days (daily / weekly / monthly first trading day),
  and only for trades whose size exceeds `min_trade_value` (avoids dust trades).
* Costs per trade: fixed commission + |trade value| × (half-spread + slippage [+ FX fee if the
  asset currency differs from the base currency]). Costs are deducted from cash.
* Prices should be total-return (dividend/split adjusted) closes, which implicitly reinvests
  dividends. Raw closes understate return for dividend payers.
* Fractional shares are allowed (Wealthsimple supports them for many, not all, securities).

Known limitations: close-to-close fills, no intraday liquidity model, no borrowing, constant
spread assumption, FX converted at a constant cost rather than a historical rate series, and the
universe is whatever the user supplies (survivorship bias if it only contains today's survivors).
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, field
from itertools import product
from typing import Callable

import numpy as np
import pandas as pd
from scipy import stats

from . import risk


@dataclass
class CostModel:
    commission: float = 0.0          # per trade, in base currency (Wealthsimple: $0 on stocks/ETFs)
    half_spread_bps: float = 5.0
    slippage_bps: float = 5.0
    fx_fee_bps: float = 150.0        # Wealthsimple charges ~1.5% FX on non-USD accounts; verify your plan
    min_trade_value: float = 1.0

    def cost(self, trade_value: float, foreign: bool) -> float:
        bps = self.half_spread_bps + self.slippage_bps + (self.fx_fee_bps if foreign else 0.0)
        return self.commission + abs(trade_value) * bps / 1e4

    def max_affordable(self, cash: float, foreign: bool) -> float:
        """Largest buy value whose value + cost fits in `cash`."""
        bps = self.half_spread_bps + self.slippage_bps + (self.fx_fee_bps if foreign else 0.0)
        return max(0.0, (cash - self.commission) / (1 + bps / 1e4))


@dataclass
class BacktestConfig:
    initial_capital: float = 100.0
    rebalance: str = "monthly"       # daily|weekly|monthly
    lag: int = 1
    costs: CostModel = field(default_factory=CostModel)
    foreign_assets: tuple[str, ...] = ()   # symbols priced in a currency other than base
    risk_free_annual: float = 0.0


@dataclass
class BacktestResult:
    equity: pd.Series
    returns: pd.Series
    weights: pd.DataFrame
    trades: list[dict]
    closed_positions: list[dict]
    metrics: dict
    config: dict
    fingerprint: str


def fingerprint(prices: pd.DataFrame) -> str:
    """SHA-256 of the input data; identical inputs + config ⇒ identical results (reproducibility)."""
    h = hashlib.sha256()
    h.update(pd.util.hash_pandas_object(prices.sort_index(axis=1), index=True).values.tobytes())
    h.update(",".join(map(str, prices.columns)).encode())
    return h.hexdigest()


def _rebalance_days(index: pd.Index, freq: str) -> set:
    idx = pd.to_datetime(pd.Index(index))
    if freq == "daily":
        return set(index)
    key = idx.to_period("W" if freq == "weekly" else "M")
    first = ~pd.Series(key).duplicated().to_numpy()
    return set(np.asarray(index)[first])


def run_backtest(prices: pd.DataFrame, target_weights: pd.DataFrame, config: BacktestConfig | None = None,
                 benchmark: pd.Series | None = None) -> BacktestResult:
    cfg = config or BacktestConfig()
    prices = prices.sort_index()
    tw = target_weights.reindex(prices.index).fillna(0.0).clip(lower=0.0)
    gross = tw.sum(axis=1)
    if (gross > 1 + 1e-9).any():
        tw = tw.div(gross.where(gross > 1, 1.0), axis=0)  # no leverage
    tw = tw.shift(cfg.lag).fillna(0.0)                   # execution lag ⇒ no look-ahead
    reb = _rebalance_days(prices.index, cfg.rebalance)

    cash = cfg.initial_capital
    shares = {c: 0.0 for c in prices.columns}
    avg_cost = {c: 0.0 for c in prices.columns}
    episode_pnl = {c: 0.0 for c in prices.columns}
    episode_start = {c: None for c in prices.columns}
    trades, closed = [], []
    equity_vals, weight_rows = [], []
    for t in prices.index:
        px = prices.loc[t]
        value = cash + sum(shares[c] * px[c] for c in prices.columns if not math.isnan(px[c]))
        if t in reb:
            for c in prices.columns:
                p = px[c]
                if math.isnan(p) or p <= 0:
                    continue
                target_val = tw.at[t, c] * value
                cur_val = shares[c] * p
                delta = target_val - cur_val
                if abs(delta) < cfg.costs.min_trade_value:
                    continue
                cost = cfg.costs.cost(delta, c in cfg.foreign_assets)
                qty = delta / p
                if qty > 0:
                    if cash - delta - cost < -1e-9:  # never borrow; scale down to available cash
                        delta = cfg.costs.max_affordable(cash, c in cfg.foreign_assets)
                        if delta < cfg.costs.min_trade_value:
                            continue
                        cost = cfg.costs.cost(delta, c in cfg.foreign_assets)
                        qty = delta / p
                    new_sh = shares[c] + qty
                    avg_cost[c] = (avg_cost[c] * shares[c] + qty * p + cost) / new_sh
                    if shares[c] <= 1e-12:
                        episode_start[c], episode_pnl[c] = t, 0.0
                    shares[c] = new_sh
                else:
                    sell = min(-qty, shares[c])
                    delta = -sell * p
                    cost = cfg.costs.cost(delta, c in cfg.foreign_assets)
                    episode_pnl[c] += sell * (p - avg_cost[c]) - cost
                    shares[c] -= sell
                    if shares[c] <= 1e-9:
                        closed.append({"symbol": c, "opened": str(episode_start[c]), "closed": str(t), "pnl": episode_pnl[c]})
                        shares[c], avg_cost[c] = 0.0, 0.0
                    qty = -sell
                cash -= delta + cost
                trades.append({"date": str(t), "symbol": c, "qty": qty, "price": p, "value": delta, "cost": cost})
        value = cash + sum(shares[c] * px[c] for c in prices.columns if not math.isnan(px[c]))
        equity_vals.append(value)
        weight_rows.append({c: (shares[c] * px[c] / value if value > 0 and not math.isnan(px[c]) else 0.0) for c in prices.columns})
    equity = pd.Series(equity_vals, index=prices.index, name="equity")
    rets = equity.pct_change().dropna()
    bench_rets = benchmark.sort_index().pct_change().dropna() if benchmark is not None else None
    m = risk.summary(rets, bench_rets, cfg.risk_free_annual)
    traded = sum(abs(tr["value"]) for tr in trades)
    years = max(len(rets) / risk.TRADING_DAYS, 1e-9)
    m["annual_turnover"] = traded / float(equity.mean()) / years if len(equity) else float("nan")
    m["total_costs"] = sum(tr["cost"] for tr in trades)
    m["n_trades"] = len(trades)
    pnls = [c["pnl"] for c in closed]
    wins, losses = [p for p in pnls if p > 0], [p for p in pnls if p <= 0]
    m["closed_positions"] = len(pnls)
    m["win_rate"] = len(wins) / len(pnls) if pnls else float("nan")
    m["avg_win"] = float(np.mean(wins)) if wins else float("nan")
    m["avg_loss"] = float(np.mean(losses)) if losses else float("nan")
    m["profit_factor"] = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else float("nan")
    m["final_equity"] = float(equity.iloc[-1]) if len(equity) else float("nan")
    cfg_dict = asdict(cfg)
    return BacktestResult(equity, rets, pd.DataFrame(weight_rows, index=prices.index), trades, closed,
                          risk.clean(m), cfg_dict, fingerprint(prices))


def check_no_lookahead(weight_fn: Callable[..., pd.DataFrame], prices: pd.DataFrame, params: dict,
                       cut_points: int = 5) -> bool:
    """Signals for dates <= T must be identical whether or not data after T is available."""
    full = weight_fn(prices, **params)
    n = len(prices)
    for k in np.linspace(n // 3, n - 2, cut_points).astype(int):
        part = weight_fn(prices.iloc[: k + 1], **params)
        a, b = full.iloc[: k + 1].fillna(-999), part.fillna(-999)
        if not np.allclose(a.to_numpy(), b.to_numpy()):
            return False
    return True


def probabilistic_sharpe(returns: pd.Series, benchmark_sr: float = 0.0) -> float:
    """PSR (Bailey & López de Prado 2012): P(true per-period SR > benchmark_sr) given sample length,
    skewness and kurtosis. benchmark_sr is per-period (not annualized)."""
    r = returns.dropna()
    n = len(r)
    if n < 10 or r.std(ddof=1) == 0:
        return float("nan")
    sr = r.mean() / r.std(ddof=1)
    g3 = stats.skew(r)
    g4 = stats.kurtosis(r, fisher=False)
    denom = math.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2, 1e-12))
    return float(stats.norm.cdf((sr - benchmark_sr) * math.sqrt(n - 1) / denom))


def expected_max_sharpe(n_trials: int, sr_variance: float) -> float:
    """Expected maximum per-period Sharpe among `n_trials` unskilled strategies (deflated-Sharpe benchmark)."""
    if n_trials <= 1:
        return 0.0
    g = 0.5772156649
    return math.sqrt(sr_variance) * ((1 - g) * stats.norm.ppf(1 - 1 / n_trials) + g * stats.norm.ppf(1 - 1 / (n_trials * math.e)))


def walk_forward(prices: pd.DataFrame, weight_fn: Callable[..., pd.DataFrame], param_grid: dict[str, list],
                 train_days: int = 756, test_days: int = 252, config: BacktestConfig | None = None,
                 warmup_days: int = 260) -> dict:
    """Rolling walk-forward: choose params by in-sample Sharpe on each train window, apply to the next
    test window, and stitch together ONLY out-of-sample returns. Reports the number of configurations
    tried and the deflated Sharpe benchmark to discourage over-reading the best in-sample result."""
    cfg = config or BacktestConfig()
    keys = list(param_grid)
    combos = [dict(zip(keys, vals)) for vals in product(*[param_grid[k] for k in keys])] or [{}]
    oos, windows, is_sharpes = [], [], []
    start = 0
    n = len(prices)
    while start + train_days + test_days <= n:
        train = prices.iloc[start: start + train_days]
        best, best_sr = None, -np.inf
        for p in combos:
            res = run_backtest(train, weight_fn(train, **p), cfg)
            sr = res.metrics.get("sharpe")
            sr = -np.inf if sr is None else sr
            is_sharpes.append(sr if np.isfinite(sr) else np.nan)
            if sr > best_sr:
                best, best_sr = p, sr
        # test window includes warmup history so indicators exist, but only test-period returns count
        lo = max(0, start + train_days - warmup_days)
        window = prices.iloc[lo: start + train_days + test_days]
        w = weight_fn(window, **best)
        res = run_backtest(window, w, cfg)
        test_idx = prices.index[start + train_days: start + train_days + test_days]
        oos.append(res.returns.reindex(test_idx).dropna())
        windows.append({"train_start": str(train.index[0]), "train_end": str(train.index[-1]),
                        "test_start": str(test_idx[0]), "test_end": str(test_idx[-1]), "params": best,
                        "in_sample_sharpe": best_sr if np.isfinite(best_sr) else None})
        start += test_days
    if not oos:
        return {"error": f"need at least {train_days + test_days} rows; have {n}"}
    oos_r = pd.concat(oos)
    sr_var = float(np.nanvar(np.array(is_sharpes) / math.sqrt(risk.TRADING_DAYS))) if is_sharpes else 0.0
    sr_star = expected_max_sharpe(len(combos), sr_var)
    return risk.clean({"windows": windows, "configurations_tested": len(combos),
                       "oos_metrics": risk.summary(oos_r, risk_free_annual=cfg.risk_free_annual),
                       "oos_psr_vs_zero": probabilistic_sharpe(oos_r, 0.0),
                       "oos_psr_vs_deflated": probabilistic_sharpe(oos_r, sr_star),
                       "deflated_sr_benchmark_per_period": sr_star,
                       "oos_returns": [(str(i), float(v)) for i, v in oos_r.items()]})


def split_in_out_of_sample(prices: pd.DataFrame, oos_fraction: float = 0.3) -> tuple[pd.DataFrame, pd.DataFrame]:
    cut = int(len(prices) * (1 - oos_fraction))
    return prices.iloc[:cut], prices.iloc[cut:]
