"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Card, ErrorBox, Field, Note, PageHeader, Table } from "@/components/ui";

export default function Construct() {
  const [f, setF] = useState({ symbols: "COPX,GLD,URA,XIC", method: "risk_parity", max_weight: "40", shrinkage: "20", capital: "100", er: "" });
  const [res, setRes] = useState<any>(null); const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const run = async () => {
    setErr(null);
    try {
      const er = f.er ? Object.fromEntries(f.er.split(",").map(p => p.split(":").map(x => x.trim())).map(([k, v]) => [k, +v / 100])) : null;
      setRes(await api("/api/portfolio/construct", { method: "POST", json: { symbols: f.symbols.split(",").map(s => s.trim()), method: f.method,
        max_weight: +f.max_weight / 100, shrinkage: +f.shrinkage / 100, capital: +f.capital, expected_returns: er } }));
    } catch (e: any) { setErr(e.message); }
  };
  return (
    <div className="space-y-4">
      <PageHeader title="Portfolio Construction" sub="Long-only, fully invested, per-asset caps, shrunk covariance. Compare against equal weight; at ~$100, simplicity, liquidity and costs matter more than optimizer precision." />
      <Card title="Inputs">
        <div className="flex flex-wrap gap-3 items-end">
          <Field label="Symbols"><input className="input w-72" value={f.symbols} onChange={set("symbols")} /></Field>
          <Field label="Method"><select className="input" value={f.method} onChange={set("method")}>{["equal_weight", "inverse_vol", "min_variance", "risk_parity", "mean_variance"].map(m => <option key={m}>{m}</option>)}</select></Field>
          <Field label="Max weight %"><input className="input w-20" value={f.max_weight} onChange={set("max_weight")} /></Field>
          <Field label="Cov shrinkage %"><input className="input w-20" value={f.shrinkage} onChange={set("shrinkage")} /></Field>
          <Field label="Capital CAD"><input className="input w-24" value={f.capital} onChange={set("capital")} /></Field>
          {f.method === "mean_variance" && <Field label="Expected returns % (SYM:x) — assumptions"><input className="input w-72" value={f.er} onChange={set("er")} /></Field>}
          <button className="btn" onClick={run}>Construct</button>
        </div>
        <ErrorBox error={err} />
      </Card>
      {res && <>
        <Card title={`${res.method} — portfolio vol ${(res.stats.volatility * 100).toFixed(1)}%`}>
          <Table rows={Object.entries(res.allocation).map(([k, v]: any) => ({ symbol: k, ...v }))} cols={[{ key: "symbol", label: "Symbol" }, { key: "weight", label: "Weight", fmt: "pct" },
            { key: "value", label: "CAD", fmt: "num" }, { key: "price", label: "Last price (native)", fmt: "num" }, { key: "shares_fractional", label: "Shares (fractional)", fmt: "num", d: 4 }]} />
          {[...res.warnings, ...res.notes].map((n: string) => <Note key={n}>{n}</Note>)}
          <Note>Share counts ignore FX: convert USD-priced holdings at the current rate. This is an allocation study, not a trade instruction — create a proposal in Live Portfolio to run risk checks.</Note>
        </Card>
        <Card title="Method comparison (annualized vol)">
          <Table rows={Object.entries(res.comparisons).map(([k, v]: any) => ({ method: k, ...v }))} cols={[{ key: "method", label: "Method" }, { key: "volatility", label: "Vol", fmt: "pct" }, { key: "error", label: "Note" }]} />
        </Card>
      </>}
    </div>
  );
}
