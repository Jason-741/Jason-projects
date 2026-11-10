"use client";
import { useApi } from "@/lib/useApi";
import { Card, Chip, ErrorBox, Note, Stat, Table } from "./ui";

export default function AccountView({ id, refreshKey }: { id: number; refreshKey: number }) {
  const snap = useApi<any>(`/api/accounts/${id}/snapshot`, [refreshKey]);
  const txs = useApi<any[]>(`/api/accounts/${id}/transactions`, [refreshKey]);
  const s = snap.data;
  return (
    <div className="space-y-4">
      <ErrorBox error={snap.error} />
      {s && <Card title={`${s.account.name}`} right={<Chip kind={s.account.kind === "live" ? "bad" : "info"}>{s.account.kind}</Chip>}>
        <div className="flex flex-wrap gap-6">
          <Stat label="Total value (CAD)" value={s.total_value_base} /><Stat label="Market value" value={s.market_value_base} />
          <Stat label="Cash (CAD eq.)" value={s.cash_base} /><Stat label="Net contributions" value={s.net_contributions_base} />
          <Stat label="Net P&L" value={s.pnl.net_pnl_base} colored /><Stat label="Gross P&L (pre-fees/FX)" value={s.pnl.gross_pnl_base} colored />
          <Stat label="Return on contributions" value={s.pnl.simple_return_on_contributions} kind="pct" colored />
          <Stat label="Realized" value={s.pnl.realized_base} colored /><Stat label="Unrealized" value={s.pnl.unrealized_base} colored />
          <Stat label="Dividends" value={s.pnl.dividends_base} /><Stat label="Fees" value={s.pnl.fees_base} /><Stat label="FX cost (est.)" value={s.pnl.fx_costs_base_est} />
        </div>
        <div className="text-xs text-slate-400 mt-2">Cash: {Object.entries(s.cash_by_currency).map(([c, v]: any) => `${c} ${v.toFixed(2)}`).join(" · ") || "none"}</div>
        {s.warnings.map((w: string, i: number) => <Note key={i}>⚠ {w}</Note>)}
        {s.missing_prices.length > 0 && <Note>No stored price for: {s.missing_prices.join(", ")} — ingest prices to value these positions.</Note>}
        {s.notes.map((n: string) => <Note key={n}>{n}</Note>)}
      </Card>}
      {s && <Card title="Holdings">
        <Table rows={s.positions} cols={[{ key: "symbol", label: "Symbol" }, { key: "quantity", label: "Qty", fmt: "num", d: 4 }, { key: "currency", label: "Ccy" },
          { key: "avg_cost_native", label: "Avg cost (native)", fmt: "num", d: 4 }, { key: "price", label: "Price", fmt: "num" }, { key: "price_date", label: "Price date" },
          { key: "market_value_base", label: "MV CAD", fmt: "num" }, { key: "acb_base", label: "ACB CAD", fmt: "num" },
          { key: "unrealized_pnl_base", label: "Unrl P&L", fmt: "num", color: true }, { key: "unrealized_pct", label: "Unrl %", fmt: "pct", color: true }, { key: "weight", label: "Weight", fmt: "pct" }]} />
      </Card>}
      <Card title="Transactions">
        <Table max={320} rows={txs.data || []} cols={[{ key: "ts", label: "Date", render: (r: any) => r.ts.slice(0, 10) }, { key: "type", label: "Type" }, { key: "symbol", label: "Symbol" },
          { key: "quantity", label: "Qty", fmt: "num", d: 4 }, { key: "price", label: "Price", fmt: "num", d: 4 }, { key: "amount", label: "Amount", fmt: "num" },
          { key: "currency", label: "Ccy" }, { key: "fees", label: "Fees", fmt: "num" }, { key: "fx_rate_to_base", label: "FX→CAD", fmt: "num", d: 4 },
          { key: "origin", label: "Origin" }, { key: "note", label: "Note" }]} />
      </Card>
    </div>
  );
}
