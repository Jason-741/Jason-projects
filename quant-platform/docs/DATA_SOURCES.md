# Data sources

| Provider | Key | Used for | Status in this build |
|---|---|---|---|
| Yahoo Finance (`yfinance`) | none | daily OHLCV, dividends, splits, profiles, indices (^GSPTSE), FX (CAD=X), futures (HG=F, GC=F, CL=F) | implemented; parser unit-tested; live fetch not run in dev (network blocked) |
| SEC EDGAR | `SEC_USER_AGENT` (name + email, SEC policy) | XBRL company facts with filing dates (point-in-time), filings index | implemented; parser unit-tested on companyfacts-shaped fixture |
| FRED | `FRED_API_KEY` (free) | rates, CAD/USD, CPI, monthly commodity series | implemented; parser unit-tested |
| Alpha Vantage | `ALPHA_VANTAGE_API_KEY` | backup unadjusted daily prices | implemented, unverified live |
| Financial Modeling Prep | `FMP_API_KEY` | company profiles (statements/estimates can be added behind the same interface) | implemented, unverified live |
| SEDAR+ | n/a — no public API | Canadian filings, NI 43-101 technical reports | manual: download and upload in Earnings Intelligence |
| Wealthsimple | n/a — no official retail API | holdings and transactions | CSV import + manual entry; credentials never requested |
| EIA, World Bank commodity data | free | energy and commodity fundamentals | not yet implemented (add a `MacroProvider`) |

Adding a provider: implement `PriceProvider`, `FundamentalsProvider`, `ProfileProvider` or `MacroProvider` from
`app/providers/base.py`, return `DatasetMeta` with the source and units, and register it in `providers/registry.py`.
Rate limiting (`RateLimiter`), retries and the on-disk cache (`JsonCache`, which never stores API keys in cache keys) live in `providers/http.py`.

Symbols: internal form is `SYMBOL` + `exchange` (`TECK.B`/`TSX`). Mapping to Yahoo is in `providers/symbols.py`
(`TECK-B.TO`, `.V` for TSXV, `.CN` for CSE).
