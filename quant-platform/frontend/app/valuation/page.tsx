"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Card, ErrorBox, Field, KV, Note, PageHeader, Stat, Table } from "@/components/ui";
import Plot from "@/components/Plot";
import { num, pct } from "@/lib/format";

const parseList = (s: string) => s.split(",").map(x => Number(x.trim()) / 100).filter(x => Number.isFinite(x));

export default function Valuation() {
  const [tab, setTab] = useState<"dcf" | "mine">("dcf");
  return (
    <div className="space-y-4">
      <PageHeader title="Valuation" sub="Every input is your assumption. Outputs are estimates conditional on those assumptions, never an objectively known price.">
        <button className={tab === "dcf" ? "btn" : "btn-ghost"} onClick={() => setTab("dcf")}>DCF / Reverse DCF</button>
        <button className={tab === "mine" ? "btn" : "btn-ghost"} onClick={() => setTab("mine")}>Mine project NPV</button>
      </PageHeader>
      {tab === "dcf" ? <DCF /> : <Mine />}
    </div>
  );
}

function DCF() {
  const [f, setF] = useState({ base_revenue: "1000", growth: "8,7,6,5,4", ebit_margin: "18", tax_rate: "26.5", wacc: "9", terminal_growth: "2",
    net_debt: "200", diluted_shares: "100", da: "5", capex: "6", nwc: "10", market_price: "", bear_margin: "14", bull_margin: "22" });
  const [res, setRes] = useState<any>(null); const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const run = async () => {
    setErr(null);
    try {
      setRes(await api("/api/valuation/dcf", { method: "POST", json: {
        base_revenue: +f.base_revenue, revenue_growth: parseList(f.growth), ebit_margin: +f.ebit_margin / 100, tax_rate: +f.tax_rate / 100,
        wacc: +f.wacc / 100, terminal_growth: +f.terminal_growth / 100, net_debt: +f.net_debt, diluted_shares: +f.diluted_shares,
        da_pct_revenue: +f.da / 100, capex_pct_revenue: +f.capex / 100, nwc_pct_revenue: +f.nwc / 100,
        market_price: f.market_price ? +f.market_price : null,
        scenarios: { bear: { ebit_margin: +f.bear_margin / 100, wacc: +f.wacc / 100 + 0.01 }, base: {}, bull: { ebit_margin: +f.bull_margin / 100 } } } }));
    } catch (e: any) { setErr(e.message); }
  };
  const r = res?.result;
  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
      <Card title="Assumptions">
        <div className="grid grid-cols-2 gap-2">
          <Field label="Base revenue"><input className="input" value={f.base_revenue} onChange={set("base_revenue")} /></Field>
          <Field label="Growth by year (%, comma)"><input className="input" value={f.growth} onChange={set("growth")} /></Field>
          <Field label="EBIT margin %"><input className="input" value={f.ebit_margin} onChange={set("ebit_margin")} /></Field>
          <Field label="Tax rate %"><input className="input" value={f.tax_rate} onChange={set("tax_rate")} /></Field>
          <Field label="WACC %"><input className="input" value={f.wacc} onChange={set("wacc")} /></Field>
          <Field label="Terminal growth %"><input className="input" value={f.terminal_growth} onChange={set("terminal_growth")} /></Field>
          <Field label="D&A % rev"><input className="input" value={f.da} onChange={set("da")} /></Field>
          <Field label="Capex % rev"><input className="input" value={f.capex} onChange={set("capex")} /></Field>
          <Field label="NWC % of Δrev"><input className="input" value={f.nwc} onChange={set("nwc")} /></Field>
          <Field label="Net debt"><input className="input" value={f.net_debt} onChange={set("net_debt")} /></Field>
          <Field label="Diluted shares"><input className="input" value={f.diluted_shares} onChange={set("diluted_shares")} /></Field>
          <Field label="Market price (optional)"><input className="input" value={f.market_price} onChange={set("market_price")} /></Field>
          <Field label="Bear EBIT margin %"><input className="input" value={f.bear_margin} onChange={set("bear_margin")} /></Field>
          <Field label="Bull EBIT margin %"><input className="input" value={f.bull_margin} onChange={set("bull_margin")} /></Field>
        </div>
        <button className="btn mt-3" onClick={run}>Run DCF</button>
        <ErrorBox error={err} />
        <Note>Units must be consistent (e.g. revenue and net debt in millions, shares in millions). Not suitable for banks/insurers or pre-production miners.</Note>
      </Card>
      <div className="xl:col-span-2 space-y-4">
        {r && <Card title="Result (estimate)">
          <div className="flex flex-wrap gap-6">
            <Stat label="Value / share" value={r.value_per_share} /><Stat label="Enterprise value" value={r.enterprise_value} />
            <Stat label="Equity value" value={r.equity_value} /><Stat label="TV share of EV" value={r.terminal_share_of_ev} kind="pct" />
            {res.valuation_range && <Stat label="Scenario range" value={`${num(res.valuation_range.low)} – ${num(res.valuation_range.high)}`} kind="text" />}
            {res.market_price && <><Stat label="Margin of safety" value={res.margin_of_safety} kind="pct" colored />
              <Stat label="Implied growth (reverse DCF)" value={res.reverse_dcf?.implied_growth} kind="pct" /></>}
          </div>
          {r.warnings.map((w: string) => <Note key={w}>⚠ {w}</Note>)}
          {res.reverse_dcf && <Note>{res.reverse_dcf.note}</Note>}
          <Note>{res.label}</Note>
        </Card>}
        {r && <Card title="Forecast">
          <Table rows={r.years} cols={[{ key: "year", label: "Yr" }, { key: "revenue", label: "Revenue", fmt: "num" }, { key: "growth", label: "g", fmt: "pct" },
            { key: "ebit", label: "EBIT", fmt: "num" }, { key: "nopat", label: "NOPAT", fmt: "num" }, { key: "d_and_a", label: "D&A", fmt: "num" },
            { key: "capex", label: "Capex", fmt: "num" }, { key: "delta_nwc", label: "ΔNWC", fmt: "num" }, { key: "fcff", label: "FCFF", fmt: "num" },
            { key: "discount_factor", label: "DF", fmt: "num", d: 4 }, { key: "pv_fcff", label: "PV", fmt: "num" }]} />
        </Card>}
        {res?.sensitivity && <Card title="Sensitivity — value/share (WACC × terminal growth)">
          <Plot height={280} data={[{ type: "heatmap", z: res.sensitivity.value_per_share, x: res.sensitivity.terminal_growths.map((g: number) => pct(g, 1)),
            y: res.sensitivity.waccs.map((w: number) => pct(w, 1)), colorscale: "Viridis", texttemplate: "%{z:.2f}" }]}
            layout={{ xaxis: { title: "terminal growth" }, yaxis: { title: "WACC" } }} />
        </Card>}
        {res?.scenarios && <Card title="Scenarios"><Table rows={Object.entries(res.scenarios).map(([k, v]: any) => ({ scenario: k, ...v, overrides: JSON.stringify(v.overrides) }))}
          cols={[{ key: "scenario", label: "Scenario" }, { key: "value_per_share", label: "Value/share", fmt: "num" }, { key: "terminal_share_of_ev", label: "TV %", fmt: "pct" }, { key: "overrides", label: "Overrides" }]} /></Card>}
      </div>
    </div>
  );
}

