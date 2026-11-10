from datetime import date

import pandas as pd
import pytest

from app.providers.keyed import parse_alpha_vantage_daily
from app.providers.base import ProviderError
from app.providers.fred import parse_fred
from app.providers.sec_edgar import parse_company_facts, parse_submissions
from app.providers.symbols import from_yahoo, to_yahoo
from app.providers.yahoo import YahooProvider
from app.services.validation import validate_prices

# Structure mirrors SEC companyfacts JSON; values are illustrative test inputs, not real filings.
FACTS = {
    "cik": 1, "entityName": "TEST CO",
    "facts": {
        "us-gaap": {
            "Revenues": {"units": {"USD": [
                {"start": "2023-01-01", "end": "2023-12-31", "val": 1000, "accn": "A1", "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-20"},
                {"start": "2023-01-01", "end": "2023-12-31", "val": 1010, "accn": "A2", "fy": 2024, "fp": "FY", "form": "10-K", "filed": "2025-02-20"},
                {"start": "2024-01-01", "end": "2024-03-31", "val": 260, "accn": "Q1", "fy": 2024, "fp": "Q1", "form": "10-Q", "filed": "2024-05-01"},
            ]}},
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
                {"start": "2023-01-01", "end": "2023-12-31", "val": 999, "accn": "A1", "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-20"}]}},
            "Assets": {"units": {"USD": [{"end": "2023-12-31", "val": 5000, "accn": "A1", "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-20"}]}},
            "EarningsPerShareDiluted": {"units": {"USD/shares": [
                {"start": "2023-01-01", "end": "2023-12-31", "val": 1.5, "accn": "A1", "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-20"}]}},
        }
    },
}


def test_sec_parser_priority_period_types_and_filing_dates():
    facts = parse_company_facts("TST", FACTS)
    rev = [f for f in facts if f.metric == "revenue"]
    fy_a1 = [f for f in rev if f.accession == "A1"][0]
    assert fy_a1.value == 1000 and fy_a1.source_tag == "us-gaap:Revenues"   # priority tag wins over 999
    assert fy_a1.available_at == date(2024, 2, 20) and fy_a1.period_type == "FY"
    assert any(f.period_type == "Q1" for f in rev)
    assets = [f for f in facts if f.metric == "total_assets"][0]
    assert assets.period_type == "INSTANT"
    eps = [f for f in facts if f.metric == "eps_diluted"][0]
    assert eps.unit == "USD/shares" and eps.currency == "USD"


def test_point_in_time_selection(tmp_path):
    from sqlalchemy.orm import sessionmaker

    from app.db import Base, make_engine
    from app.models import FundamentalFact, Security
    from app.services.market_data import facts_as_of
    eng = make_engine(f"sqlite:///{tmp_path}/pit.db")
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    sec = Security(symbol="TST", exchange="US")
    db.add(sec)
    db.flush()
    for f in parse_company_facts("TST", FACTS):
        db.add(FundamentalFact(security_id=sec.id, metric=f.metric, period_end=f.period_end, period_type=f.period_type,
                               value=f.value, available_at=f.available_at, accession=f.accession, source="sec_edgar"))
    db.commit()
    before_restatement = {(f.metric, f.period_type): f.value for f in facts_as_of(db, sec.id, date(2024, 6, 1))}
    assert before_restatement[("revenue", "FY")] == 1000
    after = {(f.metric, f.period_type): f.value for f in facts_as_of(db, sec.id, date(2025, 6, 1))}
    assert after[("revenue", "FY")] == 1010      # restated value only once it was public
    too_early = facts_as_of(db, sec.id, date(2024, 1, 1))
    assert too_early == []                       # nothing was filed yet → no look-ahead


def test_submissions_parser():
    sub = {"filings": {"recent": {"form": ["10-K", "4", "8-K"], "accessionNumber": ["0001-24-000001", "x", "0001-24-000002"],
                                  "filingDate": ["2024-02-01", "2024-02-02", "2024-03-01"], "reportDate": ["2023-12-31", "", ""],
                                  "primaryDocument": ["a10k.htm", "f4.xml", "e8k.htm"]}}}
    out = parse_submissions("0000000123", sub, ("10-K", "8-K"))
    assert [o["form"] for o in out] == ["10-K", "8-K"]
    assert out[0]["url"].endswith("/123/000124000001/a10k.htm")


def test_fred_parser_missing_values():
    s = parse_fred("DGS10", {"seriess": [{"units": "Percent", "frequency": "Daily", "title": "10Y"}]},
                   {"observations": [{"date": "2024-01-02", "value": "3.9"}, {"date": "2024-01-03", "value": "."}]})
    assert s.frame.isna().sum() == 1 and s.meta.unit == "Percent" and s.meta.notes


def test_alpha_vantage_parser_and_errors():
    data = {"Time Series (Daily)": {"2024-01-03": {"1. open": "1", "2. high": "2", "3. low": "0.5", "4. close": "1.5", "5. volume": "10"},
                                    "2024-01-02": {"1. open": "1", "2. high": "1", "3. low": "1", "4. close": "1", "5. volume": "5"}}}
    p = parse_alpha_vantage_daily("X", data, date(2024, 1, 1), None)
    assert list(p.frame.index) == [date(2024, 1, 2), date(2024, 1, 3)] and p.frame["adj_close"].isna().all()
    with pytest.raises(ProviderError):
        parse_alpha_vantage_daily("X", {"Note": "rate limited"}, date(2024, 1, 1), None)


def test_yahoo_history_parsing():
    idx = pd.DatetimeIndex(["2024-01-02", "2024-01-03"], tz="America/New_York")
    hist = pd.DataFrame({"Open": [1, 2], "High": [2, 3], "Low": [1, 1], "Close": [1.5, 2.5], "Adj Close": [1.4, 2.4],
                         "Volume": [100, 200], "Dividends": [0, 0.1], "Stock Splits": [0, 0]}, index=idx)
    pdata = YahooProvider.parse_history("X", hist, "USD")
    assert pdata.frame.index[0] == date(2024, 1, 2)
    assert pdata.dividends.iloc[0] == pytest.approx(0.1) and len(pdata.splits) == 0


def test_symbol_mapping():
    assert to_yahoo("TECK.B", "TSX") == "TECK-B.TO"
    assert to_yahoo("NXE", "TSXV") == "NXE.V"
    assert to_yahoo("BRK.B", "NYSE") == "BRK-B"
    assert from_yahoo("TECK-B.TO") == ("TECK.B", "TSX")
    assert from_yahoo("^GSPTSE") == ("^GSPTSE", "INDEX")


def test_validation_flags_problems():
    idx = list(pd.bdate_range("2024-01-01", periods=10).date)
    df = pd.DataFrame({"open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 1.0}, index=idx)
    status, issues = validate_prices(df)
    assert status == "valid" and not issues
    jump = df.copy()
    jump.iloc[5, jump.columns.get_loc("close")] = 30.0
    jump.iloc[5, jump.columns.get_loc("high")] = 31.0
    status, issues = validate_prices(jump)
    assert status == "warning" and any(i.code == "price_jump" for i in issues)
    gap = df.drop(df.index[3:9])
    assert any(i.code == "gaps" for i in validate_prices(gap)[1])
    dup = pd.concat([df, df.iloc[[0]]])
    assert validate_prices(dup)[0] == "rejected"
    bad = df.copy()
    bad.iloc[2, bad.columns.get_loc("high")] = 5.0
    assert any(i.code == "high_below_low" for i in validate_prices(bad)[1])
