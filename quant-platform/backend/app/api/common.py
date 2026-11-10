from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..analytics.risk import clean
from ..services.market_data import find_security, price_frame, total_return_series


def jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if np.isnan(f) or np.isinf(f) else f
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    return clean(obj) if isinstance(obj, dict) else obj


def price_matrix(db: Session, symbols: list[str], start=None, end=None) -> tuple[pd.DataFrame, list[str]]:
    """Total-return price matrix for symbols on common dates. Returns (frame, notes)."""
    cols, notes = {}, []
    for s in symbols:
        sec = find_security(db, s)
        if sec is None:
            raise HTTPException(404, f"{s} not in database — ingest prices first")
        df = price_frame(db, sec.id, start, end)
        if df.empty:
            raise HTTPException(422, f"no stored prices for {s}")
        series = total_return_series(df)
        if series is df["close"]:
            notes.append(f"{s}: adjusted close unavailable — using raw close (dividends excluded)")
        cols[s.upper()] = series
    frame = pd.DataFrame(cols).sort_index()
    before = len(frame)
    frame = frame.dropna()
    if len(frame) < before:
        notes.append(f"aligned to {len(frame)} common dates (dropped {before - len(frame)} with missing data)")
    frame.index = pd.to_datetime(frame.index)
    return frame, notes
