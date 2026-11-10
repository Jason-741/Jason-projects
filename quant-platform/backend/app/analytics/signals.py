"""Technical / quantitative signals.

Every function here is CAUSAL: the value at date t uses only data at or before t. The backtester
additionally lags signals by one bar before trading, so a signal computed on day t's close is
traded at day t+1's close. `tests/test_backtest.py` verifies causality by truncation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(prices: pd.DataFrame | pd.Series, window: int):
    return prices.rolling(window, min_periods=window).mean()


def momentum(prices: pd.DataFrame | pd.Series, lookback: int = 252, skip: int = 21):
    """Classic 12-1 momentum: return from t-lookback to t-skip (skips the most recent month,
    which empirically tends to mean-revert)."""
    return prices.shift(skip) / prices.shift(lookback) - 1


def rsi(prices: pd.Series | pd.DataFrame, window: int = 14):
    """Wilder's RSI using exponential smoothing with alpha = 1/window."""
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(avg_loss != 0, 100.0).where(avg_gain.notna())


def zscore(prices: pd.Series | pd.DataFrame, window: int = 20):
    m = prices.rolling(window, min_periods=window).mean()
    s = prices.rolling(window, min_periods=window).std(ddof=1)
    return (prices - m) / s


def bollinger(prices: pd.Series, window: int = 20, k: float = 2.0) -> pd.DataFrame:
    m = prices.rolling(window, min_periods=window).mean()
    s = prices.rolling(window, min_periods=window).std(ddof=1)
    return pd.DataFrame({"middle": m, "upper": m + k * s, "lower": m - k * s, "pct_b": (prices - (m - k * s)) / (2 * k * s)})


def realized_vol(prices: pd.Series | pd.DataFrame, window: int = 20, periods_per_year: int = 252):
    return prices.pct_change().rolling(window, min_periods=window).std(ddof=1) * np.sqrt(periods_per_year)


def volume_confirmation(volume: pd.Series, window: int = 50):
    """Volume relative to its trailing average (excluding today)."""
    return volume / volume.shift(1).rolling(window, min_periods=window).mean()


# ---------- target-weight generators (long-only, weights sum to <= 1, remainder in cash) ----------

def weights_buy_and_hold(prices: pd.DataFrame) -> pd.DataFrame:
    w = pd.DataFrame(1.0 / prices.shape[1], index=prices.index, columns=prices.columns)
    return w.where(prices.notna(), 0.0)


def weights_trend(prices: pd.DataFrame, window: int = 200) -> pd.DataFrame:
    """Equal weight across assets trading above their `window`-day SMA; cash otherwise."""
    on = (prices > sma(prices, window)).astype(float)
    return on.div(prices.shape[1])


def weights_cross_sectional_momentum(prices: pd.DataFrame, top_k: int = 3, lookback: int = 252, skip: int = 21,
                                     absolute_filter: bool = True) -> pd.DataFrame:
    """Hold the top_k assets by 12-1 momentum, equally weighted; optionally require momentum > 0."""
    mom = momentum(prices, lookback, skip)
    ranks = mom.rank(axis=1, ascending=False, method="first")
    sel = (ranks <= top_k) & mom.notna()
    if absolute_filter:
        sel &= mom > 0
    return sel.astype(float).div(top_k)


def weights_rsi_mean_reversion(prices: pd.DataFrame, window: int = 14, entry: float = 30, exit: float = 55) -> pd.DataFrame:
    """Enter when RSI < entry, exit when RSI > exit (stateful, causal loop). Equal-weight slots."""
    r = rsi(prices, window)
    state = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    holding = {c: False for c in prices.columns}
    for t in prices.index:
        for c in prices.columns:
            v = r.at[t, c]
            if np.isnan(v):
                holding[c] = False
            elif not holding[c] and v < entry:
                holding[c] = True
            elif holding[c] and v > exit:
                holding[c] = False
            state.at[t, c] = 1.0 if holding[c] else 0.0
    return state.div(prices.shape[1])


STRATEGIES = {
    "buy_and_hold": (weights_buy_and_hold, {}),
    "trend": (weights_trend, {"window": 200}),
    "xs_momentum": (weights_cross_sectional_momentum, {"top_k": 3, "lookback": 252, "skip": 21}),
    "rsi_mean_reversion": (weights_rsi_mean_reversion, {"window": 14, "entry": 30, "exit": 55}),
}
