"""Scenario stress tests and a simple mine-economics model.

Portfolio stress is a FIRST-ORDER linear model: each position's return under a scenario is
    r_i = β_equity,i × equity_shock + Σ_k β_k,i × factor_shock_k + idiosyncratic_shock_i
and, for a CAD-based investor holding USD assets, the CAD value also moves with USD/CAD:
    r_i,CAD = (1 + r_i) × (1 + fx_shock) - 1   (fx_shock = % change in CAD per USD).
Betas are estimates (historical regressions or analyst inputs) and are unstable in crises, when
correlations tend to rise. Treat results as illustrative magnitudes, not forecasts.
"""
from __future__ import annotations

from dataclasses import dataclass, field

BUILTIN_SCENARIOS: dict[str, dict] = {
    "equity_-10": {"label": "Equity market -10%", "equity": -0.10},
    "equity_-20": {"label": "Equity market -20%", "equity": -0.20},
    "equity_-30": {"label": "Equity market -30%", "equity": -0.30},
    "copper_-25": {"label": "Copper -25%", "factors": {"copper": -0.25}},
    "gold_-20": {"label": "Gold -20%", "factors": {"gold": -0.20}},
    "uranium_-30": {"label": "Uranium -30%", "factors": {"uranium": -0.30}},
    "oil_-40": {"label": "Oil -40%", "factors": {"oil": -0.40}},
    "rates_+200bp": {"label": "Rates +200bp", "factors": {"rates_100bp": 2.0}},
    "cad_+10": {"label": "CAD strengthens 10% vs USD", "fx_usdcad": -0.10},
    "cad_-10": {"label": "CAD weakens 10% vs USD", "fx_usdcad": 0.10},
    "vol_spike": {"label": "Volatility spike (equity -15%, commodities -15%)", "equity": -0.15,
                  "factors": {"copper": -0.15, "gold": -0.05, "oil": -0.15, "uranium": -0.15}},
    "commodity_bust_2008": {"label": "2008-style: equity -40%, copper -50%, oil -60%, CAD -15%", "equity": -0.40,
                            "factors": {"copper": -0.50, "oil": -0.60, "gold": -0.10, "uranium": -0.30},
                            "fx_usdcad": 0.15},
}


@dataclass
class StressPosition:
    symbol: str
    value_base: float                     # current value in base currency (CAD)
    currency: str = "CAD"
    beta_equity: float = 1.0
    factor_betas: dict[str, float] = field(default_factory=dict)  # e.g. {"copper": 1.4}
    sector: str | None = None


def run_stress(positions: list[StressPosition], scenarios: dict[str, dict] | None = None,
               base_currency: str = "CAD", idiosyncratic: dict[str, float] | None = None) -> dict:
    scenarios = scenarios or BUILTIN_SCENARIOS
    total = sum(p.value_base for p in positions)
    out = {}
    for key, sc in scenarios.items():
        rows, pnl = [], 0.0
        for p in positions:
            r = p.beta_equity * sc.get("equity", 0.0)
            for f, shock in sc.get("factors", {}).items():
                r += p.factor_betas.get(f, 0.0) * shock
            r += (idiosyncratic or {}).get(p.symbol, 0.0) + sc.get("idiosyncratic", {}).get(p.symbol, 0.0)
            r = max(r, -1.0)  # long-only: cannot lose more than the position
            if p.currency != base_currency and base_currency == "CAD" and p.currency == "USD":
                r = (1 + r) * (1 + sc.get("fx_usdcad", 0.0)) - 1
            loss = p.value_base * r
            pnl += loss
            rows.append({"symbol": p.symbol, "return": r, "pnl": loss})
        out[key] = {"label": sc.get("label", key), "portfolio_return": pnl / total if total else 0.0,
                    "pnl": pnl, "positions": rows}
    return out


@dataclass
class MineInputs:
    """Single-asset mine model (annual periods). Units must be consistent: e.g. production in lb,
    price and AISC in USD/lb. AISC is assumed to include sustaining capex."""
    annual_production: float
    mine_life_years: int
    commodity_price: float
    aisc: float
    initial_capex: float
    discount_rate: float = 0.08     # industry convention for project NPV is often 5–8% real
    tax_rate: float = 0.27
    royalty_rate: float = 0.0       # NSR royalty, fraction of revenue
    ramp_up: list[float] = field(default_factory=lambda: [1.0])  # production fraction in first years
    construction_delay_years: int = 0
    closure_cost: float = 0.0


def mine_npv(m: MineInputs) -> dict:
    """After-tax project NPV and IRR. Capex at t=0; production starts at t=1+delay. Tax applied to
    positive operating margin only (no depreciation shield modeled — conservative simplification)."""
    import numpy as np
    from scipy.optimize import brentq

    flows = [-m.initial_capex] + [0.0] * m.construction_delay_years
    for y in range(m.mine_life_years):
        frac = m.ramp_up[y] if y < len(m.ramp_up) else 1.0
        prod = m.annual_production * frac
        rev = prod * m.commodity_price
        margin = rev * (1 - m.royalty_rate) - prod * m.aisc
        tax = max(margin, 0.0) * m.tax_rate
        flows.append(margin - tax)
    flows[-1] -= m.closure_cost
    flows = np.array(flows)
    t = np.arange(len(flows))
    npv = float((flows / (1 + m.discount_rate) ** t).sum())
    irr = None
    f = lambda r: float((flows / (1 + r) ** t).sum())  # noqa: E731
    if flows[1:].sum() > -flows[0] and f(-0.99 + 1e-9) * f(5.0) < 0:
        irr = float(brentq(f, -0.99 + 1e-9, 5.0))
    payback = None
    cum = np.cumsum(flows)
    pos = np.where(cum >= 0)[0]
    if len(pos):
        payback = int(pos[0])
    return {"npv": npv, "irr": irr, "payback_year": payback, "cash_flows": flows.tolist()}


def mine_sensitivity(m: MineInputs, price_moves=(-0.3, -0.2, -0.1, 0.0, 0.1, 0.2), cost_moves=(-0.1, 0.0, 0.1, 0.2)) -> dict:
    from dataclasses import replace
    grid = [[mine_npv(replace(m, commodity_price=m.commodity_price * (1 + pm), aisc=m.aisc * (1 + cm)))["npv"]
             for cm in cost_moves] for pm in price_moves]
    shocks = {
        "production_-15%": mine_npv(replace(m, annual_production=m.annual_production * 0.85))["npv"],
        "capex_+30%": mine_npv(replace(m, initial_capex=m.initial_capex * 1.3))["npv"],
        "delay_2y": mine_npv(replace(m, construction_delay_years=m.construction_delay_years + 2))["npv"],
        "base": mine_npv(m)["npv"],
    }
    return {"price_moves": list(price_moves), "cost_moves": list(cost_moves), "npv_grid": grid, "shocks": shocks}
