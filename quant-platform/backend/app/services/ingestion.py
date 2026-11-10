"""Fetch → validate → store, with an IngestionRun record for every attempt (success or failure)."""
from __future__ import annotations

import math
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CorporateAction, FundamentalFact, IngestionRun, MacroObservation, PriceBar, Security
from ..providers.base import ProviderError
from ..providers.registry import Registry
from .validation import validate_prices


def _now():
    return datetime.now(timezone.utc)


def _nan_to_none(x):
    if x is None:
        return None
    try:
        return None if math.isnan(float(x)) else float(x)
    except (TypeError, ValueError):
        return None


def get_or_create_security(db: Session, symbol: str, exchange: str, **fields) -> Security:
    symbol, exchange = symbol.upper(), (exchange or "").upper()
    sec = db.scalar(select(Security).where(Security.symbol == symbol, Security.exchange == exchange))
    if sec is None:
        sec = Security(symbol=symbol, exchange=exchange, **fields)
        db.add(sec)
        db.flush()
    else:
        for k, v in fields.items():
            if v is not None:
                setattr(sec, k, v)
    return sec


def _finish(db: Session, run: IngestionRun, status: str, rows: int = 0, issues=None, error: str | None = None):
    run.status, run.rows_written, run.issues, run.error, run.finished_at = status, rows, issues, error, _now()
    db.commit()
    return run


def ingest_prices(db: Session, registry: Registry, symbol: str, exchange: str, start: date,
                  end: date | None = None, provider: str | None = None) -> IngestionRun:
    run = IngestionRun(provider=provider or "auto", dataset="daily_prices",
                       params={"symbol": symbol, "exchange": exchange, "start": start.isoformat(),
                               "end": end.isoformat() if end else None})
    db.add(run)
    db.commit()
    providers = [registry.get(provider)] if provider else registry.price_providers
    errors = []
    data = None
    for p in providers:
        if not p.status().configured:
            errors.append(f"{p.name}: not configured")
            continue
        try:
            data = p.daily_prices(symbol, exchange, start, end)
            run.provider = p.name
            break
        except ProviderError as exc:
            errors.append(f"{p.name}: {exc}")
    if data is None:
        return _finish(db, run, "error", error="; ".join(errors) or "no provider available")

    status, issues = validate_prices(data.frame, data.splits)
    issue_dicts = [i.as_dict() for i in issues] + [{"severity": "info", "code": "provider_note", "message": n}
                                                    for n in data.meta.notes]
    if status == "rejected":
        return _finish(db, run, "error", issues=issue_dicts, error="validation rejected dataset")

    sec = get_or_create_security(db, symbol, exchange, currency=data.meta.currency)
    existing = {b.date: b for b in db.scalars(select(PriceBar).where(PriceBar.security_id == sec.id,
                                                                    PriceBar.source == data.meta.source))}
    flagged = {d for i in issues if i.dates for d in i.dates}
    rows = 0
    for d, r in data.frame.iterrows():
        d = d if isinstance(d, date) else d.date()
        bar = existing.get(d) or PriceBar(security_id=sec.id, date=d, source=data.meta.source)
        bar.open, bar.high, bar.low = _nan_to_none(r["open"]), _nan_to_none(r["high"]), _nan_to_none(r["low"])
        bar.close, bar.adj_close, bar.volume = _nan_to_none(r["close"]), _nan_to_none(r["adj_close"]), _nan_to_none(r["volume"])
        bar.retrieved_at, bar.currency, bar.unit, bar.frequency = data.meta.retrieved_at, data.meta.currency, data.meta.unit, "daily"
        bar.nature = "actual"
        bar.quality_status = "warning" if any(f.startswith(str(d)) for f in flagged) else "valid"
        if d not in existing:
            db.add(bar)
        rows += 1
    for series, kind in ((data.dividends, "dividend"), (data.splits, "split")):
        if series is None:
            continue
        for d, v in series.items():
            d = d if isinstance(d, date) else d.date()
            exists = db.scalar(select(CorporateAction).where(CorporateAction.security_id == sec.id, CorporateAction.ex_date == d,
                                                             CorporateAction.action_type == kind, CorporateAction.source == data.meta.source))
            if not exists:
                db.add(CorporateAction(security_id=sec.id, ex_date=d, action_type=kind, value=float(v), source=data.meta.source,
                                       currency=data.meta.currency if kind == "dividend" else None,
                                       unit="cash per share" if kind == "dividend" else "ratio new/old",
                                       quality_status="valid", nature="actual"))
    sec.updated_at = _now()
    return _finish(db, run, "ok" if status == "valid" else "partial", rows=rows, issues=issue_dicts)


def ingest_fundamentals(db: Session, registry: Registry, symbol: str, exchange: str) -> IngestionRun:
    run = IngestionRun(provider="sec_edgar", dataset="fundamentals", params={"symbol": symbol, "exchange": exchange})
    db.add(run)
    db.commit()
    try:
        fs = registry.sec.facts(symbol, exchange)
    except ProviderError as exc:
        return _finish(db, run, "error", error=str(exc))
    sec = get_or_create_security(db, symbol, exchange)
    existing = {(f.metric, f.period_end, f.period_type, f.accession)
                for f in db.scalars(select(FundamentalFact).where(FundamentalFact.security_id == sec.id,
                                                                  FundamentalFact.source == "sec_edgar"))}
    rows = 0
    for f in fs.facts:
        key = (f.metric, f.period_end, f.period_type, f.accession)
        if key in existing:
            continue
        db.add(FundamentalFact(security_id=sec.id, metric=f.metric, source_tag=f.source_tag, statement=f.statement,
                               period_start=f.period_start, period_end=f.period_end, period_type=f.period_type,
                               fiscal_year=f.fiscal_year, value=f.value, available_at=f.available_at, form=f.form,
                               accession=f.accession, source="sec_edgar", retrieved_at=fs.meta.retrieved_at,
                               currency=f.currency, unit=f.unit, frequency=f.period_type, quality_status="valid",
                               nature="actual"))
        existing.add(key)
        rows += 1
    return _finish(db, run, "ok", rows=rows, issues=[{"severity": "info", "code": "provider_note", "message": n}
                                                     for n in fs.meta.notes])


def ingest_macro(db: Session, registry: Registry, series_id: str, start: date | None = None) -> IngestionRun:
    run = IngestionRun(provider="fred", dataset="macro", params={"series_id": series_id})
    db.add(run)
    db.commit()
    try:
        sd = registry.fred.series(series_id, start)
    except ProviderError as exc:
        return _finish(db, run, "error", error=str(exc))
    existing = {o.date: o for o in db.scalars(select(MacroObservation).where(MacroObservation.series_id == series_id,
                                                                            MacroObservation.source == "fred"))}
    rows = 0
    for d, v in sd.frame.items():
        o = existing.get(d) or MacroObservation(series_id=series_id, date=d, source="fred")
        o.value = _nan_to_none(v)
        o.unit, o.frequency, o.retrieved_at = sd.meta.unit, sd.meta.frequency, sd.meta.retrieved_at
        o.quality_status = "valid" if o.value is not None else "warning"
        o.quality_notes = None if o.value is not None else "missing observation at source"
        if d not in existing:
            db.add(o)
        rows += 1
    return _finish(db, run, "ok", rows=rows, issues=[{"severity": "info", "code": "provider_note", "message": n}
                                                     for n in sd.meta.notes])
