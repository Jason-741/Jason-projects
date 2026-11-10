"""Financial-statement analytics.

Every ratio returns a `Metric` carrying the value AND the inputs used, or None with the reason
it could not be computed. Missing data is never imputed. Definitions are in docs/METHODOLOGY.md.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Metric:
    name: str
    value: float | None
    formula: str
    inputs: dict = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    note: str | None = None

    def as_dict(self):
        return asdict(self)


def _get(d: dict, k: str):
    v = d.get(k)
    return None if v is None else float(v)


def _ratio(name, formula, num_key, den_key, d, *, num=None, den=None, inputs=None, positive_den=True, note=None):
    n = num if num is not None else _get(d, num_key)
    dd = den if den is not None else _get(d, den_key)
    inputs = inputs or {num_key: n, den_key: dd}
    missing = [k for k, v in inputs.items() if v is None]
    if missing:
        return Metric(name, None, formula, inputs, missing, note)
    if dd == 0 or (positive_den and dd < 0):
        return Metric(name, None, formula, inputs, [], "denominator is zero or negative; ratio not meaningful")
    return Metric(name, n / dd, formula, inputs, [], note)


def derived_items(s: dict) -> dict:
    """Derive EBITDA, total debt, net debt, FCF, working capital, gross profit when inputs exist."""
    out = dict(s)
    g = lambda k: _get(s, k)  # noqa: E731
    if g("gross_profit") is None and g("revenue") is not None and g("cost_of_revenue") is not None:
        out["gross_profit"] = g("revenue") - g("cost_of_revenue")
    if g("operating_income") is not None and g("d_and_a") is not None:
        out["ebitda"] = g("operating_income") + g("d_and_a")
    ltd, std = g("long_term_debt"), g("short_term_debt")
    if ltd is not None or std is not None:
        out["total_debt"] = (ltd or 0.0) + (std or 0.0)
    if out.get("total_debt") is not None and g("cash") is not None:
        out["net_debt"] = out["total_debt"] - g("cash")
    if g("operating_cash_flow") is not None and g("capex") is not None:
        out["free_cash_flow"] = g("operating_cash_flow") - abs(g("capex"))
    if g("current_assets") is not None and g("current_liabilities") is not None:
        out["working_capital"] = g("current_assets") - g("current_liabilities")
    return out


def statement_ratios(s: dict, prior: dict | None = None) -> dict[str, Metric]:
    """Profitability, leverage, liquidity and cash-flow ratios from one fiscal period."""
    d = derived_items(s)
    m: dict[str, Metric] = {}
    m["gross_margin"] = _ratio("gross_margin", "gross_profit / revenue", "gross_profit", "revenue", d)
    m["ebitda_margin"] = _ratio("ebitda_margin", "(operating_income + D&A) / revenue", "ebitda", "revenue", d)
    m["operating_margin"] = _ratio("operating_margin", "operating_income / revenue", "operating_income", "revenue", d)
    m["net_margin"] = _ratio("net_margin", "net_income / revenue", "net_income", "revenue", d)
    m["fcf_margin"] = _ratio("fcf_margin", "(CFO - capex) / revenue", "free_cash_flow", "revenue", d)
    m["cash_conversion"] = _ratio("cash_conversion", "CFO / net_income", "operating_cash_flow", "net_income", d,
                                  note="only meaningful when net income is positive")
    m["current_ratio"] = _ratio("current_ratio", "current_assets / current_liabilities", "current_assets", "current_liabilities", d)
    ca, inv, cl = _get(d, "current_assets"), _get(d, "inventory"), _get(d, "current_liabilities")
    m["quick_ratio"] = _ratio("quick_ratio", "(current_assets - inventory) / current_liabilities", "", "", d,
                              num=None if ca is None or inv is None else ca - inv, den=cl,
                              inputs={"current_assets": ca, "inventory": inv, "current_liabilities": cl})
    m["debt_to_equity"] = _ratio("debt_to_equity", "total_debt / equity", "total_debt", "equity", d,
                                 note="negative equity makes this ratio undefined")
    m["debt_to_ebitda"] = _ratio("debt_to_ebitda", "total_debt / EBITDA", "total_debt", "ebitda", d)
    m["net_debt_to_ebitda"] = _ratio("net_debt_to_ebitda", "net_debt / EBITDA", "net_debt", "ebitda", d)
    m["interest_coverage"] = _ratio("interest_coverage", "operating_income / interest_expense", "operating_income",
                                    "interest_expense", d)
    m["roa"] = _avg_ratio("roa", "net_income / avg(total_assets)", "net_income", "total_assets", d, prior)
    m["roe"] = _avg_ratio("roe", "net_income / avg(equity)", "net_income", "equity", d, prior)
    # ROIC = NOPAT / invested capital; NOPAT uses the effective tax rate when computable (clamped 0..50%)
    oi, pre, tax = _get(d, "operating_income"), _get(d, "pretax_income"), _get(d, "income_tax")
    rate = None
    if pre and tax is not None and pre > 0:
        rate = min(max(tax / pre, 0.0), 0.5)
    eq, debt, cash = _get(d, "equity"), d.get("total_debt"), _get(d, "cash")
    ic = None if eq is None or debt is None or cash is None else eq + debt - cash
    m["roic"] = _ratio("roic", "operating_income*(1-tax_rate) / (equity + total_debt - cash)", "", "", d,
                       num=None if oi is None or rate is None else oi * (1 - rate), den=ic,
                       inputs={"operating_income": oi, "effective_tax_rate": rate, "invested_capital": ic})
    divs = _get(d, "dividends_paid")
    if divs:
        m["dividend_coverage"] = _ratio("dividend_coverage", "free_cash_flow / dividends_paid", "", "", d,
                                        num=d.get("free_cash_flow"), den=abs(divs),
                                        inputs={"free_cash_flow": d.get("free_cash_flow"), "dividends_paid": abs(divs)})
    if prior:
        for k in ("revenue", "ebitda", "net_income", "eps_diluted", "free_cash_flow"):
            cur, prev = d.get(k), derived_items(prior).get(k)
            name = f"{k}_growth"
            if cur is None or prev is None:
                m[name] = Metric(name, None, f"{k}_t / {k}_t-1 - 1", {"current": cur, "prior": prev},
                                 [x for x, v in (("current", cur), ("prior", prev)) if v is None])
            elif prev <= 0:
                m[name] = Metric(name, None, f"{k}_t / {k}_t-1 - 1", {"current": cur, "prior": prev}, [],
                                 "prior value <= 0; growth rate not meaningful")
            else:
                m[name] = Metric(name, cur / prev - 1, f"{k}_t / {k}_t-1 - 1", {"current": cur, "prior": prev})
    return m


def _avg_ratio(name, formula, num_key, den_key, d, prior):
    cur = _get(d, den_key)
    prev = _get(prior, den_key) if prior else None
    den = (cur + prev) / 2 if cur is not None and prev is not None else cur
    note = None if prev is not None else f"prior {den_key} unavailable; used period-end value"
    return _ratio(name, formula, num_key, den_key, d, den=den, inputs={num_key: _get(d, num_key), den_key: den}, note=note)


def valuation_multiples(price: float, shares: float | None, s: dict, ttm: dict | None = None,
                        eps_growth_pct: float | None = None) -> dict[str, Metric]:
    """Market multiples. `s` is the latest annual (or TTM if `ttm` given) statement dict."""
    d = derived_items(ttm or s)
    mcap = price * shares if shares else None
    ev = None
    if mcap is not None and d.get("net_debt") is not None:
        ev = mcap + d["net_debt"]
    m: dict[str, Metric] = {
        "market_cap": Metric("market_cap", mcap, "price * shares_outstanding", {"price": price, "shares": shares},
                             [] if shares else ["shares"]),
        "enterprise_value": Metric("enterprise_value", ev, "market_cap + total_debt - cash",
                                   {"market_cap": mcap, "net_debt": d.get("net_debt")},
                                   [k for k, v in (("market_cap", mcap), ("net_debt", d.get("net_debt"))) if v is None],
                                   note="excludes minority interest, preferreds and leases (not captured)"),
    }
    eps = _get(d, "eps_diluted")
    m["pe"] = _ratio("pe", "price / diluted EPS", "", "", d, num=price, den=eps, inputs={"price": price, "eps_diluted": eps},
                     note="negative earnings → P/E undefined")
    m["ev_ebitda"] = _ratio("ev_ebitda", "EV / EBITDA", "", "", d, num=ev, den=d.get("ebitda"),
                            inputs={"enterprise_value": ev, "ebitda": d.get("ebitda")})
    m["ev_revenue"] = _ratio("ev_revenue", "EV / revenue", "", "", d, num=ev, den=_get(d, "revenue"),
                             inputs={"enterprise_value": ev, "revenue": _get(d, "revenue")})
    m["pb"] = _ratio("pb", "market_cap / equity", "", "", d, num=mcap, den=_get(d, "equity"),
                     inputs={"market_cap": mcap, "equity": _get(d, "equity")})
    m["ps"] = _ratio("ps", "market_cap / revenue", "", "", d, num=mcap, den=_get(d, "revenue"),
                     inputs={"market_cap": mcap, "revenue": _get(d, "revenue")})
    fcf = d.get("free_cash_flow")
    m["fcf_yield"] = Metric("fcf_yield", fcf / mcap if fcf is not None and mcap else None, "free_cash_flow / market_cap",
                            {"free_cash_flow": fcf, "market_cap": mcap},
                            [k for k, v in (("free_cash_flow", fcf), ("market_cap", mcap)) if v is None])
    pe = m["pe"].value
    if pe is not None and eps_growth_pct is not None and eps_growth_pct > 0:
        m["peg"] = Metric("peg", pe / eps_growth_pct, "P/E / EPS growth (%)", {"pe": pe, "eps_growth_pct": eps_growth_pct},
                          note="growth input is an assumption/estimate, not a fact")
    else:
        m["peg"] = Metric("peg", None, "P/E / EPS growth (%)", {"pe": pe, "eps_growth_pct": eps_growth_pct},
                          [k for k, v in (("pe", pe), ("eps_growth_pct", eps_growth_pct)) if v is None],
                          note="requires positive P/E and positive growth estimate")
    return m


def flag_changes(series: dict[str, list[float | None]], threshold: float = 0.25) -> list[dict]:
    """Flag year-over-year changes in key items larger than `threshold` (relative) for analyst review."""
    flags = []
    for k, vals in series.items():
        for i in range(1, len(vals)):
            a, b = vals[i - 1], vals[i]
            if a is None or b is None or a == 0:
                continue
            ch = (b - a) / abs(a)
            if abs(ch) >= threshold:
                flags.append({"item": k, "index": i, "from": a, "to": b, "change": ch})
    return flags
