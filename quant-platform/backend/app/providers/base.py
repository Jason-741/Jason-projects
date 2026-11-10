"""Provider interfaces and the provenance-carrying result containers they return."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import pandas as pd


class ProviderError(RuntimeError):
    """Raised for provider failures. Callers record the failure; nothing is silently substituted."""


class ProviderNotConfigured(ProviderError):
    """The provider needs an API key / setting that is not present."""


@dataclass
class DatasetMeta:
    source: str
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    currency: str | None = None
    unit: str | None = None
    frequency: str | None = None
    nature: str = "actual"
    notes: list[str] = field(default_factory=list)


@dataclass
class PriceData:
    """Daily bars indexed by date with columns open, high, low, close, adj_close, volume."""
    symbol: str
    frame: pd.DataFrame
    meta: DatasetMeta
    dividends: pd.Series | None = None   # cash per share, indexed by ex-date
    splits: pd.Series | None = None      # ratio new/old, indexed by ex-date


@dataclass
class SecurityProfile:
    symbol: str
    exchange: str
    name: str | None
    currency: str | None
    asset_type: str
    sector: str | None
    subsector: str | None
    country: str | None
    cik: str | None
    meta: DatasetMeta


@dataclass
class Fact:
    metric: str
    value: float
    period_end: date
    period_type: str
    unit: str
    currency: str | None
    period_start: date | None = None
    fiscal_year: int | None = None
    available_at: date | None = None
    form: str | None = None
    accession: str = ""
    source_tag: str | None = None
    statement: str | None = None


@dataclass
class FactSet:
    symbol: str
    facts: list[Fact]
    meta: DatasetMeta


@dataclass
class SeriesData:
    series_id: str
    frame: pd.Series
    meta: DatasetMeta
    title: str | None = None


@dataclass
class ProviderStatus:
    name: str
    configured: bool
    capabilities: list[str]
    detail: str
    requires: list[str] = field(default_factory=list)


class Provider(ABC):
    name: str = "base"
    capabilities: tuple[str, ...] = ()

    @abstractmethod
    def status(self) -> ProviderStatus: ...


class PriceProvider(Provider):
    @abstractmethod
    def daily_prices(self, symbol: str, exchange: str, start: date, end: date | None = None) -> PriceData: ...


class ProfileProvider(Provider):
    @abstractmethod
    def profile(self, symbol: str, exchange: str) -> SecurityProfile: ...


class FundamentalsProvider(Provider):
    @abstractmethod
    def facts(self, symbol: str, exchange: str) -> FactSet: ...


class MacroProvider(Provider):
    @abstractmethod
    def series(self, series_id: str, start: date | None = None) -> SeriesData: ...
