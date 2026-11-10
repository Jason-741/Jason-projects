export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try { return window.sessionStorage.getItem("qp_token"); } catch { return null; }
}
export function setToken(t: string | null) {
  try { t ? window.sessionStorage.setItem("qp_token", t) : window.sessionStorage.removeItem("qp_token"); } catch {}
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, msg: string) { super(msg); this.status = status; }
}

export async function api<T = any>(path: string, opts: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as Record<string, string>) };
  const tok = getToken();
  if (tok) headers["Authorization"] = `Bearer ${tok}`;
  let body = opts.body;
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.json); }
  const res = await fetch(`${API}${path}`, { ...opts, headers, body });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/api/auth")) {
    setToken(null);
    window.location.href = "/login";
  }
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    const d = (data as any)?.detail;
    throw new ApiError(res.status, typeof d === "string" ? d : JSON.stringify(d ?? data));
  }
  return data as T;
}
