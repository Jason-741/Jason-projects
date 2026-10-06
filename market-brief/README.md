# ENR Market Brief

An automatic morning update on markets, commodities and the Energy & Natural Resources sector,
plus alerts on the stocks you cover.

- **Weekdays, about 6am Toronto time:** the morning brief, covering the last day (Monday covers the weekend).
- **Sundays, about 6am:** the weekly recap.

It's written for someone learning the ENR sector: every section has a one-line "what am I looking at",
and every morning teaches one new term.

Each brief includes:

| Section | What's in it |
|---|---|
| Quick read | A plain-English summary of the day in 3-4 sentences |
| ☕ The 2-minute version | Written by Claude before emailing: why the big moves happened, what they mean for MP and NRG, and an "analyst angle" (see `EXPLAIN.md`) |
| 🔥 Big things | The largest price moves, 52-week highs and lows, and stories covered by several outlets |
| 👀 Your stocks | MP Materials and NRG Energy: price, 1D/1W/1M change, 52-week range, what moves each stock, related prices today, latest headlines |
| 🛢️ Commodities | Oil, natural gas, gasoline, gold, silver, copper, platinum (with units), plus the Brent–WTI spread and gold/silver ratio explained |
| 📊 Markets | S&P 500, TSX, Nasdaq, Dow, VIX, US 10Y yield, USD/CAD, dollar index |
| ⛏️ ENR sector | Energy, utilities, mining, rare earths, uranium, gold and lithium ETFs, plus top movers and laggards among ~20 peers |
| 📰 News | Sector news, markets and macro, and Fed / Bank of Canada announcements |
| 📅 Earnings | Upcoming earnings for your watchlist and peers |
| 📚 Term of the day | One ENR concept explained (crack spread, AISC, spark spread and more). Sundays recap the week's terms. Add your own in `glossary.py` |

**Sources:** Google News (Reuters, Bloomberg, WSJ, Globe and Mail and others), Yahoo Finance, CNBC,
MarketWatch, Seeking Alpha, Financial Post, Globe and Mail, OilPrice.com, Mining.com, EIA,
Investing.com, the Federal Reserve and the Bank of Canada. When the same story appears in several
outlets, it's merged into one item and ranked higher.

## How it reaches you

It runs free on GitHub Actions, so your computer doesn't need to be on.

- **Default (no setup):** the brief is posted as an issue in this repo that @mentions you, and GitHub
  emails it to the address on your GitHub account. Make sure email is on under
  GitHub **Settings → Notifications** ("Participating, @mentions and custom" → Email).
- **Optional real email:** add repo secrets `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD`
  (a Google app password from myaccount.google.com/apppasswords). You can also add `BRIEF_TO`
  to send it to a different address, or to several addresses separated by commas.

## Changing things

- **Tickers, sources, alert sizes, stock drivers:** edit `config.py`.
- **How Claude explains things:** edit `EXPLAIN.md`.
- **Send one now:** in the repo's **Actions** tab, open **ENR Market Brief**, click **Run workflow**
  and choose daily or weekly.
- **Preview locally:** `pip install -r requirements.txt && python brief.py --dry-run`.
