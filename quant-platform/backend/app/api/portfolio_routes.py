from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Account, AccountKind, JournalEntry, Strategy, TradeProposal, Transaction, User
from ..portfolio import service as P
from ..portfolio.importers import GENERIC_TEMPLATE, VALID_TYPES
from ..portfolio.risk_limits import DEFAULT_LIMITS
from ..research import readiness
from ..security.auth import current_user
from .common import jsonable

router = APIRouter(prefix="/api", tags=["portfolio"], dependencies=[Depends(current_user)])


def _acct(db, account_id) -> Account:
    try:
        return P.get_account(db, account_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))


def _wrap(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except P.SeparationError as exc:
        raise HTTPException(409, f"separation rule: {exc}")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    kind: AccountKind
    broker: str | None = None
    base_currency: str = "CAD"
    sim_commission: float = 0.0
    sim_slippage_bps: float = 10.0
    sim_fx_fee_bps: float = 150.0
    risk_limits: dict | None = None


def _acct_dict(a: Account):
    return {"id": a.id, "name": a.name, "kind": a.kind, "broker": a.broker, "base_currency": a.base_currency,
            "sim_commission": a.sim_commission, "sim_slippage_bps": a.sim_slippage_bps, "sim_fx_fee_bps": a.sim_fx_fee_bps,
            "risk_limits": {**DEFAULT_LIMITS, **(a.risk_limits or {})}}


@router.get("/accounts")
def accounts(db: Session = Depends(get_db)):
    return [_acct_dict(a) for a in db.scalars(select(Account).order_by(Account.id))]


@router.post("/accounts")
def create_account(b: AccountIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _wrap(P.ensure_unique_name, db, b.name)
    a = Account(**{**b.model_dump(), "kind": b.kind.value})
    db.add(a)
    db.flush()
    P.audit(db, "create_account", "account", a.id, {"kind": a.kind}, user.id)
    db.commit()
    return _acct_dict(a)


@router.patch("/accounts/{account_id}/risk-limits")
def set_limits(account_id: int, limits: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _acct(db, account_id)
    unknown = set(limits) - set(DEFAULT_LIMITS)
    if unknown:
        raise HTTPException(422, f"unknown limits {sorted(unknown)}")
    if limits.get("max_leverage", 0) != 0:
        raise HTTPException(422, "mandate: leverage must remain 0")
    a.risk_limits = {**(a.risk_limits or {}), **limits}
    P.audit(db, "set_risk_limits", "account", a.id, limits, user.id)
    db.commit()
    return _acct_dict(a)


@router.get("/accounts/{account_id}/snapshot")
def snapshot(account_id: int, db: Session = Depends(get_db)):
    return jsonable(P.account_snapshot(db, _acct(db, account_id)))


def _tx_dict(t: Transaction):
    return {"id": t.id, "ts": t.ts.isoformat(), "type": t.tx_type, "symbol": t.symbol, "quantity": t.quantity, "price": t.price,
            "currency": t.currency, "amount": t.amount, "fees": t.fees, "fx_rate_to_base": t.fx_rate_to_base,
            "counter_currency": t.counter_currency, "counter_amount": t.counter_amount, "origin": t.origin,
            "import_batch": t.import_batch, "note": t.note}


@router.get("/accounts/{account_id}/transactions")
def transactions(account_id: int, db: Session = Depends(get_db)):
    _acct(db, account_id)
    return [_tx_dict(t) for t in db.scalars(select(Transaction).where(Transaction.account_id == account_id).order_by(Transaction.ts))]


class TxIn(BaseModel):
    ts: datetime
    tx_type: str
    symbol: str | None = None
    quantity: float = 0.0
    price: float = 0.0
    currency: str = "CAD"
    amount: float = 0.0
    fees: float = Field(0.0, ge=0)
    fx_rate_to_base: float | None = Field(None, gt=0)
    counter_currency: str | None = None
    counter_amount: float | None = None
    note: str | None = None


@router.post("/accounts/{account_id}/transactions")
def add_tx(account_id: int, b: TxIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _acct(db, account_id)
    if b.tx_type not in VALID_TYPES:
        raise HTTPException(422, f"tx_type must be one of {sorted(VALID_TYPES)}")
    if b.tx_type in ("buy", "sell") and (not b.symbol or b.quantity <= 0 or b.price <= 0):
        raise HTTPException(422, "buy/sell needs symbol, positive quantity and price")
    origin = "manual" if a.kind == AccountKind.LIVE.value else "paper_manual"
    fields = b.model_dump()
    if fields["symbol"]:
        fields["symbol"] = fields["symbol"].upper()
    if b.tx_type in ("buy", "sell"):
        fields["amount"] = b.quantity * b.price
    tx = _wrap(P.add_transaction, db, a, origin, **fields)
    P.audit(db, "add_transaction", "transaction", tx.id, {"account": a.id, "type": b.tx_type}, user.id)
    db.commit()
    return _tx_dict(tx)


@router.post("/accounts/{account_id}/import")
async def import_csv(account_id: int, file: UploadFile = File(...), fmt: str | None = Form(None), dry_run: bool = Form(True),
                     db: Session = Depends(get_db), user: User = Depends(current_user)):
    raw = await file.read()
    if len(raw) > 5_000_000:
        raise HTTPException(413, "file too large (5 MB max)")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "file must be UTF-8 CSV")
    return jsonable(_wrap(P.import_csv, db, _acct(db, account_id), text, fmt, dry_run, user.id))


@router.get("/import/template", response_class=PlainTextResponse)
def template():
    return GENERIC_TEMPLATE


# ---------------------------------------------------------------- proposals & paper orders

class ProposalIn(BaseModel):
    symbol: str
    side: str = Field(pattern="^(buy|sell)$")
    quantity: float = Field(gt=0)
    est_price: float | None = Field(None, gt=0)
    reason: str
    risks: str | None = None
    thesis_entry_id: int | None = None
    exchange: str | None = None


def _prop_dict(p: TradeProposal):
    return {"id": p.id, "account_id": p.account_id, "created_at": p.created_at.isoformat(), "symbol": p.symbol,
            "exchange": p.exchange, "side": p.side, "quantity": p.quantity, "est_price": p.est_price, "currency": p.currency,
            "est_total_cost_base": p.est_total_cost_base, "weight_after": p.weight_after, "thesis_entry_id": p.thesis_entry_id,
            "reason": p.reason, "risks": p.risks, "risk_check": p.risk_check, "status": p.status,
            "decision_note": p.decision_note, "executed_price": p.executed_price, "executed_quantity": p.executed_quantity,
            "execution_instruction": "Review and place this order yourself in Wealthsimple. This platform never executes trades."}


@router.post("/accounts/{account_id}/proposals")
def propose(account_id: int, b: ProposalIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _acct(db, account_id)
    p = _wrap(P.propose_trade, db, a, symbol=b.symbol, side=b.side, quantity=b.quantity, est_price=b.est_price,
              reason=b.reason, risks=b.risks, thesis_entry_id=b.thesis_entry_id, exchange=b.exchange, user_id=user.id)
    return jsonable(_prop_dict(p))


@router.get("/proposals")
def proposals(db: Session = Depends(get_db)):
    return jsonable([_prop_dict(p) for p in db.scalars(select(TradeProposal).order_by(TradeProposal.id.desc()))])


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(placed|rejected)$")
    note: str | None = None
    executed_price: float | None = Field(None, gt=0)
    executed_quantity: float | None = Field(None, gt=0)
    fees: float = Field(0.0, ge=0)
    fx_rate_to_base: float | None = Field(None, gt=0)
    executed_at: datetime | None = None


@router.post("/proposals/{proposal_id}/decision")
def decide(proposal_id: int, b: DecisionIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.get(TradeProposal, proposal_id)
    if not p:
        raise HTTPException(404, "proposal not found")
    p = _wrap(P.decide_proposal, db, p, decision=b.decision, note=b.note, executed_price=b.executed_price,
              executed_quantity=b.executed_quantity, fees=b.fees, fx_rate_to_base=b.fx_rate_to_base,
              executed_at=b.executed_at, user_id=user.id)
    return jsonable(_prop_dict(p))


class PaperOrderIn(BaseModel):
    symbol: str
    side: str = Field(pattern="^(buy|sell)$")
    quantity: float = Field(gt=0)
    price: float | None = Field(None, gt=0)


@router.post("/accounts/{account_id}/paper-orders")
def paper_order(account_id: int, b: PaperOrderIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    tx = _wrap(P.paper_order, db, _acct(db, account_id), symbol=b.symbol, side=b.side, quantity=b.quantity, price=b.price,
               user_id=user.id)
    return _tx_dict(tx)


# ---------------------------------------------------------------- journal

class JournalIn(BaseModel):
    symbol: str
    account_kind: str = Field("live", pattern="^(live|paper)$")
    status: str = Field("research", pattern="^(research|open|closed|abandoned)$")
    analysis_date: date
    thesis: str = Field(min_length=1)
    valuation_low: float | None = None
    valuation_base: float | None = None
    valuation_high: float | None = None
    valuation_assumptions: str | None = None
    catalysts: str | None = None
    risks: str | None = None
    invalidation_conditions: str | None = None
    expected_holding_period: str | None = None
    confidence: int | None = Field(None, ge=1, le=5)
    entry_date: date | None = None
    entry_price: float | None = None
    allocation_pct: float | None = None


class JournalUpdate(BaseModel):
    """Post-entry fields. Original thesis fields are immutable once an entry is open (no hindsight edits)."""
    status: str | None = Field(None, pattern="^(research|open|closed|abandoned)$")
    entry_date: date | None = None
    entry_price: float | None = None
    allocation_pct: float | None = None
    exit_date: date | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    development: str | None = None
    thesis_was_correct: str | None = Field(None, pattern="^(yes|partly|no|unclear)$")
    outcome_attribution: str | None = Field(None, pattern="^(skill|luck|mixed|unclear)$")
    lessons: str | None = None


def _j(e: JournalEntry):
    d = {c.name: getattr(e, c.name) for c in JournalEntry.__table__.columns}
    d = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in d.items()}
    d["readiness"] = readiness.journal_readiness(e)
    return d


@router.get("/journal")
def journal(db: Session = Depends(get_db)):
    return [_j(e) for e in db.scalars(select(JournalEntry).order_by(JournalEntry.id.desc()))]


@router.post("/journal")
def journal_create(b: JournalIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e = JournalEntry(**{**b.model_dump(), "symbol": b.symbol.upper()}, updates=[])
    db.add(e)
    db.flush()
    P.audit(db, "journal_create", "journal", e.id, {"symbol": e.symbol}, user.id)
    db.commit()
    return _j(e)


@router.patch("/journal/{entry_id}")
def journal_update(entry_id: int, b: JournalUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e = db.get(JournalEntry, entry_id)
    if not e:
        raise HTTPException(404, "entry not found")
    data = b.model_dump(exclude_unset=True)
    dev = data.pop("development", None)
    for k, v in data.items():
        setattr(e, k, v)
    if dev:
        e.updates = [*(e.updates or []), {"date": date.today().isoformat(), "note": dev}]
    if e.exit_price and e.entry_price:
        e.realized_return = e.exit_price / e.entry_price - 1
    e.updated_at = datetime.now(timezone.utc)
    P.audit(db, "journal_update", "journal", e.id, data | ({"development": dev} if dev else {}), user.id)
    db.commit()
    return _j(e)


# ---------------------------------------------------------------- strategies / readiness

class StrategyIn(BaseModel):
    name: str
    hypothesis: str = Field(min_length=20)
    kind: str = "quant"
    params: dict | None = None


class ChecklistItem(BaseModel):
    key: str
    done: bool
    evidence: str | None = None


def _s(s: Strategy):
    return {"id": s.id, "name": s.name, "hypothesis": s.hypothesis, "kind": s.kind, "params": s.params,
            "readiness": readiness.evaluate({**(s.checklist or {}), "hypothesis": {"done": bool(s.hypothesis), "evidence": "strategy.hypothesis"}})}


@router.get("/strategies")
def strategies(db: Session = Depends(get_db)):
    return [_s(s) for s in db.scalars(select(Strategy))]


@router.post("/strategies")
def strategy_create(b: StrategyIn, db: Session = Depends(get_db)):
    s = Strategy(**b.model_dump(), checklist={})
    db.add(s)
    db.commit()
    return _s(s)


@router.post("/strategies/{sid}/checklist")
def strategy_check(sid: int, item: ChecklistItem, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = db.get(Strategy, sid)
    if not s:
        raise HTTPException(404, "strategy not found")
    keys = {k for k, _ in readiness.QUANT_ITEMS}
    if item.key not in keys:
        raise HTTPException(422, f"key must be one of {sorted(keys)}")
    s.checklist = {**(s.checklist or {}), item.key: {"done": item.done, "evidence": item.evidence,
                                                    "at": datetime.now(timezone.utc).isoformat()}}
    P.audit(db, "readiness_update", "strategy", s.id, item.model_dump(), user.id)
    db.commit()
    return _s(s)
