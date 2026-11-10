"""Application configuration.

All secrets come from environment variables (optionally a local `.env` file that is
git-ignored). Nothing secret is hard-coded. Missing provider keys simply disable that
provider; the rest of the platform keeps working and reports the provider as
"not configured" instead of pretending it works.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines). Existing env vars win."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str
    token_ttl_minutes: int
    cors_origins: list[str]
    sec_user_agent: str | None
    fred_api_key: str | None
    fmp_api_key: str | None
    alpha_vantage_api_key: str | None
    cache_dir: Path
    base_currency: str = "CAD"
    allow_registration: bool = True
    extra: dict = field(default_factory=dict)


@lru_cache
def get_settings() -> Settings:
    backend_dir = Path(__file__).resolve().parent.parent
    _load_dotenv(backend_dir / ".env")
    secret = os.getenv("APP_SECRET_KEY")
    if not secret:
        # Development fallback: random per-process key. Tokens are invalidated on restart,
        # which is the safe failure mode. Production must set APP_SECRET_KEY.
        secret = os.urandom(32).hex()
    return Settings(
        database_url=os.getenv("DATABASE_URL", f"sqlite:///{backend_dir / 'quant.db'}"),
        secret_key=secret,
        token_ttl_minutes=int(os.getenv("TOKEN_TTL_MINUTES", "720")),
        cors_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
        sec_user_agent=os.getenv("SEC_USER_AGENT") or None,
        fred_api_key=os.getenv("FRED_API_KEY") or None,
        fmp_api_key=os.getenv("FMP_API_KEY") or None,
        alpha_vantage_api_key=os.getenv("ALPHA_VANTAGE_API_KEY") or None,
        cache_dir=Path(os.getenv("CACHE_DIR", str(backend_dir / ".cache"))),
        base_currency=os.getenv("BASE_CURRENCY", "CAD"),
        allow_registration=os.getenv("ALLOW_REGISTRATION", "true").lower() == "true",
    )
