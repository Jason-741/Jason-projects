"""Seed research universe for the initial mandate (identifiers only — no market data).

(symbol, exchange, name, asset_type, sector, subsector). Names are descriptive labels; the
profile endpoint can refresh them from a provider. Edit freely.
"""
UNIVERSE = [
    # Benchmarks
    ("SPY", "NYSEARCA", "SPDR S&P 500 ETF", "etf", "Benchmark", "US large cap"),
    ("XIC", "TSX", "iShares Core S&P/TSX Capped Composite ETF", "etf", "Benchmark", "Canada broad"),
    ("^GSPTSE", "INDEX", "S&P/TSX Composite Index", "index", "Benchmark", "Canada index"),
    ("CAD=X", "FX", "USD/CAD", "fx", "FX", "USD/CAD"),
    # Copper & critical minerals
    ("COPX", "NYSEARCA", "Global X Copper Miners ETF", "etf", "Natural Resources", "Copper"),
    ("FCX", "NYSE", "Freeport-McMoRan", "equity", "Natural Resources", "Copper"),
    ("TECK.B", "TSX", "Teck Resources (Class B)", "equity", "Natural Resources", "Copper"),
    ("IVN", "TSX", "Ivanhoe Mines", "equity", "Natural Resources", "Copper"),
    ("FM", "TSX", "First Quantum Minerals", "equity", "Natural Resources", "Copper"),
    ("HG=F", "FUTURES", "Copper futures (COMEX)", "commodity", "Commodities", "Copper"),
    ("MP", "NYSE", "MP Materials", "equity", "Natural Resources", "Rare earth elements"),
    ("LIT", "NYSEARCA", "Global X Lithium & Battery Tech ETF", "etf", "Natural Resources", "Lithium"),
    # Gold & silver
    ("GLD", "NYSEARCA", "SPDR Gold Shares", "etf", "Natural Resources", "Gold"),
    ("GDX", "NYSEARCA", "VanEck Gold Miners ETF", "etf", "Natural Resources", "Gold"),
    ("AEM", "TSX", "Agnico Eagle Mines", "equity", "Natural Resources", "Gold"),
    ("ABX", "TSX", "Barrick", "equity", "Natural Resources", "Gold"),
    ("FNV", "TSX", "Franco-Nevada", "equity", "Natural Resources", "Gold"),
    ("WPM", "TSX", "Wheaton Precious Metals", "equity", "Natural Resources", "Silver"),
    ("SLV", "NYSEARCA", "iShares Silver Trust", "etf", "Natural Resources", "Silver"),
    ("GC=F", "FUTURES", "Gold futures (COMEX)", "commodity", "Commodities", "Gold"),
    # Uranium & nuclear
    ("CCO", "TSX", "Cameco", "equity", "Natural Resources", "Uranium"),
    ("NXE", "TSX", "NexGen Energy", "equity", "Natural Resources", "Uranium"),
    ("URA", "NYSEARCA", "Global X Uranium ETF", "etf", "Natural Resources", "Uranium"),
    ("CEG", "NASDAQ", "Constellation Energy", "equity", "Energy", "Nuclear energy"),
    # Energy
    ("XLE", "NYSEARCA", "Energy Select Sector SPDR", "etf", "Energy", "Oil and gas"),
    ("CNQ", "TSX", "Canadian Natural Resources", "equity", "Energy", "Oil and gas"),
    ("ENB", "TSX", "Enbridge", "equity", "Energy", "Midstream"),
    ("CL=F", "FUTURES", "WTI crude futures", "commodity", "Commodities", "Oil"),
    # Technology
    ("SMH", "NASDAQ", "VanEck Semiconductor ETF", "etf", "Technology", "Semiconductors"),
    ("NVDA", "NASDAQ", "NVIDIA", "equity", "Technology", "Semiconductors"),
    ("SHOP", "TSX", "Shopify", "equity", "Technology", "Enterprise software"),
    # Financials
    ("XLF", "NYSEARCA", "Financial Select Sector SPDR", "etf", "Financials", "Banks"),
    ("RY", "TSX", "Royal Bank of Canada", "equity", "Financials", "Banks"),
    # Industrials
    ("XLI", "NYSEARCA", "Industrial Select Sector SPDR", "etf", "Industrials", "Industrials"),
    ("CP", "TSX", "Canadian Pacific Kansas City", "equity", "Industrials", "Transportation"),
]
