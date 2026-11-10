from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..analytics import ratios as R
from ..db import get_db
from ..models import AuditLog, FundamentalFact, IngestionRun, MacroObservation, PriceBar, Security, User
from ..providers.base import ProviderError
from ..providers.registry import get_registry
from ..providers.symbols import from_yahoo
from ..security.auth import current_user, ingest_limiter
from ..services import ingestion
from ..services.market_data import annual_statements, facts_as_of, find_security, price_frame
from .common import jsonable

router = APIRouter(prefix="/api", tags=["data"], dependencies=[Depends(current_user)])


@router.get("/data/providers")
def providers():
    return [s.__dict__ for s in get_registry().statuses()]


class IngestPrices(BaseModel):
    symbol: str
    exchange: str = "US"
    start: date = date(2015, 1, 1)
    end: date | None = None
    provider: str | None = None


def _run_dict(r: IngestionRun):
    return {"id": r.id, "provider": r.provider, "dataset": r.dataset, "params": r.params, "status": r.status,
            "rows_written": r.rows_written, "issues": r.issues, "error": r.error,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None}


@router.post("/data/ingest/prices", dependencies=[Depends(ingest_limiter)])
def ingest_prices(body: IngestPrices, db: Session = Depends(get_db), user: User = Depends(current_user)):
    run = ingestion.ingest_prices(db, get_registry(), body.symbol, body.exchange, body.start, body.end, body.provider)
    return _run_dict(run)


class IngestSymbol(BaseModel):
    symbol: str
    exchange: str = "US"


@router.post("/data/ingest/fundamentals", dependencies=[Depends(ingest_limiter)])
def ingest_fundamentals(body: IngestSymbol, db: Session = Depends(get_db)):
    return _run_dict(ingestion.ingest_fundamentals(db, get_registry(), body.symbol, body.exchange))


class IngestMacro(BaseModel):
    series_id: str
    start: date | None = None


@router.post("/data/ingest/macro", dependencies=[Depends(ingest_limiter)])
def ingest_macro(body: IngestMacro, db: Session = Depends(get_db)):
    return _run_dict(ingestion.ingest_macro(db, get_registry(), body.series_id, body.start))


@router.post("/data/ingest/fx", dependencies=[Depends(ingest_limiter)])
def ingest_fx(start: date = date(2015, 1, 1), db: Session = Depends(get_db)):
    """USD→CAD daily rates from Yahoo 'CAD=X' (CAD per USD), stored in fx_rates."""
    from ..models import FxRate
    run = ingestion.ingest_prices(db, get_registry(), "CAD=X", "FX", start, provider="yahoo")
    if run.status == "error":
        return _run_dict(run)
    sec = find_security(db, "CAD=X", "FX")
    df = price_frame(db, sec.id, start)
    existing = {r.date for r in db.scalars(select(FxRate).where(FxRate.base == "USD", FxRate.quote == "CAD", FxRate.source == "yahoo"))}
    n = 0
    for d, row in df.iterrows():
        if d in existing or row["close"] is None:
            continue
        db.add(FxRate(base="USD", quote="CAD", date=d, rate=float(row["close"]), source="yahoo", currency="CAD",
                      unit="CAD per USD", frequency="daily", quality_status=row["quality"], nature="actual"))
        n += 1
    db.commit()
    out = _run_dict(run)
    out["fx_rows_written"] = n
    return out


@router.get("/data/runs")
def runs(limit: int = 50, db: Session = Depends(get_db)):
    return [_run_dict(r) for r in db.scalars(select(IngestionRun).order_by(IngestionRun.id.desc()).limit(limit))]


@router.get("/data/coverage")
def coverage(db: Session = Depends(get_db)):
    rows = db.execute(select(Security.symbol, Security.exchange, func.count(PriceBar.id), func.min(PriceBar.date), func.max(PriceBar.date))
                      .join(PriceBar, PriceBar.security_id == Security.id, isouter=True).group_by(Security.id)).all()
    facts = dict(db.execute(select(FundamentalFact.security_id, func.count()).group_by(FundamentalFact.security_id)).all())
    secs = {s.symbol: s.id for s in db.scalars(select(Security))}
    macro = db.execute(select(MacroObservation.series_id, func.count(), func.max(MacroObservation.date)).group_by(MacroObservation.series_id)).all()
    return {"securities": [{"symbol": r[0], "exchange": r[1], "price_rows": r[2], "first": str(r[3]) if r[3] else None,
                            "last": str(r[4]) if r[4] else None, "fundamental_facts": facts.get(secs.get(r[0]), 0)} for r in rows],
            "macro": [{"series_id": m[0], "rows": m[1], "last": str(m[2])} for m in macro]}


