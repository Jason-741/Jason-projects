"use client";
import { useState } from "react";
import { useApi } from "@/lib/useApi";
import { Card, Empty, ErrorBox, Field, Note, PageHeader, Table } from "@/components/ui";
import SymbolPicker from "@/components/SymbolPicker";
import { big, num, pct } from "@/lib/format";

const ORDER = ["revenue", "cost_of_revenue", "gross_profit", "operating_income", "d_and_a", "interest_expense", "pretax_income", "income_tax",
  "net_income", "eps_basic", "eps_diluted", "shares_diluted", "cash", "inventory", "current_assets", "total_assets", "current_liabilities",
  "total_liabilities", "short_term_debt", "long_term_debt", "goodwill", "equity", "operating_cash_flow", "capex", "dividends_paid", "buybacks",
  "financing_cash_flow"];
const RATIO_PCT = ["gross_margin", "ebitda_margin", "operating_margin", "net_margin", "fcf_margin", "roe", "roa", "roic", "revenue_growth",
  "ebitda_growth", "net_income_growth", "eps_diluted_growth", "free_cash_flow_growth"];

export default function Models() {
  const [sym, setSym] = useState("");
  const [asOf, setAsOf] = useState("");
  const f = useApi<any>(sym ? `/api/securities/${encodeURIComponent(sym)}/fundamentals${asOf ? `?as_of=${asOf}` : ""}` : null);
  const d = f.data;
  const periods: string[] = d?.periods || [];
  const stRows = d ? ORDER.filter(m => d.statements[m]).map(m => ({ metric: m, ...Object.fromEntries(periods.map(p => [p, d.statements[m][p]])),
    _src: d.provenance?.[m]?.[periods[periods.length - 1]] })) : [];
  const ratioKeys = d ? Array.from(new Set(periods.flatMap(p => Object.keys(d.ratios[p] || {})))) : [];
  const ratioRows = ratioKeys.map(k => ({ metric: k, ...Object.fromEntries(periods.map(p => [p, d.ratios[p]?.[k]?.value])),
    _note: d.ratios[periods[periods.length - 1]]?.[k]?.note || (d.ratios[periods[periods.length - 1]]?.[k]?.missing || []).join(", ") }));
  return (
    <div className="space-y-4">
      <PageHeader title="Financial Models" sub="Annual statements from SEC XBRL, POINT-IN-TIME: set 'as of' to see only what had been filed by that date (no look-ahead). Ratios list their formula and any missing inputs.">
        <Field label="As of (optional)"><input type="date" className="input" value={asOf} onChange={e => setAsOf(e.target.value)} /></Field>
        <SymbolPicker value={sym} onChange={setSym} />
      </PageHeader>
      <ErrorBox error={f.error} />
      {d && !periods.length && <Empty>{d.message}</Empty>}
      {periods.length > 0 && <>
        <Card title="Statements (as reported)">
          <Table rows={stRows} cols={[{ key: "metric", label: "Item" }, ...periods.map(p => ({ key: p, label: p, render: (r: any) => <span className="num">{big(r[p])}</span> })),
            { key: "_src", label: "Source (latest)", render: (r: any) => r._src ? <span className="text-slate-500">{r._src.form} filed {r._src.filed} · {r._src.tag}</span> : "" }]} />
        </Card>
        <Card title="Ratios">
          <Table rows={ratioRows} cols={[{ key: "metric", label: "Ratio" }, ...periods.map(p => ({ key: p, label: p,
            render: (r: any) => <span className="num">{RATIO_PCT.includes(r.metric) ? pct(r[p]) : num(r[p])}</span> })), { key: "_note", label: "Note / missing" }]} />
        </Card>
        {d.change_flags?.length > 0 && <Card title="Unusual changes (≥25% y/y) — review">
          <Table rows={d.change_flags.map((x: any) => ({ ...x, period: periods[x.index] }))} cols={[{ key: "item", label: "Item" }, { key: "period", label: "Period" },
            { key: "from", label: "From", render: (r: any) => big(r.from) }, { key: "to", label: "To", render: (r: any) => big(r.to) }, { key: "change", label: "Change", fmt: "pct", color: true }]} />
        </Card>}
        <Note>Banks/insurers need different models (P/B vs ROE, NIM, CET1); early-stage miners need project NPV/P-NAV (see Valuation → Mine model). Generic ratios are not appropriate for every sector.</Note>
      </>}
    </div>
  );
}
