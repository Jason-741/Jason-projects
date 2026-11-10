# Quant Research & Portfolio Intelligence Platform

A personal, institutional-style research, risk and portfolio-tracking platform for Canadian and US
equities and ETFs. It combines fundamental research, quantitative analysis, valuation and risk management.
**It never places trades.** Every live order is placed by you in Wealthsimple, and you record the actual fill.

> Research tool, not investment advice. A high model score never turns into a buy recommendation, and a
> backtest is never presented as proof of future returns.

## Architecture

```
quant-platform/
├── backend/                 Python 3.12+ · FastAPI · SQLAlchemy 2 · Alembic · pandas/NumPy/SciPy
│   ├── app/
│   │   ├── providers/       vendor-neutral data interfaces + Yahoo, SEC EDGAR, FRED, Alpha Vantage, FMP
│   │   ├── services/        ingestion (fetch → validate → store with provenance), point-in-time reads
│   │   ├── analytics/       ratios, DCF/reverse DCF, risk (VaR/CVaR…), signals, backtester, Monte Carlo,
│   │   │                    stress tests + mine NPV, portfolio optimisation
│   │   ├── portfolio/       ACB ledger, Wealthsimple/generic CSV import, risk limits, proposals, paper fills
│   │   ├── research/        transcript segmentation, guidance candidates, tone, credibility, readiness, LLM (RAG)
│   │   ├── api/             REST routes (all authenticated except /api/health and /api/auth/*)
│   │   └── security/        scrypt password hashing, JWT, rate limiting
│   ├── migrations/          Alembic
│   └── tests/               66 tests (hand-checked financial maths, separation rules, API flows)
├── frontend/                Next.js 15 · React 19 · TypeScript · Tailwind · Plotly — 16-section terminal UI
├── docs/                    METHODOLOGY · DATA_SOURCES · IMPORT_FORMAT · ROADMAP
└── docker-compose.yml       TimescaleDB/PostgreSQL, Redis, API, web
```

Design rules enforced in code:

* **Provenance on every data point.** Each stored price, fact or macro value has its source, retrieval time,
  currency, unit, frequency, quality status and whether it is actual, estimated or derived. Every fetch is logged as an `IngestionRun`.
* **Point-in-time fundamentals.** SEC facts keep their filing date, and restatements are stored as new rows. `as_of` queries only
  return what was public on that date.
* **No silent substitution.** A provider without a key reports *not configured*. A failed fetch records the error.
  Missing ratio inputs are listed, never imputed.
* **LIVE and PAPER are strictly separate.** Simulated fills cannot enter a live account, and broker imports cannot enter a paper account
  (HTTP 409, covered by tests).
* **Untrusted documents.** Transcripts and filings are stored as data. The LLM path has no tools, wraps sources in
  delimited blocks and flags citations that don't resolve to a source.
* **Audit trail.** Imports, proposals, decisions, journal changes and readiness changes are written to `audit_log`.

## Quick start (local, no Docker)

```bash
cd quant-platform/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # set APP_SECRET_KEY and SEC_USER_AGENT; add other keys if you have them
alembic upgrade head        # or: python -m app.cli init-db
python -m app.cli check-providers
python -m app.cli ingest-universe --start 2015-01-01    # seed watchlist prices (Yahoo); see app/universe.py
python -m app.cli ingest-fundamentals FCX               # point-in-time SEC data (needs SEC_USER_AGENT)
uvicorn app.main:app --reload --port 8000
```

```bash
cd quant-platform/frontend
npm install
cp .env.example .env.local
npm run dev                 # http://localhost:3000 → "Create account (first run)"
```

After creating your user, set `ALLOW_REGISTRATION=false` in `backend/.env`.

To run the full stack with Docker: `cp backend/.env.example backend/.env`, edit it, then run `docker compose up --build`.

Then fetch USD/CAD rates from **Settings → USD/CAD FX** so USD holdings can be valued in CAD.

## Tests

