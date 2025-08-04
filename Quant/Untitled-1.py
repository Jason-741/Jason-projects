# %%
def main():
    # Top 100 most traded/popular stocks
    top_100_stocks = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META', 'BRK-B', 'UNH', 'JNJ',
        'XOM', 'JPM', 'V', 'PG', 'MA', 'CVX', 'HD', 'ABBV', 'PFE', 'BAC',
        'KO', 'AVGO', 'PEP', 'TMO', 'COST', 'WMT', 'DIS', 'ABT', 'ACN', 'VZ',
        'ADBE', 'DHR', 'NFLX', 'NKE', 'TXN', 'CMCSA', 'CRM', 'QCOM', 'NEE', 'RTX',
        'LIN', 'AMD', 'PM', 'SPGI', 'HON', 'UNP', 'T', 'LOW', 'SBUX', 'IBM',
        'GS', 'ELV', 'INTU', 'CAT', 'BKNG', 'AXP', 'GILD', 'DE', 'MDLZ', 'ADI',
        'TJX', 'ADP', 'SYK', 'VRTX', 'LRCX', 'SCHW', 'MMC', 'AMT', 'FISV', 'MO',
        'TMUS', 'CVS', 'ZTS', 'BDX', 'SLB', 'EOG', 'HCA', 'GE', 'FDX', 'REGN',
        'APD', 'SO', 'BSX', 'CI', 'CL', 'WM', 'ITW', 'MU', 'AON', 'DUK',
        'CSX', 'PLD', 'COP', 'EMR', 'MMM', 'BLK', 'SHW', 'NSC', 'KLAC', 'HUM'
    ]
    
    # Commodities to analyze (using ETFs and futures)
    commodities = {
        'GLD': 'Gold',
        'SLV': 'Silver', 
        'USO': 'Oil',
        'UNG': 'Natural Gas',
        'DBA': 'Agriculture',
        'CORN': 'Corn',
        'WEAT': 'Wheat',
        'CPER': 'Copper',
        'PDBC': 'Commodities Basket',
        'GC=F': 'Gold Futures'
    }
    
    print("COMPREHENSIVE MARKET SCANNER - 100 STOCKS + COMMODITIES")
    print("=" * 70)
    print(f"Scanning {len(top_100_stocks)} stocks and {len(commodities)} commodities...")
    print("This will take approximately 3-5 minutes to complete.")
    print("=" * 70)
    
    # Summary lists for final report
    buy_signals = []
    sell_signals = []
    all_results = []  # For CSV export
    
    print("\n" + "="*25 + " TOP 100 STOCKS " + "="*25)
    for i, ticker in enumerate(top_100_stocks, 1):
        try:
            print(f"\n[{i}/100] Analyzing {ticker}...")
            result = analyze_stock_quick(ticker)
            if result:
                all_results.append(result)  # Store for export
                if 'BUY' in result['recommendation']:
                    buy_signals.append(f"{ticker}: {result['recommendation']}")
                elif 'SELL' in result['recommendation']:
                    sell_signals.append(f"{ticker}: {result['recommendation']}")
        except Exception as e:
            print(f"Error analyzing {ticker}: {e}")
    
    print("\n" + "="*25 + " COMMODITIES " + "="*25)
    commodity_results = []
    for ticker, name in commodities.items():
        try:
            print(f"\nAnalyzing {ticker} ({name})...")
            comm_result = analyze_commodity_quick(ticker, name)
            if comm_result:
                commodity_results.append(comm_result)
        except Exception as e:
            print(f"Error analyzing {ticker} ({name}): {e}")
    
    # Export to CSV
    export_to_csv(all_results, commodity_results)
    
    # Final Summary Report
    print("\n" + "="*30 + " SUMMARY REPORT " + "="*30)
    print(f"\nSTRONG BUY/SELL SIGNALS FOUND:")
    print("-" * 40)
    
    if buy_signals:
        print("\nBUY SIGNALS:")
        for signal in buy_signals[:10]:  # Top 10
            print(f"• {signal}")
    
    if sell_signals:
        print("\nSELL SIGNALS:")
        for signal in sell_signals[:10]:  # Top 10
            print(f"• {signal}")
    
    if not buy_signals and not sell_signals:
        print("No strong buy/sell signals found in current market conditions.")
    
    print(f"\nResults exported to 'market_analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.csv'")
    print("You can import this CSV file into Google Sheets or Excel!")
    
    print(f"\n{'='*70}")
    print("COMPREHENSIVE SCAN COMPLETE")
    print(f"{'='*70}")

