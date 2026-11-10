"""Command-line helpers.

    python -m app.cli init-db
    python -m app.cli check-providers
    python -m app.cli ingest-prices XEQT --exchange TSX --start 2018-01-01
    python -m app.cli ingest-universe            # seed watchlist in app/universe.py
    python -m app.cli ingest-fundamentals FCX
    python -m app.cli backup                     # copy SQLite DB to backups/ (use pg_dump for Postgres)
"""
from __future__ import annotations

import argparse
import shutil
from datetime import date, datetime

from .config import get_settings
from .db import SessionLocal, init_db
from .providers.registry import get_registry
from .services import ingestion


def main(argv=None):
    ap = argparse.ArgumentParser(prog="app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    sub.add_parser("check-providers")
    p = sub.add_parser("ingest-prices")
    p.add_argument("symbol")
    p.add_argument("--exchange", default="US")
    p.add_argument("--start", default="2015-01-01")
    p.add_argument("--provider")
    f = sub.add_parser("ingest-fundamentals")
    f.add_argument("symbol")
    f.add_argument("--exchange", default="US")
    f.add_argument("--sec-symbol", help="ticker used by SEC if different (e.g. CCJ for TSX:CCO)")
    sub.add_parser("store-fx")
    m = sub.add_parser("ingest-macro")
    m.add_argument("series_id")
    u = sub.add_parser("ingest-universe")
    u.add_argument("--start", default="2015-01-01")
    sub.add_parser("backup")
    a = ap.parse_args(argv)
    init_db()
    reg = get_registry()
    if a.cmd == "init-db":
        print("database initialized:", get_settings().database_url)
    elif a.cmd == "check-providers":
        for s in reg.statuses():
            print(f"{s.name:14} configured={s.configured!s:5} requires={s.requires} — {s.detail}")
    elif a.cmd == "ingest-prices":
        with SessionLocal() as db:
            r = ingestion.ingest_prices(db, reg, a.symbol, a.exchange, date.fromisoformat(a.start), provider=a.provider)
            print(r.status, r.provider, r.rows_written, r.error or "", r.issues or "")
    elif a.cmd == "ingest-fundamentals":
        with SessionLocal() as db:
            r = ingestion.ingest_fundamentals(db, reg, a.symbol, a.exchange, a.sec_symbol)
            print(r.status, r.rows_written, r.error or "")
    elif a.cmd == "store-fx":
        with SessionLocal() as db:
            print("fx rows written:", ingestion.store_fx_from_prices(db))
    elif a.cmd == "ingest-macro":
        with SessionLocal() as db:
            r = ingestion.ingest_macro(db, reg, a.series_id)
            print(r.status, r.rows_written, r.error or "")
    elif a.cmd == "ingest-universe":
        from .universe import UNIVERSE
        with SessionLocal() as db:
            for sym, exch, name, atype, sector, sub_ in UNIVERSE:
                ingestion.get_or_create_security(db, sym, exch, name=name, asset_type=atype, sector=sector, subsector=sub_,
                                                 source="universe_seed")
                db.commit()
                r = ingestion.ingest_prices(db, reg, sym, exch, date.fromisoformat(a.start))
                print(f"{sym:10} {exch:6} {r.status:8} rows={r.rows_written} {r.error or ''}")
    elif a.cmd == "backup":
        url = get_settings().database_url
        if not url.startswith("sqlite:///"):
            print("For PostgreSQL use: pg_dump \"$DATABASE_URL\" > backup.sql")
            return
        src = url.replace("sqlite:///", "")
        dst_dir = get_settings().cache_dir.parent / "backups"
        dst_dir.mkdir(exist_ok=True)
        dst = dst_dir / f"quant-{datetime.now():%Y%m%d-%H%M%S}.db"
        shutil.copy2(src, dst)
        print("backup written:", dst)


if __name__ == "__main__":
    main()
