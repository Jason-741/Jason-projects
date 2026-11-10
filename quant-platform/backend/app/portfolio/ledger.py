"""Position & cash ledger with Canadian adjusted-cost-base (ACB) accounting.

* ACB (CRA method): total cost of identical property, in CAD, including commissions, converted at
  the exchange rate on each transaction date. Selling reduces ACB pro-rata; gains = proceeds (CAD,
  net of fees) - ACB of shares sold. (Superficial-loss rules are NOT applied — flagged in docs.)
* Cash is tracked per currency. FX conversions move cash between currencies.
* Gross vs net: gross P/L excludes commissions and FX conversion costs; net includes them.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field

from ..models import Transaction, TxType


@dataclass
class Position:
    symbol: str
    currency: str
    quantity: float = 0.0
    acb_base: float = 0.0             # total ACB in base currency
    cost_native: float = 0.0          # total cost in trading currency (avg-cost basis)
    realized_pnl_base: float = 0.0
    dividends_base: float = 0.0
    fees_base: float = 0.0
    acb_complete: bool = True         # False if any tx lacked an FX rate
    first_buy: str | None = None

    @property
    def avg_cost_native(self) -> float | None:
        return self.cost_native / self.quantity if self.quantity > 1e-12 else None

    @property
    def acb_per_share_base(self) -> float | None:
        return self.acb_base / self.quantity if self.quantity > 1e-12 else None


@dataclass
class LedgerState:
    base_currency: str
    cash: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    positions: dict[str, Position] = field(default_factory=dict)
    contributions_base: float = 0.0
    withdrawals_base: float = 0.0
    fees_base: float = 0.0
    fx_costs_base_est: float = 0.0
    interest_base: float = 0.0
    realized_events: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self):
        return {"base_currency": self.base_currency, "cash": dict(self.cash),
                "positions": {k: {**asdict(v), "avg_cost_native": v.avg_cost_native, "acb_per_share_base": v.acb_per_share_base}
                              for k, v in self.positions.items() if v.quantity > 1e-9},
                "closed_positions": {k: asdict(v) for k, v in self.positions.items() if v.quantity <= 1e-9},
                "contributions_base": self.contributions_base, "withdrawals_base": self.withdrawals_base,
                "fees_base": self.fees_base, "fx_costs_base_est": self.fx_costs_base_est, "interest_base": self.interest_base,
                "realized_pnl_base": sum(p.realized_pnl_base for p in self.positions.values()),
                "dividends_base": sum(p.dividends_base for p in self.positions.values()),
                "realized_events": self.realized_events, "warnings": self.warnings}


def _rate(tx: Transaction, base: str, st: LedgerState) -> float:
    if tx.currency == base:
        return 1.0
    if tx.fx_rate_to_base:
        return tx.fx_rate_to_base
    st.warnings.append(f"tx {tx.id or tx.external_ref}: no FX rate for {tx.currency}; ACB in {base} incomplete (rate=1 used)")
    return float("nan")


class _Norm:
    """Read-only view of a Transaction with None numeric fields treated as 0 (unflushed ORM objects)."""

    def __init__(self, tx):
        self._tx = tx

    def __getattr__(self, k):
        v = getattr(self._tx, k)
        if v is None and k in ("quantity", "price", "amount", "fees"):
            return 0.0
        if v is None and k == "currency":
            return "CAD"
        return v


def build_ledger(transactions: list[Transaction], base_currency: str = "CAD", fx_fee_bps_est: float = 150.0) -> LedgerState:
    st = LedgerState(base_currency)
    for tx in sorted(transactions, key=lambda t: (t.ts, t.id or 0)):
        tx = _Norm(tx)
        t = tx.tx_type
        rate = _rate(tx, base_currency, st)
        known = rate == rate  # not NaN
        r = rate if known else 1.0
        if t in (TxType.BUY.value, TxType.SELL.value, TxType.DIVIDEND.value, TxType.SPLIT.value) and not tx.symbol:
            st.warnings.append(f"tx {tx.id}: {t} without symbol ignored")
            continue
        if t in (TxType.BUY.value, TxType.SELL.value, TxType.DIVIDEND.value, TxType.SPLIT.value):
            pos = st.positions.setdefault(tx.symbol, Position(tx.symbol, tx.currency))
        if t == TxType.BUY.value:
            gross = tx.quantity * tx.price
            st.cash[tx.currency] -= gross + tx.fees
            pos.quantity += tx.quantity
            pos.cost_native += gross + tx.fees
            pos.acb_base += (gross + tx.fees) * r
            pos.fees_base += tx.fees * r
            pos.acb_complete &= known
            pos.first_buy = pos.first_buy or tx.ts.date().isoformat()
            st.fees_base += tx.fees * r
        elif t == TxType.SELL.value:
            if tx.quantity > pos.quantity + 1e-9:
                st.warnings.append(f"{tx.symbol}: sell of {tx.quantity} exceeds held {pos.quantity} on {tx.ts.date()} "
                                   "(missing history or short sale) — clipped")
            qty = min(tx.quantity, pos.quantity)
            proceeds = qty * tx.price - tx.fees
            st.cash[tx.currency] += tx.quantity * tx.price - tx.fees
            frac = qty / pos.quantity if pos.quantity > 0 else 0.0
            acb_sold, cost_sold = pos.acb_base * frac, pos.cost_native * frac
            gain = proceeds * r - acb_sold
            pos.realized_pnl_base += gain
            pos.acb_base -= acb_sold
            pos.cost_native -= cost_sold
            pos.quantity -= qty
            pos.fees_base += tx.fees * r
            st.fees_base += tx.fees * r
            st.realized_events.append({"date": tx.ts.date().isoformat(), "symbol": tx.symbol, "quantity": qty,
                                       "proceeds_base": proceeds * r, "acb_sold_base": acb_sold, "gain_base": gain,
                                       "acb_complete": pos.acb_complete and known})
            if pos.quantity <= 1e-9:
                pos.quantity, pos.acb_base, pos.cost_native = 0.0, 0.0, 0.0
        elif t == TxType.DIVIDEND.value:
            st.cash[tx.currency] += tx.amount - tx.fees   # fees field carries withholding tax if any
            pos.dividends_base += (tx.amount - tx.fees) * r
        elif t == TxType.SPLIT.value:
            pos.quantity *= tx.quantity                     # ratio; ACB total unchanged
        elif t == TxType.DEPOSIT.value:
            st.cash[tx.currency] += tx.amount
            st.contributions_base += tx.amount * r
        elif t == TxType.WITHDRAWAL.value:
            st.cash[tx.currency] -= tx.amount
            st.withdrawals_base += tx.amount * r
        elif t == TxType.FEE.value:
            st.cash[tx.currency] -= tx.amount
            st.fees_base += tx.amount * r
        elif t == TxType.INTEREST.value:
            st.cash[tx.currency] += tx.amount
            st.interest_base += tx.amount * r
        elif t == TxType.FX.value:
            if not tx.counter_currency or tx.counter_amount is None:
                st.warnings.append(f"tx {tx.id}: FX conversion missing counter currency/amount — ignored")
                continue
            st.cash[tx.currency] -= tx.amount
            st.cash[tx.counter_currency] += tx.counter_amount
            st.fx_costs_base_est += tx.amount * r * fx_fee_bps_est / 1e4
        else:
            st.warnings.append(f"tx {tx.id}: unknown type {t}")
    return st


def valuation(st: LedgerState, prices: dict[str, float | None], fx_to_base: dict[str, float | None]) -> dict:
    """Mark positions to market. `prices` in each position's currency; `fx_to_base` gives base per 1 unit."""
    rows, mv_total, missing = [], 0.0, []
    for sym, p in st.positions.items():
        if p.quantity <= 1e-9:
            continue
        px = prices.get(sym)
        fx = 1.0 if p.currency == st.base_currency else fx_to_base.get(p.currency)
        if px is None or fx is None:
            missing.append(sym)
            rows.append({"symbol": sym, "quantity": p.quantity, "currency": p.currency, "price": px, "market_value_base": None,
                         "acb_base": p.acb_base, "unrealized_pnl_base": None, "note": "price or FX rate unavailable"})
            continue
        mv = p.quantity * px * fx
        mv_total += mv
        rows.append({"symbol": sym, "quantity": p.quantity, "currency": p.currency, "price": px, "fx_to_base": fx,
                     "market_value_base": mv, "acb_base": p.acb_base, "unrealized_pnl_base": mv - p.acb_base,
                     "unrealized_pct": (mv / p.acb_base - 1) if p.acb_base else None,
                     "avg_cost_native": p.avg_cost_native, "acb_complete": p.acb_complete})
    cash_base, cash_missing = 0.0, []
    for cur, amt in st.cash.items():
        fx = 1.0 if cur == st.base_currency else fx_to_base.get(cur)
        if fx is None:
            cash_missing.append(cur)
        else:
            cash_base += amt * fx
    total = mv_total + cash_base
    for r in rows:
        r["weight"] = r["market_value_base"] / total if r["market_value_base"] is not None and total > 0 else None
    net_contrib = st.contributions_base - st.withdrawals_base
    d = st.as_dict()
    realized, divs = d["realized_pnl_base"], d["dividends_base"]
    unreal = sum(r["unrealized_pnl_base"] for r in rows if r["unrealized_pnl_base"] is not None)
    net_pnl = total - net_contrib if net_contrib else None
    return {
        "positions": rows, "cash_by_currency": dict(st.cash), "cash_base": cash_base, "market_value_base": mv_total,
        "total_value_base": total, "net_contributions_base": net_contrib,
        "pnl": {"realized_base": realized, "unrealized_base": unreal, "dividends_base": divs, "interest_base": st.interest_base,
                "fees_base": st.fees_base, "fx_costs_base_est": st.fx_costs_base_est,
                "net_pnl_base": net_pnl,
                "gross_pnl_base": (net_pnl + st.fees_base + st.fx_costs_base_est) if net_pnl is not None else None,
                "simple_return_on_contributions": (net_pnl / net_contrib) if net_pnl is not None and net_contrib > 0 else None},
        "missing_prices": missing, "missing_fx": cash_missing, "warnings": st.warnings,
        "notes": ["simple return on contributions is not time-weighted; it ignores the timing of deposits",
                  "FX conversion costs are estimated from the configured fee rate unless reported by the broker",
                  "ACB excludes superficial-loss adjustments; confirm tax figures with your broker's T5008/statements"],
    }
