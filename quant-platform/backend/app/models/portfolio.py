"""Brokerage/portfolio records.

LIVE and PAPER accounts are strictly separated: the service layer refuses to write simulated
fills into LIVE accounts and refuses manual/broker imports into PAPER accounts, and holdings
are always computed per account (never aggregated across kinds).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .provenance import utcnow


class AccountKind(str, Enum):
    LIVE = "live"
    PAPER = "paper"


class TxType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    FEE = "fee"
    INTEREST = "interest"
    SPLIT = "split"            # quantity = split ratio (new shares per old share)
    FX = "fx"                  # currency conversion: amount in `currency`, counter amount in note/meta


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    kind: Mapped[str] = mapped_column(String(8))           # AccountKind
    broker: Mapped[str | None] = mapped_column(String(64), nullable=True)  # e.g. "Wealthsimple"
    base_currency: Mapped[str] = mapped_column(String(8), default="CAD")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Paper accounts only: simulation assumptions
    sim_commission: Mapped[float] = mapped_column(Float, default=0.0)
    sim_slippage_bps: Mapped[float] = mapped_column(Float, default=10.0)
    sim_fx_fee_bps: Mapped[float] = mapped_column(Float, default=150.0)
    risk_limits: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("account_id", "external_ref"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    tx_type: Mapped[str] = mapped_column(String(16))
    symbol: Mapped[str | None] = mapped_column(String(24), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    price: Mapped[float] = mapped_column(Float, default=0.0)        # per share, in `currency`
    currency: Mapped[str] = mapped_column(String(8), default="CAD")
    amount: Mapped[float] = mapped_column(Float, default=0.0)       # signed cash impact in `currency`
    fees: Mapped[float] = mapped_column(Float, default=0.0)         # in `currency`, always >= 0
    fx_rate_to_base: Mapped[float | None] = mapped_column(Float, nullable=True)  # base per 1 currency
    counter_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)  # FX: currency received
    counter_amount: Mapped[float | None] = mapped_column(Float, nullable=True)      # FX: amount received
    origin: Mapped[str] = mapped_column(String(16))   # manual|csv_import|paper_sim|reconciliation
    import_batch: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TradeProposal(Base):
    """A trade the platform PREPARES for the user. It is never executed automatically.

    status: proposed -> (user) placed | rejected | expired. When placed, the user records the
    actual fill price/quantity, which then becomes a LIVE transaction.
    """
    __tablename__ = "trade_proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    symbol: Mapped[str] = mapped_column(String(24))
    exchange: Mapped[str | None] = mapped_column(String(16), nullable=True)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[float] = mapped_column(Float)
    est_price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8))
    est_total_cost_base: Mapped[float] = mapped_column(Float)
    weight_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    thesis_entry_id: Mapped[int | None] = mapped_column(ForeignKey("journal_entries.id"), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    risks: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_check: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="proposed")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    executed_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    executed_tx_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"), nullable=True)
