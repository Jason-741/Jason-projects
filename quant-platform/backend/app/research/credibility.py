"""Management credibility tracker: compares guided ranges with subsequently reported actuals.

Inputs are guidance records the analyst has CONFIRMED from a cited source, and actuals from
filings. A miss is a fact about forecasting accuracy — it does NOT imply dishonesty.
"""
from __future__ import annotations


def score_guidance(records: list[dict]) -> dict:
    """records: [{metric, period, low, high, actual, source_guidance, source_actual, direction}]
    direction: 'higher_is_better' (revenue, production) or 'lower_is_better' (costs, capex)."""
    rows, hits, beats, misses = [], 0, 0, 0
    for r in records:
        lo, hi, act = r.get("low"), r.get("high"), r.get("actual")
        if lo is None or act is None:
            rows.append({**r, "outcome": "pending"})
            continue
        hi = hi if hi is not None else lo
        mid = (lo + hi) / 2
        better_high = r.get("direction", "higher_is_better") == "higher_is_better"
        if lo <= act <= hi:
            outcome = "within"
            hits += 1
        elif (act > hi) == better_high:
            outcome = "beat"
            beats += 1
        else:
            outcome = "miss"
            misses += 1
        rows.append({**r, "outcome": outcome, "error_vs_mid": (act - mid) / abs(mid) if mid else None})
    n = hits + beats + misses
    by_metric: dict[str, dict] = {}
    for r in rows:
        if r["outcome"] == "pending":
            continue
        d = by_metric.setdefault(r["metric"], {"n": 0, "misses": 0, "consecutive_misses": 0})
        d["n"] += 1
        d["misses"] += r["outcome"] == "miss"
        d["consecutive_misses"] = d["consecutive_misses"] + 1 if r["outcome"] == "miss" else 0
    flags = [f"{m}: {d['consecutive_misses']} consecutive misses" for m, d in by_metric.items() if d["consecutive_misses"] >= 2]
    return {"evaluated": n, "within_or_beat_rate": (hits + beats) / n if n else None, "miss_rate": misses / n if n else None,
            "rows": rows, "by_metric": by_metric, "flags": flags,
            "note": "missed forecasts measure forecasting accuracy, not honesty"}
