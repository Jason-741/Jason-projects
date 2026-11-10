"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, getToken, setToken } from "@/lib/api";
import { NAV } from "@/lib/nav";

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<string | null>(null);
  const isLogin = path === "/login";
  useEffect(() => {
    if (isLogin) return;
    if (!getToken()) { router.replace("/login"); return; }
    api("/api/auth/me").then(u => setUser(u.username)).catch(() => {});
  }, [isLogin, router]);
  if (isLogin) return <>{children}</>;
  return (
    <div className="flex min-h-screen">
      <aside className="w-56 shrink-0 bg-ink-900 border-r border-ink-700 flex flex-col">
        <div className="px-4 py-3 border-b border-ink-700">
          <div className="text-accent font-bold tracking-wide text-sm">QUANT·RESEARCH</div>
          <div className="text-[10px] text-slate-500">Research · Risk · Portfolio — manual execution only</div>
        </div>
        <nav className="flex-1 overflow-y-auto py-2">
          {NAV.map(n => {
            const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
            return (
              <Link key={n.href} href={n.href}
                className={`flex items-center gap-2 px-4 py-1.5 text-[13px] ${active ? "bg-ink-800 text-accent border-l-2 border-accent" : "text-slate-400 hover:text-slate-100 hover:bg-ink-850 border-l-2 border-transparent"}`}>
                <span className="num text-[10px] text-slate-600 w-4">{String(n.n).padStart(2, "0")}</span>{n.label}
              </Link>);
          })}
        </nav>
        <div className="px-4 py-2 border-t border-ink-700 text-[11px] text-slate-500 flex justify-between">
          <span>{user ?? "…"}</span>
          <button className="hover:text-slate-200" onClick={() => { setToken(null); router.replace("/login"); }}>sign out</button>
        </div>
      </aside>
      <main className="flex-1 min-w-0 p-5">{children}</main>
    </div>
  );
}
