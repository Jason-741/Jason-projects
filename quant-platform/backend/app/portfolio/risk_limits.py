"""Configurable pre-trade risk limits. A breach flags the proposal; the USER decides."""
from __future__ import annotations

DEFAULT_LIMITS = {
    "max_position_weight": 0.40,        # small accounts must concentrate, but not all-in
    "max_sector_weight": 0.70,
    "max_positions": 5,                 # avoid many tiny positions at ~$100 capital
    "min_position_value": 15.0,         # base currency
    "max_loss_contribution_30pct_drop": 0.15,  # position weight × 30% drop ≤ 15% of portfolio
    "min_avg_daily_dollar_volume": 1_000_000.0,
    "max_leverage": 0.0,
    "max_portfolio_drawdown_alert": 0.25,
    "allow_derivatives": False,
}


def check_trade(*, side: str, trade_value_base: float, symbol: str, sector: str | None, portfolio_value_base: float,
                cash_base: float, current_weights: dict[str, float], sector_weights: dict[str, float],
                avg_daily_dollar_volume: float | None, limits: dict | None = None, asset_type: str = "equity",
                current_drawdown: float | None = None) -> dict:
    L = {**DEFAULT_LIMITS, **(limits or {})}
    checks = []

    def add(name, ok, detail, severity="breach"):
        checks.append({"check": name, "passed": bool(ok), "severity": "ok" if ok else severity, "detail": detail})

    total = portfolio_value_base
    if side == "buy":
        add("no_leverage", trade_value_base <= cash_base + 1e-9,
            f"trade {trade_value_base:.2f} vs available cash {cash_base:.2f} (max leverage {L['max_leverage']})")
    cur_val = current_weights.get(symbol, 0.0) * total
    new_val = cur_val + (trade_value_base if side == "buy" else -trade_value_base)
    w_after = new_val / total if total > 0 else 0.0
    add("max_position_weight", w_after <= L["max_position_weight"] + 1e-9,
        f"{symbol} weight after trade {w_after:.1%} (limit {L['max_position_weight']:.0%})")
    if side == "buy":
        if sector:
            s_after = sector_weights.get(sector, 0.0) + trade_value_base / total if total > 0 else 0.0
            add("max_sector_weight", s_after <= L["max_sector_weight"] + 1e-9,
                f"{sector} weight after trade {s_after:.1%} (limit {L['max_sector_weight']:.0%})")
        else:
            add("sector_known", False, "sector unknown — concentration cannot be checked", "warning")
        n_after = len([s for s, w in current_weights.items() if w > 0] + ([symbol] if symbol not in current_weights else []))
        add("max_positions", n_after <= L["max_positions"], f"{n_after} positions after trade (limit {L['max_positions']})")
        add("min_position_value", new_val >= L["min_position_value"],
            f"position value after trade {new_val:.2f} (minimum {L['min_position_value']:.2f})", "warning")
        loss_contrib = w_after * 0.30
        add("max_loss_contribution", loss_contrib <= L["max_loss_contribution_30pct_drop"] + 1e-9,
            f"a 30% drop would cost {loss_contrib:.1%} of portfolio (limit {L['max_loss_contribution_30pct_drop']:.0%})")
        if avg_daily_dollar_volume is None:
            add("liquidity", False, "average daily dollar volume unknown", "warning")
        else:
            add("liquidity", avg_daily_dollar_volume >= L["min_avg_daily_dollar_volume"],
                f"avg daily $ volume {avg_daily_dollar_volume:,.0f} (minimum {L['min_avg_daily_dollar_volume']:,.0f})")
        if asset_type in ("option", "future", "derivative") and not L["allow_derivatives"]:
            add("derivatives", False, "derivatives not permitted by mandate")
    if current_drawdown is not None:
        add("portfolio_drawdown", current_drawdown <= L["max_portfolio_drawdown_alert"],
            f"portfolio drawdown {current_drawdown:.1%} (alert at {L['max_portfolio_drawdown_alert']:.0%})", "warning")
    breaches = [c for c in checks if c["severity"] == "breach"]
    warnings = [c for c in checks if c["severity"] == "warning"]
    return {"passed": not breaches, "breaches": len(breaches), "warnings": len(warnings), "weight_after": w_after,
            "checks": checks, "limits": L}
