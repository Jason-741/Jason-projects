"use client";
import Link from "next/link";
import { useApi } from "@/lib/useApi";
import { Card, Chip, Empty, ErrorBox, PageHeader, Table } from "@/components/ui";

export default function Overview() {
  const prov = useApi<any[]>("/api/data/providers");
  const cov = useApi<any>("/api/data/coverage");
  const accts = useApi<any[]>("/api/accounts");
  const props = useApi<any[]>("/api/proposals");
  const runs = useApi<any[]>("/api/data/runs?limit=8");
  const mk = useApi<any[]>("/api/markets/summary");
  const open = (props.data || []).filter(p => p.status === "proposed");
  const movers = (mk.data || []).filter(r => r.r_1d != null).sort((a, b) => Math.abs(b.r_1d) - Math.abs(a.r_1d)).slice(0, 10);
  return (
    <div className="space-y-4">
      <PageHeader title="Overview" sub="Platform state at a glance. Every figure comes from stored, timestamped data. Empty panels mean no data has been ingested yet; nothing here is simulated." />
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card title="Data providers" right={<Link className="text-accent" href="/settings">configure</Link>}>
          <ErrorBox error={prov.error} />
          <ul className="space-y-1 text-xs">{(prov.data || []).map(p => (
            <li key={p.name} className="flex justify-between gap-2"><span className="text-slate-300">{p.name}</span>
              {p.configured ? <Chip kind="ok">ready</Chip> : <Chip kind="warn">needs {p.requires.join(", ") || "setup"}</Chip>}</li>))}</ul>
        </Card>
        <Card title="Coverage">
          {cov.data && cov.data.securities.length ? (
            <div className="text-xs space-y-1">
              <div>{cov.data.securities.length} securities · {cov.data.securities.reduce((a: number, s: any) => a + s.price_rows, 0).toLocaleString()} price bars</div>
              <div>{cov.data.securities.filter((s: any) => s.fundamental_facts > 0).length} with point-in-time fundamentals</div>
              <div>{cov.data.macro.length} macro series</div>
            </div>) : <Empty>No data ingested. Run <code className="num">python -m app.cli ingest-universe</code> or use Settings.</Empty>}
        </Card>
        <Card title="Accounts">
          {(accts.data || []).length ? <ul className="text-xs space-y-1">{accts.data!.map(a => (
            <li key={a.id} className="flex justify-between"><Link href={a.kind === "live" ? "/live" : "/paper"} className="hover:text-accent">{a.name}</Link>
              <Chip kind={a.kind === "live" ? "bad" : "info"}>{a.kind}</Chip></li>))}</ul> : <Empty>No accounts yet.</Empty>}
        </Card>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card title="Largest 1-day moves (stored data)">
          {movers.length ? <Table rows={movers} cols={[{ key: "symbol", label: "Symbol" }, { key: "subsector", label: "Subsector" },
            { key: "last", label: "Last", fmt: "num" }, { key: "r_1d", label: "1D", fmt: "pct", color: true },
            { key: "r_1m", label: "1M", fmt: "pct", color: true }, { key: "last_date", label: "As of" }]} /> : <Empty>No price data.</Empty>}
        </Card>
        <Card title={`Open trade proposals (${open.length})`} right={<Link className="text-accent" href="/live">review</Link>}>
          {open.length ? <Table rows={open} cols={[{ key: "symbol", label: "Symbol" }, { key: "side", label: "Side" },
            { key: "quantity", label: "Qty", fmt: "num", d: 4 }, { key: "est_total_cost_base", label: "Est. cost CAD", fmt: "num" },
            { key: "weight_after", label: "Wt after", fmt: "pct" },
            { key: "risk", label: "Risk check", render: r => r.risk_check?.passed ? <Chip kind="ok">pass</Chip> : <Chip kind="bad">{r.risk_check?.breaches} breach</Chip> }]} />
            : <Empty>No proposals awaiting your decision.</Empty>}
        </Card>
      </div>
      <Card title="Recent ingestion runs">
        {(runs.data || []).length ? <Table rows={runs.data!} cols={[{ key: "id", label: "#" }, { key: "provider", label: "Provider" },
          { key: "dataset", label: "Dataset" }, { key: "params", label: "Params", render: r => <span className="text-slate-400">{JSON.stringify(r.params)}</span> },
          { key: "status", label: "Status", render: r => <Chip kind={r.status === "ok" ? "ok" : r.status === "partial" ? "warn" : "bad"}>{r.status}</Chip> },
          { key: "rows_written", label: "Rows", fmt: "int" }, { key: "error", label: "Error" }]} /> : <Empty>No runs yet.</Empty>}
      </Card>
      <p className="text-[10px] text-slate-600">Research tool only. Nothing here is investment advice; all live orders are placed by you in Wealthsimple.</p>
    </div>
  );
}