function Mine() {
  const [f, setF] = useState({ annual_production: "100", mine_life_years: "12", commodity_price: "4.2", aisc: "2.6", initial_capex: "1200",
    discount_rate: "8", tax_rate: "27", royalty_rate: "2", ramp: "50,80", delay: "0", closure: "60" });
  const [res, setRes] = useState<any>(null); const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const run = async () => {
    setErr(null);
    try { setRes(await api("/api/valuation/mine", { method: "POST", json: { annual_production: +f.annual_production, mine_life_years: +f.mine_life_years,
      commodity_price: +f.commodity_price, aisc: +f.aisc, initial_capex: +f.initial_capex, discount_rate: +f.discount_rate / 100, tax_rate: +f.tax_rate / 100,
      royalty_rate: +f.royalty_rate / 100, ramp_up: f.ramp ? f.ramp.split(",").map(x => +x / 100) : [1], construction_delay_years: +f.delay, closure_cost: +f.closure } })); }
    catch (e: any) { setErr(e.message); }
  };
  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
      <Card title="Project inputs (from technical report / guidance)">
        <div className="grid grid-cols-2 gap-2">
          {Object.entries({ annual_production: "Annual production (e.g. Mlb)", mine_life_years: "Mine life (yrs)", commodity_price: "Price (per unit)",
            aisc: "AISC (per unit)", initial_capex: "Initial capex", discount_rate: "Discount rate %", tax_rate: "Tax %", royalty_rate: "NSR royalty %",
            ramp: "Ramp-up % by year", delay: "Construction delay (yrs)", closure: "Closure cost" }).map(([k, l]) =>
            <Field key={k} label={l}><input className="input" value={(f as any)[k]} onChange={set(k)} /></Field>)}
        </div>
        <button className="btn mt-3" onClick={run}>Run</button><ErrorBox error={err} />
        <Note>Cite the NI 43-101 / S-K 1300 technical report for each input in your journal entry.</Note>
      </Card>
      {res && <div className="xl:col-span-2 space-y-4">
        <Card title="Base case"><KV data={{ npv: res.base.npv, irr: res.base.irr, payback_year: res.base.payback_year }} pctKeys={["irr"]} /><Note>{res.note}</Note></Card>
        <Card title="NPV sensitivity: commodity price × AISC">
          <Plot height={280} data={[{ type: "heatmap", z: res.sensitivity.npv_grid, x: res.sensitivity.cost_moves.map((c: number) => `AISC ${pct(c, 0)}`),
            y: res.sensitivity.price_moves.map((p: number) => `price ${pct(p, 0)}`), colorscale: [[0, "#ef4444"], [0.5, "#151b24"], [1, "#22c55e"]], zmid: 0, texttemplate: "%{z:.0f}" }]} />
        </Card>
        <Card title="Operational shocks"><Table rows={Object.entries(res.sensitivity.shocks).map(([k, v]) => ({ shock: k, npv: v }))}
          cols={[{ key: "shock", label: "Shock" }, { key: "npv", label: "NPV", fmt: "num" }]} /></Card>
      </div>}
    </div>
  );
}
