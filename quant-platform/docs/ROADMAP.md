# Next steps (prioritised)

1. **Run live ingestion** on your machine: `ingest-universe`, `ingest-fundamentals` for SEC filers, then FRED series DGS10, DGS3MO and DEXCAUS.
   Check the ingestion log for validation warnings.
2. **Import your Wealthsimple history** (dry run first), add FX rates, and confirm the holdings snapshot matches your Wealthsimple statement.
3. **Peer comparison & sector models**: a peer-set table of multiples and ratios; P/NAV for miners using the mine model;
   P/B–ROE for banks.
4. **Credibility UI**: confirm candidate guidance items and link them to later reported actuals from SEC facts.
5. **Cross-sectional point-in-time fundamentals** for the universe, which enables value/quality/profitability factor research.
   ML only after a written hypothesis exists, with purged walk-forward CV.
6. **Performance attribution**: daily valuation history, time-weighted vs money-weighted returns, and attribution by sector, currency and position.
7. **Notifications**: earnings dates, invalidation-condition alerts, risk-limit breaches, stale-data alerts.
8. **Infrastructure**: TimescaleDB hypertable for `price_bars`, Redis cache, scheduled backups (`pg_dump`), HTTPS reverse proxy.
