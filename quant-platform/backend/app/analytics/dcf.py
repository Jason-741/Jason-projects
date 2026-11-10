"""Discounted-cash-flow valuation (unlevered free cash flow to the firm).

Methodology
-----------
For forecast year t = 1..N:
    revenue_t = revenue_{t-1} * (1 + g_t)
    EBIT_t    = revenue_t * ebit_margin_t
    NOPAT_t   = EBIT_t * (1 - tax_rate)
    FCFF_t    = NOPAT_t + D&A_t - capex_t - ΔNWC_t
                with D&A_t = da_pct * revenue_t, capex_t = capex_pct * revenue_t,
                ΔNWC_t = nwc_pct * (revenue_t - revenue_{t-1})
    PV_t      = FCFF_t / (1 + WACC)^(t - 0.5 if mid_year else t)
Terminal value at N (Gordon growth): TV = FCFF_{N} * (1 + g_T) / (WACC - g_T), requires g_T < WACC.
  or exit multiple: TV = EV/EBITDA multiple * EBITDA_N.
EV = ΣPV_t + TV / (1+WACC)^N ; Equity = EV - net_debt ; value/share = Equity / diluted shares.

Assumptions & limitations
-------------------------
* Every input is an ASSUMPTION supplied by the analyst; the output is an estimate conditional on
  them, never an objectively known price. Terminal value typically dominates EV — the result
  reports TV share so this is visible.
* Not appropriate for banks/insurers (use P/B, ROE-based residual income), early-stage miners
  without cash flow (use project NPV / P/NAV), or companies with negative long-run FCF.
* Ignores minority interests, preferred equity, leases, pensions and options unless the user
  folds them into net_debt / diluted shares.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace

import numpy as np
from scipy.optimize import brentq


def capm_cost_of_equity(risk_free: float, beta: float, equity_risk_premium: float, size_premium: float = 0.0) -> float:
    return risk_free + beta * equity_risk_premium + size_premium


def wacc(equity_value: float, debt_value: float, cost_of_equity: float, pre_tax_cost_of_debt: float, tax_rate: float) -> float:
    total = equity_value + debt_value
    if total <= 0:
        raise ValueError("equity + debt must be positive")
    return equity_value / total * cost_of_equity + debt_value / total * pre_tax_cost_of_debt * (1 - tax_rate)


@dataclass
class DCFInputs:
    base_revenue: float
    revenue_growth: list[float]          # per forecast year
    ebit_margin: list[float] | float
    tax_rate: float
    wacc: float
    net_debt: float
    diluted_shares: float
    da_pct_revenue: float = 0.0
    capex_pct_revenue: float = 0.0
    nwc_pct_revenue: float = 0.0
    terminal_method: str = "gordon"      # gordon|exit_multiple
    terminal_growth: float = 0.02
    exit_ev_ebitda: float | None = None
    mid_year: bool = True

    def margins(self) -> list[float]:
        n = len(self.revenue_growth)
        if isinstance(self.ebit_margin, (int, float)):
            return [float(self.ebit_margin)] * n
        if len(self.ebit_margin) != n:
            raise ValueError("ebit_margin length must match revenue_growth")
        return list(self.ebit_margin)


@dataclass
class DCFResult:
    enterprise_value: float
    equity_value: float
    value_per_share: float
    pv_forecast: float
    pv_terminal: float
    terminal_value: float
    terminal_share_of_ev: float
    years: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


def run_dcf(inp: DCFInputs) -> DCFResult:
    if inp.diluted_shares <= 0:
        raise ValueError("diluted_shares must be positive")
    if inp.wacc <= 0:
        raise ValueError("wacc must be positive")
    if not inp.revenue_growth:
        raise ValueError("need at least one forecast year")
    warnings = []
    margins = inp.margins()
    rev_prev = inp.base_revenue
    years, pv_sum = [], 0.0
    for t, (g, mgn) in enumerate(zip(inp.revenue_growth, margins), start=1):
        rev = rev_prev * (1 + g)
        ebit = rev * mgn
        nopat = ebit * (1 - inp.tax_rate)
        da = inp.da_pct_revenue * rev
        capex = inp.capex_pct_revenue * rev
        dnwc = inp.nwc_pct_revenue * (rev - rev_prev)
        fcff = nopat + da - capex - dnwc
        exponent = t - 0.5 if inp.mid_year else t
        df = 1 / (1 + inp.wacc) ** exponent
        pv = fcff * df
        pv_sum += pv
        years.append({"year": t, "revenue": rev, "growth": g, "ebit": ebit, "ebit_margin": mgn, "nopat": nopat,
                      "d_and_a": da, "capex": capex, "delta_nwc": dnwc, "fcff": fcff, "discount_factor": df, "pv_fcff": pv,
                      "ebitda": ebit + da})
        rev_prev = rev
    n = len(years)
    last = years[-1]
    if inp.terminal_method == "gordon":
        if inp.terminal_growth >= inp.wacc:
            raise ValueError("terminal_growth must be below WACC for the Gordon growth model")
        if inp.terminal_growth > 0.04:
            warnings.append("terminal growth above ~4% exceeds plausible long-run nominal GDP growth")
        tv = last["fcff"] * (1 + inp.terminal_growth) / (inp.wacc - inp.terminal_growth)
    elif inp.terminal_method == "exit_multiple":
        if not inp.exit_ev_ebitda:
            raise ValueError("exit_ev_ebitda required for exit_multiple terminal method")
        tv = inp.exit_ev_ebitda * last["ebitda"]
        warnings.append("exit-multiple terminal value embeds today's market pricing into the 'intrinsic' estimate")
    else:
        raise ValueError("terminal_method must be 'gordon' or 'exit_multiple'")
    pv_tv = tv / (1 + inp.wacc) ** n
    ev = pv_sum + pv_tv
    equity = ev - inp.net_debt
    share = pv_tv / ev if ev else float("nan")
    if ev > 0 and share > 0.75:
        warnings.append(f"terminal value is {share:.0%} of EV — result is highly sensitive to long-run assumptions")
    if last["fcff"] < 0:
        warnings.append("final-year FCFF is negative; Gordon terminal value is negative / not meaningful")
    if equity < 0:
        warnings.append("estimated equity value is negative")
    return DCFResult(ev, equity, equity / inp.diluted_shares, pv_sum, pv_tv, tv, share, years, warnings)


def sensitivity(inp: DCFInputs, waccs: list[float], growths: list[float]) -> dict:
    """Value per share across a WACC × terminal-growth grid (Gordon method). Cells where g >= WACC are None."""
    grid = []
    for w in waccs:
        row = []
        for g in growths:
            if g >= w:
                row.append(None)
                continue
            row.append(run_dcf(replace(inp, wacc=w, terminal_growth=g, terminal_method="gordon")).value_per_share)
        grid.append(row)
    return {"waccs": waccs, "terminal_growths": growths, "value_per_share": grid}


def scenarios(base: DCFInputs, overrides: dict[str, dict]) -> dict[str, dict]:
    """Run named scenarios, e.g. {"bear": {...}, "base": {}, "bull": {...}} of DCFInputs field overrides."""
    out = {}
    for name, ov in overrides.items():
        r = run_dcf(replace(base, **ov))
        out[name] = {"value_per_share": r.value_per_share, "enterprise_value": r.enterprise_value,
                     "terminal_share_of_ev": r.terminal_share_of_ev, "warnings": r.warnings, "overrides": ov}
    return out


def reverse_dcf(inp: DCFInputs, market_price: float, lo: float = -0.5, hi: float = 1.0) -> dict:
    """Solve for the constant annual revenue growth that makes value/share equal the market price,
    holding margins, reinvestment, WACC and terminal assumptions fixed.

    Answers "what growth is the market already pricing in?" under THESE other assumptions only.
    """
    n = len(inp.revenue_growth)

    def f(g):
        return run_dcf(replace(inp, revenue_growth=[g] * n)).value_per_share - market_price

    flo, fhi = f(lo), f(hi)
    if np.sign(flo) == np.sign(fhi):
        return {"implied_growth": None, "note": "no growth rate in search range reproduces the market price "
                "under these margin/WACC assumptions (margin or WACC assumptions likely inconsistent with price)"}
    g = brentq(f, lo, hi, xtol=1e-7)
    return {"implied_growth": g, "years": n, "note": "implied constant revenue CAGR conditional on all other inputs"}


def margin_of_safety(intrinsic: float, price: float) -> float:
    """(intrinsic - price) / intrinsic. Positive = price below estimate."""
    if intrinsic <= 0:
        return float("nan")
    return (intrinsic - price) / intrinsic
