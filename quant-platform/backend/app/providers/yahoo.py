"""Yahoo Finance via `yfinance`.

Limitations (documented, not hidden): unofficial, unlicensed for redistribution, no SLA, can
change or rate-limit without notice, and fundamentals are not point-in-time. Used here only for
daily prices, dividends, splits and basic profile data for personal research.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from .base import DatasetMeta, PriceData, PriceProvider, ProfileProvider, ProviderError, ProviderStatus, SecurityProfile
from .symbols import to_yahoo


class YahooProvider(PriceProvider, ProfileProvider):
    name = "yahoo"
    capabilities = ("daily_prices", "dividends", "splits", "profile", "fx", "indices", "commodity_futures")

    def __init__(self, yf_module=None):
        self._yf = yf_module

    @property
    def yf(self):
        if self._yf is None:
            try:
                import yfinance as yf  # imported lazily so the app runs without it
            except ImportError as exc:  # pragma: no cover
                raise ProviderError("yfinance is not installed") from exc
            self._yf = yf
        return self._yf

    def status(self) -> ProviderStatus:
        try:
            self.yf
            ok = True
        except ProviderError:
            ok = False
        return ProviderStatus(self.name, ok, list(self.capabilities),
                              "No key needed. Unofficial source; fine for personal research, not point-in-time fundamentals.")

    def daily_prices(self, symbol: str, exchange: str, start: date, end: date | None = None) -> PriceData:
        ticker = to_yahoo(symbol, exchange)
        t = self.yf.Ticker(ticker)
        try:
            hist = t.history(start=start.isoformat(), end=(end + timedelta(days=1)).isoformat() if end else None,
                             interval="1d", auto_adjust=False, actions=True)
        except Exception as exc:  # yfinance raises a variety of exception types
            raise ProviderError(f"yahoo history failed for {ticker}: {type(exc).__name__}: {exc}") from exc
        if hist is None or hist.empty:
            raise ProviderError(f"yahoo returned no rows for {ticker}")
        currency = None
        try:
            currency = (t.history_metadata or {}).get("currency")
        except Exception:
            pass
        return self.parse_history(symbol, hist, currency)

    @staticmethod
    def parse_history(symbol: str, hist: pd.DataFrame, currency: str | None) -> PriceData:
        df = hist.copy()
        idx = pd.to_datetime(df.index)
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_localize(None)
        df.index = idx.normalize().date
        rename = {"Open": "open", "High": "high", "Low": "low", "Close": "close",
                  "Adj Close": "adj_close", "Volume": "volume"}
        frame = df.rename(columns=rename)
        for col in ("open", "high", "low", "close", "adj_close", "volume"):
            if col not in frame:
                frame[col] = float("nan")
        divs = df["Dividends"][df["Dividends"] > 0] if "Dividends" in df else None
        splits = df["Stock Splits"][df["Stock Splits"] > 0] if "Stock Splits" in df else None
        meta = DatasetMeta(source="yahoo", currency=currency, unit="price per share", frequency="daily",
                           notes=[] if currency else ["currency not reported by provider"])
        return PriceData(symbol, frame[["open", "high", "low", "close", "adj_close", "volume"]], meta, divs, splits)

    def profile(self, symbol: str, exchange: str) -> SecurityProfile:
        ticker = to_yahoo(symbol, exchange)
        try:
            info = self.yf.Ticker(ticker).get_info() or {}
        except Exception as exc:
            raise ProviderError(f"yahoo profile failed for {ticker}: {exc}") from exc
        qt = (info.get("quoteType") or "").lower()
        return SecurityProfile(
            symbol=symbol.upper(), exchange=exchange.upper(),
            name=info.get("longName") or info.get("shortName"),
            currency=info.get("currency"),
            asset_type={"etf": "etf", "equity": "equity", "index": "index"}.get(qt, qt or "equity"),
            sector=info.get("sector"), subsector=info.get("industry"), country=info.get("country"),
            cik=None, meta=DatasetMeta(source="yahoo"),
        )
