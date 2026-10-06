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
    r"stocks? to (buy|watch)|millionaire|motley fool|\bbest .* stocks?\b|price (today|on) \w+ \d+",
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
    title = item["title"]
    non_ascii = sum(ord(ch) > 0x2FF for ch in title)
    return bool(NOISE_RE.search(title)) or non_ascii > len(title) * 0.2


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


def fmt_price(t, last):
    if t == "^TNX":
        return f"{last:.2f}%"
    if t in ("CAD=X",):
        return f"{last:.4f}"
    return f"{last:,.2f}"


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
                note = f", new {extreme}" if extreme else ""
                alerts.append((6 + abs(move) / th[kind] * 2 + boost,
                               f"**{name}** {verb} {abs(move):.1f}% {period} ({fmt_price(t, s['last'])}{note})"))
            elif extreme:
                alerts.append((7 + boost, f"**{name}** at a {extreme} ({fmt_price(t, s['last'])})"))
            if kind == "core" and mode == "daily" and s["vol_ratio"] and s["vol_ratio"] >= 2:
                alerts.append((9, f"**{name}** traded {s['vol_ratio']:.1f}x its normal volume"))
    tnx = stats.get("^TNX")
    if tnx and tnx[key] is not None:
        prev = tnx["last"] / (1 + tnx[key] / 100)
        bps = (tnx["last"] - prev) * 100
        if abs(bps) >= (20 if mode == "weekly" else 10):
            alerts.append((8, f"**US 10Y yield** {'up' if bps > 0 else 'down'} {abs(bps):.0f} bps to {tnx['last']:.2f}%"))
    return alerts


def headline(n):
    extra = f" · {len(n['sources'])} outlets" if len(n["sources"]) > 1 else ""
    return f"[{n['title']}]({n['link']}) — _{n['source']}{extra}_"


def build_report(mode, stats, news, earnings, now_local, failures):
    limits = config.NEWS_LIMITS[mode]
    names = {**config.CORE_WATCHLIST, **config.SECTOR_PEERS, **config.MARKETS, **config.COMMODITIES, **config.SECTOR_ETFS}
    used = set()

    def take(cat, n):
        picked = [x for x in news if x["category"] == cat and x["link"] not in used][:n]
        used.update(x["link"] for x in picked)
        return picked

    # Big things: price alerts and top-scoring stories, mixed by score.
    big = [(s, text) for s, text in price_alerts(stats, mode)]
    for n in news:
        if n["score"] >= 7:
            big.append((n["score"], headline(n)))
    big.sort(key=lambda b: b[0], reverse=True)
    big = big[: limits["big"]]
    for _, text in big:
        m = re.search(r"\]\((.*?)\)", text)
        if m:
            used.add(m.group(1))

    title = "ENR Weekly Recap" if mode == "weekly" else "ENR Morning Brief"
    out = [f"# ⚡ {title} — {now_local:%a %b} {now_local.day}, {now_local.year}", ""]

    out += ["## 🔥 Big things", ""]
    out += [f"- {text}" for _, text in big] or ["- Quiet one. Nothing major moved."]

    out += ["", "## 👀 Your watchlist", ""]
    wl_news = [x for x in news if x["category"] == "watchlist" and x["link"] not in used]
    for t, name in config.CORE_WATCHLIST.items():
        s = stats.get(t)
        if s:
            rng = (s["last"] - s["lo52"]) / (s["hi52"] - s["lo52"]) * 100 if s["hi52"] > s["lo52"] else 0
            out.append(f"**{name} ({t})** ${s['last']:,.2f} · 1D {arrow(s['d1'])} · 1W {arrow(s['w1'])} · 1M {arrow(s['m1'])} · "
                       f"{rng:.0f}% of 52-wk range (${s['lo52']:,.2f}–${s['hi52']:,.2f})")
        else:
            out.append(f"**{name} ({t})** — no price data")
        mine = [x for x in wl_news if t in x["tickers"]][: limits["watchlist"]]
        used.update(x["link"] for x in mine)
        out += [f"- {headline(x)}" for x in mine] or ["- No new headlines."]
        out.append("")

    out += ["## 🛢️ Commodities", "", table(config.COMMODITIES, names, stats, mode)]
    out += ["", "## 📊 Markets", "", table(config.MARKETS, names, stats, mode)]
    out += ["", "## ⛏️ ENR sector", "", table(config.SECTOR_ETFS, names, stats, mode)]

    key = "w1" if mode == "weekly" else "d1"
    movers = sorted(((stats[t][key], t) for t in config.SECTOR_PEERS if t in stats and stats[t][key] is not None), reverse=True)
    if movers:
        up = ", ".join(f"{config.SECTOR_PEERS[t]} {v:+.1f}%" for v, t in movers[:3])
        down = ", ".join(f"{config.SECTOR_PEERS[t]} {v:+.1f}%" for v, t in movers[-3:][::-1])
        out += ["", f"**Top movers:** {up}", f"**Laggards:** {down}"]

    sections = [("sector", "📰 Sector news"), ("general", "🌎 Markets & macro"), ("central_bank", "🏦 Central banks")]
    for cat, label in sections:
        picked = take(cat, limits[cat])
        if picked:
            out += ["", f"## {label}", ""] + [f"- {headline(x)}" for x in picked]

    if earnings:
        out += ["", "## 📅 Upcoming earnings", ""]
        out += [f"- {d:%a %b} {d.day}: {names.get(t, t)} ({t})" for d, t in earnings]

    out += ["", "---", f"_Generated {now_local:%Y-%m-%d %H:%M} Toronto time. Prices are the latest close or futures quote."
            f" Edit `market-brief/config.py` to change tickers or sources._"]
    if failures:
        out.append(f"_Some sources didn't respond: {', '.join(failures)}._")
    return "\n".join(out)


# ---------------------------------------------------------------- delivery

EMAIL_CSS = """
body{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1a1a1a;max-width:720px;margin:auto;line-height:1.45;font-size:15px}
h1{font-size:22px} h2{font-size:17px;border-bottom:1px solid #ddd;padding-bottom:4px;margin-top:26px}
table{border-collapse:collapse;width:100%;font-size:14px} td,th{padding:4px 8px;border-bottom:1px solid #eee}
th{text-align:left;color:#666;font-weight:600} a{color:#0b57d0;text-decoration:none} li{margin:4px 0}
"""


def send_gmail(subject, md):
    import markdown

    sender = os.environ["GMAIL_ADDRESS"]
    to = os.environ.get("BRIEF_TO") or sender
    body = markdown.markdown(md, extensions=["tables"])
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, f"ENR Brief <{sender}>", to
    msg.attach(MIMEText(md, "plain", "utf-8"))
    msg.attach(MIMEText(f"<html><head><style>{EMAIL_CSS}</style></head><body>{body}</body></html>", "html", "utf-8"))
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
    args = parser.parse_args()

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
