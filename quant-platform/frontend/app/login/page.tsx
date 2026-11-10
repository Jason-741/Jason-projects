"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, setToken } from "@/lib/api";
import { ErrorBox } from "@/components/ui";

export default function Login() {
  const r = useRouter();
  const [u, setU] = useState(""); const [p, setP] = useState("");
  const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const go = async (mode: "login" | "register") => {
    setBusy(true); setErr(null);
    try {
      const res = await api(`/api/auth/${mode}`, { method: "POST", json: { username: u, password: p } });
      setToken(res.access_token); r.replace("/");
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="min-h-screen flex items-center justify-center">
      <form className="card p-6 w-80 flex flex-col gap-3" onSubmit={e => { e.preventDefault(); go("login"); }}>
        <div className="text-accent font-bold tracking-wide">QUANT·RESEARCH</div>
        <input className="input" placeholder="username" value={u} onChange={e => setU(e.target.value)} autoComplete="username" />
        <input className="input" placeholder="password (min 10 chars)" type="password" value={p} onChange={e => setP(e.target.value)} autoComplete="current-password" />
        <ErrorBox error={err} />
        <button className="btn" disabled={busy}>Sign in</button>
        <button type="button" className="btn-ghost" disabled={busy} onClick={() => go("register")}>Create account (first run)</button>
        <p className="text-[10px] text-slate-500">Never enter brokerage credentials here. This platform does not connect to or trade in your Wealthsimple account.</p>
      </form>
    </div>
  );
}
