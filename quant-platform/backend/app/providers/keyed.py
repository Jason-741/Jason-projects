"""Key-gated commercial providers: Alpha Vantage (prices) and Financial Modeling Prep (profiles).

These are implemented against the providers' documented response formats but could NOT be
exercised against the live APIs in the development environment. Treat them as unverified until
you run `python -m app.cli check-providers` with your own keys.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from .base import (DatasetMeta, PriceData, PriceProvider, ProfileProvider, ProviderError, ProviderNotConfigured,
                   ProviderStatus, SecurityProfile)
from .http import HttpClient, JsonCache, RateLimiter
from .symbols import is_canadian


class AlphaVantageProvider(PriceProvider):
    name = "alpha_vantage"
    capabilities = ("daily_prices_unadjusted",)
    URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str | None, cache: JsonCache | None = None):
        self.api_key = api_key
        # Free tier is heavily rate limited (documented as ~25 requests/day); keep calls sparse.
        self.client = HttpClient(RateLimiter(1, 15.0), cache=cache)

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, bool(self.api_key), list(self.capabilities),
                              "Backup price source. Free tier: very low daily request quota. Unverified in dev.",
                              requires=[] if self.api_key else ["ALPHA_VANTAGE_API_KEY"])

    def daily_prices(self, symbol: str, exchange: str, start: date, end: date | None = None) -> PriceData:
        if not self.api_key:
            raise ProviderNotConfigured("Set ALPHA_VANTAGE_API_KEY.")
        av_symbol = symbol.upper() + (".TRT" if is_canadian(exchange) else "")
        data = self.client.get_json(self.URL, params={"function": "TIME_SERIES_DAILY", "symbol": av_symbol,
                                                      "outputsize": "full", "apikey": self.api_key}, ttl_seconds=3600)
        return parse_alpha_vantage_daily(symbol, data, start, end)


def parse_alpha_vantage_daily(symbol: str, data: dict, start: date, end: date | None) -> PriceData:
    for k in ("Error Message", "Note", "Information"):
        if k in data:
            raise ProviderError(f"alpha_vantage: {str(data[k])[:200]}")
    ts = data.get("Time Series (Daily)")
    if not ts:
        raise ProviderError("alpha_vantage: unexpected response (no 'Time Series (Daily)')")
    rows = {date.fromisoformat(d): {"open": float(v["1. open"]), "high": float(v["2. high"]), "low": float(v["3. low"]),
                                    "close": float(v["4. close"]), "volume": float(v["5. volume"])}
            for d, v in ts.items()}
    frame = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    frame = frame[(frame.index >= start) & ((frame.index <= end) if end else True)]
    frame["adj_close"] = float("nan")  # unadjusted endpoint: adjusted close NOT available
    meta = DatasetMeta(source="alpha_vantage", unit="price per share", frequency="daily",
                       notes=["unadjusted prices; adj_close unavailable", "currency not reported by endpoint"])
    return PriceData(symbol, frame[["open", "high", "low", "close", "adj_close", "volume"]], meta)


class FmpProvider(ProfileProvider):
    name = "fmp"
    capabilities = ("profile",)
    URL = "https://financialmodelingprep.com/stable/profile"

    def __init__(self, api_key: str | None, cache: JsonCache | None = None):
        self.api_key = api_key
        self.client = HttpClient(RateLimiter(4, 1.0), cache=cache)

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, bool(self.api_key), list(self.capabilities),
                              "Company profiles. Statements/estimates endpoints can be added behind the same interface. Unverified in dev.",
                              requires=[] if self.api_key else ["FMP_API_KEY"])

    def profile(self, symbol: str, exchange: str) -> SecurityProfile:
        if not self.api_key:
            raise ProviderNotConfigured("Set FMP_API_KEY.")
        fmp_symbol = symbol.upper().replace(".", "-") + (".TO" if is_canadian(exchange) else "")
        data = self.client.get_json(self.URL, params={"symbol": fmp_symbol, "apikey": self.api_key}, ttl_seconds=86400)
        if not data:
            raise ProviderError(f"fmp: no profile for {fmp_symbol}")
        row = data[0] if isinstance(data, list) else data
        return SecurityProfile(symbol=symbol.upper(), exchange=exchange.upper(), name=row.get("companyName"),
                               currency=row.get("currency"), asset_type="etf" if row.get("isEtf") else "equity",
                               sector=row.get("sector"), subsector=row.get("industry"), country=row.get("country"),
                               cik=row.get("cik"), meta=DatasetMeta(source="fmp"))
