"""Return and risk statistics. See docs/METHODOLOGY.md for definitions, assumptions and limitations.

Conventions: inputs are SIMPLE periodic returns (daily unless stated). Annualization assumes
`periods_per_year` (252 trading days) and i.i.d. returns — an approximation that understates
risk when returns are autocorrelated or volatility clusters. VaR/CVaR are reported as POSITIVE
loss fractions (0.03 = 3% loss).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

TRADING_DAYS = 252


def to_returns(prices: pd.Series | pd.DataFrame) -> pd.Series | pd.DataFrame:
    return prices.sort_index().pct_change().dropna(how="all")


def annualized_return(returns: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    r = returns.dropna()
    if len(r) == 0:
        return float("nan")
    growth = float((1 + r).prod())
    if growth <= 0:
        return -1.0
    return growth ** (periods_per_year / len(r)) - 1


def total_return(returns: pd.Series) -> float:
    return float((1 + returns.dropna()).prod() - 1)


def annualized_volatility(returns: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    return float(returns.dropna().std(ddof=1) * np.sqrt(periods_per_year))


def sharpe_ratio(returns: pd.Series, risk_free_annual: float = 0.0, periods_per_year: int = TRADING_DAYS) -> float:
    r = returns.dropna()
    excess = r - (1 + risk_free_annual) ** (1 / periods_per_year) + 1
    sd = excess.std(ddof=1)
    return float(excess.mean() / sd * np.sqrt(periods_per_year)) if sd > 0 else float("nan")


def sortino_ratio(returns: pd.Series, risk_free_annual: float = 0.0, periods_per_year: int = TRADING_DAYS) -> float:
    """Mean excess return / downside deviation (target = risk-free), annualized."""
    r = returns.dropna()
    excess = r - ((1 + risk_free_annual) ** (1 / periods_per_year) - 1)
    downside = np.minimum(excess, 0.0)
    dd = np.sqrt((downside ** 2).mean())
    return float(excess.mean() / dd * np.sqrt(periods_per_year)) if dd > 0 else float("nan")


def drawdown_series(returns: pd.Series) -> pd.Series:
    wealth = (1 + returns.fillna(0)).cumprod()
    peak = wealth.cummax()
    return wealth / peak - 1


def max_drawdown(returns: pd.Series) -> float:
    """Largest peak-to-trough decline as a positive fraction."""
    dd = drawdown_series(returns)
    return float(-dd.min()) if len(dd) else float("nan")


def calmar_ratio(returns: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    mdd = max_drawdown(returns)
    return annualized_return(returns, periods_per_year) / mdd if mdd > 0 else float("nan")


def historical_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """Empirical loss quantile: the loss not exceeded on `confidence` of historical periods."""
    r = returns.dropna().to_numpy()
    return float(-np.quantile(r, 1 - confidence, method="linear"))


def historical_cvar(returns: pd.Series, confidence: float = 0.95) -> float:
    """Expected shortfall: mean loss on periods at or beyond the VaR threshold."""
    r = returns.dropna().to_numpy()
    q = np.quantile(r, 1 - confidence, method="linear")
    tail = r[r <= q]
    return float(-tail.mean()) if len(tail) else float("nan")


def parametric_var(returns: pd.Series, confidence: float = 0.95, horizon_days: int = 1) -> float:
    """Gaussian VaR: -(μh - z σ√h). Understates tail risk for fat-tailed returns."""
    r = returns.dropna()
    mu, sd = r.mean(), r.std(ddof=1)
    z = stats.norm.ppf(confidence)
    return float(-(mu * horizon_days - z * sd * np.sqrt(horizon_days)))


def parametric_cvar(returns: pd.Series, confidence: float = 0.95) -> float:
    r = returns.dropna()
    mu, sd = r.mean(), r.std(ddof=1)
    z = stats.norm.ppf(confidence)
    return float(-(mu - sd * stats.norm.pdf(z) / (1 - confidence)))


def beta(asset: pd.Series, benchmark: pd.Series) -> float:
    df = pd.concat([asset, benchmark], axis=1, join="inner").dropna()
    if len(df) < 3:
        return float("nan")
    cov = np.cov(df.iloc[:, 0], df.iloc[:, 1], ddof=1)
    return float(cov[0, 1] / cov[1, 1]) if cov[1, 1] > 0 else float("nan")


def portfolio_returns(asset_returns: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Constant-weight (daily rebalanced) portfolio return series."""
    w = pd.Series(weights, dtype=float).reindex(asset_returns.columns).fillna(0.0)
    return asset_returns.fillna(0.0) @ w


