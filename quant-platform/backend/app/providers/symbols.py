"""Provider-neutral symbol handling. Internal form: SYMBOL + exchange, e.g. ("TECK.B", "TSX")."""
from __future__ import annotations

CANADIAN_EXCHANGES = {"TSX": ".TO", "TSXV": ".V", "CSE": ".CN", "NEO": ".NE"}
US_EXCHANGES = {"NYSE", "NASDAQ", "NYSEARCA", "AMEX", "ARCA", "BATS", "US", ""}


def to_yahoo(symbol: str, exchange: str) -> str:
    """Map internal symbol to Yahoo Finance ticker. ('TECK.B','TSX') -> 'TECK-B.TO'."""
    exchange = (exchange or "").upper()
    if exchange in ("INDEX", "FX", "FUTURES"):
        return symbol  # already in Yahoo form, e.g. ^GSPTSE, CAD=X, HG=F
    base = symbol.upper().replace(".", "-")
    if exchange in CANADIAN_EXCHANGES:
        return base + CANADIAN_EXCHANGES[exchange]
    return base


def from_yahoo(ticker: str) -> tuple[str, str]:
    t = ticker.upper()
    for exch, suffix in CANADIAN_EXCHANGES.items():
        if t.endswith(suffix.upper()):
            return t[: -len(suffix)].replace("-", "."), exch
    if t.startswith("^"):
        return t, "INDEX"
    if t.endswith("=X"):
        return t, "FX"
    if t.endswith("=F"):
        return t, "FUTURES"
    return t.replace("-", "."), "US"


def is_canadian(exchange: str) -> bool:
    return (exchange or "").upper() in CANADIAN_EXCHANGES