```bash
cd quant-platform/backend && python -m pytest -q      # 66 passed
cd quant-platform/frontend && npx tsc --noEmit && npm run build
```

The tests check financial calculations against values worked out by hand in the test file. Coverage includes:

* DCF cash flows, terminal value and enterprise value.
* Reverse DCF recovering a known growth rate.
* VaR/CVaR quantiles, max drawdown on a known price path, and Sharpe/Sortino/CAGR formulas.
* Euler risk contributions summing to portfolio volatility.
* Closed-form minimum-variance weights.
* Mine NPV and IRR (quadratic closed form).
* CRA-method ACB for USD positions with FX.
* Look-ahead detection: every built-in strategy passes, and a deliberately cheating signal is caught.
* Point-in-time selection: a restated value is only visible after its filing date.

Test price data is **synthetic** (seeded random walks) and exists only inside the test database.

## Status by roadmap phase

| Phase | Implemented | Outstanding |
|---|---|---|
| 1 Foundation | Schema with provenance, provider abstraction, ingestion + validation, search, auth, dashboard, migrations, Docker, CI | TimescaleDB hypertables (plain Postgres tables today), Redis cache (disk JSON cache used) |
| 2 Research intelligence | EDGAR filings index + XBRL facts, document upload (txt/PDF), transcript speaker/role/section segmentation, candidate guidance extraction with locations, tone, call-to-call comparison, credibility scoring API, BM25 retrieval + cited LLM answers (needs key) | SEDAR+ automation (no public API; manual upload workflow), credibility UI, investor-presentation table extraction, vector DB |
| 3 Financial analysis | Point-in-time annual statements, 25+ ratios with formulas, multiples, change flags, DCF, scenarios, sensitivity, reverse DCF, WACC, mine NPV | Peer-comparison table, sector-specific models (banks, REITs), forward estimates (need a licensed source) |
| 4 Quant | Causal signals, 4 strategies, cost-aware backtester, hold-out split, walk-forward, PSR/deflated Sharpe, saved runs with data hashes | Factor models (need point-in-time fundamentals for the whole universe), ML (deliberately deferred until a written hypothesis and enough data exist) |
| 5 Risk | Historical/parametric VaR & CVaR, drawdown, beta, correlation, risk contributions, concentration, factor stress tests, block-bootstrap Monte Carlo, pre-trade limits | Automatic beta estimation versus commodity series, liquidity-adjusted VaR |
| 6 Portfolio | Optimisers (EW/IV/MinVar/ERC/MV), paper trading, Wealthsimple + generic CSV import with dedupe, ACB ledger, proposals → user decision → recorded fill, journal with immutable thesis, readiness checklists | Time-weighted return and performance attribution, reconciliation against broker statement balances, notifications |
| 7 Integration | Unified dashboard, structured access logs, audit log | Alerts/notifications, earnings calendar, deployment hardening (HTTPS, backups schedule) |

## Data limitations (read before trusting numbers)

* **Yahoo Finance** (via `yfinance`) is unofficial and unlicensed, and can break or rate-limit without notice. Use it for personal research only.
* **SEC EDGAR** only covers SEC registrants. Many Canadian juniors file only on **SEDAR+**, which has no public API, so upload their documents yourself.
* **Alpha Vantage / FMP** integrations follow the vendors' published response formats but were **not tested against the live APIs**
  (no keys in the development environment). Check them with `python -m app.cli check-providers` and a test ingest.
* **Wealthsimple** offers no official public account or trading API for retail clients, so this platform uses CSV and manual entry only.
  The Wealthsimple CSV parser is best-effort. Always use the dry-run preview.
* Commodity operating metrics (AISC, reserves, grades) come from company disclosures. You enter them yourself, with a citation.
* The development environment's network blocked Yahoo and SEC, so **live data ingestion was not run here.** The provider
  parsers are unit-tested against sample responses shaped like each documented format.

See `docs/METHODOLOGY.md` for every formula, assumption and limitation.
