from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .provenance import utcnow


class Document(Base):
    """A retrieved research document (filing, transcript, presentation). Content is UNTRUSTED input."""
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int | None] = mapped_column(ForeignKey("securities.id"), nullable=True, index=True)
    doc_type: Mapped[str] = mapped_column(String(32))  # 10-K|10-Q|8-K|40-F|transcript|presentation|...
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source: Mapped[str] = mapped_column(String(64))
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class DocumentSegment(Base):
    """A located piece of a document (speaker turn, page, section) so every claim can cite its source."""
    __tablename__ = "document_segments"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(32), nullable=True)   # prepared_remarks|qa
    speaker: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str | None] = mapped_column(String(32), nullable=True)      # ceo|cfo|executive|analyst|operator
    location: Mapped[str | None] = mapped_column(String(64), nullable=True)  # e.g. "page 4" / "turn 12"
    text: Mapped[str] = mapped_column(Text)


class JournalEntry(Base):
    """Investment journal: the thesis as written BEFORE the outcome was known, plus later reviews."""
    __tablename__ = "journal_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    account_kind: Mapped[str] = mapped_column(String(8), default="live")
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    status: Mapped[str] = mapped_column(String(16), default="research")  # research|open|closed|abandoned
    analysis_date: Mapped[date] = mapped_column(Date)
    thesis: Mapped[str] = mapped_column(Text)
    valuation_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    valuation_base: Mapped[float | None] = mapped_column(Float, nullable=True)
    valuation_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    valuation_assumptions: Mapped[str | None] = mapped_column(Text, nullable=True)
    catalysts: Mapped[str | None] = mapped_column(Text, nullable=True)
    risks: Mapped[str | None] = mapped_column(Text, nullable=True)
    invalidation_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_holding_period: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1..5, recorded up front
    entry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    allocation_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    realized_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    updates: Mapped[list | None] = mapped_column(JSON, nullable=True)       # dated developments
    thesis_was_correct: Mapped[str | None] = mapped_column(String(16), nullable=True)  # yes|partly|no|unclear
    outcome_attribution: Mapped[str | None] = mapped_column(String(16), nullable=True)  # skill|luck|mixed|unclear
    lessons: Mapped[str | None] = mapped_column(Text, nullable=True)


class Strategy(Base):
    """A quantitative strategy and its live-readiness checklist (see docs/READINESS.md)."""
    __tablename__ = "strategies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    hypothesis: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32))
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    checklist: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("strategies.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    config: Mapped[dict] = mapped_column(JSON)
    data_fingerprint: Mapped[str] = mapped_column(String(64))  # hash of the input price data → reproducibility
    metrics: Mapped[dict] = mapped_column(JSON)
    equity_curve: Mapped[list | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
