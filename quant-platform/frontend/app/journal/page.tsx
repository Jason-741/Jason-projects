"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Card, Chip, Empty, ErrorBox, Field, Note, PageHeader } from "@/components/ui";
import { num, pct } from "@/lib/format";

const EMPTY = { symbol: "", analysis_date: new Date().toISOString().slice(0, 10), thesis: "", valuation_low: "", valuation_base: "", valuation_high: "",
  valuation_assumptions: "", catalysts: "", risks: "", invalidation_conditions: "", expected_holding_period: "", confidence: "3", account_kind: "live" };

export default function Journal() {
  const j = useApi<any[]>("/api/journal");
  const [f, setF] = useState<any>(EMPTY); const [err, setErr] = useState<string | null>(null);
  const [rev, setRev] = useState<Record<number, any>>({});
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const n = (v: string) => (v === "" ? null : +v);
  const create = async () => {
    setErr(null);
    try { await api("/api/journal", { method: "POST", json: { ...f, valuation_low: n(f.valuation_low), valuation_base: n(f.valuation_base), valuation_high: n(f.valuation_high), confidence: n(f.confidence) } }); setF(EMPTY); j.reload(); }
    catch (e: any) { setErr(e.message); }
  };
  const update = async (id: number) => {
    setErr(null); const r = rev[id] || {};
    const body: any = {}; Object.entries(r).forEach(([k, v]) => { if (v !== "") body[k] = ["entry_price", "exit_price", "allocation_pct"].includes(k) ? +(v as string) : v; });
    try { await api(`/api/journal/${id}`, { method: "PATCH", json: body }); setRev({ ...rev, [id]: {} }); j.reload(); } catch (e: any) { setErr(e.message); }
  };
  const ta = (k: string, label: string, h = "h-16") => <Field label={label}><textarea className={`input w-full ${h}`} value={f[k]} onChange={set(k)} /></Field>;
  return (
    <div className="space-y-4">
      <PageHeader title="Investment Journal" sub="Write the thesis BEFORE the outcome is known. Original thesis fields cannot be edited later; developments and reviews are appended. Judge decisions separately from outcomes." />
      <ErrorBox error={err} />
      <Card title="New entry">
        <div className="grid grid-cols-2 md:grid-cols-7 gap-2">
          <Field label="Symbol"><input className="input" value={f.symbol} onChange={e => setF({ ...f, symbol: e.target.value.toUpperCase() })} /></Field>
          <Field label="Analysis date"><input type="date" className="input" value={f.analysis_date} onChange={set("analysis_date")} /></Field>
          <Field label="Value low"><input className="input" value={f.valuation_low} onChange={set("valuation_low")} /></Field>
          <Field label="Value base"><input className="input" value={f.valuation_base} onChange={set("valuation_base")} /></Field>
          <Field label="Value high"><input className="input" value={f.valuation_high} onChange={set("valuation_high")} /></Field>
          <Field label="Confidence 1–5"><input className="input" value={f.confidence} onChange={set("confidence")} /></Field>
          <Field label="Book"><select className="input" value={f.account_kind} onChange={set("account_kind")}><option>live</option><option>paper</option></select></Field>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
          {ta("thesis", "Thesis (what the market is missing, with evidence)", "h-24")}{ta("valuation_assumptions", "Valuation assumptions", "h-24")}
          {ta("catalysts", "Expected catalysts")}{ta("risks", "Identified risks")}
          {ta("invalidation_conditions", "Thesis invalidation conditions (specific, observable)")}
          <Field label="Expected holding period"><input className="input" value={f.expected_holding_period} onChange={set("expected_holding_period")} /></Field>
        </div>
        <button className="btn mt-2" onClick={create} disabled={!f.symbol || !f.thesis}>Save entry</button>
      </Card>
      {(j.data || []).length === 0 && <Empty>No entries yet.</Empty>}
      {(j.data || []).map(e => (
        <Card key={e.id} title={`#${e.id} ${e.symbol} · ${e.analysis_date}`} right={<span className="flex gap-2"><Chip kind="info">{e.status}</Chip><Chip kind={e.account_kind === "live" ? "bad" : "info"}>{e.account_kind}</Chip>
          <Chip kind={e.readiness.completed === e.readiness.total ? "ok" : "warn"}>readiness {e.readiness.completed}/{e.readiness.total}</Chip></span>}>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 text-xs">
            <div className="lg:col-span-2 space-y-1">
              <div className="text-slate-200 whitespace-pre-wrap">{e.thesis}</div>
              <div className="text-slate-400">Valuation {num(e.valuation_low)} / {num(e.valuation_base)} / {num(e.valuation_high)} · confidence {e.confidence ?? "—"} · horizon {e.expected_holding_period ?? "—"}</div>
              {e.catalysts && <div><span className="label">Catalysts</span> {e.catalysts}</div>}
              {e.risks && <div><span className="label">Risks</span> {e.risks}</div>}
              {e.invalidation_conditions && <div><span className="label">Invalidation</span> {e.invalidation_conditions}</div>}
              {(e.updates || []).map((u: any, i: number) => <div key={i} className="border-l-2 border-ink-600 pl-2"><span className="text-slate-500">{u.date}</span> {u.note}</div>)}
              {e.realized_return != null && <div>Realized: <b className="num">{pct(e.realized_return)}</b> · thesis correct: {e.thesis_was_correct ?? "—"} · attribution: {e.outcome_attribution ?? "—"}</div>}
              {e.lessons && <div><span className="label">Lessons</span> {e.lessons}</div>}
            </div>
            <div className="space-y-1">
              <div className="label">Update / review</div>
              <select className="input w-full" onChange={x => setRev({ ...rev, [e.id]: { ...rev[e.id], status: x.target.value } })} defaultValue=""><option value="">status…</option>{["research", "open", "closed", "abandoned"].map(s => <option key={s}>{s}</option>)}</select>
              <div className="grid grid-cols-2 gap-1">
                <input className="input" placeholder="entry price" onChange={x => setRev({ ...rev, [e.id]: { ...rev[e.id], entry_price: x.target.value } })} />
                <input type="date" className="input" onChange={x => setRev({ ...rev, [e.id]: { ...rev[e.id], entry_date: x.target.value } })} />
                <input className="input" placeholder="exit price" onChange={x => setRev({ ...rev, [e.id]: { ...rev[e.id], exit_price: x.target.value } })} />
                <input type="date" className="input" onChange={x => setRev({ ...rev, [e.id]: { ...rev[e.id], exit_date: x.target.value } })} />
              </div>
              <input className="input w-full" placeholder="development (earnings, guidance change…)" onChange={x => setRev({ ...rev, [e.id]: { ...rev[e.id], development: x.target.value } })} />
              <div className="grid grid-cols-2 gap-1">
                <select className="input" defaultValue="" onChange={x => setRev({ ...rev, [e.id]: { ...rev[e.id], thesis_was_correct: x.target.value } })}><option value="">thesis correct?</option>{["yes", "partly", "no", "unclear"].map(s => <option key={s}>{s}</option>)}</select>
                <select className="input" defaultValue="" onChange={x => setRev({ ...rev, [e.id]: { ...rev[e.id], outcome_attribution: x.target.value } })}><option value="">skill or luck?</option>{["skill", "luck", "mixed", "unclear"].map(s => <option key={s}>{s}</option>)}</select>
              </div>
              <textarea className="input w-full h-12" placeholder="lessons learned" onChange={x => setRev({ ...rev, [e.id]: { ...rev[e.id], lessons: x.target.value } })} />
              <button className="btn-ghost" onClick={() => update(e.id)}>Append update</button>
            </div>
          </div>
          {e.readiness.items.filter((i: any) => !i.done).length > 0 && <Note>Missing for readiness: {e.readiness.items.filter((i: any) => !i.done).map((i: any) => i.label).join("; ")}</Note>}
        </Card>))}
    </div>
  );
}
