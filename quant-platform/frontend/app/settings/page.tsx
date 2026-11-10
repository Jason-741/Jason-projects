"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Card, Chip, ErrorBox, Field, Note, PageHeader, Table } from "@/components/ui";

export default function Settings() {
  const prov = useApi<any[]>("/api/data/providers");
  const cov = useApi<any>("/api/data/coverage");
  const runs = useApi<any[]>("/api/data/runs?limit=30");
  const audit = useApi<any[]>("/api/audit?limit=50");
  const strategies = useApi<any[]>("/api/strategies");
  const [ing, setIng] = useState({ symbol: "", exchange: "TSX", start: "2015-01-01" });
  const [sec, setSec] = useState({ symbol: "", exchange: "TSX", name: "", currency: "CAD", asset_type: "equity", sector: "Natural Resources", subsector: "" });
  const [macro, setMacro] = useState("DGS10");
  const [st, setSt] = useState({ name: "", hypothesis: "", kind: "quant" });
  const [msg, setMsg] = useState<string | null>(null); const [err, setErr] = useState<string | null>(null);
  const call = async (fn: () => Promise<any>) => { setErr(null); setMsg(null); try { const r = await fn(); setMsg(JSON.stringify(r).slice(0, 400)); runs.reload(); cov.reload(); audit.reload(); strategies.reload(); } catch (e: any) { setErr(e.message); } };
  return (
    <div className="space-y-4">
      <PageHeader title="Settings & Data Sources" sub="Provider configuration lives in backend/.env (never in the browser). Every ingestion is logged with source, time, validation issues and errors." />
      <ErrorBox error={err} />{msg && <Note>{msg}</Note>}
      <Card title="Providers">
        <Table rows={prov.data || []} cols={[{ key: "name", label: "Provider" }, { key: "configured", label: "Status", render: (r: any) => r.configured ? <Chip kind="ok">configured</Chip> : <Chip kind="warn">set {r.requires.join(", ")}</Chip> },
          { key: "capabilities", label: "Capabilities", render: (r: any) => r.capabilities.join(", ") }, { key: "detail", label: "Notes", render: (r: any) => <span className="whitespace-normal">{r.detail}</span> }]} />
        <Note>SEDAR+ has no public API: download filings from sedarplus.ca yourself and upload them in Earnings Intelligence. Wealthsimple has no official public account API: use CSV import.</Note>
      </Card>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card title="Add / classify a security">
          <div className="grid grid-cols-2 gap-2">
            {Object.keys(sec).map(k => <Field key={k} label={k}><input className="input" value={(sec as any)[k]} onChange={e => setSec({ ...sec, [k]: k === "symbol" ? e.target.value.toUpperCase() : e.target.value })} /></Field>)}
          </div>
          <div className="flex gap-2 mt-2"><button className="btn" onClick={() => call(() => api("/api/securities", { method: "POST", json: sec }))} disabled={!sec.symbol}>Save</button>
            <button className="btn-ghost" onClick={() => call(() => api(`/api/securities/${sec.symbol}/profile?exchange=${sec.exchange}`, { method: "POST" }))} disabled={!sec.symbol}>Fetch profile</button></div>
          <Note>Exchanges: TSX, TSXV, CSE, NYSE, NASDAQ, NYSEARCA; INDEX / FX / FUTURES for Yahoo symbols like ^GSPTSE, CAD=X, HG=F.</Note>
        </Card>
        <Card title="Ingest data">
          <div className="grid grid-cols-3 gap-2">
            <Field label="Symbol"><input className="input" value={ing.symbol} onChange={e => setIng({ ...ing, symbol: e.target.value.toUpperCase() })} /></Field>
            <Field label="Exchange"><input className="input" value={ing.exchange} onChange={e => setIng({ ...ing, exchange: e.target.value.toUpperCase() })} /></Field>
            <Field label="Start"><input type="date" className="input" value={ing.start} onChange={e => setIng({ ...ing, start: e.target.value })} /></Field>
          </div>
          <div className="flex flex-wrap gap-2 mt-2">
            <button className="btn" disabled={!ing.symbol} onClick={() => call(() => api("/api/data/ingest/prices", { method: "POST", json: ing }))}>Prices</button>
            <button className="btn-ghost" disabled={!ing.symbol} onClick={() => call(() => api("/api/data/ingest/fundamentals", { method: "POST", json: { symbol: ing.symbol, exchange: ing.exchange } }))}>SEC fundamentals</button>
            <button className="btn-ghost" onClick={() => call(() => api(`/api/data/ingest/fx?start=${ing.start}`, { method: "POST" }))}>USD/CAD FX</button>
          </div>
          <div className="flex gap-2 mt-3 items-end"><Field label="FRED series"><input className="input" value={macro} onChange={e => setMacro(e.target.value)} /></Field>
            <button className="btn-ghost" onClick={() => call(() => api("/api/data/ingest/macro", { method: "POST", json: { series_id: macro } }))}>Macro</button></div>
        </Card>
        <Card title="Strategy registry & readiness">
          <div className="flex flex-col gap-2">
            <input className="input" placeholder="strategy name" value={st.name} onChange={e => setSt({ ...st, name: e.target.value })} />
            <textarea className="input h-14" placeholder="hypothesis: why should this edge exist?" value={st.hypothesis} onChange={e => setSt({ ...st, hypothesis: e.target.value })} />
            <button className="btn" onClick={() => call(() => api("/api/strategies", { method: "POST", json: st }))}>Register</button>
          </div>
          {(strategies.data || []).map(s => <div key={s.id} className="text-xs mt-3 border-t border-ink-700 pt-2"><b>{s.name}</b> — {s.readiness.status} ({s.readiness.completed}/{s.readiness.total})
            <ul className="mt-1">{s.readiness.items.map((i: any) => <li key={i.key} className="flex justify-between gap-2"><span className={i.done ? "text-green-300" : "text-slate-500"}>{i.done ? "✓" : "○"} {i.label}</span>
              {!i.done && <button className="text-accent" onClick={() => { const ev = prompt(`Evidence for "${i.label}" (e.g. backtest run id, paper account dates)`); if (ev) call(() => api(`/api/strategies/${s.id}/checklist`, { method: "POST", json: { key: i.key, done: true, evidence: ev } })); }}>mark</button>}</li>)}</ul></div>)}
        </Card>
      </div>
      <Card title="Coverage"><Table max={300} rows={cov.data?.securities || []} cols={[{ key: "symbol", label: "Symbol" }, { key: "exchange", label: "Exch" }, { key: "price_rows", label: "Bars", fmt: "int" },
        { key: "first", label: "First" }, { key: "last", label: "Last" }, { key: "fundamental_facts", label: "Facts", fmt: "int" }]} /></Card>
      <Card title="Ingestion log"><Table max={300} rows={runs.data || []} cols={[{ key: "id", label: "#" }, { key: "started_at", label: "Started" }, { key: "provider", label: "Provider" }, { key: "dataset", label: "Dataset" },
        { key: "params", label: "Params", render: (r: any) => JSON.stringify(r.params) }, { key: "status", label: "Status" }, { key: "rows_written", label: "Rows", fmt: "int" },
        { key: "issues", label: "Issues", render: (r: any) => (r.issues || []).filter((i: any) => i.severity !== "info").map((i: any) => i.code).join(", ") }, { key: "error", label: "Error" }]} /></Card>
      <Card title="Audit trail"><Table max={300} rows={audit.data || []} cols={[{ key: "ts", label: "When" }, { key: "action", label: "Action" }, { key: "entity", label: "Entity" }, { key: "entity_id", label: "Id" },
        { key: "detail", label: "Detail", render: (r: any) => JSON.stringify(r.detail) }]} /></Card>
    </div>
  );
}
