export const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
export const pct = (v: unknown, d = 1) => (isNum(v) ? `${(v * 100).toFixed(d)}%` : "—");
export const num = (v: unknown, d = 2) => (isNum(v) ? v.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }) : "—");
export const big = (v: unknown) => {
  if (!isNum(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (a >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return v.toFixed(2);
};
export const tone = (v: unknown) => (isNum(v) ? (v > 0 ? "text-up" : v < 0 ? "text-down" : "text-slate-300") : "text-slate-500");
