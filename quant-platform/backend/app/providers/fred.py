"""FRED (St. Louis Fed) macro series. Free API key: https://fred.stlouisfed.org/docs/api/api_key.html"""
from __future__ import annotations

from datetime import date

import pandas as pd

from .base import DatasetMeta, MacroProvider, ProviderNotConfigured, ProviderStatus, SeriesData
from .http import HttpClient, JsonCache, RateLimiter

USEFUL_SERIES = {
    "DGS10": "US 10-year Treasury yield (%)",
    "DGS3MO": "US 3-month Treasury yield (%) — risk-free proxy",
    "DEXCAUS": "CAD per USD, daily noon rate",
    "CPIAUCSL": "US CPI (index)",
    "DCOILWTICO": "WTI crude spot (USD/bbl)",
    "PCOPPUSDM": "Global copper price (USD/metric ton, monthly, IMF)",
    "IRLTLT01CAM156N": "Canada long-term government bond yield (%)",
}


class FredProvider(MacroProvider):
    name = "fred"
    capabilities = ("macro_series", "rates", "fx_cad_usd", "commodity_prices_monthly")
    BASE = "https://api.stlouisfed.org/fred"

    def __init__(self, api_key: str | None, cache: JsonCache | None = None):
        self.api_key = api_key
        self.client = HttpClient(RateLimiter(2, 1.0), cache=cache)

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, bool(self.api_key), list(self.capabilities),
                              "Official macro data (rates, FX, CPI, some commodity series).",
                              requires=[] if self.api_key else ["FRED_API_KEY"])

    def series(self, series_id: str, start: date | None = None) -> SeriesData:
        if not self.api_key:
            raise ProviderNotConfigured("Set FRED_API_KEY to enable FRED.")
        params = {"series_id": series_id, "api_key": self.api_key, "file_type": "json"}
        info = self.client.get_json(f"{self.BASE}/series", params=params, ttl_seconds=86400)
        if start:
            params["observation_start"] = start.isoformat()
        obs = self.client.get_json(f"{self.BASE}/series/observations", params=params, ttl_seconds=3600)
        return parse_fred(series_id, info, obs)


def parse_fred(series_id: str, info: dict, obs: dict) -> SeriesData:
    meta_row = (info.get("seriess") or [{}])[0]
    values = {}
    for o in obs.get("observations", []):
        v = o.get("value")
        values[date.fromisoformat(o["date"])] = None if v in (None, ".", "") else float(v)
    s = pd.Series(values, dtype="float64").sort_index()
    meta = DatasetMeta(source="fred", unit=meta_row.get("units"), frequency=meta_row.get("frequency"),
                       notes=[f"{int(s.isna().sum())} missing observations reported as '.'"] if s.isna().any() else [])
    return SeriesData(series_id, s, meta, title=meta_row.get("title"))
