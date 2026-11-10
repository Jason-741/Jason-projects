"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Card, Chip, ErrorBox, Field, KV, Note, PageHeader, Table } from "@/components/ui";
import Plot from "@/components/Plot";

const PCT = ["total_return", "cagr", "volatility", "max_drawdown", "var_95_hist", "cvar_95_hist", "var_99_hist", "var_95_param", "win_rate",
  "benchmark_cagr", "excess_cagr", "tracking_error", "annual_turnover"];

export default function Backtest() {
  const strategies = useApi<any>("/api/backtest/strategies");
  const runs = useApi<any[]>("/api/backtest/runs");
  const [f, setF] = useState({ symbols: "COPX,GLD,URA,XIC", strategy: "trend", params: '{"window": 200}', benchmark: "XIC", start: "", rebalance: "monthly",
    initial_capital: "100", half_spread_bps: "5", slippage_bps: "5", fx_fee_bps: "150", foreign_assets: "COPX,GLD,URA", oos_fraction: "30",
    grid: '{"window": [100, 150, 200]}' });
  const [res, setRes] = useState<any>(null); const [wf, setWf] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const body = () => ({ symbols: f.symbols.split(",").map(s => s.trim()).filter(Boolean), strategy: f.strategy, params: JSON.parse(f.params || "{}"),
    benchmark: f.benchmark || null, start: f.start || null, rebalance: f.rebalance, initial_capital: +f.initial_capital,
    half_spread_bps: +f.half_spread_bps, slippage_bps: +f.slippage_bps, fx_fee_bps: +f.fx_fee_bps,
    foreign_assets: f.foreign_assets.split(",").map(s => s.trim()).filter(Boolean), oos_fraction: +f.oos_fraction / 100 });
  const run = async () => { setErr(null); setBusy(true); try { setRes(await api("/api/backtest/run", { method: "POST", json: body() })); runs.reload(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); } };
  const runWf = async () => { setErr(null); setBusy(true); try { setWf(await api("/api/backtest/walk-forward", { method: "POST", json: { ...body(), param_grid: JSON.parse(f.grid) } })); } catch (e: any) { setErr(e.message); } finally { setBusy(false); } };
  return (
    <div className="space-y-4">
      <PageHeader title="Backtesting" sub="Long-only, one-bar execution lag, explicit spread/slippage/FX costs, no leverage. A backtest is a historical simulation — never proof of future profitability." />
      <Card title="Configuration">
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-2">
          <Field label="Symbols"><input className="input" value={f.symbols} onChange={set("symbols")} /></Field>
          <Field label="Strategy"><select className="input" value={f.strategy} onChange={e => setF({ ...f, strategy: e.target.value, params: JSON.stringify(strategies.data?.[e.target.value]?.params || {}) })}>
            {Object.keys(strategies.data || {}).map(s => <option key={s}>{s}</option>)}</select></Field>
          <Field label="Params (JSON)"><input className="input" value={f.params} onChange={set("params")} /></Field>
          <Field label="Benchmark"><input className="input" value={f.benchmark} onChange={set("benchmark")} /></Field>
          <Field label="Start"><input type="date" className="input" value={f.start} onChange={set("start")} /></Field>
          <Field label="Rebalance"><select className="input" value={f.rebalance} onChange={set("rebalance")}>{["daily", "weekly", "monthly"].map(x => <option key={x}>{x}</option>)}</select></Field>
          <Field label="Capital (CAD)"><input className="input" value={f.initial_capital} onChange={set("initial_capital")} /></Field>
          <Field label="Half-spread bps"><input className="input" value={f.half_spread_bps} onChange={set("half_spread_bps")} /></Field>
          <Field label="Slippage bps"><input className="input" value={f.slippage_bps} onChange={set("slippage_bps")} /></Field>
          <Field label="FX fee bps"><input className="input" value={f.fx_fee_bps} onChange={set("fx_fee_bps")} /></Field>
          <Field label="Foreign-ccy assets"><input className="input" value={f.foreign_assets} onChange={set("foreign_assets")} /></Field>
          <Field label="Hold-out %"><input className="input" value={f.oos_fraction} onChange={set("oos_fraction")} /></Field>
          <Field label="Walk-forward grid"><input className="input" value={f.grid} onChange={set("grid")} /></Field>
        </div>
        <div className="flex gap-2 mt-3"><button className="btn" onClick={run} disabled={busy}>Run backtest</button>
          <button className="btn-ghost" onClick={runWf} disabled={busy}>Walk-forward</button></div>
        <ErrorBox error={err} />
        {f.strategy && strategies.data?.[f.strategy]?.doc && <Note>{strategies.data[f.strategy].doc}</Note>}
      </Card>
      {res && <>
        <Card title="Equity curve" right={<span className="flex gap-2">{res.lookahead_check_passed ? <Chip kind="ok">look-ahead check passed</Chip> : <Chip kind="bad">look-ahead detected</Chip>}
          <span className="num">data {res.fingerprint.slice(0, 12)}</span></span>}>
          <Plot height={320} data={[{ x: res.equity_curve.map((p: any) => p[0]), y: res.equity_curve.map((p: any) => p[1]), type: "scatter", mode: "lines", name: f.strategy, line: { color: "#f5a524" } },
            { x: res.buy_and_hold_curve.map((p: any) => p[0]), y: res.buy_and_hold_curve.map((p: any) => p[1]), type: "scatter", mode: "lines", name: "equal-weight buy & hold", line: { color: "#64748b" } }]}
            layout={{ shapes: res.split?.oos_start ? [{ type: "line", x0: res.split.oos_start, x1: res.split.oos_start, yref: "paper", y0: 0, y1: 1, line: { color: "#ef4444", dash: "dot" } }] : [] }} />
          {res.notes.map((n: string) => <Note key={n}>{n}</Note>)}<Note>{res.disclaimer}</Note>
        </Card>
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <Card title="Strategy metrics (full period)"><KV data={res.metrics} pctKeys={PCT} /></Card>
          <Card title="Buy & hold comparison"><KV data={res.buy_and_hold_metrics} pctKeys={PCT} /></Card>
          {res.split?.in_sample && <Card title="In-sample"><KV data={res.split.in_sample} pctKeys={PCT} /></Card>}
          {res.split?.out_of_sample && <Card title={`Hold-out from ${res.split.oos_start}`}><KV data={res.split.out_of_sample} pctKeys={PCT} /><Note>{res.split.note}</Note></Card>}
        </div>
        <Card title={`Trades (last ${res.trades.length})`}><Table max={300} rows={res.trades} cols={[{ key: "date", label: "Date" }, { key: "symbol", label: "Symbol" },
          { key: "qty", label: "Qty", fmt: "num", d: 4 }, { key: "price", label: "Price", fmt: "num" }, { key: "value", label: "Value", fmt: "num" }, { key: "cost", label: "Cost", fmt: "num", d: 4 }]} /></Card>
      </>}
      {wf && <Card title={`Walk-forward — ${wf.configurations_tested} configurations tested`}>
        <KV data={wf.oos_metrics} pctKeys={PCT} />
        <div className="flex gap-6 mt-2 text-xs"><span>PSR vs 0: <b className="num">{(wf.oos_psr_vs_zero ?? 0).toFixed(3)}</b></span>
          <span>PSR vs deflated benchmark: <b className="num">{(wf.oos_psr_vs_deflated ?? 0).toFixed(3)}</b></span></div>
        <Table rows={wf.windows.map((w: any) => ({ ...w, params: JSON.stringify(w.params) }))} cols={[{ key: "train_start", label: "Train from" }, { key: "train_end", label: "to" },
          { key: "test_start", label: "Test from" }, { key: "test_end", label: "to" }, { key: "params", label: "Chosen params" }, { key: "in_sample_sharpe", label: "IS Sharpe", fmt: "num" }]} />
        <Note>Only out-of-sample returns are stitched together. The deflated benchmark adjusts for the number of configurations tried (multiple-testing bias).</Note>
      </Card>}
      <Card title="Saved runs (reproducible: config + data fingerprint)">
        <Table max={260} rows={(runs.data || []).map(r => ({ ...r, strategy: r.config.strategy, symbols: r.config.symbols?.join(","), cagr: r.metrics.cagr, sharpe: r.metrics.sharpe, mdd: r.metrics.max_drawdown, fp: r.fingerprint.slice(0, 12) }))}
          cols={[{ key: "id", label: "#" }, { key: "created_at", label: "When" }, { key: "strategy", label: "Strategy" }, { key: "symbols", label: "Symbols" },
            { key: "cagr", label: "CAGR", fmt: "pct", color: true }, { key: "sharpe", label: "Sharpe", fmt: "num" }, { key: "mdd", label: "MaxDD", fmt: "pct" }, { key: "fp", label: "Data hash" }]} />
      </Card>
    </div>
  );
}
