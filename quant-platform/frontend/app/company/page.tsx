"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Card, Chip, Empty, ErrorBox, Note, PageHeader, Stat, Table } from "@/components/ui";
import Plot from "@/components/Plot";
import SymbolPicker from "@/components/SymbolPicker";

export default function Company() {
  const [sym, setSym] = useState("");
  useEffect(() => { const s = new URLSearchParams(window.location.search).get("symbol"); if (s) setSym(s); }, []);
  const sec = useApi<any>(sym ? `/api/securities/${encodeURIComponent(sym)}` : null);
  const px = useApi<any>(sym ? `/api/securities/${encodeURIComponent(sym)}/prices` : null);
  const sig = useApi<any>(sym ? `/api/quant/signals/${encodeURIComponent(sym)}` : null);
  const mult = useApi<any>(sym ? `/api/securities/${encodeURIComponent(sym)}/multiples` : null);
  const [filings, setFilings] = useState<any[] | null>(null);
  const [fErr, setFErr] = useState<string | null>(null);
  const bars = px.data?.bars || [];
  const loadFilings = async () => { setFErr(null); try { setFilings(await api(`/api/securities/${encodeURIComponent(sym)}/filings`)); } catch (e: any) { setFErr(e.message); } };
  return (
    <div className="space-y-4">
      <PageHeader title="Company Research" sub="Prices, indicators, valuation multiples and filings for one security. Every series shows its source.">
        <SymbolPicker value={sym} onChange={setSym} />
      </PageHeader>
      {!sym && <Empty>Pick a security. Add new ones in Settings → Securities.</Empty>}
      <ErrorBox error={sec.error} />
      {sec.data && <Card title={`${sec.data.symbol} · ${sec.data.exchange}`} right={<span>{sec.data.sector} / {sec.data.subsector}</span>}>
        <div className="flex flex-wrap gap-6">
          <Stat label="Name" value={sec.data.name} kind="text" /><Stat label="Currency" value={sec.data.currency} kind="text" />
          <Stat label="Type" value={sec.data.asset_type} kind="text" />
          {sig.data && <><Stat label="Last" value={sig.data.latest.close} /><Stat label="RSI14" value={sig.data.latest.rsi14} d={1} />
            <Stat label="Mom 12-1" value={sig.data.latest.mom_12_1} kind="pct" colored /><Stat label="Vol 20d" value={sig.data.latest.vol20} kind="pct" />
            <Stat label="As of" value={sig.data.as_of} kind="text" /></>}
        </div>
      </Card>}
      {sym && <Card title="Price" right={<span>source: {px.data?.provenance?.sources?.join(", ") || "—"} {px.data?.flagged_bars ? <Chip kind="warn">{px.data.flagged_bars} flagged bars</Chip> : null}</span>}>
        <ErrorBox error={px.error} />
        {bars.length ? <Plot height={340} data={[
          { type: "candlestick", x: bars.map((b: any) => b.date), open: bars.map((b: any) => b.open), high: bars.map((b: any) => b.high),
            low: bars.map((b: any) => b.low), close: bars.map((b: any) => b.close), name: "OHLC", increasing: { line: { color: "#22c55e" } }, decreasing: { line: { color: "#ef4444" } } },
          ...(sig.data ? [{ type: "scatter", mode: "lines", x: sig.data.series.map((s: any) => s.date), y: sig.data.series.map((s: any) => s.sma50), name: "SMA50", line: { color: "#f5a524", width: 1 } },
            { type: "scatter", mode: "lines", x: sig.data.series.map((s: any) => s.date), y: sig.data.series.map((s: any) => s.sma200), name: "SMA200", line: { color: "#60a5fa", width: 1 } }] : [])]}
          layout={{ xaxis: { rangeslider: { visible: false } } }} /> : !px.error && <Empty>No prices stored.</Empty>}
      </Card>}
      {sym && <Card title="Valuation multiples (latest fiscal year, SEC data)">
        {mult.error ? <Note>{mult.error}. Ingest fundamentals (SEC EDGAR) for this company in Settings.</Note> : mult.data &&
          <><Table rows={Object.values(mult.data.multiples)} cols={[{ key: "name", label: "Metric" }, { key: "value", label: "Value", fmt: "num" },
            { key: "formula", label: "Formula" }, { key: "missing", label: "Missing", render: (r: any) => r.missing?.join(", ") || "" }, { key: "note", label: "Note" }]} />
            <Note>Fiscal period {mult.data.fiscal_period}; price {mult.data.price}. {mult.data.note}</Note></>}
      </Card>}
      {sym && <Card title="SEC filings" right={<button className="btn-ghost" onClick={loadFilings}>fetch from EDGAR</button>}>
        <ErrorBox error={fErr} />
        {filings ? <Table rows={filings} cols={[{ key: "form", label: "Form" }, { key: "filed", label: "Filed" }, { key: "report_date", label: "Period" },
          { key: "url", label: "Document", render: (r: any) => <a className="text-accent" href={r.url} target="_blank" rel="noreferrer noopener">open</a> }]} />
          : <Note>Canadian issuers that file only on SEDAR+ are not in EDGAR: download documents from sedarplus.ca and upload them in Earnings Intelligence.</Note>}
      </Card>}
    </div>
  );
}
