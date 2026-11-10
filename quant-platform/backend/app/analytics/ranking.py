"""Multi-factor research ranking of the covered universe.

Purpose: narrow a universe down to the candidates most worth researching NOW. The ranking
is an evidence summary, not a buy signal: it says nothing about price relative to intrinsic
value unless valuation data exists, and past factor efficacy does not guarantee future efficacy.

Method
------
For each security, compute factor values from stored data (prices up to `as_of`; fundamentals
filed by `as_of`). Each factor is converted to a cross-sectional percentile rank in [0, 1]
(direction-adjusted so 1 = better). Factor ranks are averaged within groups, and group scores
are combined with weights:

    trend & momentum (0.40): 12-1 momentum, 6-month return, price vs 200-day SMA
    risk (0.25):             1-year volatility (lower better), 3-year max drawdown (lower better),
                             3-year Sharpe
    quality (0.35):          ROE, operating margin, FCF margin, net debt / EBITDA (lower better),
                             revenue growth — only for companies with SEC fundamentals

Missing groups are dropped and the remaining weights renormalised; `coverage` reports which
groups contributed, so a score built from price data alone is visible as such.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from . import ratios as R
from . import signals as S

GROUPS = {
    "trend_momentum": (0.40, {"mom_12_1": 1, "ret_6m": 1, "vs_sma200": 1}),
    "risk": (0.25, {"vol_1y": -1, "mdd_3y": -1, "sharpe_3y": 1}),
    "quality": (0.35, {"roe": 1, "operating_margin": 1, "fcf_margin": 1, "net_debt_to_ebitda": -1, "revenue_growth": 1}),
}


def price_factors(px: pd.Series, volume: pd.Series | None = None) -> dict:
    px = px.dropna()
    out: dict = {"bars": int(len(px))}
    if len(px) < 260:
        return out
    r = px.pct_change().dropna()
    out["mom_12_1"] = float(S.momentum(px).iloc[-1])
    out["ret_6m"] = float(px.iloc[-1] / px.iloc[-127] - 1)
    out["vs_sma200"] = float(px.iloc[-1] / px.tail(200).mean() - 1)
    out["vol_1y"] = float(r.tail(252).std() * np.sqrt(252))
    w = px.tail(756)
    out["mdd_3y"] = float(-(w / w.cummax() - 1).min())
    r3 = r.tail(756)
    out["sharpe_3y"] = float(r3.mean() / r3.std() * np.sqrt(252)) if r3.std() > 0 else None
    out["ret_1y"] = float(px.iloc[-1] / px.iloc[-253] - 1)
    if volume is not None:
        dv = (px * volume.reindex(px.index)).tail(60).dropna()
        out["avg_dollar_volume"] = float(dv.mean()) if len(dv) else None
    return out


def fundamental_factors(latest: dict, prior: dict | None) -> dict:
    m = R.statement_ratios(latest, prior)
    out = {k: m[k].value for k in ("roe", "operating_margin", "fcf_margin", "net_debt_to_ebitda") if k in m}
    if "revenue_growth" in m:
        out["revenue_growth"] = m["revenue_growth"].value
    nd = out.get("net_debt_to_ebitda")
    d = R.derived_items(latest)
    if nd is None and d.get("net_debt") is not None and d["net_debt"] < 0:
        out["net_debt_to_ebitda"] = -1.0   # net cash: treat as best-in-class leverage
    return out


def rank(rows: list[dict]) -> list[dict]:
    """rows: [{symbol, ..., factors: {...}}] → adds group scores, total score, coverage, rank."""
    df = pd.DataFrame([{"symbol": r["symbol"], **r["factors"]} for r in rows]).set_index("symbol")
    pct = {}
    for _, (_, factors) in GROUPS.items():
        for f, sign in factors.items():
            if f in df and df[f].notna().sum() >= 3:
                pct[f] = (df[f] * sign).rank(pct=True)
    for r in rows:
        s = r["symbol"]
        groups, total_w, total = {}, 0.0, 0.0
        for g, (w, factors) in GROUPS.items():
            vals = [pct[f][s] for f in factors if f in pct and pd.notna(pct[f].get(s))]
            need = 2 if g != "quality" else 3
            if len(vals) >= need:
                groups[g] = float(np.mean(vals))
                total += w * groups[g]
                total_w += w
        r["group_scores"] = groups
        r["score"] = total / total_w if total_w else None
        r["coverage"] = sorted(groups)
    ranked = sorted([r for r in rows if r["score"] is not None], key=lambda r: -r["score"])
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return ranked + [r for r in rows if r["score"] is None]


def weights_composite(prices: pd.DataFrame, top_k: int = 3, lookback: int = 252, skip: int = 21) -> pd.DataFrame:
    """Price-only version of the ranking for historical testing: each day, rank by the average
    percentile of 12-1 momentum, distance above SMA200 and (inverse) 1-year volatility; hold the
    top_k with positive momentum, equally weighted. Causal: uses data up to each date only."""
    mom = S.momentum(prices, lookback, skip)
    trend = prices / S.sma(prices, 200) - 1
    vol = prices.pct_change().rolling(252, min_periods=252).std()
    score = (mom.rank(axis=1, pct=True) + trend.rank(axis=1, pct=True) + (-vol).rank(axis=1, pct=True)) / 3
    ok = mom.notna() & trend.notna() & vol.notna() & (mom > 0)
    score = score.where(ok)
    sel = score.rank(axis=1, ascending=False, method="first") <= top_k
    return (sel & ok).astype(float).div(top_k)
