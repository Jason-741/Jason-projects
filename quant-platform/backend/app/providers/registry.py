"""Builds the configured providers. Swap or reorder vendors here without touching callers."""
from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .base import FundamentalsProvider, MacroProvider, PriceProvider, ProfileProvider, ProviderStatus
from .fred import FredProvider
from .http import JsonCache
from .keyed import AlphaVantageProvider, FmpProvider
from .sec_edgar import SecEdgarProvider
from .yahoo import YahooProvider


class Registry:
    def __init__(self, settings=None):
        s = settings or get_settings()
        cache = JsonCache(s.cache_dir / "http")
        self.yahoo = YahooProvider()
        self.sec = SecEdgarProvider(s.sec_user_agent, cache)
        self.fred = FredProvider(s.fred_api_key, cache)
        self.alpha_vantage = AlphaVantageProvider(s.alpha_vantage_api_key, cache)
        self.fmp = FmpProvider(s.fmp_api_key, cache)
        self.price_providers: list[PriceProvider] = [self.yahoo, self.alpha_vantage]
        self.profile_providers: list[ProfileProvider] = [self.fmp, self.yahoo]
        self.fundamentals_providers: list[FundamentalsProvider] = [self.sec]
        self.macro_providers: list[MacroProvider] = [self.fred]

    def all(self):
        return [self.yahoo, self.sec, self.fred, self.alpha_vantage, self.fmp]

    def statuses(self) -> list[ProviderStatus]:
        return [p.status() for p in self.all()]

    def get(self, name: str):
        for p in self.all():
            if p.name == name:
                return p
        raise KeyError(name)


@lru_cache
def get_registry() -> Registry:
    return Registry()
