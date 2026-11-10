"""Provenance columns attached to every stored financial data point.

Required by the platform's principles: each value carries its source, retrieval timestamp,
currency, units, frequency, quality status and whether it is actual / estimated / derived.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DataNature(str, Enum):
    ACTUAL = "actual"        # reported / observed fact
    ESTIMATED = "estimated"  # analyst or provider estimate
    DERIVED = "derived"      # computed by this platform from other stored data


class QualityStatus(str, Enum):
    UNVALIDATED = "unvalidated"
    VALID = "valid"
    WARNING = "warning"      # passed with warnings (e.g. gap, outlier flagged)
    REJECTED = "rejected"


class ProvenanceMixin:
    source: Mapped[str] = mapped_column(String(64), index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quality_status: Mapped[str] = mapped_column(String(16), default=QualityStatus.UNVALIDATED.value)
    quality_notes: Mapped[str | None] = mapped_column(String(512), nullable=True)
    nature: Mapped[str] = mapped_column(String(16), default=DataNature.ACTUAL.value)
