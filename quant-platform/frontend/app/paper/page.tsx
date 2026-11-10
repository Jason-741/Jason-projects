"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import AccountPicker from "@/components/AccountPicker";
import AccountView from "@/components/AccountView";
import { Card, ErrorBox, Field, Note, PageHeader } from "@/components/ui";

export default function Paper() {
  const [id, setId] = useState<number | null>(null); const [k, setK] = useState(0);
  const [o, setO] = useState({ symbol: "", side: "buy", quantity: "", price: "" });
  const [dep, setDep] = useState("100"); const [err, setErr] = useState<string | null>(null);
  const order = async () => { setErr(null); try { await api(`/api/accounts/${id}/paper-orders`, { method: "POST", json: { symbol: o.symbol, side: o.side, quantity: +o.quantity, price: o.price ? +o.price : null } }); setK(k + 1); } catch (e: any) { setErr(e.message); } };
  const deposit = async () => { setErr(null); try { await api(`/api/accounts/${id}/transactions`, { method: "POST", json: { ts: new Date().toISOString(), tx_type: "deposit", amount: +dep, currency: "CAD" } }); setK(k + 1); } catch (e: any) { setErr(e.message); } };
  return (
    <div className="space-y-4">
      <PageHeader title="Paper Trading" sub="Simulated account, strictly separate from real money. Fills use the latest stored close ± configured slippage, plus commission and FX fee assumptions.">
        <AccountPicker kind="paper" value={id} onChange={setId} />
      </PageHeader>
      {id && <Card title="Simulated order">
        <div className="flex flex-wrap gap-3 items-end">
          <Field label="Symbol"><input className="input w-28" value={o.symbol} onChange={e => setO({ ...o, symbol: e.target.value.toUpperCase() })} /></Field>
          <Field label="Side"><select className="input" value={o.side} onChange={e => setO({ ...o, side: e.target.value })}><option>buy</option><option>sell</option></select></Field>
          <Field label="Quantity"><input className="input w-24" value={o.quantity} onChange={e => setO({ ...o, quantity: e.target.value })} /></Field>
          <Field label="Ref price (blank = last close)"><input className="input w-28" value={o.price} onChange={e => setO({ ...o, price: e.target.value })} /></Field>
          <button className="btn" onClick={order} disabled={!o.symbol || !o.quantity}>Simulate fill</button>
          <span className="w-6" />
          <Field label="Simulated deposit CAD"><input className="input w-24" value={dep} onChange={e => setDep(e.target.value)} /></Field>
          <button className="btn-ghost" onClick={deposit}>Deposit</button>
        </div>
        <ErrorBox error={err} />
        <Note>USD-priced securities need simulated USD cash: record an FX transaction (fx type) or buy CAD-listed equivalents. Strategy readiness requires a paper-trading period before live use.</Note>
      </Card>}
      {id && <AccountView id={id} refreshKey={k} />}
    </div>
  );
}
