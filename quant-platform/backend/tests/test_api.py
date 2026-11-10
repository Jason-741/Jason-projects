"""End-to-end API tests on an isolated DB with SYNTHETIC price rows inserted directly."""
from datetime import date

from conftest import synthetic_prices

from app.db import SessionLocal
from app.models import FxRate, PriceBar, Security


def _seed():
    with SessionLocal() as db:
        if db.query(Security).filter_by(symbol="AAA").first():
            return
        px = synthetic_prices(n=600)
        for sym in px.columns:
            sec = Security(symbol=sym, exchange="TSX", currency="CAD", sector="Natural Resources" if sym != "CCC" else "Technology",
                           asset_type="equity", source="test_synthetic")
            db.add(sec)
            db.flush()
            for d, v in px[sym].items():
                db.add(PriceBar(security_id=sec.id, date=d.date(), open=v, high=v * 1.01, low=v * 0.99, close=v, adj_close=v,
                                volume=1e6, source="test_synthetic", quality_status="valid"))
        usd = Security(symbol="UUU", exchange="NYSE", currency="USD", sector="Natural Resources", source="test_synthetic")
        db.add(usd)
        db.flush()
        db.add(PriceBar(security_id=usd.id, date=date(2026, 1, 2), close=20.0, adj_close=20.0, volume=1e7, source="test_synthetic"))
        db.add(FxRate(base="USD", quote="CAD", date=date(2026, 1, 2), rate=1.40, source="test_synthetic"))
        db.commit()


def test_auth_required(client):
    from fastapi.testclient import TestClient

    from app.main import app
    anon = TestClient(app)
    assert anon.get("/api/securities").status_code == 401
    assert anon.get("/api/health").status_code == 200
    assert anon.post("/api/auth/login", json={"username": "tester", "password": "wrong-password!!"}).status_code == 401


def test_providers_report_unconfigured(client):
    st = {p["name"]: p for p in client.get("/api/data/providers").json()}
    assert st["sec_edgar"]["configured"] is False and "SEC_USER_AGENT" in st["sec_edgar"]["requires"]
    assert st["fred"]["configured"] is False


def test_ingest_without_config_records_error(client):
    r = client.post("/api/data/ingest/fundamentals", json={"symbol": "FCX"}).json()
    assert r["status"] == "error" and "SEC_USER_AGENT" in r["error"]


def test_search_prices_signals_backtest(client):
    _seed()
    assert any(s["symbol"] == "AAA" for s in client.get("/api/securities?q=AA").json())
    bars = client.get("/api/securities/AAA/prices").json()
    assert len(bars["bars"]) == 600 and bars["provenance"]["sources"] == ["test_synthetic"]
    sig = client.get("/api/quant/signals/AAA").json()
    assert "rsi14" in sig["latest"]
    bt = client.post("/api/backtest/run", json={"symbols": ["AAA", "BBB", "CCC"], "strategy": "trend",
                                                "params": {"window": 50}, "benchmark": "AAA"}).json()
    assert bt["lookahead_check_passed"] is True and bt["run_id"]
    assert "out_of_sample" in bt["split"] and "beta" in bt["metrics"]
    assert client.get("/api/backtest/runs").json()[0]["fingerprint"] == bt["fingerprint"]


def test_risk_and_construction_endpoints(client):
    _seed()
    r = client.post("/api/risk/portfolio", json={"weights": {"AAA": 0.6, "BBB": 0.4}}).json()
    assert r["summary"]["var_95_hist"] > 0
    mc = client.post("/api/risk/montecarlo", json={"weights": {"AAA": 1.0}, "n_paths": 200, "horizon_days": 30}).json()
    assert 0 <= mc["prob_loss"] <= 1
    c = client.post("/api/portfolio/construct", json={"symbols": ["AAA", "BBB", "CCC"], "method": "min_variance", "max_weight": 0.5}).json()
    assert abs(sum(c["weights"].values()) - 1) < 1e-6 and max(c["weights"].values()) <= 0.5 + 1e-9


def test_dcf_endpoint(client):
    r = client.post("/api/valuation/dcf", json={"base_revenue": 100, "revenue_growth": [0.05] * 5, "ebit_margin": 0.2,
                                                "tax_rate": 0.25, "wacc": 0.09, "net_debt": 10, "diluted_shares": 10,
                                                "market_price": 15, "scenarios": {"bear": {"wacc": 0.11}, "base": {}, "bull": {"wacc": 0.08}}})
    j = r.json()
    assert r.status_code == 200 and "reverse_dcf" in j and j["valuation_range"]["low"] < j["valuation_range"]["high"]
    bad = client.post("/api/valuation/dcf", json={"base_revenue": 100, "revenue_growth": [0.05], "ebit_margin": 0.2, "tax_rate": 0.25,
                                                  "wacc": 0.05, "terminal_growth": 0.06, "net_debt": 0, "diluted_shares": 1})
    assert bad.status_code == 422