def export_to_csv(stock_results, commodity_results):
    """Export results to CSV file for easy import to Google Sheets"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    filename = f'market_analysis_{timestamp}.csv'
    
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # Header
            writer.writerow(['Asset Type', 'Symbol', 'Name', 'Price', 'RSI', 'MACD Signal', 'Recommendation', 'Analysis Time'])
            
            # Stock data
            for result in stock_results:
                writer.writerow([
                    'Stock',
                    result['ticker'],
                    result['ticker'],  # Company name could be added later
                    f"${result['price']:.2f}",
                    f"{result['rsi']:.1f}",
                    result.get('macd_signal', 'N/A'),
                    result['recommendation'],
                    datetime.now().strftime('%Y-%m-%d %H:%M')
                ])
            
            # Commodity data
            for result in commodity_results:
                writer.writerow([
                    'Commodity',
                    result['ticker'],
                    result['name'],
                    f"${result['price']:.2f}",
                    f"{result['rsi']:.1f}",
                    result.get('macd_signal', 'N/A'),
                    result['recommendation'],
                    datetime.now().strftime('%Y-%m-%d %H:%M')
                ])
        
        print(f"\n✓ Results saved to: {filename}")
        
    except Exception as e:
        print(f"Error saving CSV: {e}")

def analyze_commodity_quick(ticker, name):
    """Quick commodity analysis for export"""
    try:
        stock = yf.Ticker(ticker)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        
        hist = stock.history(start=start_date, end=end_date)
        
        if hist.empty:
            return None
        
        latest_price = hist['Close'].iloc[-1]
        rsi = calculate_rsi(hist['Close']).iloc[-1]
        macd, signal_line, _ = calculate_macd(hist['Close'])
        latest_macd = macd.iloc[-1]
        latest_signal = signal_line.iloc[-1]
        
        # Quick recommendation
        if latest_rsi < 35 and latest_macd > latest_signal:
            recommendation = "BUY - Strong oversold bounce"
        elif latest_rsi > 65 and latest_macd < latest_signal:
            recommendation = "SELL - Overbought momentum turning"
        elif latest_rsi < 40:
            recommendation = "ACCUMULATE - Pullback opportunity"
        elif latest_rsi > 60:
            recommendation = "HOLD/TAKE_PROFITS - Extended gains"
        else:
            recommendation = "HOLD - Wait for signals"
        
        macd_signal = "BULLISH" if latest_macd > latest_signal else "BEARISH"
        
        print(f"{ticker} ({name}): ${latest_price:.2f} | RSI: {rsi:.1f} | {recommendation}")
        
        return {
            'ticker': ticker,
            'name': name,
            'price': latest_price,
            'rsi': rsi,
            'macd_signal': macd_signal,
            'recommendation': recommendation
        }
        
    except Exception as e:
        print(f"{ticker}: Error - {e}")
        return None

def analyze_stock_quick(ticker):
    """Quick analysis version for mass scanning"""
    try:
        stock = yf.Ticker(ticker)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=45)
        
        hist = stock.history(start=start_date, end=end_date)
        
        if hist.empty:
            return None
        
        latest_price = hist['Close'].iloc[-1]
        rsi = calculate_rsi(hist['Close']).iloc[-1]
        macd, signal_line, _ = calculate_macd(hist['Close'])
        latest_macd = macd.iloc[-1]
        latest_signal = signal_line.iloc[-1]
        
        # Quick recommendation logic
        macd_signal = "BULLISH" if latest_macd > latest_signal else "BEARISH"
        
        if rsi < 30 and latest_macd > latest_signal:
            recommendation = "STRONG BUY"
        elif rsi < 35:
            recommendation = "BUY"
        elif rsi > 70 and latest_macd < latest_signal:
            recommendation = "STRONG SELL"
        elif rsi > 65:
            recommendation = "SELL"
        else:
            recommendation = "HOLD"
        
        print(f"{ticker}: ${latest_price:.2f} | RSI: {rsi:.1f} | {recommendation}")
        
        return {
            'ticker': ticker,
            'price': latest_price,
            'rsi': rsi,
            'macd_signal': macd_signal,
            'recommendation': recommendation
        }
        
    except Exception as e:
        print(f"{ticker}: Error - {e}")
        return None# pip install yfinance requests beautifulsoup4 textblob gspread oauth2client

import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
from textblob import TextBlob
from datetime import datetime, timedelta
import time
import csv
import os

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(prices, fast=12, slow=26, signal=9):
    ema_fast = prices.ewm(span=fast).mean()
    ema_slow = prices.ewm(span=slow).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram

def calculate_bollinger_bands(prices, period=20, std_dev=2):
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    return upper_band, sma, lower_band

def calculate_stochastic(high, low, close, k_period=14, d_period=3):
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    k_percent = 100 * ((close - lowest_low) / (highest_high - lowest_low))
    d_percent = k_percent.rolling(window=d_period).mean()
    return k_percent, d_percent

def calculate_williams_r(high, low, close, period=14):
    highest_high = high.rolling(window=period).max()
    lowest_low = low.rolling(window=period).min()
    williams_r = -100 * ((highest_high - close) / (highest_high - lowest_low))
    return williams_r

def get_sentiment(headline):
    blob = TextBlob(headline)
    return blob.sentiment.polarity

def get_stock_news(ticker):
    try:
        # Try Alpha Vantage news (free tier)
        url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={ticker}&apikey=demo&limit=5"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        headlines = []
        if 'feed' in data:
            for article in data['feed'][:5]:
                if 'title' in article:
                    headlines.append(article['title'])
        
        if headlines:
            return headlines
            
        # Fallback: try financial modeling prep (free tier)
        url2 = f"https://financialmodelingprep.com/api/v3/stock_news?tickers={ticker}&limit=5&apikey=demo"
        response2 = requests.get(url2, timeout=10)
        data2 = response2.json()
        
        if isinstance(data2, list):
            for article in data2[:5]:
                if 'title' in article:
                    headlines.append(article['title'])
        
        return headlines[:5]
        
    except Exception as e:
        print(f"Error fetching news for {ticker}: {e}")
        return []

def analyze_stock(ticker):
    print(f"\n{'='*50}")
    print(f"ANALYZING: {ticker}")
    print(f"{'='*50}")
    
    stock = yf.Ticker(ticker)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=45)
    
    hist = stock.history(start=start_date, end=end_date)
    
    if hist.empty:
        print(f"No data available for {ticker}")
        return
    
    # Technical Analysis
    latest_price = hist['Close'].iloc[-1]
    rsi = calculate_rsi(hist['Close'])
    latest_rsi = rsi.iloc[-1]
    
    macd, signal_line, histogram = calculate_macd(hist['Close'])
    latest_macd = macd.iloc[-1]
    latest_signal = signal_line.iloc[-1]
    latest_histogram = histogram.iloc[-1]
    
    upper_bb, middle_bb, lower_bb = calculate_bollinger_bands(hist['Close'])
    latest_upper = upper_bb.iloc[-1]
    latest_middle = middle_bb.iloc[-1]
    latest_lower = lower_bb.iloc[-1]
    
    stoch_k, stoch_d = calculate_stochastic(hist['High'], hist['Low'], hist['Close'])
    latest_stoch_k = stoch_k.iloc[-1]
    latest_stoch_d = stoch_d.iloc[-1]
    
    williams_r = calculate_williams_r(hist['High'], hist['Low'], hist['Close'])
    latest_williams = williams_r.iloc[-1]
    
    # Moving Averages
    sma_20 = hist['Close'].rolling(window=20).mean().iloc[-1]
    sma_50 = hist['Close'].rolling(window=50).mean().iloc[-1] if len(hist) >= 50 else None
    ema_12 = hist['Close'].ewm(span=12).mean().iloc[-1]
    ema_26 = hist['Close'].ewm(span=26).mean().iloc[-1]
    
    # Volume Analysis
    avg_volume = hist['Volume'].rolling(window=20).mean().iloc[-1]
    latest_volume = hist['Volume'].iloc[-1]
    volume_ratio = latest_volume / avg_volume
    
    print(f"Latest Price: ${latest_price:.2f}")
    print(f"Volume: {latest_volume:,.0f} (Ratio: {volume_ratio:.2f}x)")
    print()
    
    print("TECHNICAL INDICATORS:")
    print(f"RSI (14): {latest_rsi:.2f}")
    print(f"MACD: {latest_macd:.4f} | Signal: {latest_signal:.4f} | Histogram: {latest_histogram:.4f}")
    print(f"Stochastic: %K={latest_stoch_k:.2f} | %D={latest_stoch_d:.2f}")
    print(f"Williams %R: {latest_williams:.2f}")
    print()
    
    print("MOVING AVERAGES:")
    print(f"SMA 20: ${sma_20:.2f}")
    if sma_50:
        print(f"SMA 50: ${sma_50:.2f}")
    print(f"EMA 12: ${ema_12:.2f}")
    print(f"EMA 26: ${ema_26:.2f}")
    print()
    
    print("BOLLINGER BANDS:")
    print(f"Upper: ${latest_upper:.2f}")
    print(f"Middle: ${latest_middle:.2f}")
    print(f"Lower: ${latest_lower:.2f}")
    bb_position = (latest_price - latest_lower) / (latest_upper - latest_lower) * 100
    print(f"BB Position: {bb_position:.1f}%")
    print()
    
    print(f"\nRecent News Headlines and Sentiment:")
    print("-" * 40)
    
    headlines = get_stock_news(ticker)
    sentiments = []
    
    if headlines:
        for headline in headlines:
            sentiment = get_sentiment(headline)
            sentiments.append(sentiment)
            
            sentiment_label = "Positive" if sentiment > 0 else "Negative" if sentiment < 0 else "Neutral"
            print(f"• {headline}")
            print(f"  Sentiment: {sentiment:.3f} ({sentiment_label})")
            print()
    else:
        print("No recent news found")
    
    avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0
    print(f"Average Sentiment: {avg_sentiment:.3f}")
    print()
    
    # Advanced Trading Signals
    signals = []
    
    # RSI Signals
    if latest_rsi < 30:
        signals.append("RSI: OVERSOLD")
    elif latest_rsi > 70:
        signals.append("RSI: OVERBOUGHT")
    
    # MACD Signals
    if latest_macd > latest_signal and latest_histogram > 0:
        signals.append("MACD: BULLISH")
    elif latest_macd < latest_signal and latest_histogram < 0:
        signals.append("MACD: BEARISH")
    
    # Bollinger Band Signals
    if latest_price > latest_upper:
        signals.append("BB: OVERBOUGHT")
    elif latest_price < latest_lower:
        signals.append("BB: OVERSOLD")
    
    # Stochastic Signals
    if latest_stoch_k < 20 and latest_stoch_d < 20:
        signals.append("STOCH: OVERSOLD")
    elif latest_stoch_k > 80 and latest_stoch_d > 80:
        signals.append("STOCH: OVERBOUGHT")
    
    # Williams %R Signals
    if latest_williams < -80:
        signals.append("WILLIAMS: OVERSOLD")
    elif latest_williams > -20:
        signals.append("WILLIAMS: OVERBOUGHT")
    
    # Moving Average Signals
    if latest_price > sma_20 and sma_50 and sma_20 > sma_50:
        signals.append("MA: BULLISH TREND")
    elif latest_price < sma_20 and sma_50 and sma_20 < sma_50:
        signals.append("MA: BEARISH TREND")
    
    # Volume Signals
    if volume_ratio > 1.5:
        signals.append("VOLUME: HIGH")
    elif volume_ratio < 0.5:
        signals.append("VOLUME: LOW")
    
    print("TRADING SIGNALS:")
    if signals:
        for signal in signals:
            print(f"• {signal}")
    else:
        print("• No strong signals")
    print()
    
    # Overall Recommendation
    bullish_count = sum(1 for s in signals if any(word in s for word in ['OVERSOLD', 'BULLISH']))
    bearish_count = sum(1 for s in signals if any(word in s for word in ['OVERBOUGHT', 'BEARISH']))
    
    if bullish_count > bearish_count and avg_sentiment > 0:
        suggestion = "STRONG BUY"
    elif bullish_count > bearish_count:
        suggestion = "BUY"
    elif bearish_count > bullish_count and avg_sentiment < 0:
        suggestion = "STRONG SELL"
    elif bearish_count > bullish_count:
        suggestion = "SELL"
    else:
        suggestion = "HOLD"
    
    print(f"OVERALL RECOMMENDATION: {suggestion}")
    
    # Confidence Score
    total_signals = len(signals)
    confidence = min(100, total_signals * 15) if total_signals > 0 else 50
    print(f"CONFIDENCE: {confidence}%")
    
    time.sleep(1)

def main():
    # Stocks to analyze
    stocks = ['AAPL', 'MSFT', 'TSLA', 'NVDA', 'AMZN', 'GOOGL', 'META', 'NFLX', 'SPY', 'QQQ']
    
    # Commodities to analyze (using ETFs and futures)
    commodities = {
        'GLD': 'Gold',
        'SLV': 'Silver', 
        'USO': 'Oil',
        'UNG': 'Natural Gas',
        'DBA': 'Agriculture',
        'CORN': 'Corn',
        'WEAT': 'Wheat',
        'CPER': 'Copper',
        'PDBC': 'Commodities Basket',
        'GC=F': 'Gold Futures'
    }
    
    print("COMPREHENSIVE MARKET ANALYSIS")
    print("=" * 60)
    
    print("\n" + "="*20 + " STOCK ANALYSIS " + "="*20)
    for ticker in stocks:
        try:
            analyze_stock(ticker)
        except Exception as e:
            print(f"Error analyzing {ticker}: {e}")
    
    print("\n" + "="*20 + " COMMODITY ANALYSIS " + "="*20)
    for ticker, name in commodities.items():
        try:
            print(f"\n{'='*50}")
            print(f"ANALYZING: {ticker} ({name})")
            print(f"{'='*50}")
            analyze_commodity(ticker, name)
        except Exception as e:
            print(f"Error analyzing {ticker} ({name}): {e}")
    
    print(f"\n{'='*60}")
    print("COMPREHENSIVE ANALYSIS COMPLETE")
    print(f"{'='*60}")

def analyze_commodity(ticker, name):
    stock = yf.Ticker(ticker)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)  # More data for commodities
    
    hist = stock.history(start=start_date, end=end_date)
    
    if hist.empty:
        print(f"No data available for {ticker}")
        return
    
    latest_price = hist['Close'].iloc[-1]
    
    # Technical Analysis
    rsi = calculate_rsi(hist['Close'])
    latest_rsi = rsi.iloc[-1]
    
    macd, signal_line, histogram = calculate_macd(hist['Close'])
    latest_macd = macd.iloc[-1]
    latest_signal = signal_line.iloc[-1]
    latest_histogram = histogram.iloc[-1]
    
    # Moving Averages
    sma_20 = hist['Close'].rolling(window=20).mean().iloc[-1]
    sma_50 = hist['Close'].rolling(window=50).mean().iloc[-1] if len(hist) >= 50 else None
    
    # Volatility
    volatility = hist['Close'].pct_change().rolling(window=20).std().iloc[-1] * 100
    
    # 30-day performance
    if len(hist) >= 30:
        price_30_days_ago = hist['Close'].iloc[-30]
        performance_30d = ((latest_price - price_30_days_ago) / price_30_days_ago) * 100
    else:
        performance_30d = 0
    
    print(f"Latest Price: ${latest_price:.2f}")
    print(f"30-Day Performance: {performance_30d:+.2f}%")
    print(f"Volatility (20d): {volatility:.2f}%")
    print()
    
    print("TECHNICAL INDICATORS:")
    print(f"RSI (14): {latest_rsi:.2f}")
    print(f"MACD: {latest_macd:.4f} | Signal: {latest_signal:.4f}")
    print(f"SMA 20: ${sma_20:.2f}")
    if sma_50:
        print(f"SMA 50: ${sma_50:.2f}")
    print()
    
    # Commodity-specific signals
    signals = []
    
    if latest_rsi < 30:
        signals.append("RSI: OVERSOLD - Potential buying opportunity")
    elif latest_rsi > 70:
        signals.append("RSI: OVERBOUGHT - Consider taking profits")
    
    if latest_macd > latest_signal:
        signals.append("MACD: BULLISH momentum")
    elif latest_macd < latest_signal:
        signals.append("MACD: BEARISH momentum")
    
    if latest_price > sma_20:
        signals.append("PRICE: Above 20-day average")
    else:
        signals.append("PRICE: Below 20-day average")
    
    if volatility > 3:
        signals.append("VOLATILITY: HIGH - Increased risk/reward")
    elif volatility < 1:
        signals.append("VOLATILITY: LOW - Stable conditions")
    
    print("COMMODITY SIGNALS:")
    for signal in signals:
        print(f"• {signal}")
    
    # Overall recommendation for commodities
    if latest_rsi < 35 and latest_macd > latest_signal:
        recommendation = "BUY - Strong oversold bounce potential"
    elif latest_rsi > 65 and latest_macd < latest_signal:
        recommendation = "SELL - Overbought with momentum turning"
    elif performance_30d > 10:
        recommendation = "HOLD/TAKE_PROFITS - Strong recent gains"
    elif performance_30d < -10:
        recommendation = "ACCUMULATE - Significant pullback"
    else:
        recommendation = "HOLD - Wait for clearer signals"
    
    print(f"\nCOMMODITY RECOMMENDATION: {recommendation}")
    
    time.sleep(0.5)

if __name__ == "__main__":
    main()


