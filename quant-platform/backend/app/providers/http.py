"""Shared HTTP plumbing: per-host rate limiting, retries with backoff, and an on-disk JSON cache."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import httpx

from .base import ProviderError


class RateLimiter:
    """Simple token bucket: at most `rate` calls per `per` seconds (thread-safe)."""

    def __init__(self, rate: int, per: float = 1.0):
        self.rate, self.per = rate, per
        self.allowance = float(rate)
        self.last = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        with self.lock:
            now = time.monotonic()
            self.allowance = min(self.rate, self.allowance + (now - self.last) * self.rate / self.per)
            self.last = now
            if self.allowance < 1.0:
                wait = (1.0 - self.allowance) * self.per / self.rate
                time.sleep(wait)
                self.allowance = 0.0
                self.last = time.monotonic()
            else:
                self.allowance -= 1.0


class JsonCache:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, key: str) -> Path:
        return self.root / f"{hashlib.sha256(key.encode()).hexdigest()}.json"

    def get(self, key: str, ttl_seconds: float):
        p = self._path(key)
        if not p.exists() or (time.time() - p.stat().st_mtime) > ttl_seconds:
            return None
        try:
            return json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def set(self, key: str, value) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._path(key).write_text(json.dumps(value))


class HttpClient:
    def __init__(self, limiter: RateLimiter, headers: dict | None = None, cache: JsonCache | None = None,
                 timeout: float = 30.0, retries: int = 3):
        self.limiter, self.headers, self.cache = limiter, headers or {}, cache
        self.timeout, self.retries = timeout, retries

    def get_json(self, url: str, params: dict | None = None, ttl_seconds: float = 0,
                 redact_params: tuple[str, ...] = ("apikey", "api_key")) -> dict | list:
        # Cache key never includes secrets.
        safe = {k: v for k, v in (params or {}).items() if k.lower() not in redact_params}
        key = url + "?" + json.dumps(safe, sort_keys=True)
        if self.cache and ttl_seconds > 0:
            hit = self.cache.get(key, ttl_seconds)
            if hit is not None:
                return hit
        last_exc: Exception | None = None
        for attempt in range(self.retries):
            self.limiter.acquire()
            try:
                r = httpx.get(url, params=params, headers=self.headers, timeout=self.timeout, follow_redirects=True)
                if r.status_code == 429 or r.status_code >= 500:
                    raise ProviderError(f"HTTP {r.status_code} from {httpx.URL(url).host}")
                if r.status_code >= 400:
                    # Client errors are not retried; message excludes query params (may hold keys).
                    raise ProviderError(f"HTTP {r.status_code} from {httpx.URL(url).host}{httpx.URL(url).path}")
                data = r.json()
                if self.cache and ttl_seconds > 0:
                    self.cache.set(key, data)
                return data
            except ProviderError as exc:
                last_exc = exc
                if "HTTP 4" in str(exc) and "429" not in str(exc):
                    raise
            except (httpx.HTTPError, ValueError) as exc:
                last_exc = ProviderError(f"{type(exc).__name__} contacting {httpx.URL(url).host}")
            time.sleep(min(2 ** attempt, 8))
        raise last_exc or ProviderError("request failed")
