"""Assemble the research ranking from stored data (prices + point-in-time fundamentals)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics import ranking
from ..models import Security
from .market_data import annual_statements, facts_as_of, price_frame, total_return_series

EXCLUDE_SECTORS = {"Benchmark", "FX", "Commodities"}


def build_ranking(db: Session, as_of: date | None = None) -> dict:
    rows = []
    for sec in db.scalars(select(Security).where(Security.active.is_(True))):
        if sec.sector in EXCLUDE_SECTORS or sec.asset_type in ("index", "fx", "commodity"):
            continue
        df = price_frame(db, sec.id, end=as_of)
        if df.empty:
            continue
        px = total_return_series(df)
        f = ranking.price_factors(px, df["volume"].astype(float))
        if len(px):
            f["last"] = float(df["close"].dropna().iloc[-1])
            f["last_date"] = str(px.dropna().index[-1])
        table = annual_statements(facts_as_of(db, sec.id, as_of), 2)
        fy = None
        if not table.empty:
            cols = list(table.columns)
            latest = {m: (None if v != v else v) for m, v in table[cols[-1]].items()}
            prior = {m: (None if v != v else v) for m, v in table[cols[-2]].items()} if len(cols) > 1 else None
            f.update(ranking.fundamental_factors(latest, prior))
            fy = str(cols[-1])
        rows.append({"symbol": sec.symbol, "exchange": sec.exchange, "name": sec.name, "currency": sec.currency,
                     "asset_type": sec.asset_type, "sector": sec.sector, "subsector": sec.subsector,
                     "fiscal_year_end": fy, "factors": f})
    ranked = ranking.rank(rows)
    return {"as_of": str(as_of) if as_of else "latest stored data", "method": ranking.__doc__.strip(),
            "groups": {g: {"weight": w, "factors": list(fs)} for g, (w, fs) in ranking.GROUPS.items()},
            "results": ranked}
