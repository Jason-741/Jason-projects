"""Monte Carlo portfolio simulation by stationary block bootstrap of historical returns.

Why bootstrap: resampling contiguous blocks of JOINT historical daily returns preserves fat tails,
cross-asset correlation and short-range volatility clustering without assuming normality.
Limitations: the simulation can only produce environments resembling the sample period; regime
changes, structural breaks and events absent from history are not represented. Output
probabilities are model probabilities, NOT real-world guarantees.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def block_bootstrap_paths(returns: pd.DataFrame, weights: dict[str, float], horizon: int = 252, n_paths: int = 5000,
                          mean_block: int = 10, seed: int = 42) -> np.ndarray:
    r = returns.dropna().to_numpy()
    w = pd.Series(weights, dtype=float).reindex(returns.columns).fillna(0.0).to_numpy()
    port = r @ w
    n = len(port)
    if n < 2 * mean_block:
        raise ValueError(f"need at least {2 * mean_block} observations")
    rng = np.random.default_rng(seed)
    out = np.empty((n_paths, horizon))
    p = 1.0 / mean_block
    for i in range(n_paths):
        idx = np.empty(horizon, dtype=int)
        j = rng.integers(n)
        for h in range(horizon):
            if h > 0 and rng.random() < p:
                j = rng.integers(n)
            idx[h] = j
            j = (j + 1) % n
        out[i] = port[idx]
    return out


def simulate(returns: pd.DataFrame, weights: dict[str, float], initial_value: float = 100.0, horizon: int = 252,
             n_paths: int = 5000, mean_block: int = 10, seed: int = 42) -> dict:
    paths = block_bootstrap_paths(returns, weights, horizon, n_paths, mean_block, seed)
    wealth = initial_value * np.cumprod(1 + paths, axis=1)
    terminal = wealth[:, -1] / initial_value - 1
    peak = np.maximum.accumulate(np.concatenate([np.full((n_paths, 1), initial_value), wealth], axis=1), axis=1)
    mdd = (1 - np.concatenate([np.full((n_paths, 1), initial_value), wealth], axis=1) / peak).max(axis=1)
    pct = [1, 5, 25, 50, 75, 95, 99]
    fan = {str(q): np.percentile(wealth, q, axis=0).tolist() for q in (5, 25, 50, 75, 95)}
    hist, edges = np.histogram(terminal, bins=50)
    return {
        "method": "stationary block bootstrap of historical joint returns",
        "seed": seed, "n_paths": n_paths, "horizon_days": horizon, "mean_block": mean_block,
        "sample_observations": int(len(returns.dropna())),
        "terminal_return_percentiles": {str(q): float(np.percentile(terminal, q)) for q in pct},
        "prob_loss": float((terminal < 0).mean()),
        "prob_loss_gt_10pct": float((terminal < -0.10).mean()),
        "prob_loss_gt_20pct": float((terminal < -0.20).mean()),
        "max_drawdown_percentiles": {str(q): float(np.percentile(mdd, q)) for q in (50, 75, 95, 99)},
        "expected_terminal_value": float(wealth[:, -1].mean()),
        "fan_chart": fan,
        "histogram": {"counts": hist.tolist(), "edges": edges.tolist()},
        "caveat": "Model probabilities conditional on the historical sample; not real-world guarantees.",
    }