def test_live_paper_separation_and_proposal_flow(client):
    _seed()
    live = client.post("/api/accounts", json={"name": "WS TFSA", "kind": "live", "broker": "Wealthsimple"}).json()
    paper = client.post("/api/accounts", json={"name": "Paper 1", "kind": "paper"}).json()
    # cannot place simulated orders in live, nor import broker CSV into paper
    assert client.post(f"/api/accounts/{live['id']}/paper-orders", json={"symbol": "AAA", "side": "buy", "quantity": 1}).status_code == 409
    files = {"file": ("x.csv", "date,type,symbol,quantity,price\n2026-01-01,deposit,,,\n", "text/csv")}
    assert client.post(f"/api/accounts/{paper['id']}/import", files=files, data={"dry_run": "false"}).status_code == 409

    csv = ("date,type,symbol,quantity,price,currency,fees,fx_rate_to_base,amount,counter_currency,counter_amount,reference,note\n"
           "2026-01-02,deposit,,,,CAD,,,100,,,,\n")
    files = {"file": ("ws.csv", csv, "text/csv")}
    dry = client.post(f"/api/accounts/{live['id']}/import", files=files, data={"dry_run": "true"}).json()
    assert dry["new"] == 1 and dry["batch"] is None
    files = {"file": ("ws.csv", csv, "text/csv")}
    client.post(f"/api/accounts/{live['id']}/import", files=files, data={"dry_run": "false"})
    files = {"file": ("ws.csv", csv, "text/csv")}
    again = client.post(f"/api/accounts/{live['id']}/import", files=files, data={"dry_run": "false"}).json()
    assert again["new"] == 0 and again["duplicates"] == 1

    short = client.post(f"/api/accounts/{live['id']}/proposals", json={"symbol": "AAA", "side": "buy", "quantity": 1, "reason": "x"})
    assert short.status_code == 422
    prop = client.post(f"/api/accounts/{live['id']}/proposals", json={
        "symbol": "UUU", "side": "buy", "quantity": 1, "reason": "Copper thesis documented in journal entry; within limits test."}).json()
    assert prop["currency"] == "USD" and prop["risk_check"]["cost_breakdown"]["fx_rate"] == 1.40
    assert abs(prop["est_total_cost_base"] - 20 * 1.40 * 1.015) < 1e-9
    assert "never executes" in prop["execution_instruction"]
    big = client.post(f"/api/accounts/{live['id']}/proposals", json={
        "symbol": "UUU", "side": "buy", "quantity": 3, "reason": "Deliberately oversized to test risk limit flags."}).json()
    assert big["risk_check"]["passed"] is False
    placed = client.post(f"/api/proposals/{prop['id']}/decision", json={"decision": "placed", "executed_price": 20.1,
                                                                       "executed_quantity": 1, "fx_rate_to_base": 1.41}).json()
    assert placed["status"] == "placed"
    snap = client.get(f"/api/accounts/{live['id']}/snapshot").json()
    assert any(p["symbol"] == "UUU" for p in snap["positions"])
    assert client.post(f"/api/proposals/{prop['id']}/decision", json={"decision": "rejected"}).status_code == 422

    client.post(f"/api/accounts/{paper['id']}/transactions", json={"ts": "2026-01-02T00:00:00Z", "tx_type": "deposit", "amount": 100})
    fill = client.post(f"/api/accounts/{paper['id']}/paper-orders", json={"symbol": "AAA", "side": "buy", "quantity": 0.5}).json()
    assert fill["origin"] == "paper_sim"
    psnap = client.get(f"/api/accounts/{paper['id']}/snapshot").json()
    lsnap_syms = {p["symbol"] for p in snap["positions"]}
    assert "AAA" not in lsnap_syms and any(p["symbol"] == "AAA" for p in psnap["positions"])
    assert client.post(f"/api/accounts/{paper['id']}/paper-orders", json={"symbol": "AAA", "side": "sell", "quantity": 5}).status_code == 422


def test_journal_and_readiness(client):
    e = client.post("/api/journal", json={"symbol": "fcx", "analysis_date": "2026-01-01", "thesis": "t" * 60,
                                          "valuation_low": 30, "valuation_base": 40, "valuation_high": 55, "risks": "copper price",
                                          "invalidation_conditions": "AISC above $2.80/lb for two quarters", "confidence": 3}).json()
    assert e["symbol"] == "FCX" and e["readiness"]["completed"] == 4
    u = client.patch(f"/api/journal/{e['id']}", json={"thesis": "rewritten", "entry_price": 40, "exit_price": 44,
                                                      "development": "Q4 beat", "outcome_attribution": "luck"}).json()
    assert u["thesis"] == "t" * 60          # thesis is immutable via update (field not accepted)
    assert abs(u["realized_return"] - 0.10) < 1e-9 and u["updates"][0]["note"] == "Q4 beat"
    s = client.post("/api/strategies", json={"name": "trend-200", "hypothesis": "Time-series trend persists in commodity equities."}).json()
    s = client.post(f"/api/strategies/{s['id']}/checklist", json={"key": "out_of_sample", "done": True, "evidence": "backtest run 1"}).json()
    assert s["readiness"]["completed"] == 2 and "not ready" in s["readiness"]["status"]


def test_research_upload_and_analysis(client):
    from test_research import TRANSCRIPT
    r = client.post("/api/research/documents", files={"file": ("call.txt", TRANSCRIPT, "text/plain")},
                    data={"doc_type": "transcript", "title": "Test call"}).json()
    a = client.get(f"/api/research/documents/{r['id']}/analysis").json()
    assert a["segments_by_role"]["ceo"] >= 2 and a["guidance_candidates"]
    ask = client.post("/api/research/ask", json={"question": "What is production guidance?", "document_ids": [r["id"]]}).json()
    assert ask["configured"] is False and ask["retrieved"]


def test_audit_trail(client):
    actions = {a["action"] for a in client.get("/api/audit").json()}
    assert {"register", "create_account", "propose_trade", "decide_proposal", "import_csv"} <= actions
