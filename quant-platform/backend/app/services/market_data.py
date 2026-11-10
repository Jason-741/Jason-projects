"""Read-side helpers that return analysis-ready frames from stored data, with point-in-time guards."""
from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FundamentalFact, PriceBar, Security


def find_security(db: Session, symbol: str, exchange: str | None = None) -> Security | None:
    q = select(Security).where(Security.symbol == symbol.upper())
    if exchange:
        q = q.where(Security.exchange == exchange.upper())
    return db.scalars(q).first()


def price_frame(db: Session, security_id: int, start: date | None = None, end: date | None = None,
                source: str | None = None) -> pd.DataFrame:
    q = select(PriceBar).where(PriceBar.security_id == security_id)
    if start:
        q = q.where(PriceBar.date >= start)
    if end:
        q = q.where(PriceBar.date <= end)
    if source:
        q = q.where(PriceBar.source == source)
    rows = db.scalars(q.order_by(PriceBar.date)).all()
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "adj_close", "volume"])
    df = pd.DataFrame([{"date": r.date, "open": r.open, "high": r.high, "low": r.low, "close": r.close,
                        "adj_close": r.adj_close, "volume": r.volume, "source": r.source,
                        "quality": r.quality_status} for r in rows])
    # If several sources exist, prefer the first one encountered per date (deterministic by source name).
    df = df.sort_values(["date", "source"]).drop_duplicates("date").set_index("date")
    return df


def total_return_series(df: pd.DataFrame) -> pd.Series:
    """Prefer dividend/split-adjusted close; fall back to raw close (flagged by caller)."""
    if "adj_close" in df and df["adj_close"].notna().sum() >= 0.95 * len(df):
        return df["adj_close"].astype(float)
    return df["close"].astype(float)


def facts_as_of(db: Session, security_id: int, as_of: date | None = None) -> list[FundamentalFact]:
    """Facts that were PUBLIC on `as_of` (available_at <= as_of). Latest filing wins per period."""
    q = select(FundamentalFact).where(FundamentalFact.security_id == security_id)
    if as_of:
        q = q.where(FundamentalFact.available_at <= as_of)
    rows = db.scalars(q.order_by(FundamentalFact.available_at)).all()
    latest: dict[tuple, FundamentalFact] = {}
    for r in rows:  # later filings (restatements) override earlier ones for the same period
        latest[(r.metric, r.period_end, r.period_type)] = r
    return list(latest.values())


def annual_statements(facts: list[FundamentalFact], years: int = 5) -> pd.DataFrame:
    """Pivot to metric x fiscal-period-end for FY durations and balance-sheet instants at FY ends."""
    fy = [f for f in facts if f.period_type == "FY"]
    fy_ends = sorted({f.period_end for f in fy})[-years:]
    data: dict[str, dict] = {}
    for f in facts:
        if f.period_end in fy_ends and f.period_type in ("FY", "INSTANT"):
            data.setdefault(f.metric, {})[f.period_end] = f.value
    df = pd.DataFrame(data).T
    return df.reindex(columns=sorted(df.columns)) if not df.empty else df
