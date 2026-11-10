"use client";
import { useState } from "react";
import { useApi } from "@/lib/useApi";
import { Card, Empty, ErrorBox, KV, Note, PageHeader } from "@/components/ui";
import Plot from "@/components/Plot";
import SymbolPicker from "@/components/SymbolPicker";

export default function Quant() {
  const [sym, setSym] = useState("");
  const s = useApi<any>(sym ? `/api/quant/signals/${encodeURIComponent(sym)}` : null);
  const ser = s.data?.series || [];
  const x = ser.map((r: any) => r.date);
  return (
    <div className="space-y-4">
      <PageHeader title="Quantitative Research" sub="Causal indicators (each value uses only data up to that date): trend, momentum, mean-reversion and volatility. Descriptive inputs to research — not trade signals by themselves.">
        <SymbolPicker value={sym} onChange={setSym} />
      </PageHeader>
      <ErrorBox error={s.error} />
      {!sym && <Empty>Pick a security with stored prices.</Empty>}
      {s.data && <>
        <Card title={`Latest (${s.data.as_of})`}><KV data={s.data.latest} pctKeys={["mom_12_1", "vol20", "pct_b"]} /><Note>{s.data.note}</Note></Card>
        <Card title="Price, SMA50/200, Bollinger(20,2)">
          <Plot height={320} data={[
            { x, y: ser.map((r: any) => r.upper), type: "scatter", mode: "lines", name: "BB upper", line: { color: "#334155", width: 1 } },
            { x, y: ser.map((r: any) => r.lower), type: "scatter", mode: "lines", name: "BB lower", line: { color: "#334155", width: 1 }, fill: "tonexty", fillcolor: "rgba(51,65,85,0.15)" },
            { x, y: ser.map((r: any) => r.close), type: "scatter", mode: "lines", name: "close", line: { color: "#e2e8f0", width: 1.2 } },
            { x, y: ser.map((r: any) => r.sma50), type: "scatter", mode: "lines", name: "SMA50", line: { color: "#f5a524", width: 1 } },
            { x, y: ser.map((r: any) => r.sma200), type: "scatter", mode: "lines", name: "SMA200", line: { color: "#60a5fa", width: 1 } }]} />
        </Card>
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <Card title="RSI(14)"><Plot height={200} data={[{ x, y: ser.map((r: any) => r.rsi14), type: "scatter", mode: "lines", line: { color: "#a78bfa" } }]}
            layout={{ shapes: [30, 70].map(v => ({ type: "line", xref: "paper", x0: 0, x1: 1, y0: v, y1: v, line: { color: "#475569", dash: "dot" } })), yaxis: { range: [0, 100] } }} /></Card>
          <Card title="Z-score(20)"><Plot height={200} data={[{ x, y: ser.map((r: any) => r.z20), type: "scatter", mode: "lines", line: { color: "#34d399" } }]} /></Card>
          <Card title="Realized vol (20d, annualized)"><Plot height={200} data={[{ x, y: ser.map((r: any) => r.vol20), type: "scatter", mode: "lines", line: { color: "#f87171" } }]} /></Card>
        </div>
        <Note>Factor models (value, quality, profitability) and ML methods are deliberately not enabled until a cross-sectional point-in-time fundamentals dataset and a written hypothesis exist — see docs/ROADMAP.md.</Note>
      </>}
    </div>
  );
}
