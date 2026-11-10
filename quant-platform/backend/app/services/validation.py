"""Data-quality checks. Each check returns explicit issues; nothing is silently "fixed"."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Issue:
    severity: str   # error|warning|info
    code: str
    message: str
    dates: list[str] | None = None

    def as_dict(self):
        return {"severity": self.severity, "code": self.code, "message": self.message, "dates": self.dates}


def validate_prices(frame: pd.DataFrame, splits: pd.Series | None = None, max_gap_bdays: int = 5,
                    jump_threshold: float = 0.5) -> tuple[str, list[Issue]]:
    """Validate daily bars. Returns (quality_status, issues).

    Checks: empty, duplicate dates, non-positive/NaN closes, high < low, close outside [low, high],
    calendar gaps longer than `max_gap_bdays` business days, and single-day |return| above
    `jump_threshold` that are not explained by a recorded split (possible bad print or
    unrecorded corporate action).
    """
    issues: list[Issue] = []
    if frame is None or frame.empty:
        return "rejected", [Issue("error", "empty", "no rows")]
    idx = pd.Index(frame.index)
    dups = idx[idx.duplicated()]
    if len(dups):
        issues.append(Issue("error", "duplicate_dates", f"{len(dups)} duplicated dates", [str(d) for d in dups[:20]]))
    close = frame["close"].astype(float)
    bad = close[(close <= 0) | close.isna()]
    if len(bad):
        issues.append(Issue("error", "bad_close", f"{len(bad)} non-positive or missing closes", [str(d) for d in bad.index[:20]]))
    if {"high", "low"} <= set(frame.columns):
        hl = frame[(frame["high"] < frame["low"])]
        if len(hl):
            issues.append(Issue("error", "high_below_low", f"{len(hl)} bars with high < low", [str(d) for d in hl.index[:20]]))
        outside = frame[(close > frame["high"] * 1.0001) | (close < frame["low"] * 0.9999)]
        if len(outside):
            issues.append(Issue("warning", "close_outside_range", f"{len(outside)} closes outside high/low",
                                [str(d) for d in outside.index[:20]]))
    dates = pd.to_datetime(pd.Index(sorted(set(idx))))
    if len(dates) > 1:
        gaps = np.busday_count(dates[:-1].values.astype("datetime64[D]"), dates[1:].values.astype("datetime64[D]"))
        long = [(str(dates[i].date()), int(g)) for i, g in enumerate(gaps) if g > max_gap_bdays]
        if long:
            issues.append(Issue("warning", "gaps", f"{len(long)} gaps > {max_gap_bdays} business days",
                                [f"{d} (+{g}bd)" for d, g in long[:20]]))
    rets = close.sort_index().pct_change().dropna()
    jumps = rets[rets.abs() > jump_threshold]
    if len(jumps):
        split_dates = set(pd.to_datetime(pd.Index(splits.index)).date) if splits is not None and len(splits) else set()
        unexplained = [d for d in jumps.index if pd.Timestamp(d).date() not in split_dates]
        if unexplained:
            issues.append(Issue("warning", "price_jump", f"{len(unexplained)} daily moves > {jump_threshold:.0%} without a recorded split",
                                [str(d) for d in unexplained[:20]]))
    if any(i.severity == "error" for i in issues):
        status = "rejected" if close.isna().all() or len(dups) else "warning"
    elif issues:
        status = "warning"
    else:
        status = "valid"
    return status, issues
