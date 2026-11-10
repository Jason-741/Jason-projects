"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ErrorBox, Field } from "./ui";

export default function AccountPicker({ kind, value, onChange }: { kind: "live" | "paper"; value: number | null; onChange: (id: number) => void }) {
  const accts = useApi<any[]>("/api/accounts");
  const [name, setName] = useState(""); const [err, setErr] = useState<string | null>(null);
  const list = (accts.data || []).filter(a => a.kind === kind);
  const create = async () => {
    setErr(null);
    try { const a = await api("/api/accounts", { method: "POST", json: { name, kind, broker: kind === "live" ? "Wealthsimple" : null } }); await accts.reload(); onChange(a.id); setName(""); }
    catch (e: any) { setErr(e.message); }
  };
  return (
    <div className="flex gap-2 items-end flex-wrap">
      <Field label={`${kind} account`}><select className="input" value={value ?? ""} onChange={e => onChange(Number(e.target.value))}>
        <option value="">—</option>{list.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
      <Field label="New account name"><input className="input" value={name} onChange={e => setName(e.target.value)} placeholder={kind === "live" ? "Wealthsimple TFSA" : "Paper — copper"} /></Field>
      <button className="btn-ghost" disabled={!name} onClick={create}>Create</button>
      <ErrorBox error={err} />
    </div>
  );
}
