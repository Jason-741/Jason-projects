"use client";
import { useEffect, useRef } from "react";

const LAYOUT = {
  paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#94a3b8", size: 11, family: "ui-monospace, Menlo, monospace" },
  margin: { l: 50, r: 16, t: 10, b: 36 },
  xaxis: { gridcolor: "#1f2733", zerolinecolor: "#2b3544" },
  yaxis: { gridcolor: "#1f2733", zerolinecolor: "#2b3544" },
  legend: { orientation: "h", y: 1.08, x: 0 },
  hovermode: "x unified",
};

export default function Plot({ data, layout = {}, height = 300 }: { data: any[]; layout?: any; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let cancelled = false;
    let Plotly: any;
    import("plotly.js-dist-min").then(mod => {
      if (cancelled || !ref.current) return;
      Plotly = (mod as any).default ?? mod;
      Plotly.react(ref.current, data, { ...LAYOUT, ...layout, height,
        xaxis: { ...LAYOUT.xaxis, ...(layout.xaxis || {}) }, yaxis: { ...LAYOUT.yaxis, ...(layout.yaxis || {}) } },
        { displaylogo: false, responsive: true });
    });
    const el = ref.current;
    return () => { cancelled = true; if (Plotly && el) Plotly.purge(el); };
  }, [data, layout, height]);
  return <div ref={ref} style={{ width: "100%", height }} />;
}
