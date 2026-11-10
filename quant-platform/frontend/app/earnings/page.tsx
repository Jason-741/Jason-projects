"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Card, Chip, Empty, ErrorBox, Field, Note, PageHeader, Table } from "@/components/ui";
import { num } from "@/lib/format";

export default function Earnings() {
  const docs = useApi<any[]>("/api/research/documents");
  const [sel, setSel] = useState<number | null>(null);
  const an = useApi<any>(sel ? `/api/research/documents/${sel}/analysis` : null);
  const [up, setUp] = useState({ doc_type: "transcript", symbol: "", title: "", url: "", published_at: "" });
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState(""); const [ans, setAns] = useState<any>(null);
  const [cmp, setCmp] = useState<number | null>(null); const [cmpRes, setCmpRes] = useState<any>(null);
  const upload = async () => {
    if (!file) return; setErr(null);
    const fd = new FormData(); fd.append("file", file);
    Object.entries(up).forEach(([k, v]) => v && fd.append(k, v));
    try { const r = await api("/api/research/documents", { method: "POST", body: fd }); docs.reload(); setSel(r.id); } catch (e: any) { setErr(e.message); }
  };
  const ask = async () => { setErr(null); try { setAns(await api("/api/research/ask", { method: "POST", json: { question: q, document_ids: [sel] } })); } catch (e: any) { setErr(e.message); } };
  const compare = async () => { if (!sel || !cmp) return; try { setCmpRes(await api(`/api/research/compare?prev_id=${cmp}&cur_id=${sel}`)); } catch (e: any) { setErr(e.message); } };
  return (
    <div className="space-y-4">
      <PageHeader title="Earnings Intelligence" sub="Upload transcripts, MD&A, presentations or filings you obtained from the company, SEDAR+ or EDGAR. Documents are untrusted data: they are segmented with locations so every extracted item cites where it came from." />
      <ErrorBox error={err} />
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card title="Upload document">
          <div className="flex flex-col gap-2">
            <Field label="Type"><select className="input" value={up.doc_type} onChange={e => setUp({ ...up, doc_type: e.target.value })}>
              {["transcript", "presentation", "annual_report", "quarterly_report", "md&a", "press_release", "technical_report"].map(t => <option key={t}>{t}</option>)}</select></Field>
            <Field label="Symbol"><input className="input" value={up.symbol} onChange={e => setUp({ ...up, symbol: e.target.value.toUpperCase() })} /></Field>
            <Field label="Title"><input className="input" value={up.title} onChange={e => setUp({ ...up, title: e.target.value })} /></Field>
            <Field label="Source URL"><input className="input" value={up.url} onChange={e => setUp({ ...up, url: e.target.value })} /></Field>
            <Field label="Published"><input type="date" className="input" value={up.published_at} onChange={e => setUp({ ...up, published_at: e.target.value })} /></Field>
            <input type="file" accept=".txt,.md,.pdf" className="text-xs" onChange={e => setFile(e.target.files?.[0] || null)} />
            <button className="btn" onClick={upload} disabled={!file}>Upload & segment</button>
          </div>
        </Card>
        <Card title="Library" className="xl:col-span-2">
          {(docs.data || []).length ? <Table rows={docs.data!} onRow={r => setSel(r.id)} cols={[{ key: "id", label: "#" }, { key: "title", label: "Title" },
            { key: "doc_type", label: "Type" }, { key: "published_at", label: "Published" }, { key: "source", label: "Source" },
            { key: "sel", label: "", render: r => r.id === sel ? <Chip kind="ok">selected</Chip> : null }]} /> : <Empty>No documents yet.</Empty>}
        </Card>
      </div>
      {an.data && <>
        <Card title={`Analysis — ${an.data.document.title}`} right={<span>{Object.entries(an.data.segments_by_role).map(([k, v]) => `${k}: ${v}`).join(" · ")}</span>}>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 text-xs">
            {Object.entries(an.data.tone).map(([g, t]: any) => (
              <div key={g} className="border border-ink-700 rounded p-2"><div className="label">{g}</div>
                <div>words {t.words} · confidence/1k {num(t.confidence_per_1k, 1)} · uncertainty/1k {num(t.uncertainty_per_1k, 1)} · net {num(t.net_tone_per_1k, 1)}</div></div>))}
          </div>
          {an.data.notes.map((n: string) => <Note key={n}>{n}</Note>)}
        </Card>
        <Card title={`Candidate guidance statements (${an.data.guidance_candidates.length})`}>
          {an.data.guidance_candidates.length ? <Table rows={an.data.guidance_candidates} cols={[{ key: "speaker", label: "Speaker" }, { key: "role", label: "Role" },
            { key: "metrics", label: "Metrics", render: (r: any) => r.metrics.join(", ") }, { key: "text", label: "Statement", render: (r: any) => <span className="whitespace-normal">{r.text}</span> },
            { key: "location", label: "Location" }]} /> : <Empty>No forward-looking numeric statements detected.</Empty>}
        </Card>
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <Card title="Ask the research assistant (cited answers only)">
            <div className="flex gap-2"><input className="input flex-1" value={q} onChange={e => setQ(e.target.value)} placeholder="What production guidance did management give?" />
              <button className="btn" onClick={ask} disabled={q.length < 5}>Ask</button></div>
            {ans && <div className="mt-3 text-xs space-y-2">
              {ans.answer ? <pre className="whitespace-pre-wrap font-sans text-slate-200">{ans.answer}</pre> : <Note>{ans.message}</Note>}
              {ans.citations?.unresolved?.length > 0 && <ErrorBox error={`Unresolved citations: ${ans.citations.unresolved.join(", ")} — treat answer with caution`} />}
              <div className="label mt-2">Retrieved evidence</div>
              {ans.retrieved.map((r: any) => <div key={r.id} className="border-l-2 border-ink-600 pl-2"><span className="text-accent">[{r.id}]</span> {r.speaker} · {r.location}<div className="text-slate-400">{r.excerpt}</div></div>)}
            </div>}
          </Card>
          <Card title="Compare with a previous call">
            <div className="flex gap-2 items-end"><Field label="Previous document"><select className="input" value={cmp ?? ""} onChange={e => setCmp(Number(e.target.value) || null)}>
              <option value="">—</option>{(docs.data || []).filter(d => d.id !== sel).map(d => <option key={d.id} value={d.id}>{d.title}</option>)}</select></Field>
              <button className="btn" onClick={compare} disabled={!cmp}>Compare tone</button></div>
            {cmpRes && <div className="text-xs mt-2">Management net tone change per 1k words: <b className="num">{num(cmpRes.management_net_tone_change_per_1k, 2)}</b><Note>{cmpRes.note}</Note></div>}
          </Card>
        </div>
        <Card title="Segments">
          <div className="max-h-96 overflow-auto text-xs space-y-2">{an.data.segments.map((s: any) => (
            <div key={s.seq}><span className="text-accent">{s.speaker}</span> <Chip kind="info">{s.role}</Chip> <span className="text-slate-500">{s.section} · {s.location}</span>
              <div className="text-slate-300">{s.text}</div></div>))}</div>
        </Card>
      </>}
    </div>
  );
}
