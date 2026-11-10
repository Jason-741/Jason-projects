"""Broker CSV importers.

Wealthsimple does not offer an official public trading/account API for retail clients (as of
this writing), so this platform never logs into Wealthsimple and never stores brokerage
credentials. Data comes in via files you download yourself.

Two formats are supported:

1. `generic` — the platform's own fully specified template (docs/IMPORT_FORMAT.md):
     date,type,symbol,quantity,price,currency,fees,fx_rate_to_base,amount,counter_currency,counter_amount,reference,note
2. `wealthsimple_activity` — BEST-EFFORT parser for Wealthsimple's account activity/statement
   CSV (columns like date, transaction, description, amount, balance, currency). Wealthsimple
   changes these exports over time; ALWAYS run a dry-run preview and check unparsed rows.

Every row gets a deterministic `external_ref` (hash of the raw row) so re-importing the same file
does not duplicate transactions.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

VALID_TYPES = {"buy", "sell", "dividend", "deposit", "withdrawal", "fee", "interest", "split", "fx"}


@dataclass
class ParsedRow:
    ts: datetime
    tx_type: str
    symbol: str | None = None
    quantity: float = 0.0
    price: float = 0.0
    currency: str = "CAD"
    fees: float = 0.0
    fx_rate_to_base: float | None = None
    amount: float = 0.0
    counter_currency: str | None = None
    counter_amount: float | None = None
    external_ref: str = ""
    note: str | None = None


@dataclass
class ImportResult:
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    format: str = ""


def _num(v, default=0.0):
    if v is None:
        return default
    s = str(v).strip().replace(",", "").replace("$", "")
    if s == "":
        return default
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    return float(s)


def _date(v: str) -> datetime:
    s = v.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(f"unrecognized date '{v}'") from exc


def _ref(fmt: str, row: dict, line_no: int) -> str:
    raw = fmt + "|" + "|".join(f"{k}={row[k]}" for k in sorted(row))
    return f"{fmt}:{hashlib.sha256(raw.encode()).hexdigest()[:32]}"


def detect_format(header: list[str]) -> str:
    h = {c.strip().lower() for c in header}
    if {"date", "type", "symbol", "quantity", "price"} <= h:
        return "generic"
    if {"date", "transaction", "description", "amount"} <= h:
        return "wealthsimple_activity"
    return "unknown"


def parse_csv(text: str, fmt: str | None = None, base_currency: str = "CAD") -> ImportResult:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    header = reader.fieldnames or []
    fmt = fmt or detect_format(header)
    res = ImportResult(format=fmt)
    if fmt == "unknown":
        res.errors.append({"line": 1, "error": f"unrecognized header {header}; use the generic template"})
        return res
    seen = set()
    for i, raw in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        if not any(row.values()):
            continue
        try:
            parsed = _parse_generic(row) if fmt == "generic" else _parse_ws(row, base_currency)
        except (ValueError, KeyError) as exc:
            res.errors.append({"line": i, "error": str(exc), "row": row})
            continue
        if parsed is None:
            res.skipped.append({"line": i, "reason": "row type not imported (informational)", "row": row})
            continue
        parsed.external_ref = row.get("reference") or _ref(fmt, row, i)
        if parsed.external_ref in seen:  # identical duplicate lines in the same file
            parsed.external_ref += f"#L{i}"
        seen.add(parsed.external_ref)
        res.rows.append(parsed)
    return res


def _parse_generic(row: dict) -> ParsedRow:
    t = row["type"].lower()
    if t not in VALID_TYPES:
        raise ValueError(f"type '{t}' not in {sorted(VALID_TYPES)}")
    p = ParsedRow(ts=_date(row["date"]), tx_type=t, symbol=(row.get("symbol") or None),
                  quantity=_num(row.get("quantity")), price=_num(row.get("price")),
                  currency=(row.get("currency") or "CAD").upper(), fees=abs(_num(row.get("fees"))),
                  fx_rate_to_base=_num(row.get("fx_rate_to_base"), None) if row.get("fx_rate_to_base") else None,
                  amount=abs(_num(row.get("amount"))), counter_currency=(row.get("counter_currency") or None),
                  counter_amount=_num(row.get("counter_amount"), None) if row.get("counter_amount") else None,
                  note=row.get("note") or None)
    if p.symbol:
        p.symbol = p.symbol.upper()
    if t in ("buy", "sell") and (p.quantity <= 0 or p.price <= 0 or not p.symbol):
        raise ValueError("buy/sell rows need symbol, positive quantity and price")
    if t in ("buy", "sell"):
        p.amount = p.quantity * p.price
    if t == "split" and p.quantity <= 0:
        raise ValueError("split rows need quantity = ratio (new shares per old share)")
    return p


# Wealthsimple activity descriptions look like:
#   "VFV - Vanguard S&P 500 Index ETF: Bought 0.2500 shares (executed at 2024-03-01)"
#   "AAPL - Apple Inc.: Sold 1.0000 shares (executed at 2024-03-01), FX Rate: 1.3550"
_TRADE_RE = re.compile(r"^(?P<sym>[A-Z0-9.\-]+)\s*-\s*.*?:\s*(?P<side>Bought|Sold)\s+(?P<qty>[\d.,]+)\s+shares?"
                       r"(?:.*?FX Rate:\s*(?P<fx>[\d.]+))?", re.I)
_DIV_RE = re.compile(r"^(?P<sym>[A-Z0-9.\-]+)\s*-", re.I)
_WS_TYPES = {
    "BUY": "buy", "SELL": "sell", "DIV": "dividend", "DIVIDEND": "dividend",
    "CONT": "deposit", "DEP": "deposit", "DEPOSIT": "deposit", "EFT": "deposit", "TRFIN": "deposit",
    "WD": "withdrawal", "WITHDRAWAL": "withdrawal", "TRFOUT": "withdrawal",
    "FEE": "fee", "INT": "interest", "FPLINT": "interest", "INTEREST": "interest",
}


def _parse_ws(row: dict, base_currency: str) -> ParsedRow | None:
    code = row["transaction"].upper().strip()
    t = _WS_TYPES.get(code)
    if t is None:
        return None
    amount = _num(row["amount"])
    cur = (row.get("currency") or base_currency).upper()
    desc = row.get("description", "")
    ts = _date(row["date"])
    if t in ("buy", "sell"):
        m = _TRADE_RE.search(desc)
        if not m:
            raise ValueError(f"could not parse trade description: {desc[:120]}")
        qty = _num(m.group("qty"))
        if qty <= 0:
            raise ValueError("trade quantity is zero")
        # Wealthsimple reports the cash amount in account currency; price = |amount| / qty.
        price = abs(amount) / qty
        fx = float(m.group("fx")) if m.group("fx") else None
        note = "price derived from cash amount / quantity (includes any FX spread embedded by broker)"
        return ParsedRow(ts=ts, tx_type=t, symbol=m.group("sym").upper(), quantity=qty, price=price, currency=cur,
                         amount=abs(amount), fx_rate_to_base=None if cur == base_currency else fx, note=note + (f"; FX {fx}" if fx else ""))
    if t == "dividend":
        m = _DIV_RE.search(desc)
        return ParsedRow(ts=ts, tx_type=t, symbol=m.group("sym").upper() if m else None, amount=abs(amount), currency=cur,
                         note=desc[:200] or None)
    return ParsedRow(ts=ts, tx_type=t, amount=abs(amount), currency=cur, note=desc[:200] or None)


GENERIC_TEMPLATE = (
    "date,type,symbol,quantity,price,currency,fees,fx_rate_to_base,amount,counter_currency,counter_amount,reference,note\n"
    "2026-01-05,deposit,,,,CAD,,,100.00,,,,initial contribution\n"
    "2026-01-06,buy,XEQT,2.5,32.10,CAD,0,,,,,,example only - replace with your fills\n"
)
