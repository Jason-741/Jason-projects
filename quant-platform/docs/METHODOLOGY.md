# Methodology, assumptions and limitations

All code paths referenced below live in `backend/app/analytics` unless noted.

## 1. Data conventions
* Prices: daily bars. `adj_close` (provider split- and dividend-adjusted) is used for returns when ≥95% populated; otherwise
  raw `close` is used and the response says so (dividends are excluded in that case).
* Returns are simple returns. Annualisation uses 252 trading days and assumes i.i.d. returns, which understates risk under
  autocorrelation or volatility clustering.
* Point-in-time: `facts_as_of(as_of)` returns facts with `available_at ≤ as_of`. For the same (metric, period), the latest filing up to
  that date wins, so restatements only appear once they were public.
* Validation (`services/validation.py`) checks for duplicates, non-positive or missing closes, high < low, closes outside the
  high–low range, gaps of more than 5 business days, and moves of more than 50% with no recorded split. Flagged bars are stored with `quality_status=warning`.
  Datasets with duplicate dates are rejected.

## 2. Financial ratios (`ratios.py`)
Derived items: EBITDA = operating income + D&A, total debt = long-term + short-term debt, net debt = total debt − cash,
FCF = CFO − |capex|, working capital = current assets − current liabilities.
ROE and ROA use the average of opening and closing denominators when the prior period exists. ROIC = EBIT × (1 − effective tax rate)
/ (equity + debt − cash), with the effective tax rate clamped to 0–50%. Ratios with zero or negative denominators return no value plus an explanation.
EV excludes minority interest, preferred shares and leases, and the output says so. Banks, insurers and pre-production miners need different
frameworks (P/B–ROE, NIM/CET1, P/NAV).

## 3. DCF (`dcf.py`)
FCFF_t = EBIT_t(1−t) + D&A_t − capex_t − ΔNWC_t, discounted at WACC with an optional mid-year convention.
Terminal value uses either the Gordon growth model (requires g < WACC, with a warning above 4%) or an exit EV/EBITDA multiple (with a warning that this embeds
market pricing). Equity = EV − net debt, divided by diluted shares. A warning is raised when terminal value is more than 75% of EV.
Sensitivity grid: WACC × g. Scenarios: field overrides. Reverse DCF: Brent's method solves for the constant revenue CAGR that
reproduces the market price, holding every other assumption fixed.
CAPM: k_e = r_f + β·ERP (+ size premium). WACC uses market-value weights and the after-tax cost of debt.

## 4. Risk (`risk.py`, `stress.py`, `montecarlo.py`)
| Measure | Definition | Main limitation |
|---|---|---|
| Historical VaR(α) | −quantile_{1−α}(returns), linear interpolation | assumes the sample is representative |
| Historical CVaR | −mean(returns ≤ VaR quantile) | few tail observations |
| Parametric VaR | −(μh − z_α σ√h) | normality understates fat tails |
| Max drawdown | max(1 − wealth/running peak) | path-dependent, one realisation |
| Sharpe | mean excess return / sd × √252 | unstable on short samples |
| Sortino | mean excess return / √mean(min(excess, 0)²) × √252 | target = risk-free rate |
| Beta | cov(a, b)/var(b) | unstable across regimes |
| Risk contribution | w_i(Σw)_i/σ_p, sums to σ_p | covariance estimation error |
Stress tests use a first-order factor model, r = β_eq·shock + Σβ_k·factor shock + idiosyncratic shock, floored at −100%. USD assets are translated
with (1+r)(1+ΔUSDCAD)−1. Betas are user-supplied estimates.
Monte Carlo is a stationary block bootstrap (mean block 10 days) of joint daily portfolio returns with a fixed seed. Outputs are model
probabilities conditional on the sample period, not real-world guarantees.
Mine NPV: capex at t=0, an optional construction delay, ramp-up, after-tax margin = (price·(1−royalty) − AISC)·production, and
closure cost in the final year. It omits the depreciation tax shield and working capital, so it is conservative and simplified.

## 5. Signals and backtesting (`signals.py`, `backtest.py`)
* Every indicator is causal. The backtester also lags target weights by one bar, so a signal from day t trades at day t+1's close.
  `check_no_lookahead` recomputes signals on truncated data and requires them to be identical. It is tested against a deliberately cheating signal.
* The simulation is share-based (fractional shares), long-only, with gross weight ≤ 1 and no borrowing. It rebalances daily, weekly or on the first trading day of each month,
  and skips trades below a minimum size.
* Costs: commission + |value| × (half-spread + slippage + FX fee for foreign-currency assets). The defaults are 5 + 5 bps, plus 150 bps FX
  (verify your Wealthsimple plan).
* Metrics: CAGR, volatility, Sharpe, Sortino, Calmar, max drawdown, VaR/CVaR, turnover, costs, win rate, profit factor and average win/loss
  (per closed position), plus beta, tracking error and information ratio against a benchmark.
* Hold-out: the final X% of the sample is reported separately. Walk-forward re-selects parameters on each training window by in-sample
  Sharpe and stitches together only out-of-sample returns. It reports the number of configurations tested, the Probabilistic Sharpe Ratio and a
  deflated-Sharpe benchmark (expected maximum Sharpe across N unskilled trials) to account for multiple testing.
* Reproducibility: each run stores its full configuration and a SHA-256 fingerprint of the input price matrix.
* Not modelled: intraday liquidity, partial fills, historical FX rate paths, taxes. Survivorship bias exists if the universe only contains
  today's survivors. Delisted securities are never deleted from the database, so they can be included.

## 6. Portfolio construction (`optimize.py`)
Long-only and fully invested, with per-asset caps, solved by SLSQP. Covariance = (1−λ)·sample + λ·diag(sample), with λ defaulting to 0.2.
The methods are equal weight, inverse volatility, minimum variance, equal risk contribution and mean-variance. Mean-variance requires your expected returns and carries a warning.

## 7. Ledger (`portfolio/ledger.py`)
Canadian ACB: CAD cost including commissions, converted at each transaction's FX rate. Sales remove ACB pro rata, and gain = net proceeds in
CAD − ACB of the shares sold. Splits change quantity but not total ACB. Superficial-loss rules are **not** applied. FX conversion costs are estimated
from the configured fee rate unless the broker reports them. Net P&L = total value − net contributions. Gross P&L adds back fees and estimated FX
costs. The simple return on contributions is not time-weighted.

## 8. Research text tools (`research/`)
Transcript segmentation is rule-based: it reads the participant list for roles, detects speaker lines and finds the Q&A marker. Guidance candidates are
management sentences containing forward-looking terms and numbers, each with a turn and sentence location, and marked *candidate*.
Tone counts confidence and uncertainty words per 1,000 words. It is a supporting indicator only. The credibility tracker classifies each result as within, beat or miss
against the guided range and flags two or more consecutive misses, explicitly noting that a miss says nothing about honesty.

## 9. Live-readiness
A quant strategy needs 10 evidenced checklist items (hypothesis, data, reproducible backtest, OOS, walk-forward, costs, stress,
benchmark, paper trading, limitations review). An item marked done without evidence does not count. A discretionary idea needs a thesis,
valuation range, risk assessment and invalidation conditions. The status reads "eligible for user consideration (not a guarantee)" at best.
