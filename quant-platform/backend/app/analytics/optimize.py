"""Portfolio construction: equal weight, inverse volatility, minimum variance, equal risk
contribution (risk parity), and mean-variance with user-supplied expected returns.

All methods are long-only and fully invested with per-asset caps. Covariance is estimated from
historical returns with optional shrinkage toward the diagonal (reduces estimation noise).
Mean-variance is notoriously sensitive to expected-return inputs; it is provided for comparison,
and the API flags it accordingly. For small accounts, simple weights usually dominate once
transaction costs and estimation error are considered.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

TRADING_DAYS = 252


def covariance(returns: pd.DataFrame, shrinkage: float = 0.2, periods_per_year: int = TRADING_DAYS) -> pd.DataFrame:
    s = returns.dropna().cov() * periods_per_year
    if shrinkage > 0:
        target = np.diag(np.diag(s.to_numpy()))
        s = pd.DataFrame((1 - shrinkage) * s.to_numpy() + shrinkage * target, index=s.index, columns=s.columns)
    return s


def _solve(objective, n, max_weight, x0=None):
    if max_weight * n < 1 - 1e-9:
        raise ValueError(f"max_weight {max_weight} too low for {n} assets to be fully invested")
    x0 = np.full(n, 1 / n) if x0 is None else x0
    res = minimize(objective, x0, method="SLSQP", bounds=[(0.0, max_weight)] * n,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}], options={"maxiter": 500, "ftol": 1e-12})
    if not res.success:
        raise RuntimeError(f"optimizer failed: {res.message}")
    w = np.clip(res.x, 0, None)
    return w / w.sum()


def equal_weight(cols) -> dict[str, float]:
    return {c: 1 / len(cols) for c in cols}


def inverse_volatility(cov: pd.DataFrame) -> dict[str, float]:
    iv = 1 / np.sqrt(np.diag(cov.to_numpy()))
    return dict(zip(cov.columns, iv / iv.sum()))


def min_variance(cov: pd.DataFrame, max_weight: float = 1.0) -> dict[str, float]:
    S = cov.to_numpy()
    return dict(zip(cov.columns, _solve(lambda w: w @ S @ w, len(S), max_weight)))


def risk_parity(cov: pd.DataFrame, max_weight: float = 1.0) -> dict[str, float]:
    """Equal risk contribution: minimize Σ (RC_i - σ_p/n)^2."""
    S = cov.to_numpy()
    n = len(S)

    def obj(w):
        sig = np.sqrt(w @ S @ w)
        rc = w * (S @ w) / sig
        return ((rc - sig / n) ** 2).sum() * 1e4

    x0 = np.array(list(inverse_volatility(cov).values()))
    return dict(zip(cov.columns, _solve(obj, n, max_weight, x0)))


def mean_variance(cov: pd.DataFrame, expected_returns: dict[str, float], risk_aversion: float = 3.0,
                  max_weight: float = 1.0) -> dict[str, float]:
    S = cov.to_numpy()
    mu = pd.Series(expected_returns).reindex(cov.columns).fillna(0.0).to_numpy()
    return dict(zip(cov.columns, _solve(lambda w: -(w @ mu) + risk_aversion / 2 * (w @ S @ w), len(S), max_weight)))


def portfolio_stats(weights: dict[str, float], cov: pd.DataFrame, expected_returns: dict[str, float] | None = None) -> dict:
    w = pd.Series(weights).reindex(cov.columns).fillna(0.0).to_numpy()
    vol = float(np.sqrt(w @ cov.to_numpy() @ w))
    out = {"volatility": vol}
    if expected_returns:
        mu = pd.Series(expected_returns).reindex(cov.columns).fillna(0.0).to_numpy()
        out["expected_return"] = float(w @ mu)
    return out


def construct(returns: pd.DataFrame, method: str, max_weight: float = 1.0, shrinkage: float = 0.2,
              expected_returns: dict[str, float] | None = None) -> dict:
    cov = covariance(returns, shrinkage)
    warnings = []
    if method == "equal_weight":
        w = equal_weight(list(returns.columns))
    elif method == "inverse_vol":
        w = inverse_volatility(cov)
    elif method == "min_variance":
        w = min_variance(cov, max_weight)
    elif method == "risk_parity":
        w = risk_parity(cov, max_weight)
    elif method == "mean_variance":
        if not expected_returns:
            raise ValueError("mean_variance requires expected_returns (these are assumptions, not facts)")
        w = mean_variance(cov, expected_returns, max_weight=max_weight)
        warnings.append("mean-variance weights are highly sensitive to expected-return assumptions")
    else:
        raise ValueError(f"unknown method {method}")
    if max_weight < 1 and method in ("equal_weight", "inverse_vol") and max(w.values()) > max_weight + 1e-9:
        warnings.append("weights exceed max_weight; cap not applied for this heuristic method")
    if len(returns.dropna()) < 252:
        warnings.append("covariance estimated from < 1 year of data")
    return {"method": method, "weights": w, "stats": portfolio_stats(w, cov, expected_returns), "warnings": warnings,
            "observations": int(len(returns.dropna()))}
