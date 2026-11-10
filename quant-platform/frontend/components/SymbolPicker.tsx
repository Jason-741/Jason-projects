"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function SymbolPicker({ value, onChange }: { value: string; onChange: (s: string) => void }) {
  const [q, setQ] = useState(value);
  const [opts, setOpts] = useState<any[]>([]);
  useEffect(() => setQ(value), [value]);
  useEffect(() => {
    const t = setTimeout(() => { api(`/api/securities?q=${encodeURIComponent(q)}&limit=12`).then(setOpts).catch(() => setOpts([])); }, 200);
    return () => clearTimeout(t);
  }, [q]);
  return (
    <div className="relative">
      <input className="input w-56" placeholder="search symbol / name" value={q} onChange={e => setQ(e.target.value.toUpperCase())}
        onKeyDown={e => { if (e.key === "Enter") onChange(q); }} list="sym-opts" />
      <datalist id="sym-opts">{opts.map(o => <option key={o.id} value={o.symbol}>{o.name} · {o.exchange}</option>)}</datalist>
      <button className="btn ml-2" onClick={() => onChange(q)}>Load</button>
    </div>
  );
}
