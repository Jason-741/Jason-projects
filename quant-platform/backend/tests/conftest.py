"""Test configuration. Uses an isolated temporary SQLite database.

All price data in tests is SYNTHETIC (seeded random walks) or hand-constructed so that results can
be checked independently. It is never written to the application database.
"""
import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="quant-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["APP_SECRET_KEY"] = "test-secret-key-not-for-production-0123456789"
os.environ["CACHE_DIR"] = f"{_tmp}/cache"
for k in ("SEC_USER_AGENT", "FRED_API_KEY", "FMP_API_KEY", "ALPHA_VANTAGE_API_KEY", "ANTHROPIC_API_KEY"):
    os.environ.pop(k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402


def synthetic_prices(n=800, symbols=("AAA", "BBB", "CCC"), seed=7, drift=0.0003, vol=0.015, start="2020-01-01"):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    data = {}
    for i, s in enumerate(symbols):
        r = rng.normal(drift * (1 + 0.5 * i), vol * (1 + 0.3 * i), n)
        data[s] = 50 * np.exp(np.cumsum(r))
    return pd.DataFrame(data, index=idx)


@pytest.fixture
def prices():
    return synthetic_prices()


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.db import init_db
    from app.main import app
    init_db()
    with TestClient(app) as c:
        r = c.post("/api/auth/register", json={"username": "tester", "password": "correct-horse-battery"})
        assert r.status_code == 200, r.text
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c
