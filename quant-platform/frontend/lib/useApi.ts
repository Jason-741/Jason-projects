"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

export function useApi<T = any>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    if (!path) return;
    setLoading(true); setError(null);
    try { setData(await api<T>(path)); } catch (e: any) { setError(e.message); } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  useEffect(() => { load(); }, [load]);
  return { data, error, loading, reload: load, setData };
}

export function useAction<A extends unknown[], T>(fn: (...a: A) => Promise<T>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<T | null>(null);
  const run = async (...a: A) => {
    setBusy(true); setError(null);
    try { const r = await fn(...a); setResult(r); return r; } catch (e: any) { setError(e.message); return null; } finally { setBusy(false); }
  };
  return { run, busy, error, result, setResult };
}
