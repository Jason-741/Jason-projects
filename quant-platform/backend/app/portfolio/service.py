"""Portfolio service: enforces LIVE/PAPER separation, imports, proposals, paper fills."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Account, AccountKind, AuditLog, FxRate, Security, TradeProposal, Transaction
from ..services.market_data import find_security, price_frame
from . import ledger
from .importers import parse_csv
from .risk_limits import DEFAULT_LIMITS, check_trade


class SeparationError(ValueError):
    """Attempt to mix simulated and real-money records."""


def audit(db: Session, action: str, entity: str, entity_id=None, detail=None, user_id=None):
    db.add(AuditLog(action=action, entity=entity, entity_id=str(entity_id) if entity_id is not None else None,
                    detail=detail, user_id=user_id))


def get_account(db: Session, account_id: int) -> Account:
    acct = db.get(Account, account_id)
    if acct is None:
        raise LookupError(f"account {account_id} not found")
    return acct


def add_transaction(db: Session, acct: Account, origin: str, **fields) -> Transaction:
    if acct.kind == AccountKind.LIVE.value and origin == "paper_sim":
        raise SeparationError("simulated fills cannot be written to a LIVE account")
    if acct.kind == AccountKind.PAPER.value and origin in ("csv_import", "reconciliation", "proposal_fill"):
        raise SeparationError("broker imports and real fills cannot be written to a PAPER account")
    tx = Transaction(account_id=acct.id, origin=origin, **fields)
    db.add(tx)
    db.flush()
    return tx


def import_csv(db: Session, acct: Account, text: str, fmt: str | None = None, dry_run: bool = True, user_id=None) -> dict:
    if acct.kind != AccountKind.LIVE.value:
        raise SeparationError("CSV broker imports are only allowed into LIVE accounts")
    res = parse_csv(text, fmt, acct.base_currency)
    existing = set(db.scalars(select(Transaction.external_ref).where(Transaction.account_id == acct.id)))
    new = [r for r in res.rows if r.external_ref not in existing]
    dupes = len(res.rows) - len(new)
    batch = datetime.now(timezone.utc).strftime("imp-%Y%m%dT%H%M%S")
    if not dry_run and new:
        for r in new:
            add_transaction(db, acct, "csv_import", ts=r.ts, tx_type=r.tx_type, symbol=r.symbol, quantity=r.quantity,
                            price=r.price, currency=r.currency, fees=r.fees, fx_rate_to_base=r.fx_rate_to_base,
                            amount=r.amount, counter_currency=r.counter_currency, counter_amount=r.counter_amount,
                            external_ref=r.external_ref, note=r.note, import_batch=batch)
        audit(db, "import_csv", "account", acct.id, {"format": res.format, "rows": len(new), "batch": batch}, user_id)
        db.commit()
    return {"format": res.format, "dry_run": dry_run, "parsed": len(res.rows), "new": len(new), "duplicates": dupes,
            "errors": res.errors, "skipped": res.skipped, "batch": batch if not dry_run else None,
            "preview": [{"date": r.ts.date().isoformat(), "type": r.tx_type, "symbol": r.symbol, "quantity": r.quantity,
                         "price": r.price, "currency": r.currency, "amount": r.amount, "fees": r.fees,
                         "fx_rate_to_base": r.fx_rate_to_base, "note": r.note} for r in new[:200]]}


def latest_price(db: Session, symbol: str) -> tuple[float | None, str | None, str | None]:
    sec = find_security(db, symbol)
    if sec is None:
        return None, None, None
    df = price_frame(db, sec.id, start=(datetime.now(timezone.utc) - timedelta(days=30)).date())
    if df.empty:
        df = price_frame(db, sec.id)
    if df.empty or df["close"].dropna().empty:
        return None, sec.currency, None
    last = df["close"].dropna()
    return float(last.iloc[-1]), sec.currency, str(last.index[-1])


def latest_fx(db: Session, currency: str, base: str) -> float | None:
    if currency == base:
        return 1.0
    row = db.scalars(select(FxRate).where(FxRate.base == currency, FxRate.quote == base).order_by(FxRate.date.desc())).first()
    if row:
        return row.rate
    inv = db.scalars(select(FxRate).where(FxRate.base == base, FxRate.quote == currency).order_by(FxRate.date.desc())).first()
    return 1 / inv.rate if inv and inv.rate else None


def account_snapshot(db: Session, acct: Account, price_overrides: dict[str, float] | None = None) -> dict:
    txs = list(db.scalars(select(Transaction).where(Transaction.account_id == acct.id)))
    st = ledger.build_ledger(txs, acct.base_currency, acct.sim_fx_fee_bps)
    prices, price_dates, fx = {}, {}, {}
    for sym, p in st.positions.items():
        if p.quantity <= 1e-9:
            continue
        px, _, d = latest_price(db, sym)
        if price_overrides and sym in price_overrides:
            px, d = price_overrides[sym], "user-supplied"
        prices[sym], price_dates[sym] = px, d
        fx[p.currency] = latest_fx(db, p.currency, acct.base_currency)
    for cur in st.cash:
        fx.setdefault(cur, latest_fx(db, cur, acct.base_currency))
    v = ledger.valuation(st, prices, fx)
    for row in v["positions"]:
        row["price_date"] = price_dates.get(row["symbol"])
    v.update({"account": {"id": acct.id, "name": acct.name, "kind": acct.kind, "broker": acct.broker,
                          "base_currency": acct.base_currency}, "realized_events": st.realized_events,
              "closed_positions": st.as_dict()["closed_positions"]})
    return v


def _sector_weights(db: Session, snap: dict) -> tuple[dict, dict]:
    weights, sectors = {}, {}
    for r in snap["positions"]:
        w = r.get("weight") or 0.0
        weights[r["symbol"]] = w
        sec = find_security(db, r["symbol"])
        key = (sec.sector if sec else None) or "Unknown"
        sectors[key] = sectors.get(key, 0.0) + w
    return weights, sectors


def avg_dollar_volume(db: Session, symbol: str, days: int = 60) -> float | None:
    sec = find_security(db, symbol)
    if not sec:
        return None
    df = price_frame(db, sec.id).tail(days)
    if df.empty or df["volume"].dropna().empty:
        return None
    return float((df["close"] * df["volume"]).dropna().mean())


def propose_trade(db: Session, acct: Account, *, symbol: str, side: str, quantity: float, est_price: float | None,
                  reason: str, risks: str | None, thesis_entry_id: int | None, exchange: str | None = None,
                  user_id=None) -> TradeProposal:
    if acct.kind != AccountKind.LIVE.value:
        raise SeparationError("trade proposals are for LIVE accounts; use paper orders for PAPER accounts")
    if not reason or len(reason.strip()) < 20:
        raise ValueError("a proposal needs a written reason (>= 20 characters) linking it to evidence")
    sym = symbol.upper()
    px, cur, _ = latest_price(db, sym)
    price = est_price or px
    if price is None:
        raise ValueError(f"no stored price for {sym}; supply est_price")
    sec = find_security(db, sym)
    cur = (sec.currency if sec and sec.currency else cur) or acct.base_currency
    fx = latest_fx(db, cur, acct.base_currency)
    if fx is None:
        raise ValueError(f"no {cur}->{acct.base_currency} FX rate stored; ingest FX (e.g. CAD=X) first")
    gross_base = quantity * price * fx
    fx_fee = gross_base * acct.sim_fx_fee_bps / 1e4 if cur != acct.base_currency else 0.0
    total = gross_base + fx_fee if side == "buy" else gross_base - fx_fee
    snap = account_snapshot(db, acct)
    weights, sectors = _sector_weights(db, snap)
    rc = check_trade(side=side, trade_value_base=total, symbol=sym, sector=sec.sector if sec else None,
                     portfolio_value_base=snap["total_value_base"], cash_base=snap["cash_base"],
                     current_weights=weights, sector_weights=sectors, avg_daily_dollar_volume=avg_dollar_volume(db, sym),
                     limits={**DEFAULT_LIMITS, **(acct.risk_limits or {})}, asset_type=sec.asset_type if sec else "equity")
    rc["cost_breakdown"] = {"gross_base": gross_base, "fx_fee_est_base": fx_fee, "fx_rate": fx, "price_currency": cur}
    prop = TradeProposal(account_id=acct.id, symbol=sym, exchange=exchange or (sec.exchange if sec else None), side=side,
                         quantity=quantity, est_price=price, currency=cur, est_total_cost_base=total,
                         weight_after=rc["weight_after"], thesis_entry_id=thesis_entry_id, reason=reason, risks=risks,
                         risk_check=rc, status="proposed")
    db.add(prop)
    db.flush()
    audit(db, "propose_trade", "trade_proposal", prop.id, {"symbol": sym, "side": side, "qty": quantity,
                                                           "risk_passed": rc["passed"]}, user_id)
    db.commit()
    return prop


def decide_proposal(db: Session, prop: TradeProposal, *, decision: str, note: str | None, executed_price: float | None,
                    executed_quantity: float | None, fees: float = 0.0, fx_rate_to_base: float | None = None,
                    executed_at: datetime | None = None, user_id=None) -> TradeProposal:
    if prop.status != "proposed":
        raise ValueError(f"proposal already {prop.status}")
    if decision not in ("placed", "rejected"):
        raise ValueError("decision must be 'placed' or 'rejected'")
    prop.status, prop.decision_note, prop.decided_at = decision, note, datetime.now(timezone.utc)
    if decision == "placed":
        if not executed_price or not executed_quantity:
            raise ValueError("record the actual executed price and quantity from Wealthsimple")
        acct = get_account(db, prop.account_id)
        tx = add_transaction(db, acct, "proposal_fill", ts=executed_at or datetime.now(timezone.utc), tx_type=prop.side,
                             symbol=prop.symbol, quantity=executed_quantity, price=executed_price, currency=prop.currency,
                             fees=fees, fx_rate_to_base=fx_rate_to_base, amount=executed_quantity * executed_price,
                             external_ref=f"proposal:{prop.id}", note=f"manual execution of proposal {prop.id}")
        prop.executed_price, prop.executed_quantity, prop.executed_tx_id = executed_price, executed_quantity, tx.id
    audit(db, "decide_proposal", "trade_proposal", prop.id, {"decision": decision, "executed_price": executed_price}, user_id)
    db.commit()
    return prop


def paper_order(db: Session, acct: Account, *, symbol: str, side: str, quantity: float, price: float | None = None,
                user_id=None) -> Transaction:
    if acct.kind != AccountKind.PAPER.value:
        raise SeparationError("paper orders can only be placed in PAPER accounts")
    sym = symbol.upper()
    px, cur, d = latest_price(db, sym)
    ref_price = price or px
    if ref_price is None:
        raise ValueError(f"no stored price for {sym}; ingest prices first or pass a reference price")
    sec = find_security(db, sym)
    cur = (sec.currency if sec and sec.currency else cur) or acct.base_currency
    slip = acct.sim_slippage_bps / 1e4
    fill = ref_price * (1 + slip) if side == "buy" else ref_price * (1 - slip)
    fx = latest_fx(db, cur, acct.base_currency)
    if cur != acct.base_currency and fx is None:
        raise ValueError(f"no FX rate {cur}->{acct.base_currency} stored")
    fx_fee = quantity * fill * acct.sim_fx_fee_bps / 1e4 if cur != acct.base_currency else 0.0
    fees = acct.sim_commission + fx_fee
    snap = account_snapshot(db, acct)
    if side == "buy":
        need = quantity * fill + fees
        avail = snap["cash_by_currency"].get(cur, 0.0)
        if need > avail + 1e-9:
            raise ValueError(f"insufficient simulated {cur} cash: need {need:.2f}, have {avail:.2f} "
                             "(record a simulated FX conversion or deposit first)")
    else:
        held = next((p["quantity"] for p in snap["positions"] if p["symbol"] == sym), 0.0)
        if quantity > held + 1e-9:
            raise ValueError(f"cannot sell {quantity} {sym}; simulated holding is {held}")
    tx = add_transaction(db, acct, "paper_sim", ts=datetime.now(timezone.utc), tx_type=side, symbol=sym, quantity=quantity,
                         price=fill, currency=cur, fees=fees, fx_rate_to_base=fx, amount=quantity * fill,
                         note=f"simulated fill: ref {ref_price:.4f} ({d or 'user price'}), slippage {acct.sim_slippage_bps}bps, "
                              f"fx fee {fx_fee:.4f}")
    audit(db, "paper_order", "account", acct.id, {"symbol": sym, "side": side, "qty": quantity, "fill": fill}, user_id)
    db.commit()
    return tx


def ensure_unique_name(db: Session, name: str):
    if db.scalar(select(Account).where(Account.name == name)):
        raise ValueError(f"account '{name}' exists")


__all__ = ["SeparationError", "import_csv", "account_snapshot", "propose_trade", "decide_proposal", "paper_order",
           "add_transaction", "get_account", "audit", "IntegrityError", "Security"]
