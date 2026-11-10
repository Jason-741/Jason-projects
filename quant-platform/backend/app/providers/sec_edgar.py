"""SEC EDGAR XBRL "company facts" — free, official, and point-in-time (each fact has a filing date).

SEC fair-access policy: max 10 requests/second and a User-Agent that identifies you with a
contact email. Configure SEC_USER_AGENT="Your Name your@email". Without it the provider is
reported as not configured rather than sending anonymous traffic.

Coverage: US domestic filers (10-K/10-Q, us-gaap taxonomy) and foreign filers that submit XBRL
(20-F/40-F, often ifrs-full taxonomy). Many Canadian juniors file only on SEDAR+ and are NOT
covered here — see docs/DATA_SOURCES.md for the SEDAR+ manual-document workflow.
"""
from __future__ import annotations

from datetime import date

from .base import DatasetMeta, Fact, FactSet, FundamentalsProvider, ProviderError, ProviderNotConfigured, ProviderStatus
from .http import HttpClient, JsonCache, RateLimiter

# normalized metric -> (statement, [candidate tags in priority order])
# us-gaap tags are standard; ifrs-full tags follow the IFRS taxonomy and should be spot-checked
# against a filer's actual companyfacts response before relying on them.
TAG_MAP: dict[str, tuple[str, list[str]]] = {
    "revenue": ("IS", ["us-gaap:Revenues", "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                       "us-gaap:SalesRevenueNet", "ifrs-full:Revenue", "ifrs-full:RevenueFromContractsWithCustomers"]),
    "cost_of_revenue": ("IS", ["us-gaap:CostOfRevenue", "us-gaap:CostOfGoodsAndServicesSold", "ifrs-full:CostOfSales"]),
    "gross_profit": ("IS", ["us-gaap:GrossProfit", "ifrs-full:GrossProfit"]),
    "operating_income": ("IS", ["us-gaap:OperatingIncomeLoss", "ifrs-full:ProfitLossFromOperatingActivities"]),
    "pretax_income": ("IS", ["us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                             "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
                             "ifrs-full:ProfitLossBeforeTax"]),
    "income_tax": ("IS", ["us-gaap:IncomeTaxExpenseBenefit", "ifrs-full:IncomeTaxExpenseContinuingOperations"]),
    "net_income": ("IS", ["us-gaap:NetIncomeLoss", "ifrs-full:ProfitLossAttributableToOwnersOfParent", "ifrs-full:ProfitLoss"]),
    "interest_expense": ("IS", ["us-gaap:InterestExpense", "us-gaap:InterestExpenseNonoperating", "ifrs-full:FinanceCosts"]),
    "d_and_a": ("CF", ["us-gaap:DepreciationDepletionAndAmortization", "us-gaap:DepreciationAndAmortization",
                       "us-gaap:DepreciationAmortizationAndAccretionNet", "ifrs-full:DepreciationAndAmortisationExpense"]),
    "eps_basic": ("IS", ["us-gaap:EarningsPerShareBasic", "ifrs-full:BasicEarningsLossPerShare"]),
    "eps_diluted": ("IS", ["us-gaap:EarningsPerShareDiluted", "ifrs-full:DilutedEarningsLossPerShare"]),
    "shares_diluted": ("IS", ["us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
                              "ifrs-full:AdjustedWeightedAverageShares"]),
    "cash": ("BS", ["us-gaap:CashAndCashEquivalentsAtCarryingValue", "ifrs-full:CashAndCashEquivalents"]),
    "inventory": ("BS", ["us-gaap:InventoryNet", "ifrs-full:Inventories"]),
    "current_assets": ("BS", ["us-gaap:AssetsCurrent", "ifrs-full:CurrentAssets"]),
    "total_assets": ("BS", ["us-gaap:Assets", "ifrs-full:Assets"]),
    "current_liabilities": ("BS", ["us-gaap:LiabilitiesCurrent", "ifrs-full:CurrentLiabilities"]),
    "total_liabilities": ("BS", ["us-gaap:Liabilities", "ifrs-full:Liabilities"]),
    "long_term_debt": ("BS", ["us-gaap:LongTermDebtNoncurrent", "us-gaap:LongTermDebt", "ifrs-full:NoncurrentPortionOfNoncurrentLoansReceived",
                              "ifrs-full:LongtermBorrowings"]),
    "short_term_debt": ("BS", ["us-gaap:LongTermDebtCurrent", "us-gaap:DebtCurrent", "us-gaap:ShortTermBorrowings",
                               "ifrs-full:CurrentPortionOfLongtermBorrowings", "ifrs-full:ShorttermBorrowings"]),
    "goodwill": ("BS", ["us-gaap:Goodwill", "ifrs-full:Goodwill"]),
    "equity": ("BS", ["us-gaap:StockholdersEquity", "ifrs-full:EquityAttributableToOwnersOfParent"]),
    "operating_cash_flow": ("CF", ["us-gaap:NetCashProvidedByUsedInOperatingActivities", "ifrs-full:CashFlowsFromUsedInOperatingActivities"]),
    "capex": ("CF", ["us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
                     "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"]),
    "dividends_paid": ("CF", ["us-gaap:PaymentsOfDividends", "us-gaap:PaymentsOfDividendsCommonStock",
                              "ifrs-full:DividendsPaidClassifiedAsFinancingActivities"]),
    "buybacks": ("CF", ["us-gaap:PaymentsForRepurchaseOfCommonStock", "ifrs-full:PaymentsToAcquireOrRedeemEntitysShares"]),
    "financing_cash_flow": ("CF", ["us-gaap:NetCashProvidedByUsedInFinancingActivities",
                                   "ifrs-full:CashFlowsFromUsedInFinancingActivities"]),
    "shares_outstanding": ("BS", ["dei:EntityCommonStockSharesOutstanding"]),
}


def _period_type(start: date | None, end: date, fp: str | None) -> str:
    if start is None:
        return "INSTANT"
    days = (end - start).days
    if days >= 340:
        return "FY"
    if 80 <= days <= 100:
        return fp if fp in ("Q1", "Q2", "Q3", "Q4") else "Q"
    return f"D{days}"  # non-standard duration (e.g. 6- or 9-month YTD) — kept but labeled


def parse_company_facts(symbol: str, payload: dict) -> list[Fact]:
    """Turn a companyfacts JSON document into normalized, point-in-time Facts.

    Priority tags win when several tags report the same (metric, period, filing).
    """
    facts_root = payload.get("facts", {})
    out: dict[tuple, Fact] = {}
    for metric, (stmt, tags) in TAG_MAP.items():
        for priority, full_tag in enumerate(tags):
            taxonomy, tag = full_tag.split(":", 1)
            node = facts_root.get(taxonomy, {}).get(tag)
            if not node:
                continue
            for unit, rows in node.get("units", {}).items():
                currency = unit if len(unit) == 3 and unit.isupper() else (unit.split("/")[0] if "/" in unit else None)
                for row in rows:
                    try:
                        end = date.fromisoformat(row["end"])
                        start = date.fromisoformat(row["start"]) if row.get("start") else None
                        filed = date.fromisoformat(row["filed"]) if row.get("filed") else None
                        value = float(row["val"])
                    except (KeyError, ValueError, TypeError):
                        continue
                    ptype = _period_type(start, end, row.get("fp"))
                    key = (metric, end, ptype, row.get("accn", ""))
                    existing = out.get(key)
                    if existing is not None and existing._priority <= priority:  # type: ignore[attr-defined]
                        continue
                    f = Fact(metric=metric, value=value, period_end=end, period_type=ptype, unit=unit,
                             currency=currency if stmt != "BS" or metric != "shares_outstanding" else None,
                             period_start=start, fiscal_year=row.get("fy"), available_at=filed,
                             form=row.get("form"), accession=row.get("accn", ""), source_tag=full_tag, statement=stmt)
                    f._priority = priority  # type: ignore[attr-defined]
                    out[key] = f
    return sorted(out.values(), key=lambda f: (f.metric, f.period_end, f.available_at or date.min))


class SecEdgarProvider(FundamentalsProvider):
    name = "sec_edgar"
    capabilities = ("fundamentals_point_in_time", "filings_index", "cik_lookup")
    TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
    FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

    def __init__(self, user_agent: str | None, cache: JsonCache | None = None):
        self.user_agent = user_agent
        self.client = HttpClient(RateLimiter(8, 1.0), headers={"User-Agent": user_agent or ""}, cache=cache)

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, bool(self.user_agent), list(self.capabilities),
                              "Official SEC XBRL data with filing dates (point-in-time). US/SEC filers only.",
                              requires=[] if self.user_agent else ["SEC_USER_AGENT"])

    def _require(self):
        if not self.user_agent:
            raise ProviderNotConfigured("Set SEC_USER_AGENT='Name email@example.com' (SEC fair-access policy).")

    def cik_for(self, symbol: str) -> str:
        self._require()
        data = self.client.get_json(self.TICKERS_URL, ttl_seconds=86400)
        sym = symbol.upper().replace(".", "-")
        for row in (data.values() if isinstance(data, dict) else data):
            if str(row.get("ticker", "")).upper() == sym:
                return str(row["cik_str"]).zfill(10)
        raise ProviderError(f"{symbol} not found in SEC ticker list (may not be an SEC registrant)")

    def facts(self, symbol: str, exchange: str) -> FactSet:
        cik = self.cik_for(symbol)
        payload = self.client.get_json(self.FACTS_URL.format(cik=cik), ttl_seconds=6 * 3600)
        facts = parse_company_facts(symbol, payload)
        meta = DatasetMeta(source="sec_edgar", frequency="quarterly/annual", unit="as reported",
                           notes=[f"CIK {cik}", "values as filed; restatements kept as separate rows"])
        return FactSet(symbol, facts, meta)

    def recent_filings(self, symbol: str, forms: tuple[str, ...] = ("10-K", "10-Q", "8-K", "20-F", "40-F", "6-K")) -> list[dict]:
        cik = self.cik_for(symbol)
        sub = self.client.get_json(self.SUBMISSIONS_URL.format(cik=cik), ttl_seconds=3600)
        return parse_submissions(cik, sub, forms)


def parse_submissions(cik: str, sub: dict, forms: tuple[str, ...]) -> list[dict]:
    recent = sub.get("filings", {}).get("recent", {})
    out = []
    for i, form in enumerate(recent.get("form", [])):
        if form not in forms:
            continue
        accn = recent["accessionNumber"][i]
        doc = recent.get("primaryDocument", [""] * (i + 1))[i]
        out.append({
            "form": form, "accession": accn, "filed": recent["filingDate"][i],
            "report_date": (recent.get("reportDate") or [None] * (i + 1))[i],
            "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{doc}",
            "source": "sec_edgar",
        })
    return out
