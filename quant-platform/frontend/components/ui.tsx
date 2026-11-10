"use client";
import React from "react";
import { isNum, num, pct, tone } from "@/lib/format";

export function Card({ title, right, children, className = "" }: { title?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {title !== undefined && <div className="card-h"><span>{title}</span>{right}</div>}
      <div className="p-3">{children}</div>
    </section>
  );
}

export function PageHeader({ title, sub, children }: { title: string; sub?: string; children?: React.ReactNode }) {
  return (
    <div className="flex items-end justify-between mb-4 gap-4 flex-wrap">
      <div>
        <h1 className="text-lg font-semibold text-slate-100">{title}</h1>
        {sub && <p className="text-xs text-slate-500 mt-0.5 max-w-3xl">{sub}</p>}
      </div>
      <div className="flex gap-2 items-center flex-wrap">{children}</div>
    </div>
  );
}

export function ErrorBox({ error }: { error: string | null | undefined }) {
  if (!error) return null;
  return <div className="text-xs border border-down/40 bg-down/10 text-red-300 rounded px-3 py-2 my-2 break-words">{error}</div>;
}

export function Note({ children }: { children: React.ReactNode }) {
  return <div className="text-[11px] text-slate-500 border-l-2 border-ink-600 pl-2 my-2">{children}</div>;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="text-sm text-slate-500 py-6 text-center">{children}</div>;
}

export function Chip({ kind, children }: { kind: "ok" | "warn" | "bad" | "info"; children: React.ReactNode }) {
  const c = { ok: "bg-up/15 text-green-300 border-up/30", warn: "bg-accent/15 text-amber-300 border-accent/30",
    bad: "bg-down/15 text-red-300 border-down/30", info: "bg-ink-700 text-slate-300 border-ink-600" }[kind];
  return <span className={`inline-block text-[10px] uppercase tracking-wide border rounded px-1.5 py-0.5 ${c}`}>{children}</span>;
}

export function Stat({ label, value, kind = "num", d = 2, colored = false }: { label: string; value: unknown; kind?: "num" | "pct" | "text"; d?: number; colored?: boolean }) {
  const txt = kind === "pct" ? pct(value, d) : kind === "num" ? num(value, Number.isInteger(value) ? 0 : d) : String(value ?? "—");
  return (
    <div className="min-w-[90px]">
      <div className="label">{label}</div>
      <div className={`num text-sm ${colored ? tone(value) : "text-slate-100"}`}>{txt}</div>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="flex flex-col gap-1"><span className="label">{label}</span>{children}</label>;
}

export type Col<T> = { key: string; label: string; fmt?: "pct" | "num" | "int" | "text"; color?: boolean; render?: (r: T) => React.ReactNode; d?: number };

export function Table<T extends Record<string, any>>({ rows, cols, onRow, max = 600 }: { rows: T[]; cols: Col<T>[]; onRow?: (r: T) => void; max?: number }) {
  const [sort, setSort] = React.useState<{ k: string; dir: 1 | -1 } | null>(null);
  const sorted = React.useMemo(() => {
    if (!sort) return rows;
    return [...rows].sort((a, b) => {
      const x = a[sort.k], y = b[sort.k];
      if (x == null) return 1; if (y == null) return -1;
      return (x > y ? 1 : x < y ? -1 : 0) * sort.dir;
    });
  }, [rows, sort]);
  return (
    <div className="overflow-auto" style={{ maxHeight: max }}>
      <table className="grid-t">
        <thead><tr>{cols.map(c => (
          <th key={c.key} className="cursor-pointer select-none" onClick={() => setSort(s => ({ k: c.key, dir: s?.k === c.key && s.dir === -1 ? 1 : -1 }))}>
            {c.label}{sort?.k === c.key ? (sort.dir === -1 ? " ↓" : " ↑") : ""}
          </th>))}</tr></thead>
        <tbody>{sorted.map((r, i) => (
          <tr key={i} onClick={() => onRow?.(r)} className={onRow ? "cursor-pointer" : ""}>
            {cols.map(c => {
              const v = r[c.key];
              const content = c.render ? c.render(r) : c.fmt === "pct" ? pct(v, c.d ?? 1) : c.fmt === "num" ? num(v, c.d ?? 2) : c.fmt === "int" ? (isNum(v) ? v.toFixed(0) : "—") : (v ?? "—");
              return <td key={c.key} className={`${c.fmt && c.fmt !== "text" ? "num text-right" : ""} ${c.color ? tone(v) : ""}`}>{content as React.ReactNode}</td>;
            })}
          </tr>))}</tbody>
      </table>
    </div>
  );
}

export function KV({ data, pctKeys = [] }: { data: Record<string, unknown>; pctKeys?: string[] }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-2">
      {Object.entries(data).filter(([, v]) => typeof v !== "object" || v === null).map(([k, v]) => (
        <Stat key={k} label={k.replace(/_/g, " ")} value={v} kind={typeof v === "string" ? "text" : pctKeys.includes(k) ? "pct" : "num"} />
      ))}
    </div>
  );
}
