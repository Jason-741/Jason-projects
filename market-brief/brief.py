"""
ENR market brief: pulls prices and headlines, ranks what matters, and delivers it.

Delivery, in order of preference:
  1. Gmail, if GMAIL_ADDRESS and GMAIL_APP_PASSWORD are set.
  2. A GitHub issue that @mentions you, if GITHUB_TOKEN is set (GitHub emails it to you).
  3. Printed to the terminal.

Run locally:  python market-brief/brief.py --mode daily --dry-run
"""

import argparse
import calendar
import html
import os
import re
import smtplib
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import config
import glossary

TZ = ZoneInfo(config.TIMEZONE)
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


# ---------------------------------------------------------------- scheduling

def scheduled_run_is_due(schedule, now_utc=None):
    """GitHub cron runs in UTC, so the workflow fires at two UTC hours and only the
    one that lands just before 6am Toronto (EDT or EST) goes ahead."""
    if not schedule:
        return True
    now_utc = now_utc or datetime.now(timezone.utc)
    hour_utc = int(schedule.split()[1])
    offset_hours = int(now_utc.astimezone(TZ).utcoffset().total_seconds() // 3600)
    return (hour_utc + offset_hours) % 24 == 5


def mode_from_schedule(schedule):
    return "weekly" if schedule and schedule.split()[4] == "0" else "daily"


def lookback_hours(mode, now_local):
    if mode == "weekly":
        return 7 * 24
    # Monday's brief covers the weekend.
    return 72 if now_local.weekday() == 0 else 26


# ---------------------------------------------------------------- prices

def fetch_prices(tickers):
    import yfinance as yf

    data = yf.download(
        list(tickers), period="1y", interval="1d", group_by="ticker",
        auto_adjust=False, progress=False, threads=True,
    )
    frames = {}
    for t in tickers:
        try:
            df = data[t][["Close", "Volume"]].dropna(subset=["Close"])
        except (KeyError, TypeError):
            continue
        if len(df) >= 2:
            frames[t] = df
    return frames


def pct(a, b):
    return (a / b - 1) * 100 if b else None


def summarize(df):
    close = df["Close"]
    last = float(close.iloc[-1])

    def back(n):
        return float(close.iloc[-1 - n]) if len(close) > n else None

    vol = df["Volume"]
    avg_vol = float(vol.iloc[-21:-1].mean()) if len(vol) > 21 else None
    return {
        "last": last,
        "d1": pct(last, back(1)),
        "w1": pct(last, back(5)),
        "m1": pct(last, back(21)),
        "hi52": float(close.max()),
        "lo52": float(close.min()),
        "vol_ratio": (float(vol.iloc[-1]) / avg_vol) if avg_vol else None,
    }


def fetch_earnings(tickers, days_ahead):
    import yfinance as yf

    today = datetime.now(TZ).date()
    upcoming = []

    def one(t):
        try:
            cal = yf.Ticker(t).calendar
            dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
            for d in dates or []:
                d = d.date() if hasattr(d, "date") and callable(d.date) else d
                if today <= d <= today + timedelta(days=days_ahead):
                    return (d, t)
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(8) as pool:
        for r in pool.map(one, tickers):
            if r:
                upcoming.append(r)
    return sorted(upcoming)


# ---------------------------------------------------------------- news

SECTOR_RE = re.compile(
    r"\b(oil|crude|opec|brent|wti|natural gas|lng|gasoline|diesel|refin\w*|pipeline\w*|energy|"
    r"power|electricity|utilit\w+|grid|nuclear|uranium|gold|silver|copper|lithium|nickel|cobalt|"
    r"rare earths?|ndpr|neodymium|praseodymium|magnets?|critical minerals?|mining|miners?|mines?|"
    r"metals?|coal|commodit\w+|drill\w*|shale|rig count|solar|wind|batter\w+|aluminum|iron ore|"
    r"potash|oilsands?|oil sands|exxon|chevron|suncor|enbridge|cameco|newmont|freeport)\b",
    re.I,
)
CENTRAL_BANK_RE = re.compile(
    r"\b(federal reserve|fed|fomc|powell|(?<!national )bank of canada|macklem|interest rates?|rate cuts?|"
    r"rate hikes?|ecb|bank of england|bank of japan)\b",
    re.I,
)
BIG_WORDS = {
    r"opec\+?": 3, r"rate (cut|hike)s?|cuts rates|raises rates|holds rates": 3,
    r"tariffs?": 2, r"sanctions?": 2, r"export (ban|controls?|curbs?)": 3, r"price floor": 3,
    r"acqui\w+|merger|takeover|buyout|\bdeal\b": 2, r"guidance|outlook": 2, r"earnings|results": 1,
    r"plunge\w*|soar\w*|surge\w*|tumble\w*|slump\w*|crash\w*|record": 2, r"downgrade|upgrade": 2,
    r"\bwar\b|attack\w*|strikes?|missile": 2, r"hurricane|outage|shutdown": 2,
    r"pentagon|department of defense|\bdod\b|department of war": 2, r"china|beijing": 1,
    r"inventor(y|ies)|stockpile": 1, r"bankrupt\w*": 3, r"ceo|resign\w*": 1,
}
BIG_RE = [(re.compile(p, re.I), w) for p, w in BIG_WORDS.items()]
# Template headlines, clickbait and promo posts that add nothing.
NOISE_RE = re.compile(
    r"outpaced the stock market|stock market today:? .*(dips|rises|falls|beats|outpaced)|\bwhy .* (outpaced|lagged|dipped)|"
    r"what you should know|should you buy|is it time to buy|\bI'm (buying|making)\b|if the stock market crashes|"
    r"price prediction|to present at|virtual conference|investor conference|webinar|top \d+ .*stocks to|"
    r"stocks? to (buy|watch)|millionaire|motley fool|\bbest .* stocks?\b|price (today|on) \w+ \d+|"
    r"^\w+ prices? (today|\w+ \d{1,2},? \d{4})$|stock price, news|quote (&|and) history|security guards?|"
    r"\bstrike (passes|enters|continues)",
    re.I,
)
STOPWORDS = set("a an the to of in on for and or as at by with from is are be after amid over its it this that says say new".split())


def watchlist_patterns():
    pats = {}
    for t, name in config.CORE_WATCHLIST.items():
        pats[t] = [re.compile(re.escape(name), re.I),
                   re.compile(rf"\({re.escape(t)}\)|(NYSE|NASDAQ|TSX):\s?{re.escape(t)}\b")]
        # Bare tickers must be 3+ letters and uppercase, or "MP" would match Canadian MPs.
        if len(t) >= 3:
            pats[t].append(re.compile(rf"\b{re.escape(t)}\b"))
    return pats


def fetch_feed(source, url, ticker=None):
    import feedparser
    import requests

    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as e:
        print(f"  feed failed: {source}: {e}", file=sys.stderr)
        return []
    items = []
    for e in parsed.entries:
        title = html.unescape(re.sub(r"<[^>]+>", "", e.get("title", ""))).strip()
        when = e.get("published_parsed") or e.get("updated_parsed")
        if not title or not when:
            continue
        src = source
        if source == "Google News":
            src = (e.get("source") or {}).get("title") or source
            title = re.sub(r"\s+-\s+[^-]+$", "", title)
        items.append({
            "title": title,
            "link": e.get("link", ""),
            "source": src,
            "feed": source,
            "published": datetime.fromtimestamp(calendar.timegm(when), timezone.utc),
            "ticker": ticker,
        })
    return items


def fetch_news():
    jobs = [("Google News", f"https://news.google.com/rss/search?q={quote_plus(q)}+when:7d&hl=en-CA&gl=CA&ceid=CA:en")
            for q in config.GOOGLE_NEWS_QUERIES]
    jobs += [("Yahoo Finance", f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={quote_plus(t)}&region=US&lang=en-US", t)
             for t in config.CORE_WATCHLIST]
    jobs += list(config.RSS_FEEDS)
    with ThreadPoolExecutor(10) as pool:
        results = pool.map(lambda j: fetch_feed(*j), jobs)
    items = [i for r in results for i in r]
    print(f"Fetched {len(items)} headlines from {len(jobs)} feeds", file=sys.stderr)
    return items


def tokens(title):
    words = re.findall(r"[a-z0-9$%.]+", title.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 1}


def is_noise(item):
    title, source = item["title"], item.get("source", "")
    def foreign(text):
        return text and sum(ord(ch) > 0x2FF for ch in text) > len(text) * 0.2
    # Non-English headlines, or English ones from non-English sites (often machine-written).
    return bool(NOISE_RE.search(title)) or foreign(title) or foreign(source)


def cluster(items):
    """Group the same story told by different outlets. More outlets = bigger story."""
    clusters = []
    for item in sorted(items, key=lambda i: i["published"], reverse=True):
        tk = tokens(item["title"])
        for c in clusters:
            inter = len(tk & c["tokens"])
            if tk and inter / len(tk | c["tokens"]) >= 0.5:
                c["items"].append(item)
                break
        else:
            clusters.append({"tokens": tk, "items": [item]})
    return clusters


def score_and_tag(clusters, now_utc):
    wl = watchlist_patterns()
    out = []
    for c in clusters:
        lead = c["items"][0]
        title = lead["title"]
        sources = {i["source"] for i in c["items"]}
        tickers = [t for t, pats in wl.items()
                   if any(p.search(title) for p in pats) or any(i.get("ticker") == t for i in c["items"])]
        is_cb_feed = lead["feed"] in ("Federal Reserve", "Bank of Canada")
        if tickers:
            cat = "watchlist"
        elif is_cb_feed or (CENTRAL_BANK_RE.search(title) and not SECTOR_RE.search(title)):
            cat = "central_bank"
        elif SECTOR_RE.search(title):
            cat = "sector"
        else:
            cat = "general"
        score = 3 * (len(sources) - 1)
        score += sum(w for r, w in BIG_RE if r.search(title))
        score += 4 if tickers else 0
        score += 1 if cat == "sector" else 0
        score += 2 if now_utc - lead["published"] < timedelta(hours=12) else 0
        out.append({**lead, "sources": sorted(sources), "tickers": tickers, "category": cat, "score": score})
    return sorted(out, key=lambda s: (s["score"], s["published"]), reverse=True)


# ---------------------------------------------------------------- report

def arrow(v):
    if v is None:
        return "–"
    return f"🟢 +{v:.1f}%" if v >= 0 else f"🔴 {v:.1f}%"


def short(name):
    """'WTI crude ($/bbl)' -> 'WTI crude'."""
    return re.sub(r" \(\$[^)]*\)", "", name)


def fmt_price(t, last):
    if t == "^TNX":
        return f"{last:.2f}%"
    if t == "CAD=X":
        return f"{last:.4f}"
    return f"{last:,.2f}"


def money(t, last):
    is_index = t.startswith("^") or t.endswith("=X") or t.startswith("DX-")
    return fmt_price(t, last) if is_index else f"${last:,.2f}"


def yield_bps(s, key):
    if not s or s.get(key) is None:
        return None
    prev = s["last"] / (1 + s[key] / 100)
    return (s["last"] - prev) * 100


def table(rows, names, stats, mode):
    if mode == "weekly":
        head = "| | Last | 1W | 1M |\n|---|---:|---:|---:|"
        cols = ("w1", "m1")
    else:
        head = "| | Last | 1D | 1W |\n|---|---:|---:|---:|"
        cols = ("d1", "w1")
    lines = [head]
    for t in rows:
        s = stats.get(t)
        if not s:
            continue
        lines.append(f"| {names[t]} | {fmt_price(t, s['last'])} | {arrow(s[cols[0]])} | {arrow(s[cols[1]])} |")
    return "\n".join(lines) if len(lines) > 1 else "_No data_"


def note(text):
    return f"_{text}_"


def quick_read(stats, mode):
    """One plain-English paragraph summarizing the day (or week)."""
    key = "w1" if mode == "weekly" else "d1"
    when = "this week" if mode == "weekly" else ""

    def mv(t):
        s = stats.get(t)
        return s[key] if s and s.get(key) is not None else None

    def word(v, up="rose", down="fell", flat="was flat"):
        if v is None:
            return None
        return flat if abs(v) < 0.3 else (up if v > 0 else down)

    parts = []
    spx, tsx = mv("^GSPC"), mv("^GSPTSE")
    if spx is not None and tsx is not None:
        if (spx >= 0) == (tsx >= 0):
            verb = "rose" if spx >= 0 else "fell"
            parts.append(f"Stocks {verb} {when}".strip() + f" (S&P 500 {spx:+.1f}%, TSX {tsx:+.1f}%).")
        else:
            parts.append(f"Stocks were mixed (S&P 500 {spx:+.1f}%, TSX {tsx:+.1f}%).")
    for t, label in (("CL=F", "Oil (WTI)"), ("NG=F", "Natural gas"), ("GC=F", "Gold"), ("HG=F", "Copper")):
        v, s = mv(t), stats.get(t)
        w = word(v)
        if w:
            if w == "was flat":
                parts.append(f"{label} was flat at ${fmt_price(t, s['last'])}.")
            else:
                parts.append(f"{label} {w} {abs(v):.1f}% to ${fmt_price(t, s['last'])}.")
    bps = yield_bps(stats.get("^TNX"), key)
    if bps is not None:
        if abs(bps) < 3:
            parts.append(f"The US 10-year yield held near {stats['^TNX']['last']:.2f}%.")
        else:
            parts.append(f"The US 10-year yield {'rose' if bps > 0 else 'fell'} {abs(bps):.0f} bps to {stats['^TNX']['last']:.2f}%.")
    cad = mv("CAD=X")
    if cad is not None and abs(cad) >= 0.2:
        parts.append(f"The Canadian dollar {'weakened' if cad > 0 else 'strengthened'} (USD/CAD {stats['CAD=X']['last']:.4f}).")
    wl = [f"{t} {mv(t):+.1f}%" for t in config.CORE_WATCHLIST if mv(t) is not None]
    if wl:
        parts.append("Your stocks: " + ", ".join(wl) + ".")
    return " ".join(parts)


def spreads(stats):
    lines = []
    wti, brent = stats.get("CL=F"), stats.get("BZ=F")
    if wti and brent:
        lines.append(f"- **Brent–WTI spread: ${brent['last'] - wti['last']:.2f}/bbl.** "
                     "Brent is the global oil price and WTI the US one. A wider gap usually means global supply is tighter than US supply.")
    gold, silver = stats.get("GC=F"), stats.get("SI=F")
    if gold and silver and silver["last"]:
        lines.append(f"- **Gold/silver ratio: {gold['last'] / silver['last']:.0f}.** "
                     "How many ounces of silver buy one ounce of gold. A rising ratio often means investors are playing it safe.")
    return lines


def price_alerts(stats, mode):
    th = config.ALERT_THRESHOLDS
    key = "w1" if mode == "weekly" else "d1"
    scale = 2 if mode == "weekly" else 1
    groups = [
        (config.CORE_WATCHLIST, "core"), (config.SECTOR_PEERS, "peer"),
        (config.COMMODITIES, "commodity"), (config.SECTOR_ETFS, "etf"),
        ({k: v for k, v in config.MARKETS.items() if k != "^VIX"}, "index"), ({"^VIX": "VIX"}, "vix"),
    ]
    alerts = []
    period = "this week" if mode == "weekly" else "on the day"
    for names, kind in groups:
        for t, name in names.items():
            s = stats.get(t)
            if not s or s[key] is None or t == "^TNX":
                continue
            name = short(name)
            move = s[key]
            boost = 4 if kind == "core" else 0
            extreme = ""
            if kind in ("core", "peer", "commodity"):
                if s["last"] >= s["hi52"] * 0.999:
                    extreme = "52-week high"
                elif s["last"] <= s["lo52"] * 1.001:
                    extreme = "52-week low"
            if abs(move) >= th[kind] * scale:
                verb = "up" if move > 0 else "down"
                extra = f", a new {extreme}" if extreme else ""
                alerts.append((6 + abs(move) / th[kind] * 2 + boost,
                               f"📈 **{name}** {verb} {abs(move):.1f}% {period} to {money(t, s['last'])}{extra}"
                               if move > 0 else
                               f"📉 **{name}** {verb} {abs(move):.1f}% {period} to {money(t, s['last'])}{extra}"))
            elif extreme:
                alerts.append((7 + boost, f"📌 **{name}** hit a {extreme} ({money(t, s['last'])})"))
            if kind == "core" and mode == "daily" and s["vol_ratio"] and s["vol_ratio"] >= 2:
                alerts.append((9, f"🔊 **{name}** traded {s['vol_ratio']:.1f}x its normal volume, a sign big investors were active"))
    bps = yield_bps(stats.get("^TNX"), key)
    if bps is not None and abs(bps) >= (20 if mode == "weekly" else 10):
        alerts.append((8, f"🏦 **US 10-year yield** {'up' if bps > 0 else 'down'} {abs(bps):.0f} bps to {stats['^TNX']['last']:.2f}%"))
    return alerts


def headline(n):
    extra = f" · {len(n['sources'])} outlets" if len(n["sources"]) > 1 else ""
    return f"[{n['title']}]({n['link']}) — _{n['source']}{extra}_"


def build_report(mode, stats, news, earnings, now_local, failures):
    limits = config.NEWS_LIMITS[mode]
    names = {**config.CORE_WATCHLIST, **config.SECTOR_PEERS, **config.MARKETS, **config.COMMODITIES, **config.SECTOR_ETFS}
    key = "w1" if mode == "weekly" else "d1"
    used = set()

    def take(cat, n):
        picked = [x for x in news if x["category"] == cat and x["link"] not in used][:n]
        used.update(x["link"] for x in picked)
        return picked

    # Big things: price alerts and top-scoring stories, mixed by score.
    big = [(s, text) for s, text in price_alerts(stats, mode)]
    for n in news:
        if n["score"] >= 7:
            big.append((n["score"], "📰 " + headline(n)))
    big.sort(key=lambda b: b[0], reverse=True)
    big = big[: limits["big"]]
    for _, text in big:
        m = re.search(r"\]\((.*?)\)", text)
        if m:
            used.add(m.group(1))

    title = "ENR Weekly Recap" if mode == "weekly" else "ENR Morning Brief"
    out = [f"# ⚡ {title} — {now_local:%A, %B} {now_local.day}, {now_local.year}", ""]
    qr = quick_read(stats, mode)
    if qr:
        out += [f"> **Quick read:** {qr}", ""]

    out += ["## 🔥 Big things", "", note("The biggest price moves and the stories covered by the most outlets."), ""]
    out += [f"- {text}" for _, text in big] or ["- A quiet one. Nothing major moved."]

    out += ["", "## 👀 Your stocks", ""]
    wl_news = [x for x in news if x["category"] == "watchlist" and x["link"] not in used]
    for t, name in config.CORE_WATCHLIST.items():
        ctx = config.CORE_CONTEXT.get(t, {})
        s = stats.get(t)
        out.append(f"### {name} ({t})")
        out.append("")
        if s:
            rng = (s["last"] - s["lo52"]) / (s["hi52"] - s["lo52"]) * 100 if s["hi52"] > s["lo52"] else 0
            out.append(f"**${s['last']:,.2f}** · 1D {arrow(s['d1'])} · 1W {arrow(s['w1'])} · 1M {arrow(s['m1'])}")
            out.append("")
            out.append(f"52-week range ${s['lo52']:,.2f}–${s['hi52']:,.2f}: trading **{rng:.0f}%** of the way from its low to its high.")
        else:
            out.append("No price data today.")
        out.append("")
        if ctx.get("what"):
            out += [note(ctx["what"]), ""]
        if ctx.get("drivers"):
            out += ["**What moves it:**", ""] + [f"- {d}" for d in ctx["drivers"]] + [""]
        related = [f"{short(names.get(r, r))} {arrow(stats[r][key])}" for r in ctx.get("related", []) if r in stats and r != "^TNX"]
        bps = yield_bps(stats.get("^TNX"), key) if "^TNX" in ctx.get("related", []) else None
        if bps is not None:
            related.append(f"10Y yield {bps:+.0f} bps")
        if related:
            out += ["**Related today:** " + " · ".join(related), ""]
        mine = [x for x in wl_news if t in x["tickers"]][: limits["watchlist"]]
        used.update(x["link"] for x in mine)
        out += ["**Headlines:**", ""] + ([f"- {headline(x)}" for x in mine] or ["- No major headlines."])
        out.append("")

    out += ["## 🛢️ Commodities", "", note(config.SECTION_NOTES["commodities"]), "", table(config.COMMODITIES, names, stats, mode)]
    sp = spreads(stats)
    if sp:
        out += ["", "**Numbers worth knowing:**", ""] + sp
    out += ["", "## 📊 Markets", "", note(config.SECTION_NOTES["markets"]), "", table(config.MARKETS, names, stats, mode)]
    out += ["", "## ⛏️ ENR sector", "", note(config.SECTION_NOTES["sector"]), "", table(config.SECTOR_ETFS, names, stats, mode)]

    movers = sorted(((stats[t][key], t) for t in config.SECTOR_PEERS if t in stats and stats[t][key] is not None), reverse=True)
    if movers:
        up = ", ".join(f"{config.SECTOR_PEERS[t]} {v:+.1f}%" for v, t in movers[:3])
        down = ", ".join(f"{config.SECTOR_PEERS[t]} {v:+.1f}%" for v, t in movers[-3:][::-1])
        out += ["", f"**Best in the sector:** {up}", "", f"**Worst in the sector:** {down}"]

    sections = [
        ("sector", "📰 Sector news", "Energy, power, mining and metals stories."),
        ("general", "🌎 Markets & economy", "The wider news that moves all stocks: trade, inflation, jobs, politics."),
        ("central_bank", "🏦 Central banks", "The Fed and Bank of Canada set interest rates, which affect borrowing costs and stock valuations."),
    ]
    for cat, label, desc in sections:
        picked = take(cat, limits[cat])
        if picked:
            out += ["", f"## {label}", "", note(desc), ""] + [f"- {headline(x)}" for x in picked]

    if earnings:
        out += ["", "## 📅 Upcoming earnings", "",
                note("Companies report quarterly results on these dates. Stocks often move a lot the next day."), ""]
        out += [f"- {d:%a %b} {d.day}: {names.get(t, t)} ({t})" for d, t in earnings]

    out += ["", "## 📚 " + ("This week's terms" if mode == "weekly" else "Term of the day"), ""]
    day_index = now_local.date().toordinal()
    if mode == "weekly":
        # The five weekday terms from the week just ended, as a recap.
        days = [now_local.date() - timedelta(days=d) for d in range(6, 1, -1)]
        for d in days:
            term, what, why = glossary.term_for(d.toordinal())
            out += [f"- **{term}:** {what}"]
    else:
        term, what, why = glossary.term_for(day_index)
        out += [f"**{term}**", "", what, "", f"_Why it matters:_ {why}"]

    out += ["", "---", "",
            "_How to read this: 1D = change since the previous close, 1W = last 5 trading days, 1M = last 21 trading days. "
            "Commodity prices are front-month futures. Headlines are ranked higher when several outlets cover the same story._",
            "", f"_Generated {now_local:%Y-%m-%d %H:%M} Toronto time._"]
    if failures:
        out.append(f"_Some sources didn't respond: {', '.join(failures)}._")
    return "\n".join(out)


# ---------------------------------------------------------------- delivery

EMAIL_CSS = """
body{margin:0;padding:0;background:#f4f5f7}
.wrap{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;color:#1f2328;max-width:680px;margin:0 auto;
  padding:20px 22px;background:#ffffff;line-height:1.5;font-size:15px}
h1{font-size:22px;margin:4px 0 14px} h2{font-size:18px;margin:30px 0 6px;padding-bottom:5px;border-bottom:2px solid #eaecef}
h3{font-size:16px;margin:20px 0 4px}
blockquote{margin:12px 0;padding:10px 14px;background:#eef4ff;border-left:4px solid #0b57d0;border-radius:4px}
blockquote p{margin:0}
table{border-collapse:collapse;width:100%;font-size:14px;margin:6px 0} td,th{padding:6px 8px;border-bottom:1px solid #eef0f2}
th{text-align:left;color:#57606a;font-weight:600;font-size:13px} tr:nth-child(even) td{background:#fafbfc}
a{color:#0b57d0;text-decoration:none} li{margin:6px 0} em{color:#57606a}
.up{color:#1a7f37;font-weight:600;white-space:nowrap} .down{color:#cf222e;font-weight:600;white-space:nowrap}
.ai{background:#fff8e6;border:1px solid #f0d58c;border-radius:6px;padding:4px 16px 8px;margin:14px 0}
hr{border:0;border-top:1px solid #eaecef;margin:26px 0 10px}
"""


def to_html(md):
    """Render the brief's Markdown as a styled HTML email with green/red numbers."""
    import markdown

    body = markdown.markdown(md, extensions=["tables", "md_in_html"])
    body = re.sub(r"🟢 \+([\d.,]+%)", r'<span class="up">▲ \1</span>', body)
    body = re.sub(r"🔴 -([\d.,]+%)", r'<span class="down">▼ \1</span>', body)
    # Gmail drops <style> classes in some views, so inline the two colours too.
    body = body.replace('class="up"', 'class="up" style="color:#1a7f37;font-weight:600;white-space:nowrap"')
    body = body.replace('class="down"', 'class="down" style="color:#cf222e;font-weight:600;white-space:nowrap"')
    return (f"<html><head><meta charset='utf-8'><style>{EMAIL_CSS}</style></head>"
            f"<body><div class='wrap'>{body}</div></body></html>")


def send_gmail(subject, md):
    sender = os.environ["GMAIL_ADDRESS"]
    to = os.environ.get("BRIEF_TO") or sender
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, f"ENR Brief <{sender}>", to
    msg.attach(MIMEText(md, "plain", "utf-8"))
    msg.attach(MIMEText(to_html(md), "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(sender, os.environ["GMAIL_APP_PASSWORD"])
        smtp.sendmail(sender, [a.strip() for a in to.split(",")], msg.as_string())
    print(f"Emailed to {to}", file=sys.stderr)


def post_github_issue(subject, md):
    import requests

    repo = os.environ["GITHUB_REPOSITORY"]
    mention = os.environ.get("BRIEF_MENTION")
    body = (f"@{mention} your brief is ready.\n\n" if mention else "") + md
    resp = requests.post(
        f"https://api.github.com/repos/{repo}/issues",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"},
        json={"title": subject, "body": body[:65000]},
        timeout=30,
    )
    resp.raise_for_status()
    print(f"Posted {resp.json()['html_url']}", file=sys.stderr)


def deliver(subject, md, dry_run):
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(md + "\n")
    if dry_run:
        print(md)
        return
    if os.environ.get("GMAIL_ADDRESS") and os.environ.get("GMAIL_APP_PASSWORD"):
        send_gmail(subject, md)
    elif os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPOSITORY"):
        post_github_issue(subject, md)
    else:
        print(md)


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daily", "weekly"])
    parser.add_argument("--dry-run", action="store_true", help="print instead of sending")
    parser.add_argument("--render-email", metavar="MARKDOWN_FILE", help="print a brief as styled email HTML and exit")
    args = parser.parse_args()

    if args.render_email:
        with open(args.render_email, encoding="utf-8") as f:
            print(to_html(f.read()))
        return

    schedule = os.environ.get("SCHEDULE", "").strip()
    if not scheduled_run_is_due(schedule):
        print(f"Skipping: {schedule!r} is the other daylight-saving slot.", file=sys.stderr)
        return
    mode = args.mode or os.environ.get("MODE") or mode_from_schedule(schedule)

    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(TZ)
    cutoff = now_utc - timedelta(hours=lookback_hours(mode, now_local))

    all_tickers = {**config.CORE_WATCHLIST, **config.SECTOR_PEERS, **config.MARKETS, **config.COMMODITIES, **config.SECTOR_ETFS}
    frames = fetch_prices(all_tickers)
    stats = {t: summarize(df) for t, df in frames.items()}
    missing = [t for t in all_tickers if t not in stats]
    if missing:
        print(f"No price data for: {', '.join(missing)}", file=sys.stderr)

    raw = [i for i in fetch_news() if i["published"] >= cutoff and not is_noise(i)]
    news = score_and_tag(cluster(raw), now_utc)

    earnings = fetch_earnings(list(config.CORE_WATCHLIST) + list(config.SECTOR_PEERS), 14 if mode == "weekly" else 7)

    failures = []
    if len(stats) < len(all_tickers) / 2:
        failures.append("price data")
    if not raw:
        failures.append("news feeds")

    md = build_report(mode, stats, news, earnings, now_local, failures)
    title = "ENR Weekly Recap" if mode == "weekly" else "ENR Morning Brief"
    deliver(f"⚡ {title} — {now_local:%a %b} {now_local.day}", md, args.dry_run)


if __name__ == "__main__":
    main()