@router.get("/audit")
def audit_log(limit: int = 100, db: Session = Depends(get_db)):
    return [{"ts": a.ts.isoformat(), "action": a.action, "entity": a.entity, "entity_id": a.entity_id, "detail": a.detail}
            for a in db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))]


# ---------------------------------------------------------------- securities

class SecurityIn(BaseModel):
    symbol: str
    exchange: str = "US"
    name: str | None = None
    currency: str | None = None
    asset_type: str = "equity"
    sector: str | None = None
    subsector: str | None = None
    country: str | None = None


def _sec_dict(s: Security):
    return {"id": s.id, "symbol": s.symbol, "exchange": s.exchange, "name": s.name, "currency": s.currency,
            "asset_type": s.asset_type, "sector": s.sector, "subsector": s.subsector, "country": s.country,
            "active": s.active, "source": s.source}


@router.get("/securities")
def search(q: str = "", sector: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    stmt = select(Security)
    if q:
        like = f"%{q.upper()}%"
        stmt = stmt.where(or_(func.upper(Security.symbol).like(like), func.upper(Security.name).like(like)))
    if sector:
        stmt = stmt.where(Security.sector == sector)
    return [_sec_dict(s) for s in db.scalars(stmt.order_by(Security.symbol).limit(limit))]


@router.post("/securities")
def upsert_security(body: SecurityIn, db: Session = Depends(get_db)):
    fields = body.model_dump(exclude={"symbol", "exchange"})
    sec = ingestion.get_or_create_security(db, body.symbol, body.exchange, **fields, source="manual")
    db.commit()
    return _sec_dict(sec)


@router.post("/securities/{symbol}/profile")
def fetch_profile(symbol: str, exchange: str = "US", db: Session = Depends(get_db)):
    reg = get_registry()
    errors = []
    for p in reg.profile_providers:
        if not p.status().configured:
            continue
        try:
            prof = p.profile(symbol, exchange)
        except ProviderError as exc:
            errors.append(f"{p.name}: {exc}")
            continue
        sec = ingestion.get_or_create_security(db, symbol, exchange, name=prof.name, currency=prof.currency,
                                               asset_type=prof.asset_type, sector=prof.sector, subsector=prof.subsector,
                                               country=prof.country, cik=prof.cik, source=prof.meta.source)
        db.commit()
        return _sec_dict(sec)
    raise HTTPException(502, "; ".join(errors) or "no profile provider configured")


def _sec_or_404(db, symbol, exchange=None):
    sec = find_security(db, symbol, exchange)
    if sec is None:
        raise HTTPException(404, f"{symbol} not found — add or ingest it first")
    return sec


@router.get("/securities/{symbol}")
def get_security(symbol: str, exchange: str | None = None, db: Session = Depends(get_db)):
    return _sec_dict(_sec_or_404(db, symbol, exchange))


@router.get("/securities/{symbol}/prices")
def prices(symbol: str, exchange: str | None = None, start: date | None = None, end: date | None = None,
           db: Session = Depends(get_db)):
    sec = _sec_or_404(db, symbol, exchange)
    df = price_frame(db, sec.id, start, end)
    bars = [{"date": str(d), **{k: r[k] for k in ("open", "high", "low", "close", "adj_close", "volume", "source", "quality")}}
            for d, r in df.iterrows()]
    warn = sum(1 for b in bars if b["quality"] != "valid")
    return jsonable({"symbol": sec.symbol, "currency": sec.currency, "bars": bars, "flagged_bars": warn,
                     "provenance": {"sources": sorted(df["source"].unique().tolist()) if not df.empty else []}})


@router.get("/securities/{symbol}/fundamentals")
def fundamentals(symbol: str, as_of: date | None = None, years: int = 5, exchange: str | None = None,
                 db: Session = Depends(get_db)):
    """Annual statements as known on `as_of` (point-in-time), with derived ratios and provenance."""
    sec = _sec_or_404(db, symbol, exchange)
    facts = facts_as_of(db, sec.id, as_of)
    table = annual_statements(facts, years)
    if table.empty:
        return {"symbol": sec.symbol, "as_of": str(as_of) if as_of else None, "periods": [], "statements": {},
                "ratios": {}, "message": "no annual fundamentals stored (ingest from SEC EDGAR or enter manually)"}
    periods = [str(c) for c in table.columns]
    statements = {m: {str(c): (None if v != v else v) for c, v in row.items()} for m, row in table.iterrows()}
    by_period = [{m: statements[m][p] for m in statements} for p in periods]
    ratios = {}
    for i, p in enumerate(periods):
        prior = by_period[i - 1] if i > 0 else None
        ratios[p] = {k: v.as_dict() for k, v in R.statement_ratios(by_period[i], prior).items()}
    prov = {}
    for f in facts:
        if str(f.period_end) in periods:
            prov.setdefault(f.metric, {})[str(f.period_end)] = {"source": f.source, "tag": f.source_tag, "form": f.form,
                                                                "filed": str(f.available_at), "accession": f.accession,
                                                                "unit": f.unit}
    flags = R.flag_changes({m: [statements[m][p] for p in periods] for m in ("revenue", "net_income", "operating_cash_flow",
                                                                           "total_liabilities", "goodwill") if m in statements})
    return jsonable({"symbol": sec.symbol, "as_of": str(as_of) if as_of else None, "periods": periods,
                     "statements": statements, "derived": {p: R.derived_items(by_period[i]) for i, p in enumerate(periods)},
                     "ratios": ratios, "provenance": prov, "change_flags": flags})


@router.get("/securities/{symbol}/multiples")
def multiples(symbol: str, price: float | None = None, eps_growth_pct: float | None = None, exchange: str | None = None,
              db: Session = Depends(get_db)):
    sec = _sec_or_404(db, symbol, exchange)
    facts = facts_as_of(db, sec.id, None)
    table = annual_statements(facts, 1)
    if table.empty:
        raise HTTPException(422, "no fundamentals stored")
    latest = {m: (None if v != v else v) for m, v in table.iloc[:, -1].items()}
    if price is None:
        df = price_frame(db, sec.id)
        if df.empty:
            raise HTTPException(422, "no price stored; pass ?price=")
        price = float(df["close"].dropna().iloc[-1])
    shares_facts = sorted([f for f in facts if f.metric == "shares_outstanding"], key=lambda f: f.period_end)
    shares = shares_facts[-1].value if shares_facts else latest.get("shares_diluted")
    out = {k: v.as_dict() for k, v in R.valuation_multiples(price, shares, latest, eps_growth_pct=eps_growth_pct).items()}
    return jsonable({"symbol": sec.symbol, "price": price, "fiscal_period": str(table.columns[-1]), "multiples": out,
                     "note": "multiples use latest fiscal-year statements; currency mismatch possible for foreign filers"})


@router.get("/securities/{symbol}/filings")
def filings(symbol: str):
    try:
        return get_registry().sec.recent_filings(symbol)
    except ProviderError as exc:
        raise HTTPException(502, str(exc))


@router.get("/symbols/parse")
def parse_symbol(ticker: str = Query(..., description="Yahoo-style ticker, e.g. TECK-B.TO")):
    s, e = from_yahoo(ticker)
    return {"symbol": s, "exchange": e}


@router.get("/markets/summary")
def markets_summary(db: Session = Depends(get_db)):
    """Per-security trailing returns and descriptive quant stats computed from STORED prices only."""
    import numpy as np

    from ..analytics import signals as SG
    from ..services.market_data import total_return_series
    out = []
    for sec in db.scalars(select(Security).order_by(Security.sector, Security.symbol)):
        df = price_frame(db, sec.id)
        row = {**_sec_dict(sec), "last": None, "last_date": None}
        if len(df) < 2:
            out.append(row)
            continue
        px = total_return_series(df).dropna()
        last_date = px.index[-1]

        def ret(days):
            return float(px.iloc[-1] / px.iloc[-1 - days] - 1) if len(px) > days else None

        ytd_base = px[[d.year < last_date.year for d in px.index]]
        row.update({
            "last": float(df["close"].dropna().iloc[-1]), "last_date": str(last_date), "bars": len(px),
            "r_1d": ret(1), "r_1w": ret(5), "r_1m": ret(21), "r_3m": ret(63), "r_1y": ret(252),
            "r_ytd": float(px.iloc[-1] / ytd_base.iloc[-1] - 1) if len(ytd_base) else None,
            "vol_60d": float(px.pct_change().tail(60).std() * np.sqrt(252)) if len(px) > 61 else None,
            "mom_12_1": float(SG.momentum(px).iloc[-1]) if len(px) > 253 else None,
            "vs_sma200": float(px.iloc[-1] / px.tail(200).mean() - 1) if len(px) >= 200 else None,
            "rsi14": float(SG.rsi(px).iloc[-1]) if len(px) > 15 else None,
            "high_52w": float(df["high"].tail(252).max()) if df["high"].notna().any() else None,
            "low_52w": float(df["low"].tail(252).min()) if df["low"].notna().any() else None,
            "stale_days": (date.today() - last_date).days,
        })
        out.append(row)
    return jsonable(out)
