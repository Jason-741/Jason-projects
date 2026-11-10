"use client";
import { useMemo, useState } from "react";
import { useApi } from "@/lib/useApi";
import { Card, Empty, ErrorBox, Note, PageHeader, Table } from "@/components/ui";
import Plot from "@/components/Plot";
import { MARKET_COLS } from "@/components/MarketCols";

const H = ["r_1w", "r_1m", "r_3m", "r_ytd", "r_1y"];

export default function Sectors() {
  const { data, error } = useApi<any[]>("/api/markets/summary");
  const [sector, setSector] = useState<string | null>(null);
  const priced = (data || []).filter(r => r.last != null && !["FX"].includes(r.sector));
  const groups = useMemo(() => {
    const g: Record<string, any[]> = {};
    priced.forEach(r => { const k = `${r.sector ?? "Unclassified"} / ${r.subsector ?? "—"}`; (g[k] ||= []).push(r); });
    return Object.entries(g).map(([k, rs]) => {
      const out: any = { group: k, sector: rs[0].sector, n: rs.length };
      H.forEach(h => { const v = rs.map(r => r[h]).filter((x: any) => x != null); out[h] = v.length ? v.reduce((a: number, b: number) => a + b, 0) / v.length : null; });
      return out;
    }).sort((a, b) => a.group.localeCompare(b.group));
  }, [priced]);
  const z = groups.map(g => H.map(h => g[h] == null ? null : g[h] * 100));
  return (
    <div className="space-y-4">
      <PageHeader title="Sector Intelligence" sub="Equal-weighted average trailing returns of covered securities by sector/subsector. Coverage-dependent: a subsector with one name reflects that name only." />
      <ErrorBox error={error} />
      {groups.length ? <Card title="Heatmap — average trailing return (%)">
        <Plot height={Math.max(260, groups.length * 26 + 60)} data={[{ type: "heatmap", z, x: ["1W", "1M", "3M", "YTD", "1Y"], y: groups.map(g => `${g.group} (${g.n})`),
          colorscale: [[0, "#ef4444"], [0.5, "#151b24"], [1, "#22c55e"]], zmid: 0, texttemplate: "%{z:.1f}", hoverongaps: false }]}
          layout={{ margin: { l: 280, r: 10, t: 10, b: 30 }, yaxis: { automargin: true } }} />
      </Card> : <Empty>No priced securities with sector labels. Seed the universe (python -m app.cli ingest-universe).</Empty>}
      <Card title="Drill-down" right={<select className="input" value={sector ?? ""} onChange={e => setSector(e.target.value || null)}>
        <option value="">all sectors</option>{Array.from(new Set(priced.map(p => p.sector))).map(s => <option key={s} value={s}>{s}</option>)}</select>}>
        <Table rows={priced.filter(p => !sector || p.sector === sector)} cols={MARKET_COLS} />
      </Card>
      <Note>Sector-specific operating metrics (AISC, reserves, grade, production) require company disclosures — capture them per company in Earnings Intelligence and Valuation → Mine model. They are not available from free price feeds.</Note>
    </div>
  );
}
