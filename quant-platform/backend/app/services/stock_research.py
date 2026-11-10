"""One-command research report for any ticker, built only from live provider data.

    python -m app.cli research SHOP.TO --out report.json

Steps: resolve the listing → ingest prices (Yahoo), profile, SEC fundamentals when the company
files with the SEC → compute price/risk statistics, statements and ratios, valuation multiples,
a reverse DCF under stated assumptions, a percentile score against the stored universe, and a
rule-based bull / bear / risk review. Every number in the report comes from those sources or is
derived from them with the methods in docs/METHODOLOGY.md; assumptions are listed in the report.
The conclusion is one of: "worth deeper research", "mixed evidence", "weak evidence" or
"insufficient evidence" — never a buy or sell instruction.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from ..analytics import dcf as D
from ..analytics import ranking
from ..analytics import ratios as R
from ..analytics import risk as RK
from ..analytics import signals as SG
from ..analytics.risk import clean
from ..providers.base import ProviderError
from ..providers.registry import Registry
from ..providers.symbols import from_yahoo
from . import ingestion
from .market_data import annual_statements, facts_as_of, find_security, price_frame, total_return_series
from .research_rank import build_ranking

SUFFIX_EXCH = {".TO": "TSX", ".V": "TSXV", ".CN": "CSE", ".NE": "NEO"}


def resolve(raw: str) -> list[tuple[str, str]]:
    """Candidate (symbol, exchange) listings to try, most likely first."""
    t = raw.strip().upper()
    if ":" in t:                                     # TSX:SHOP style
        ex, sym = t.split(":", 1)
        return [(sym, ex)]
    for suf in SUFFIX_EXCH:
        if t.endswith(suf):
            return [from_yahoo(t)]
    if t.startswith("^") or t.endswith("=X") or t.endswith("=F"):
        return [from_yahoo(t)]
    return [(t.replace("-", "."), "US"), (t.replace("-", "."), "TSX")]


def _ret(px: pd.Series, days: int):
    return float(px.iloc[-1] / px.iloc[-1 - days] - 1) if len(px) > days else None


def build_report(db: Session, reg: Registry, raw_ticker: str, start: date = date(2015, 1, 1),
                 refresh_universe: bool = True) -> dict:
    gaps, notes = [], []
    # 1. listing + prices
    sym = exch = None
    last_err = None
    for s, e in resolve(raw_ticker):
        run = ingestion.ingest_prices(db, reg, s, e, start, provider="yahoo")
        if run.status != "error":
            sym, exch = s, e
            break
        last_err = run.error
    if sym is None:
        return {"ticker": raw_ticker.upper(), "status": "not_found",
                "error": f"No price data found for {raw_ticker}. Check the ticker (for TSX add .TO, e.g. SHOP.TO). {last_err or ''}".strip()}
    try:
        prof = reg.yahoo.profile(sym, exch)
        ingestion.get_or_create_security(db, sym, exch, name=prof.name, currency=prof.currency, asset_type=prof.asset_type,
                                         sector=prof.sector, subsector=prof.subsector, country=prof.country, source="yahoo")
        db.commit()
    except ProviderError as exc:
        gaps.append(f"Company profile unavailable ({exc}).")
    sec = find_security(db, sym, exch)

    # 2. benchmarks, FX and (optionally) the peer universe for scoring
    bench_sym = "XIC" if exch in SUFFIX_EXCH.values() or sec.currency == "CAD" else "SPY"
    for s, e in ((bench_sym, "TSX" if bench_sym == "XIC" else "NYSEARCA"), ("CAD=X", "FX")):
        if not find_security(db, s, e):
            ingestion.ingest_prices(db, reg, s, e, start, provider="yahoo")
    ingestion.store_fx_from_prices(db)
    if refresh_universe:
        from ..universe import UNIVERSE
        for s, e, name, atype, sector, sub in UNIVERSE:
            if not find_security(db, s, e) or price_frame(db, find_security(db, s, e).id).empty:
                ingestion.get_or_create_security(db, s, e, name=name, asset_type=atype, sector=sector, subsector=sub, source="universe_seed")
                db.commit()
                ingestion.ingest_prices(db, reg, s, e, start, provider="yahoo")

    # 3. SEC fundamentals
    fund_run = None
    if sec.asset_type not in ("etf", "index", "fx", "commodity"):
        fund_run = ingestion.ingest_fundamentals(db, reg, sym, exch, sec_symbol=sym.replace(".", "-"))
        if fund_run.status == "error":
            gaps.append("No SEC filings found: the company may file only on SEDAR+ (Canada) or not at all. "
                        "Fundamentals, valuation multiples and the quality score are missing.")

    # 4. prices & risk
    df = price_frame(db, sec.id)
    px = total_return_series(df).dropna()
    px.index = pd.to_datetime(px.index)
    if px is df["close"]:
        notes.append("Adjusted prices unavailable; dividends excluded from returns.")
    rets = px.pct_change().dropna()
    bdf = price_frame(db, find_security(db, bench_sym).id) if find_security(db, bench_sym) else pd.DataFrame()
    bench = total_return_series(bdf).pct_change().dropna() if not bdf.empty else None
    if bench is not None:
        bench.index = pd.to_datetime(bench.index)
    summ = RK.summary(rets.tail(756), bench.tail(800) if bench is not None else None, 0.03)
    last_close = float(df["close"].dropna().iloc[-1])
    price = {
        "last": last_close, "currency": sec.currency, "as_of": str(px.index[-1].date()), "bars": int(len(px)),
        "first_date": str(px.index[0].date()),
        "returns": {"1m": _ret(px, 21), "3m": _ret(px, 63), "6m": _ret(px, 126), "1y": _ret(px, 252), "3y": _ret(px, 756),
                    "5y": _ret(px, 1260)},
        "high_52w": float(df["high"].tail(252).max()), "low_52w": float(df["low"].tail(252).min()),
        "risk_3y": {k: summ.get(k) for k in ("volatility", "max_drawdown", "sharpe", "sortino", "var_95_hist", "cvar_95_hist",
                                             "beta", "correlation", "cagr")},
        "benchmark": bench_sym,
        "signals": {"rsi14": float(SG.rsi(px).iloc[-1]) if len(px) > 15 else None,
                    "vs_sma50": float(px.iloc[-1] / px.tail(50).mean() - 1) if len(px) >= 50 else None,
                    "vs_sma200": float(px.iloc[-1] / px.tail(200).mean() - 1) if len(px) >= 200 else None,
                    "mom_12_1": float(SG.momentum(px).iloc[-1]) if len(px) > 253 else None},
        "avg_dollar_volume_60d": float((df["close"] * df["volume"]).tail(60).mean()) if df["volume"].notna().any() else None,
        "monthly": [(str(d.date()), float(v)) for d, v in px.resample("ME").last().tail(120).items()],
    }
    if len(px) < 252:
        gaps.append(f"Only {len(px)} trading days of history: risk statistics are unreliable.")

    # 5. fundamentals
    facts = facts_as_of(db, sec.id, None)
    table = annual_statements(facts, 5)
    fundamentals = None
    valuation = None
    if not table.empty:
        periods = [str(c) for c in table.columns]
        by_p = [{m: (None if v != v else v) for m, v in table[c].items()} for c in table.columns]
        ratios_by_p = {periods[i]: {k: v.value for k, v in R.statement_ratios(by_p[i], by_p[i - 1] if i else None).items()}
                       for i in range(len(periods))}
        cur_facts = [f for f in facts if str(f.period_end) == periods[-1] and f.currency]
        fact_ccy = max({f.currency for f in cur_facts}, key=lambda c: sum(f.currency == c for f in cur_facts)) if cur_facts else None
        filed = max((f.available_at for f in facts if str(f.period_end) == periods[-1] and f.available_at), default=None)
        fundamentals = {"periods": periods, "currency": fact_ccy, "latest_filed": str(filed) if filed else None,
                        "statements": {m: [r.get(m) for r in by_p] for m in
                                       ("revenue", "gross_profit", "operating_income", "net_income", "eps_diluted",
                                        "operating_cash_flow", "capex", "cash", "long_term_debt", "short_term_debt", "equity")
                                       if any(r.get(m) is not None for r in by_p)},
                        "derived": {m: [R.derived_items(r).get(m) for r in by_p] for m in ("ebitda", "free_cash_flow", "net_debt")},
                        "ratios": ratios_by_p,
                        "change_flags": R.flag_changes({m: [r.get(m) for r in by_p] for m in ("revenue", "net_income", "operating_cash_flow")})}
        # valuation: convert price to the reporting currency if needed
        fx = None
        if fact_ccy and sec.currency and fact_ccy != sec.currency:
            from .market_data import find_security as fs
            cad = fs(db, "CAD=X", "FX")
            usdcad = float(price_frame(db, cad.id)["close"].dropna().iloc[-1]) if cad else None
            if usdcad and {fact_ccy, sec.currency} == {"USD", "CAD"}:
                fx = (1 / usdcad) if sec.currency == "CAD" else usdcad
                notes.append(f"Price converted from {sec.currency} to {fact_ccy} at USD/CAD {usdcad:.4f} to match the filings.")
            else:
                gaps.append(f"Filings are in {fact_ccy} but the stock trades in {sec.currency}; multiples skipped.")
        price_rc = last_close * fx if fx else (last_close if not fact_ccy or fact_ccy == sec.currency else None)
        if price_rc is not None:
            shares_f = sorted([f for f in facts if f.metric == "shares_outstanding"], key=lambda f: f.period_end)
            shares = shares_f[-1].value if shares_f else by_p[-1].get("shares_diluted")
            mult = {k: v.value for k, v in R.valuation_multiples(price_rc, shares, by_p[-1]).items()}
            valuation = {"price_in_reporting_ccy": price_rc, "shares": shares, "multiples": mult,
                         "fiscal_period": periods[-1]}
            # reverse DCF under stated, generic assumptions
            d = R.derived_items(by_p[-1])
            rev, oi = by_p[-1].get("revenue"), by_p[-1].get("operating_income")
            if rev and oi and oi > 0 and shares and d.get("net_debt") is not None:
                capex = abs(by_p[-1].get("capex") or 0) / rev
                da = (by_p[-1].get("d_and_a") or 0) / rev
                assumptions = {"years": 10, "ebit_margin": oi / rev, "tax_rate": 0.25, "wacc": 0.09, "terminal_growth": 0.025,
                               "capex_pct_revenue": capex, "da_pct_revenue": da, "nwc_pct_revenue": 0.05}
                inp = D.DCFInputs(base_revenue=rev, revenue_growth=[0.0] * 10, ebit_margin=oi / rev, tax_rate=0.25, wacc=0.09,
                                  net_debt=d["net_debt"], diluted_shares=shares, da_pct_revenue=da, capex_pct_revenue=capex,
                                  nwc_pct_revenue=0.05, terminal_growth=0.025)
                rd = D.reverse_dcf(inp, price_rc)
                valuation["reverse_dcf"] = {"implied_revenue_cagr_10y": rd.get("implied_growth"), "assumptions": assumptions,
                                            "note": "Growth the current price implies if margins stay at the latest level, with a "
                                                    "9% cost of capital. Change the assumptions in the DCF tab to test others."}
            else:
                gaps.append("Reverse DCF skipped: needs positive operating income, revenue, shares and net debt.")
    elif sec.asset_type not in ("etf", "index"):
        gaps.append("No annual statements available.")

    # 6. peer score
    rk = build_ranking(db)
    me = next((r for r in rk["results"] if r["symbol"] == sec.symbol), None)
    peers = len([r for r in rk["results"] if r.get("score") is not None])
    score = {"score": me.get("score") if me else None, "rank": me.get("rank") if me else None, "of": peers,
             "group_scores": me.get("group_scores") if me else {}, "factors": me.get("factors") if me else {}}

    # 7. committee (rule-based, evidence-linked)
    review = committee(price, fundamentals, valuation, score, sec)
    conclusion = conclude(score, review, gaps, fundamentals, sec)
    return clean({
        "ticker": raw_ticker.upper(), "status": "ok", "symbol": sec.symbol, "exchange": sec.exchange, "name": sec.name,
        "sector": sec.sector, "industry": sec.subsector, "country": sec.country, "asset_type": sec.asset_type,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": ["Yahoo Finance (prices, profile)"] + (["SEC EDGAR XBRL company facts"] if fundamentals else []),
        "price": price, "fundamentals": fundamentals, "valuation": valuation, "score": score,
        "review": review, "conclusion": conclusion, "gaps": gaps, "notes": notes,
        "disclaimer": "Research summary from public data. Not investment advice and not a prediction. You make and place every trade.",
    })


def committee(price, fundamentals, valuation, score, sec) -> dict:
    bull, bear, risk = [], [], []
    r, s, k = price["returns"], price["signals"], price["risk_3y"]
    if (s.get("vs_sma200") or 0) > 0 and (s.get("mom_12_1") or 0) > 0:
        bull.append(f"Uptrend: {s['vs_sma200']:.0%} above its 200-day average, 12-1 month momentum {s['mom_12_1']:+.0%}.")
    if (s.get("vs_sma200") or 0) < 0:
        bear.append(f"Downtrend: {s['vs_sma200']:.0%} below its 200-day average.")
    if r.get("1y") is not None and r["1y"] < -0.2:
        bear.append(f"Down {r['1y']:.0%} over the past year.")
    if (k.get("sharpe") or 0) > 1:
        bull.append(f"Strong risk-adjusted returns over 3 years (Sharpe {k['sharpe']:.2f}).")
    if s.get("rsi14") and s["rsi14"] > 75:
        bear.append(f"Short-term overbought (RSI {s['rsi14']:.0f}); entries after sharp runs often see pullbacks.")
    if s.get("rsi14") and s["rsi14"] < 30:
        bull.append(f"Short-term oversold (RSI {s['rsi14']:.0f}); only meaningful if the business case holds.")
    if fundamentals:
        last = fundamentals["ratios"][fundamentals["periods"][-1]]
        om, roe, nde, g, fcfm = (last.get(x) for x in ("operating_margin", "roe", "net_debt_to_ebitda", "revenue_growth", "fcf_margin"))
        fy = fundamentals['periods'][-1][:4]
        if om is not None and om > 0.15:
            bull.append(f"Operating margin {om:.0%} in FY{fy}.")
        elif om is not None and om < 0.05:
            bear.append(f"Thin or negative operating margin ({om:.0%}) in FY{fy}.")
        if roe is not None and roe > 0.15:
            bull.append(f"Return on equity {roe:.0%}" + (" (inflated by buybacks shrinking equity)." if roe > 0.6 else "."))
        elif roe is not None and roe < 0.05:
            bear.append(f"Low return on equity ({roe:.0%}).")
        if g is not None and g > 0.08:
            bull.append(f"Revenue growth {g:+.0%} year over year.")
        elif g is not None and g < 0:
            bear.append(f"Revenue fell {g:.0%} year over year.")
        if fcfm is not None and fcfm < 0:
            bear.append(f"Negative free cash flow ({fcfm:.0%} of revenue): may need financing or dilution.")
        elif fcfm is not None and fcfm > 0.1:
            bull.append(f"Free cash flow {fcfm:.0%} of revenue.")
        if nde is not None and nde > 3:
            bear.append(f"High leverage: net debt is {nde:.1f}× EBITDA.")
        nd = fundamentals["derived"]["net_debt"][-1]
        if nd is not None and nd < 0:
            bull.append("More cash than debt.")
        for fl in fundamentals["change_flags"][-3:]:
            bear.append(f"Large change in {fl['item'].replace('_', ' ')} ({fl['change']:+.0%}) — check the filing for the cause.")
    if valuation:
        m = valuation["multiples"]
        pe, ev = m.get("pe"), m.get("ev_ebitda")
        if pe and pe > 25:
            bear.append(f"P/E {pe:.1f}: priced well above the market average, so growth has to deliver.")
        elif pe and pe < 12:
            bull.append(f"P/E {pe:.1f}: low multiple (check why — cyclical peak earnings can make this misleading).")
        rd = (valuation.get("reverse_dcf") or {}).get("implied_revenue_cagr_10y")
        if rd is not None:
            (bear if rd > 0.12 else bull if rd < 0.03 else bull).append(
                f"Price implies about {rd:.0%} revenue growth a year for 10 years at current margins" +
                (" — a demanding expectation." if rd > 0.12 else " — a modest expectation." if rd < 0.03 else "."))
    vol = k.get("volatility")
    if vol:
        risk.append(f"Volatility {vol:.0%} a year: a typical year could move about ±{vol:.0%}.")
        cap = min(0.40, 0.10 / vol) if vol > 0 else 0.40
        risk.append(f"Volatility-scaled position limit: {cap:.0%} of the portfolio (about ${cap * 100:.0f} of $100), "
                    "so a one-standard-deviation bad year costs at most ~10% of the account.")
    if k.get("max_drawdown"):
        risk.append(f"Worst peak-to-trough fall in 3 years: {k['max_drawdown']:.0%}.")
    if k.get("beta") is not None:
        risk.append(f"Beta {k['beta']:.2f} versus {price['benchmark']}.")
    if price.get("avg_dollar_volume_60d") is not None and price["avg_dollar_volume_60d"] < 1e6:
        risk.append("Thinly traded (under $1M a day): wider spreads.")
    if sec.currency == "USD":
        risk.append("Priced in USD: Wealthsimple charges about 1.5% to convert on each buy and sell, and CAD/USD moves change your return.")
    if sec.sector in ("Basic Materials", "Energy", "Natural Resources"):
        risk.append("Earnings depend heavily on commodity prices.")
    return {"bull": bull, "bear": bear, "risk": risk}


def conclude(score, review, gaps, fundamentals, sec) -> dict:
    sc = score.get("score")
    if sc is None or (fundamentals is None and sec.asset_type not in ("etf",) and len(gaps) >= 2):
        verdict = "insufficient evidence"
        why = "Not enough data to judge the business. Research the filings directly before considering it."
    elif sc >= 0.65 and len(review["bull"]) > len(review["bear"]):
        verdict = "worth deeper research"
        why = "Ranks in the top third of the universe with more supporting than opposing evidence."
    elif sc <= 0.35 or len(review["bear"]) > len(review["bull"]) + 1:
        verdict = "weak evidence"
        why = "Ranks low or the evidence against outweighs the evidence for."
    else:
        verdict = "mixed evidence"
        why = "Some supporting evidence, some concerns; no clear edge either way."
    return {"verdict": verdict, "why": why,
            "next_steps": ["Read the latest annual report / MD&A and the most recent earnings call.",
                           "Set your own assumptions in the DCF tab and compare with the price.",
                           "Write the thesis and the conditions that would prove it wrong in the Journal tab before buying."]}
