"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import AccountPicker from "@/components/AccountPicker";
import AccountView from "@/components/AccountView";
import { Card, Chip, ErrorBox, Field, Note, PageHeader, Table } from "@/components/ui";
import { num, pct } from "@/lib/format";

export default function Live() {
  const [id, setId] = useState<number | null>(null); const [k, setK] = useState(0);
  const journal = useApi<any[]>("/api/journal");
  const props = useApi<any[]>("/api/proposals", [k]);
  const [file, setFile] = useState<File | null>(null); const [fmt, setFmt] = useState(""); const [imp, setImp] = useState<any>(null);
  const [tx, setTx] = useState({ ts: new Date().toISOString().slice(0, 10), tx_type: "buy", symbol: "", quantity: "", price: "", currency: "CAD", amount: "", fees: "0", fx_rate_to_base: "" });
  const [p, setP] = useState({ symbol: "", side: "buy", quantity: "", est_price: "", reason: "", risks: "", thesis_entry_id: "" });
  const [dec, setDec] = useState<Record<number, any>>({});
  const [err, setErr] = useState<string | null>(null);
  const doImport = async (dry: boolean) => {
    if (!file) return; setErr(null);
    const fd = new FormData(); fd.append("file", file); fd.append("dry_run", String(dry)); if (fmt) fd.append("fmt", fmt);
    try { setImp(await api(`/api/accounts/${id}/import`, { method: "POST", body: fd })); if (!dry) setK(k + 1); } catch (e: any) { setErr(e.message); }
  };
  const addTx = async () => {
    setErr(null);
    try { await api(`/api/accounts/${id}/transactions`, { method: "POST", json: { ts: `${tx.ts}T16:00:00Z`, tx_type: tx.tx_type, symbol: tx.symbol || null,
      quantity: +tx.quantity || 0, price: +tx.price || 0, currency: tx.currency, amount: +tx.amount || 0, fees: +tx.fees || 0, fx_rate_to_base: tx.fx_rate_to_base ? +tx.fx_rate_to_base : null } }); setK(k + 1); }
    catch (e: any) { setErr(e.message); }
  };
  const propose = async () => {
    setErr(null);
    try { await api(`/api/accounts/${id}/proposals`, { method: "POST", json: { symbol: p.symbol, side: p.side, quantity: +p.quantity, est_price: p.est_price ? +p.est_price : null,
      reason: p.reason, risks: p.risks || null, thesis_entry_id: p.thesis_entry_id ? +p.thesis_entry_id : null } }); setK(k + 1); }
    catch (e: any) { setErr(e.message); }
  };
  const decide = async (pid: number, decision: string) => {
    setErr(null); const d = dec[pid] || {};
    try { await api(`/api/proposals/${pid}/decision`, { method: "POST", json: { decision, note: d.note || null, executed_price: d.price ? +d.price : null,
      executed_quantity: d.qty ? +d.qty : null, fees: d.fees ? +d.fees : 0, fx_rate_to_base: d.fx ? +d.fx : null } }); setK(k + 1); }
    catch (e: any) { setErr(e.message); }
  };
  const mine = (props.data || []).filter(x => x.account_id === id);
  return (
    <div className="space-y-4">
      <PageHeader title="Live Portfolio" sub="Your real Wealthsimple holdings, kept in sync by CSV import or manual entry. The platform prepares proposals with risk checks; you place every order yourself in Wealthsimple and record the actual fill.">
        <AccountPicker kind="live" value={id} onChange={setId} />
      </PageHeader>
      <ErrorBox error={err} />
      {id && <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card title="Import Wealthsimple CSV / generic template">
          <div className="flex flex-wrap gap-2 items-end">
            <input type="file" accept=".csv" className="text-xs" onChange={e => setFile(e.target.files?.[0] || null)} />
            <Field label="Format"><select className="input" value={fmt} onChange={e => setFmt(e.target.value)}><option value="">auto-detect</option><option value="generic">generic</option><option value="wealthsimple_activity">wealthsimple_activity</option></select></Field>
            <button className="btn-ghost" onClick={() => doImport(true)} disabled={!file}>Preview (dry run)</button>
            <button className="btn" onClick={() => doImport(false)} disabled={!file || !imp || imp.dry_run !== true}>Commit import</button>
          </div>
          {imp && <div className="text-xs mt-2 space-y-1">
            <div>Format <b>{imp.format}</b> · parsed {imp.parsed} · new {imp.new} · duplicates {imp.duplicates} · errors {imp.errors.length} · skipped {imp.skipped.length} {imp.dry_run ? <Chip kind="warn">preview</Chip> : <Chip kind="ok">committed</Chip>}</div>
            {imp.errors.slice(0, 10).map((e: any, i: number) => <div key={i} className="text-red-300">line {e.line}: {e.error}</div>)}
            <Table max={200} rows={imp.preview} cols={[{ key: "date", label: "Date" }, { key: "type", label: "Type" }, { key: "symbol", label: "Sym" }, { key: "quantity", label: "Qty", fmt: "num", d: 4 },
              { key: "price", label: "Price", fmt: "num", d: 4 }, { key: "amount", label: "Amount", fmt: "num" }, { key: "currency", label: "Ccy" }]} />
          </div>}
          <Note>The Wealthsimple parser is best-effort — export formats change. Always preview. <a className="text-accent" href="/api/import/template" target="_blank" rel="noreferrer">Generic template</a> (requires auth header; see docs/IMPORT_FORMAT.md).</Note>
        </Card>
        <Card title="Manual transaction">
          <div className="grid grid-cols-3 gap-2">
            <Field label="Date"><input type="date" className="input" value={tx.ts} onChange={e => setTx({ ...tx, ts: e.target.value })} /></Field>
            <Field label="Type"><select className="input" value={tx.tx_type} onChange={e => setTx({ ...tx, tx_type: e.target.value })}>{["buy", "sell", "dividend", "deposit", "withdrawal", "fee", "interest", "split", "fx"].map(t => <option key={t}>{t}</option>)}</select></Field>
            <Field label="Symbol"><input className="input" value={tx.symbol} onChange={e => setTx({ ...tx, symbol: e.target.value.toUpperCase() })} /></Field>
            <Field label="Quantity / split ratio"><input className="input" value={tx.quantity} onChange={e => setTx({ ...tx, quantity: e.target.value })} /></Field>
            <Field label="Price"><input className="input" value={tx.price} onChange={e => setTx({ ...tx, price: e.target.value })} /></Field>
            <Field label="Currency"><select className="input" value={tx.currency} onChange={e => setTx({ ...tx, currency: e.target.value })}><option>CAD</option><option>USD</option></select></Field>
            <Field label="Amount (cash tx)"><input className="input" value={tx.amount} onChange={e => setTx({ ...tx, amount: e.target.value })} /></Field>
            <Field label="Fees / withholding"><input className="input" value={tx.fees} onChange={e => setTx({ ...tx, fees: e.target.value })} /></Field>
            <Field label="FX rate → CAD (USD tx)"><input className="input" value={tx.fx_rate_to_base} onChange={e => setTx({ ...tx, fx_rate_to_base: e.target.value })} /></Field>
          </div>
          <button className="btn mt-2" onClick={addTx}>Record</button>
        </Card>
      </div>}
      {id && <Card title="Prepare a trade proposal (never executed by this platform)">
        <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
          <Field label="Symbol"><input className="input" value={p.symbol} onChange={e => setP({ ...p, symbol: e.target.value.toUpperCase() })} /></Field>
          <Field label="Side"><select className="input" value={p.side} onChange={e => setP({ ...p, side: e.target.value })}><option>buy</option><option>sell</option></select></Field>
          <Field label="Quantity"><input className="input" value={p.quantity} onChange={e => setP({ ...p, quantity: e.target.value })} /></Field>
          <Field label="Est. price (blank = last)"><input className="input" value={p.est_price} onChange={e => setP({ ...p, est_price: e.target.value })} /></Field>
          <Field label="Linked thesis"><select className="input" value={p.thesis_entry_id} onChange={e => setP({ ...p, thesis_entry_id: e.target.value })}><option value="">—</option>
            {(journal.data || []).map(j => <option key={j.id} value={j.id}>#{j.id} {j.symbol}</option>)}</select></Field>
        </div>
        <Field label="Reason (evidence-based, ≥20 chars)"><textarea className="input w-full h-14 mt-1" value={p.reason} onChange={e => setP({ ...p, reason: e.target.value })} /></Field>
        <Field label="Key risks"><textarea className="input w-full h-10 mt-1" value={p.risks} onChange={e => setP({ ...p, risks: e.target.value })} /></Field>
        <button className="btn mt-2" onClick={propose}>Run risk checks & create proposal</button>
      </Card>}
      {id && mine.length > 0 && <Card title="Proposals">
        <div className="space-y-3">{mine.map(x => (
          <div key={x.id} className="border border-ink-700 rounded p-2 text-xs">
            <div className="flex justify-between flex-wrap gap-2"><span><b className="text-slate-100">#{x.id} {x.side.toUpperCase()} {num(x.quantity, 4)} {x.symbol}</b> @ ~{num(x.est_price)} {x.currency} · est. {num(x.est_total_cost_base)} CAD · weight after {pct(x.weight_after)}</span>
              <span className="flex gap-2">{x.risk_check?.passed ? <Chip kind="ok">risk checks passed</Chip> : <Chip kind="bad">{x.risk_check?.breaches} limit breach(es)</Chip>}<Chip kind={x.status === "proposed" ? "warn" : "info"}>{x.status}</Chip></span></div>
            <div className="text-slate-400 mt-1">{x.reason}</div>
            <ul className="mt-1">{x.risk_check?.checks.map((c: any) => <li key={c.check} className={c.passed ? "text-slate-500" : c.severity === "breach" ? "text-red-300" : "text-amber-300"}>{c.passed ? "✓" : "✗"} {c.check}: {c.detail}</li>)}</ul>
            {x.status === "proposed" && <div className="flex flex-wrap gap-2 items-end mt-2">
              <Field label="Executed price"><input className="input w-24" onChange={e => setDec({ ...dec, [x.id]: { ...dec[x.id], price: e.target.value } })} /></Field>
              <Field label="Executed qty"><input className="input w-24" onChange={e => setDec({ ...dec, [x.id]: { ...dec[x.id], qty: e.target.value } })} /></Field>
              <Field label="Fees"><input className="input w-20" onChange={e => setDec({ ...dec, [x.id]: { ...dec[x.id], fees: e.target.value } })} /></Field>
              <Field label="FX → CAD"><input className="input w-20" onChange={e => setDec({ ...dec, [x.id]: { ...dec[x.id], fx: e.target.value } })} /></Field>
              <Field label="Note"><input className="input w-48" onChange={e => setDec({ ...dec, [x.id]: { ...dec[x.id], note: e.target.value } })} /></Field>
              <button className="btn" onClick={() => decide(x.id, "placed")}>I placed it in Wealthsimple</button>
              <button className="btn-ghost" onClick={() => decide(x.id, "rejected")}>Reject</button>
            </div>}
            {x.status === "placed" && <div className="text-slate-400 mt-1">Executed {num(x.executed_quantity, 4)} @ {num(x.executed_price, 4)} — {x.decision_note}</div>}
          </div>))}</div>
      </Card>}
      {id && <AccountView id={id} refreshKey={k} />}
    </div>
  );
}
