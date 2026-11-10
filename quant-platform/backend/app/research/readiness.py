"""Live-investment readiness checklist (Section 20 of the mandate).

Status is derived ONLY from recorded evidence; attractive returns alone never change it.
"""
from __future__ import annotations

QUANT_ITEMS = [
    ("hypothesis", "Documented investment hypothesis (why the edge should exist)"),
    ("data_verified", "Verified and sufficiently complete data"),
    ("reproducible_backtest", "Reproducible backtest (stored config + data fingerprint)"),
    ("out_of_sample", "Out-of-sample validation"),
    ("walk_forward", "Walk-forward testing (where applicable)"),
    ("realistic_costs", "Realistic transaction, spread, slippage and FX costs"),
    ("stress_tested", "Drawdown and stress testing"),
    ("benchmarked", "Comparison against appropriate benchmarks"),
    ("paper_traded", "Paper-trading observation period"),
    ("limitations_reviewed", "Independent review of model limitations"),
]
DISCRETIONARY_ITEMS = [
    ("thesis", "Documented thesis"),
    ("valuation_range", "Valuation range (low / base / high)"),
    ("risk_assessment", "Risk assessment"),
    ("invalidation", "Explicit thesis-invalidation conditions"),
]


def evaluate(checklist: dict | None, kind: str = "quant") -> dict:
    items = QUANT_ITEMS if kind == "quant" else DISCRETIONARY_ITEMS
    cl = checklist or {}
    rows = [{"key": k, "label": label, "done": bool((cl.get(k) or {}).get("done")), "evidence": (cl.get(k) or {}).get("evidence")}
            for k, label in items]
    for r in rows:  # an item without evidence does not count
        if r["done"] and not r["evidence"]:
            r["done"] = False
            r["note"] = "marked done without evidence — not counted"
    done = sum(r["done"] for r in rows)
    if done == len(rows):
        status = "research-complete: eligible for user consideration (not a guarantee)"
    elif done >= len(rows) // 2:
        status = "in validation"
    else:
        status = "research only — not ready for live use"
    return {"status": status, "completed": done, "total": len(rows), "items": rows}


def journal_readiness(entry) -> dict:
    cl = {
        "thesis": {"done": bool(entry.thesis and len(entry.thesis) > 50), "evidence": "journal.thesis"},
        "valuation_range": {"done": None not in (entry.valuation_low, entry.valuation_base, entry.valuation_high),
                            "evidence": "journal.valuation_*"},
        "risk_assessment": {"done": bool(entry.risks), "evidence": "journal.risks"},
        "invalidation": {"done": bool(entry.invalidation_conditions), "evidence": "journal.invalidation_conditions"},
    }
    return evaluate(cl, "discretionary")
