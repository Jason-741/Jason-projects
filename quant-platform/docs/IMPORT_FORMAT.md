# Transaction import formats

## Generic template (fully specified)
```
date,type,symbol,quantity,price,currency,fees,fx_rate_to_base,amount,counter_currency,counter_amount,reference,note
```
* `type`: buy, sell, dividend, deposit, withdrawal, fee, interest, split, fx
* buy/sell: `quantity` > 0 and `price` per share in `currency`. `amount` is computed.
* dividend/deposit/withdrawal/fee/interest: `amount` is a positive magnitude. For dividends, `fees` holds withholding tax.
* split: `quantity` = new shares per old share (e.g. 2 for a 2-for-1 split).
* fx: `amount` of `currency` converted into `counter_amount` of `counter_currency`.
* `fx_rate_to_base`: CAD per 1 unit of `currency` on that date. It is required for correct ACB on USD trades.
* `reference`: optional unique id. Otherwise a hash of the row is used, so re-importing a file never duplicates rows.

## Wealthsimple activity CSV (best effort)
The importer detects headers `date, transaction, description, amount[, balance, currency]` and maps the codes
BUY, SELL, DIV, CONT/DEP/EFT/TRFIN (deposit), WD/TRFOUT (withdrawal), FEE and INT/FPLINT (interest). It reads quantities from descriptions like
`"VFV - Vanguard ...: Bought 0.5000 shares (executed at ...)"`. The price is derived as |amount| / quantity, so any broker
FX spread is embedded in it. Other codes are listed as *skipped*. Wealthsimple changes its exports, so **always run the dry-run preview**.
If the preview is wrong, convert your file to the generic template instead.
