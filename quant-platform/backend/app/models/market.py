from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from .provenance import ProvenanceMixin


class Security(Base):
    """A listed instrument. Delisted securities are kept (never deleted) to avoid survivorship bias."""
    __tablename__ = "securities"
    __table_args__ = (UniqueConstraint("symbol", "exchange"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)          # provider-neutral, e.g. "TECK.B"
    exchange: Mapped[str] = mapped_column(String(16), default="")        # e.g. TSX, NYSE, NASDAQ
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    asset_type: Mapped[str] = mapped_column(String(16), default="equity")  # equity|etf|index|fx|commodity
    sector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subsector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    cik: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)  # SEC id (US filers)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    delisted_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    prices = relationship("PriceBar", back_populates="security", cascade="all, delete-orphan")


class PriceBar(ProvenanceMixin, Base):
    """Daily OHLCV. `close` is the raw close; `adj_close` is provider split/dividend adjusted."""
    __tablename__ = "price_bars"
    __table_args__ = (UniqueConstraint("security_id", "date", "source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    adj_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)

    security = relationship("Security", back_populates="prices")


class CorporateAction(ProvenanceMixin, Base):
    __tablename__ = "corporate_actions"
    __table_args__ = (UniqueConstraint("security_id", "ex_date", "action_type", "source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id", ondelete="CASCADE"), index=True)
    ex_date: Mapped[date] = mapped_column(Date)
    action_type: Mapped[str] = mapped_column(String(16))   # split|dividend|spinoff
    value: Mapped[float] = mapped_column(Float)             # split ratio (new/old) or cash per share


class FundamentalFact(ProvenanceMixin, Base):
    """A single reported financial fact, stored POINT-IN-TIME.

    `available_at` is when the fact became public (e.g. the SEC filing date). Backtests and
    historical screens must only use facts with available_at <= decision date. Restated values
    are stored as new rows (different accession / available_at) rather than overwriting.
    """
    __tablename__ = "fundamental_facts"
    __table_args__ = (
        UniqueConstraint("security_id", "metric", "period_end", "period_type", "accession", "source"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id", ondelete="CASCADE"), index=True)
    metric: Mapped[str] = mapped_column(String(64), index=True)      # platform-normalized name, e.g. "revenue"
    source_tag: Mapped[str | None] = mapped_column(String(128), nullable=True)  # e.g. us-gaap:Revenues
    statement: Mapped[str | None] = mapped_column(String(16), nullable=True)    # IS|BS|CF|OPS
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    period_type: Mapped[str] = mapped_column(String(8))              # FY|Q1..Q4|INSTANT|TTM
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value: Mapped[float] = mapped_column(Float)
    available_at: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    form: Mapped[str | None] = mapped_column(String(16), nullable=True)
    accession: Mapped[str] = mapped_column(String(32), default="")


class MacroObservation(ProvenanceMixin, Base):
    __tablename__ = "macro_observations"
    __table_args__ = (UniqueConstraint("series_id", "date", "source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[str] = mapped_column(String(64), index=True)
    date: Mapped[date] = mapped_column(Date)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)


class FxRate(ProvenanceMixin, Base):
    """Units of `quote` per 1 unit of `base` (e.g. base=USD, quote=CAD, rate=1.37)."""
    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("base", "quote", "date", "source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    base: Mapped[str] = mapped_column(String(8))
    quote: Mapped[str] = mapped_column(String(8))
    date: Mapped[date] = mapped_column(Date, index=True)
    rate: Mapped[float] = mapped_column(Float)
