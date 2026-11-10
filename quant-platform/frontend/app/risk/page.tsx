"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Card, ErrorBox, Field, KV, Note, PageHeader, Table } from "@/components/ui";
import Plot from "@/components/Plot";
import { pct } from "@/lib/format";

const PCT = ["total_return", "cagr", "volatility", "max_drawdown", "var_95_hist", "cvar_95_hist", "var_99_hist", "var_95_param", "benchmark_cagr", "excess_cagr", "tracking_error", "max_weight", "hhi"];

export default function Risk() {
  const accts = useApi<any[]>("/api/accounts");
  const [w, setW] = useState("COPX:0.35, GLD:0.35, URA:0.30");
  const [bench, setBench] = useState("XIC");
  const [res, setRes] = useState<any>(null); const [mc, setMc] = useState<any>(null); const [st, setSt] = useState<any>(null);
  const [betas, setBetas] = useState("COPX: equity=1.1 copper=1.3 | USD\nGLD: equity=0.1 gold=1.0 | USD\nURA: equity=1.0 uranium=1.2 | USD");
  const [err, setErr] = useState<string | null>(null);
  const weights = () => Object.fromEntries(w.split(",").map(p => p.split(":").map(x => x.trim())).filter(p => p.length === 2).map(([k, v]) => [k.toUpperCase(), +v]));
  const fromAccount = async (id: string) => {
    if (!id) return;
    const s = await api(`/api/accounts/${id}/snapshot`);
    setW(s.positions.filter((p: any) => p.weight).map((p: any) => `${p.symbol}:${p.weight.toFixed(4)}`).join(", "));
  };
  const run = async () => {
    setErr(null);
    try {
      setRes(await api("/api/risk/portfolio", { method: "POST", json: { weights: weights(), benchmark: bench || null } }));
      setMc(await api("/api/risk/montecarlo", { method: "POST", json: { weights: weights(), n_paths: 4000 } }));
      const total = 100;
      const positions = betas.split("\n").filter(Boolean).map(line => {
        const [l, cur] = line.split("|"); const [sym, rest] = l.split(":");
        const kv = Object.fromEntries((rest || "").trim().split(/\s+/).filter(Boolean).map(t => t.split("=")));
        const { equity, ...factors } = kv as any;
        return { symbol: sym.trim().toUpperCase(), value_base: (weights()[sym.trim().toUpperCase()] || 0) * total, currency: (cur || "CAD").trim(),
          beta_equity: equity ? +equity : 1, factor_betas: Object.fromEntries(Object.entries(factors).map(([k, v]) => [k, +(v as string)])) };
      });
      setSt(await api("/api/risk/stress", { method: "POST", json: { positions } }));
    } catch (e: any) { setErr(e.message); }
  };
  const corr = res?.correlation; const syms = corr ? Object.keys(corr) : [];
  return (
    <div className="space-y-4">
      <PageHeader title="Risk Management" sub="Historical and parametric VaR/CVaR, drawdowns, correlations, Euler risk contributions, factor stress tests and block-bootstrap Monte Carlo. Each measure lists its assumptions." />
      <Card title="Portfolio">
        <div className="flex flex-wrap gap-3 items-end">
          <Field label="Weights (SYM:w, …)"><input className="input w-96" value={w} onChange={e => setW(e.target.value)} /></Field>
          <Field label="Benchmark"><input className="input w-24" value={bench} onChange={e => setBench(e.target.value)} /></Field>
          <Field label="…or load from account"><select className="input" onChange={e => fromAccount(e.target.value)}><option value="">—</option>
            {(accts.data || []).map(a => <option key={a.id} value={a.id}>{a.name} ({a.kind})</option>)}</select></Field>
          <button className="btn" onClick={run}>Analyze</button>
        </div>
        <Field label="Stress betas (SYM: equity=β factor=β | currency) — estimates you supply"><textarea className="input w-full h-20 mt-2 num" value={betas} onChange={e => setBetas(e.target.value)} /></Field>
        <ErrorBox error={err} />
      </Card>
      {res && <>
        <Card title="Risk summary (daily data)"><KV data={{ ...res.summary, ...res.concentration }} pctKeys={PCT} />
          {res.assumptions.map((a: string) => <Note key={a}>{a}</Note>)}{res.notes.map((a: string) => <Note key={a}>{a}</Note>)}</Card>
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <Card title="Risk contributions"><Table rows={Object.entries(res.risk_contributions).map(([k, v]: any) => ({ symbol: k, ...v, vol: res.asset_vol[k], beta: res.betas?.[k] }))}
            cols={[{ key: "symbol", label: "Symbol" }, { key: "weight", label: "Weight", fmt: "pct" }, { key: "vol", label: "Vol", fmt: "pct" },
              { key: "beta", label: "β vs bench", fmt: "num" }, { key: "pct_of_risk", label: "% of risk", fmt: "pct" }]} /></Card>
          <Card title="Correlation"><Plot height={260} data={[{ type: "heatmap", z: syms.map(a => syms.map(b => corr[a][b])), x: syms, y: syms, zmin: -1, zmax: 1,
            colorscale: [[0, "#3b82f6"], [0.5, "#151b24"], [1, "#ef4444"]], texttemplate: "%{z:.2f}" }]} /></Card>
        </div>
        <Card title="Drawdown"><Plot height={200} data={[{ x: res.drawdown.map((d: any) => d[0]), y: res.drawdown.map((d: any) => d[1]), type: "scatter", fill: "tozeroy", line: { color: "#ef4444" } }]} layout={{ yaxis: { tickformat: ".0%" } }} /></Card>
      </>}
      {st && <Card title="Stress tests (first-order factor model)">
        <Table rows={Object.entries(st.results).map(([k, v]: any) => ({ key: k, label: v.label, ret: v.portfolio_return, pnl: v.pnl,
          worst: v.positions.reduce((a: any, b: any) => (a && a.pnl < b.pnl ? a : b), null)?.symbol }))}
          cols={[{ key: "label", label: "Scenario" }, { key: "ret", label: "Portfolio", fmt: "pct", color: true }, { key: "pnl", label: "P&L per $100", fmt: "num", color: true }, { key: "worst", label: "Worst position" }]} />
        <Note>{st.method}. Correlations rise in crises; real losses can exceed these estimates.</Note>
      </Card>}
      {mc && <Card title={`Monte Carlo — ${mc.n_paths} paths × ${mc.horizon_days} days (${mc.method})`}>
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <Plot height={260} data={["5", "25", "50", "75", "95"].map((q, i) => ({ y: mc.fan_chart[q], type: "scatter", mode: "lines", name: `p${q}`,
            line: { color: ["#ef4444", "#f59e0b", "#e2e8f0", "#84cc16", "#22c55e"][i], width: q === "50" ? 2 : 1 } }))} layout={{ xaxis: { title: "days" } }} />
          <div className="text-xs space-y-1">
            <div>P(loss over horizon): <b className="num">{pct(mc.prob_loss)}</b> · P(&gt;10% loss): <b className="num">{pct(mc.prob_loss_gt_10pct)}</b> · P(&gt;20% loss): <b className="num">{pct(mc.prob_loss_gt_20pct)}</b></div>
            <div>Terminal return percentiles: {Object.entries(mc.terminal_return_percentiles).map(([k, v]) => `p${k} ${pct(v)}`).join(" · ")}</div>
            <div>Max drawdown percentiles: {Object.entries(mc.max_drawdown_percentiles).map(([k, v]) => `p${k} ${pct(v)}`).join(" · ")}</div>
            <div>Sample: {mc.sample_observations} days · seed {mc.seed}</div>
            <Note>{mc.caveat}</Note>
          </div>
        </div>
      </Card>}
    </div>
  );
}
