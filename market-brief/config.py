"""
Settings for the ENR market brief. Edit this file to change what you track.
Tickers use Yahoo Finance symbols (Canadian stocks end in .TO).
"""

TIMEZONE = "America/Toronto"

# Stocks you cover. These get the full treatment: price, alerts, headlines, earnings.
CORE_WATCHLIST = {
    "MP": "MP Materials",
    "NRG": "NRG Energy",
}

# Wider Energy & Natural Resources universe. Used for "top movers" and earnings dates.
SECTOR_PEERS = {
    # Oil & gas majors / E&P
    "XOM": "ExxonMobil",
    "CVX": "Chevron",
    "COP": "ConocoPhillips",
    "OXY": "Occidental",
    # Canadian energy
    "SU.TO": "Suncor",
    "CNQ.TO": "Canadian Natural",
    "CVE.TO": "Cenovus",
    "ENB.TO": "Enbridge",
    "TRP.TO": "TC Energy",
    # Power producers (NRG peers)
    "VST": "Vistra",
    "CEG": "Constellation Energy",
    # Uranium
    "CCJ": "Cameco",
    "NXE": "NexGen Energy",
    # Rare earths & critical minerals (MP peers)
    "LYC.AX": "Lynas Rare Earths",
    "USAR": "USA Rare Earth",
    "UUUU": "Energy Fuels",
    "ALB": "Albemarle",
    "FCX": "Freeport-McMoRan",
    "TECK": "Teck Resources",
    # Gold
    "NEM": "Newmont",
    "AEM": "Agnico Eagle",
}

MARKETS = {
    "^GSPC": "S&P 500",
    "^GSPTSE": "TSX",
    "^IXIC": "Nasdaq",
    "^DJI": "Dow",
    "^VIX": "VIX",
    "^TNX": "US 10Y yield",
    "CAD=X": "USD/CAD",
    "DX-Y.NYB": "US Dollar Index",
}

COMMODITIES = {
    "CL=F": "WTI crude",
    "BZ=F": "Brent crude",
    "NG=F": "Natural gas",
    "RB=F": "Gasoline",
    "GC=F": "Gold",
    "SI=F": "Silver",
    "HG=F": "Copper",
    "PL=F": "Platinum",
}

SECTOR_ETFS = {
    "XLE": "US Energy (XLE)",
    "XOP": "Oil & Gas E&P (XOP)",
    "XEG.TO": "TSX Energy (XEG)",
    "XLU": "US Utilities (XLU)",
    "XME": "Metals & Mining (XME)",
    "REMX": "Rare Earths (REMX)",
    "URNM": "Uranium Miners (URNM)",
    "GDX": "Gold Miners (GDX)",
    "LIT": "Lithium (LIT)",
}

# A move at least this big (in %) becomes a "Big thing" alert.
ALERT_THRESHOLDS = {
    "core": 4.0,
    "peer": 6.0,
    "commodity": 3.0,
    "etf": 2.5,
    "index": 1.5,
    "vix": 12.0,
}

# Google News searches. These pull from Reuters, Bloomberg, WSJ, the Globe and Mail and others.
GOOGLE_NEWS_QUERIES = [
    "MP Materials",
    "NRG Energy",
    "rare earths OR NdPr OR \"critical minerals\"",
    "oil prices OR OPEC OR crude",
    "natural gas prices OR LNG",
    "gold price OR silver price",
    "copper price OR lithium price",
    "uranium OR nuclear power",
    "power prices OR \"electricity demand\" OR \"data center power\"",
    "Canadian energy stocks OR oilsands OR pipeline",
    "mining stocks OR mining deal",
    "stock market today",
    "Bank of Canada",
    "Federal Reserve",
    "tariffs trade",
]

# Fixed news feeds: (source name, RSS url)
RSS_FEEDS = [
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("CNBC Energy", "https://www.cnbc.com/id/19836768/device/rss/rss.html"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("Seeking Alpha", "https://seekingalpha.com/market_currents.xml"),
    ("Financial Post", "https://financialpost.com/feed"),
    ("Globe and Mail", "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/business/"),
    ("OilPrice.com", "https://oilprice.com/rss/main"),
    ("Mining.com", "https://www.mining.com/feed/"),
    ("Kitco", "https://www.kitco.com/rss/KitcoNews.xml"),
    ("EIA", "https://www.eia.gov/rss/todayinenergy.xml"),
    ("Investing.com", "https://www.investing.com/rss/news_11.rss"),
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("Bank of Canada", "https://www.bankofcanada.ca/content_type/press-releases/feed/"),
]

# How many headlines to show per section.
NEWS_LIMITS = {
    "daily": {"big": 6, "watchlist": 3, "sector": 8, "general": 6, "central_bank": 3},
    "weekly": {"big": 8, "watchlist": 5, "sector": 12, "general": 8, "central_bank": 5},
}