def risk_contributions(asset_returns: pd.DataFrame, weights: dict[str, float], periods_per_year: int = TRADING_DAYS) -> pd.DataFrame:
    """Euler decomposition of portfolio volatility: RC_i = w_i (Σw)_i / σ_p. Σ RC_i = σ_p."""
    cols = list(asset_returns.columns)
    w = pd.Series(weights, dtype=float).reindex(cols).fillna(0.0).to_numpy()
    cov = asset_returns.dropna().cov().to_numpy() * periods_per_year
    port_var = float(w @ cov @ w)
    sigma = np.sqrt(port_var) if port_var > 0 else 0.0
    mrc = cov @ w / sigma if sigma > 0 else np.zeros_like(w)
    rc = w * mrc
    return pd.DataFrame({"weight": w, "marginal_contribution": mrc, "risk_contribution": rc,
                         "pct_of_risk": rc / sigma if sigma > 0 else np.zeros_like(w)}, index=cols)


def concentration(weights: dict[str, float]) -> dict:
    w = np.array([v for v in weights.values() if v > 0], dtype=float)
    if w.sum() <= 0:
        return {"hhi": float("nan"), "effective_n": float("nan"), "max_weight": float("nan")}
    w = w / w.sum()
    hhi = float((w ** 2).sum())
    return {"hhi": hhi, "effective_n": 1 / hhi, "max_weight": float(w.max())}


def summary(returns: pd.Series, benchmark: pd.Series | None = None, risk_free_annual: float = 0.0,
            periods_per_year: int = TRADING_DAYS) -> dict:
    r = returns.dropna()
    out = {
        "observations": int(len(r)),
        "start": str(r.index[0])[:10] if len(r) else None,
        "end": str(r.index[-1])[:10] if len(r) else None,
        "total_return": total_return(r),
        "cagr": annualized_return(r, periods_per_year),
        "volatility": annualized_volatility(r, periods_per_year),
        "sharpe": sharpe_ratio(r, risk_free_annual, periods_per_year),
        "sortino": sortino_ratio(r, risk_free_annual, periods_per_year),
        "max_drawdown": max_drawdown(r),
        "calmar": calmar_ratio(r, periods_per_year),
        "var_95_hist": historical_var(r, 0.95),
        "cvar_95_hist": historical_cvar(r, 0.95),
        "var_99_hist": historical_var(r, 0.99),
        "var_95_param": parametric_var(r, 0.95),
        "skew": float(stats.skew(r)) if len(r) > 2 else float("nan"),
        "excess_kurtosis": float(stats.kurtosis(r)) if len(r) > 3 else float("nan"),
    }
    if benchmark is not None:
        b = benchmark.reindex(r.index).dropna()
        rr = r.reindex(b.index)
        out["beta"] = beta(rr, b)
        out["benchmark_cagr"] = annualized_return(b, periods_per_year)
        out["excess_cagr"] = out["cagr"] - out["benchmark_cagr"]
        active = rr - b
        te = active.std(ddof=1) * np.sqrt(periods_per_year)
        out["tracking_error"] = float(te)
        out["information_ratio"] = float(active.mean() * periods_per_year / te) if te > 0 else float("nan")
        out["correlation"] = float(rr.corr(b))
    if len(r) < 252:
        out["warning"] = "fewer than 252 observations — statistics are highly uncertain"
    return out


def clean(d: dict) -> dict:
    """Replace NaN/inf with None for JSON."""
    def c(v):
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            return None
        if isinstance(v, (np.floating,)):
            return c(float(v))
        if isinstance(v, dict):
            return {k: c(x) for k, x in v.items()}
        if isinstance(v, list):
            return [c(x) for x in v]
        return v
    return c(d)
