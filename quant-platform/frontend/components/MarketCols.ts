import type { Col } from "./ui";
export const MARKET_COLS: Col<any>[] = [
  { key: "symbol", label: "Symbol" }, { key: "exchange", label: "Exch" }, { key: "name", label: "Name" },
  { key: "subsector", label: "Subsector" }, { key: "currency", label: "Ccy" },
  { key: "last", label: "Last", fmt: "num" }, { key: "r_1d", label: "1D", fmt: "pct", color: true },
  { key: "r_1w", label: "1W", fmt: "pct", color: true }, { key: "r_1m", label: "1M", fmt: "pct", color: true },
  { key: "r_3m", label: "3M", fmt: "pct", color: true }, { key: "r_ytd", label: "YTD", fmt: "pct", color: true },
  { key: "r_1y", label: "1Y", fmt: "pct", color: true }, { key: "vol_60d", label: "Vol60", fmt: "pct" },
  { key: "last_date", label: "As of" },
];
