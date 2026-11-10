"use client";
import { useRouter } from "next/navigation";
import { useApi } from "@/lib/useApi";
import { Card, Empty, ErrorBox, Note, PageHeader, Table } from "@/components/ui";
import { MARKET_COLS } from "@/components/MarketCols";

const GROUPS = ["Benchmark", "Commodities", "FX"];

export default function Markets() {
  const { data, error } = useApi<any[]>("/api/markets/summary");
  const r = useRouter();
  const rows = data || [];
  const macro = rows.filter(x => GROUPS.includes(x.sector));
  const rest = rows.filter(x => !GROUPS.includes(x.sector) && x.last != null);
  const stale = rows.filter(x => x.stale_days > 5);
  return (
    <div className="space-y-4">
      <PageHeader title="Markets" sub="Benchmarks, commodities, FX and the coverage universe, computed from stored daily closes (total-return adjusted where available)." />
      <ErrorBox error={error} />
      {stale.length > 0 && <Note>{stale.length} series are more than 5 days old — refresh via Settings → ingest. Returns shown are as of each row's date.</Note>}
      <Card title="Benchmarks · Commodities · FX">
        {macro.length ? <Table rows={macro} cols={MARKET_COLS} onRow={x => r.push(`/company?symbol=${encodeURIComponent(x.symbol)}`)} /> : <Empty>Ingest SPY, XIC, ^GSPTSE, HG=F, GC=F, CL=F, CAD=X to populate.</Empty>}
      </Card>
      <Card title="Universe">
        {rest.length ? <Table rows={rest} cols={MARKET_COLS} onRow={x => r.push(`/company?symbol=${encodeURIComponent(x.symbol)}`)} /> : <Empty>No priced securities.</Empty>}
      </Card>
    </div>
  );
}
