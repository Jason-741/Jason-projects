"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useApi } from "@/lib/useApi";
import { Card, ErrorBox, Field, Note, PageHeader, Table } from "@/components/ui";

type F = { key: string; label: string; min?: number; max?: number };
const DEFAULT: F[] = [
  { key: "mom_12_1", label: "Momentum 12-1 min (%)" }, { key: "vs_sma200", label: "vs SMA200 min (%)" },
  { key: "vol_60d", label: "Vol 60d max (%)" }, { key: "rsi14", label: "RSI14 max" }, { key: "r_1m", label: "1M return min (%)" },
];

export default function Screener() {
  const { data, error } = useApi<any[]>("/api/markets/summary");
  const r = useRouter();
  const [f, setF] = useState<Record<string, string>>({});
  const [sector, setSector] = useState("");
  const rows = (data || []).filter(x => x.last != null && (!sector || x.sector === sector)).filter(x => {
    const g = (k: string) => (f[k] === undefined || f[k] === "" ? null : Number(f[k]));
    if (g("mom_12_1") != null && !(x.mom_12_1 != null && x.mom_12_1 * 100 >= g("mom_12_1")!)) return false;
    if (g("vs_sma200") != null && !(x.vs_sma200 != null && x.vs_sma200 * 100 >= g("vs_sma200")!)) return false;
    if (g("vol_60d") != null && !(x.vol_60d != null && x.vol_60d * 100 <= g("vol_60d")!)) return false;
    if (g("rsi14") != null && !(x.rsi14 != null && x.rsi14 <= g("rsi14")!)) return false;
    if (g("r_1m") != null && !(x.r_1m != null && x.r_1m * 100 >= g("r_1m")!)) return false;
    return true;
  });
  return (
    <div className="space-y-4">
      <PageHeader title="Stock Screener" sub="Quantitative screen over stored prices. A screen produces candidates for research — never a buy list." />
      <ErrorBox error={error} />
      <Card title="Filters">
        <div className="flex flex-wrap gap-3 items-end">
          <Field label="Sector"><select className="input" value={sector} onChange={e => setSector(e.target.value)}>
            <option value="">all</option>{Array.from(new Set((data || []).map(d => d.sector).filter(Boolean))).map(s => <option key={s}>{s}</option>)}</select></Field>
          {DEFAULT.map(d => <Field key={d.key} label={d.label}><input className="input w-28" value={f[d.key] ?? ""} onChange={e => setF({ ...f, [d.key]: e.target.value })} /></Field>)}
          <button className="btn-ghost" onClick={() => { setF({}); setSector(""); }}>reset</button>
        </div>
        <Note>Fundamental screens (valuation, profitability, leverage, sector operating metrics) use point-in-time SEC data per company in Financial Models; a cross-sectional fundamental screen needs fundamentals ingested for the whole universe first.</Note>
      </Card>
      <Card title={`Results (${rows.length})`}>
        <Table rows={rows} onRow={x => r.push(`/company?symbol=${encodeURIComponent(x.symbol)}`)} cols={[
          { key: "symbol", label: "Symbol" }, { key: "name", label: "Name" }, { key: "sector", label: "Sector" }, { key: "subsector", label: "Subsector" },
          { key: "last", label: "Last", fmt: "num" }, { key: "mom_12_1", label: "Mom 12-1", fmt: "pct", color: true },
          { key: "vs_sma200", label: "vs SMA200", fmt: "pct", color: true }, { key: "rsi14", label: "RSI14", fmt: "num", d: 1 },
          { key: "vol_60d", label: "Vol60", fmt: "pct" }, { key: "r_1m", label: "1M", fmt: "pct", color: true }, { key: "r_1y", label: "1Y", fmt: "pct", color: true }]} />
      </Card>
    </div>
  );
}
