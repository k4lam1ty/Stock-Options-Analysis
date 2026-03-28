import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from math import log, sqrt, exp
from scipy.stats import norm
import time
import requests
import feedparser
from bs4 import BeautifulSoup
import json
import os
import pytz

st.set_page_config(page_title="Stock Analysis Dashboard", layout="wide")

# ============================================================
# RATE LIMIT PROTECTION
# ============================================================

rate_limit_active = False
rate_limit_until = 0
request_count = 0
request_window_start = time.time()

def check_rate_limit():
    global rate_limit_active, rate_limit_until
    if rate_limit_active and time.time() < rate_limit_until:
        return True
    rate_limit_active = False
    return False

def set_rate_limit(seconds=300):
    global rate_limit_active, rate_limit_until
    rate_limit_active = True
    rate_limit_until = time.time() + seconds

def track_request():
    global request_count, request_window_start
    request_count += 1
    if time.time() - request_window_start > 60:
        request_count = 0
        request_window_start = time.time()

# ============================================================
# CACHING DECORATORS
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_stock_info(ticker):
    try:
        stock = yf.Ticker(ticker)
        return stock.info
    except:
        return {}

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_stock_history(ticker, period='1y'):
    try:
        stock = yf.Ticker(ticker)
        return stock.history(period=period)
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_balance_sheet(ticker):
    try:
        stock = yf.Ticker(ticker)
        return stock.balance_sheet
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_financials(ticker):
    try:
        stock = yf.Ticker(ticker)
        return stock.financials
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_cashflow(ticker):
    try:
        stock = yf.Ticker(ticker)
        return stock.cashflow
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_options(ticker):
    try:
        stock = yf.Ticker(ticker)
        return stock.options
    except:
        return []

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_option_chain(ticker, expiration):
    try:
        stock = yf.Ticker(ticker)
        return stock.option_chain(expiration)
    except:
        return None

# ============================================================
# TIMEZONE FUNCTIONS
# ============================================================

def get_local_time():
    central = pytz.timezone('America/Chicago')
    return datetime.now(central)

def format_local_time(dt=None):
    if dt is None:
        dt = get_local_time()
    return dt.strftime('%I:%M:%S %p').lstrip('0').replace(' 0', ' ')

def format_local_date(dt=None):
    if dt is None:
        dt = get_local_time()
    return dt.strftime('%A, %B %d, %Y')

# ============================================================
# SESSION STATE (Simplified)
# ============================================================

if 'watchlist' not in st.session_state:
    st.session_state.watchlist = ['AAPL', 'MSFT', 'SPY', 'QQQ']

# ============================================================
# FORMATTING FUNCTIONS
# ============================================================

def format_currency(value):
    if value is None or value == 0:
        return "$0.00"
    return f"${value:,.2f}"

def format_number(value):
    if value is None or value == 0:
        return "0"
    return f"{value:,.0f}"

def format_percentage(value):
    if value is None:
        return "0%"
    return f"{value:,.2f}%"

def format_large_number(value):
    """Format large numbers with appropriate abbreviations"""
    if value is None or value == 0:
        return "$0"
    if value >= 1_000_000_000:
        return f"${value/1_000_000_000:,.2f}B"
    elif value >= 1_000_000:
        return f"${value/1_000_000:,.2f}M"
    elif value >= 1_000:
        return f"${value/1_000:,.2f}K"
    else:
        return f"${value:,.2f}"

def format_volume(value):
    if value is None or value == 0:
        return "0"
    if value >= 1_000_000_000:
        return f"{value/1_000_000_000:,.1f}B"
    elif value >= 1_000_000:
        return f"{value/1_000_000:,.1f}M"
    elif value >= 1_000:
        return f"{value/1_000:,.1f}K"
    else:
        return f"{value:,.0f}"

# ============================================================
# NEWS FUNCTIONS
# ============================================================

def get_high_quality_news(ticker, max_articles=20):
    """Fetch news from reputable sources only"""
    news_items = []
    
    # Yahoo Finance API
    try:
        stock = yf.Ticker(ticker)
        yf_news = stock.news
        if yf_news:
            for article in yf_news[:max_articles]:
                publisher = article.get('publisher', '').lower()
                if 'seeking alpha' in publisher:
                    continue
                
                title = article.get('title', '')
                link = article.get('link', '')
                if link and not link.startswith('http'):
                    link = f"https://finance.yahoo.com{link}"
                
                importance = 50
                if 'bloomberg' in publisher:
                    importance += 25
                elif 'reuters' in publisher:
                    importance += 25
                elif 'wsj' in publisher or 'wall street' in publisher:
                    importance += 25
                elif 'cnbc' in publisher:
                    importance += 20
                
                news_items.append({
                    'title': title,
                    'link': link,
                    'publisher': article.get('publisher', 'Yahoo Finance'),
                    'date': article.get('providerPublishTime', None),
                    'source': 'Yahoo Finance',
                    'importance': importance
                })
    except:
        pass
    
    # Google News RSS
    try:
        search_term = ticker
        google_url = f"https://news.google.com/rss/search?q={search_term}+stock&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(google_url)
        
        skip_domains = ['seekingalpha.com', 'fool.com']
        
        for entry in feed.entries[:max_articles]:
            publisher = entry.get('source', {}).get('title', '') if hasattr(entry, 'source') else ''
            link = entry.link
            
            skip = False
            for domain in skip_domains:
                if domain in link.lower() or domain in publisher.lower():
                    skip = True
                    break
            if skip:
                continue
            
            pub_date = None
            if hasattr(entry, 'published_parsed'):
                pub_date = time.mktime(entry.published_parsed)
            
            title = entry.title
            importance = 40
            
            publisher_lower = publisher.lower()
            if 'bloomberg' in publisher_lower:
                importance += 25
            elif 'reuters' in publisher_lower:
                importance += 25
            elif 'wsj' in publisher_lower or 'wall street' in publisher_lower:
                importance += 25
            elif 'cnbc' in publisher_lower:
                importance += 20
            
            news_items.append({
                'title': title,
                'link': link,
                'publisher': publisher if publisher else 'Google News',
                'date': pub_date,
                'source': 'Google News',
                'importance': importance
            })
    except:
        pass
    
    seen_titles = set()
    unique_news = []
    for item in news_items:
        clean_title = item['title'].lower().strip()
        if clean_title not in seen_titles and len(clean_title) > 10:
            seen_titles.add(clean_title)
            unique_news.append(item)
    
    unique_news.sort(key=lambda x: (x['importance'], x['date'] if x['date'] else 0), reverse=True)
    return unique_news[:max_articles]

def get_catalyst_news(ticker, max_articles=15):
    """Fetch catalyst-focused news with links"""
    catalyst_items = []
    
    # Yahoo Finance
    try:
        stock = yf.Ticker(ticker)
        yf_news = stock.news
        if yf_news:
            for article in yf_news[:max_articles]:
                title = article.get('title', '')
                link = article.get('link', '')
                if link and not link.startswith('http'):
                    link = f"https://finance.yahoo.com{link}"
                
                catalyst_keywords = ['earnings', 'acquisition', 'merger', 'ceo', 'lawsuit', 'fda', 'approval', 
                                     'bankruptcy', 'stock split', 'dividend', 'buyback', 'guidance', 
                                     'forecast', 'upgrade', 'downgrade', 'contract', 'partnership',
                                     'record', 'high', 'low', 'crash', 'rally']
                
                if any(keyword in title.lower() for keyword in catalyst_keywords):
                    catalyst_items.append({
                        'title': title,
                        'link': link,
                        'publisher': article.get('publisher', 'Yahoo Finance'),
                        'date': article.get('providerPublishTime', None),
                        'source': 'Yahoo Finance'
                    })
    except:
        pass
    
    # Google News with specific search
    try:
        search_term = f"{ticker} earnings OR acquisition OR merger OR upgrade OR downgrade OR lawsuit"
        google_url = f"https://news.google.com/rss/search?q={search_term}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(google_url)
        
        for entry in feed.entries[:max_articles]:
            title = entry.title
            link = entry.link
            publisher = entry.get('source', {}).get('title', 'Google News') if hasattr(entry, 'source') else 'Google News'
            
            catalyst_items.append({
                'title': title,
                'link': link,
                'publisher': publisher,
                'date': None,
                'source': 'Google News'
            })
    except:
        pass
    
    # Remove duplicates
    seen_titles = set()
    unique_items = []
    for item in catalyst_items:
        clean_title = item['title'].lower().strip()
        if clean_title not in seen_titles and len(clean_title) > 10:
            seen_titles.add(clean_title)
            unique_items.append(item)
    
    return unique_items[:max_articles]

# ============================================================
# EARNINGS FUNCTIONS
# ============================================================

def get_next_earnings(ticker):
    """Get actual next earnings date from Yahoo Finance"""
    try:
        stock = yf.Ticker(ticker)
        calendar = stock.calendar
        if calendar is not None and not calendar.empty:
            if 'Earnings Date' in calendar.index:
                earnings_date = calendar.loc['Earnings Date']
                if isinstance(earnings_date, pd.Series):
                    earnings_date = earnings_date.iloc[0]
                if isinstance(earnings_date, datetime) or isinstance(earnings_date, pd.Timestamp):
                    return earnings_date
                if isinstance(earnings_date, list) and len(earnings_date) > 0:
                    return earnings_date[0]
        
        info = get_cached_stock_info(ticker)
        earnings_date = info.get('earningsDate', None)
        if earnings_date:
            if isinstance(earnings_date, list):
                return earnings_date[0]
            return earnings_date
        
        return None
    except:
        return None

def get_earnings_history(ticker):
    """Get historical earnings dates and surprises from multiple sources"""
    earnings_data = []
    
    # Method 1: Yahoo Finance earnings object
    try:
        stock = yf.Ticker(ticker)
        earnings = stock.earnings
        
        if earnings is not None and not earnings.empty:
            for date, row in earnings.iterrows():
                if isinstance(row, pd.Series):
                    eps_actual = row.get('epsActual', row.get('Earnings', None))
                    eps_estimate = row.get('epsEstimate', row.get('Estimate', None))
                    
                    if eps_actual and eps_estimate:
                        surprise_pct = ((eps_actual - eps_estimate) / abs(eps_estimate)) * 100
                        earnings_data.append({
                            'date': date,
                            'actual': eps_actual,
                            'estimate': eps_estimate,
                            'surprise_pct': surprise_pct
                        })
                    elif eps_actual:
                        earnings_data.append({
                            'date': date,
                            'actual': eps_actual,
                            'estimate': None,
                            'surprise_pct': None
                        })
    except:
        pass
    
    # Method 2: Get from financials if available
    try:
        if len(earnings_data) == 0:
            financials = get_cached_financials(ticker)
            if financials is not None and not financials.empty and 'Net Income' in financials.index:
                net_income = financials.loc['Net Income']
                if not net_income.empty:
                    for i, (date, value) in enumerate(net_income.items()):
                        if i < 4:
                            earnings_data.append({
                                'date': date,
                                'actual': value / 1e6 if abs(value) > 1e6 else value,
                                'estimate': None,
                                'surprise_pct': None,
                                'is_net_income': True
                            })
    except:
        pass
    
    if earnings_data:
        earnings_data.sort(key=lambda x: x['date'] if isinstance(x['date'], (datetime, pd.Timestamp)) else datetime.min, reverse=True)
        return earnings_data[:4]
    
    return None

# ============================================================
# IMPLIED VOLATILITY FUNCTIONS
# ============================================================

def get_implied_volatility(ticker, current_price, option_type):
    try:
        expirations = get_cached_options(ticker)
        if not expirations:
            return None
        nearest_exp = expirations[0]
        opt_chain = get_cached_option_chain(ticker, nearest_exp)
        if opt_chain is None:
            return None
        if option_type == "Call":
            chain = opt_chain.calls
        else:
            chain = opt_chain.puts
        if chain.empty:
            return None
        chain['diff'] = abs(chain['strike'] - current_price)
        closest = chain.loc[chain['diff'].idxmin()]
        if 'impliedVolatility' in closest and not pd.isna(closest['impliedVolatility']):
            return closest['impliedVolatility'] * 100
        return None
    except:
        return None

def get_implied_volatility_for_strike(ticker, strike, expiration_date, option_type):
    try:
        expirations = get_cached_options(ticker)
        exp_date_str = expiration_date.strftime('%Y-%m-%d')
        if exp_date_str not in expirations:
            exp_dates = [datetime.strptime(d, '%Y-%m-%d') for d in expirations]
            exp_dates = [d for d in exp_dates if d >= expiration_date]
            if not exp_dates:
                return None
            closest_exp = min(exp_dates)
        else:
            closest_exp = datetime.strptime(exp_date_str, '%Y-%m-%d')
        closest_exp_str = closest_exp.strftime('%Y-%m-%d')
        opt_chain = get_cached_option_chain(ticker, closest_exp_str)
        if opt_chain is None:
            return None
        if option_type == "Call":
            chain = opt_chain.calls
        else:
            chain = opt_chain.puts
        if chain.empty:
            return None
        chain['diff'] = abs(chain['strike'] - strike)
        closest = chain.loc[chain['diff'].idxmin()]
        if 'impliedVolatility' in closest and not pd.isna(closest['impliedVolatility']):
            return closest['impliedVolatility'] * 100
        return None
    except:
        return None

# ============================================================
# TRADINGVIEW CHART
# ============================================================

def tradingview_full_chart(ticker, timeframe="D", theme="dark"):
    chart_html = f"""
    <div class="tradingview-widget-container">
        <div id="tradingview_full_chart"></div>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <script type="text/javascript">
        new TradingView.widget({{
            "width": "100%",
            "height": 700,
            "symbol": "{ticker}",
            "interval": "{timeframe}",
            "timezone": "America/Chicago",
            "theme": "{theme}",
            "style": "1",
            "locale": "en",
            "toolbar_bg": "#f1f3f6",
            "enable_publishing": true,
            "allow_symbol_change": true,
            "save_image": true,
            "calendar": true,
            "container_id": "tradingview_full_chart",
            "studies": ["RSI@tv-basicstudies", "MACD@tv-basicstudies"],
            "withdateranges": true,
            "hide_side_toolbar": false,
            "show_popup_button": true,
            "popup_width": "1000",
            "popup_height": "650",
            "loading_screen": {{ "backgroundColor": "#1e1e2e" }}
        }});
        </script>
    </div>
    """
    return st.components.v1.html(chart_html, height=750)

def tradingview_direct_link(ticker):
    return f"https://www.tradingview.com/chart/?symbol={ticker}"

# ============================================================
# DATA FUNCTIONS
# ============================================================

def is_index(ticker):
    index_tickers = ['SPY', 'QQQ', 'DIA', 'IWM', 'VIX', 'VOO', 'IVV', 'TLT', 'AGG', 'BND', 'GLD', 'SLV']
    return ticker.upper() in [x.upper() for x in index_tickers]

def get_stock_data(ticker):
    info = get_cached_stock_info(ticker)
    hist = get_cached_stock_history(ticker, '1y')
    
    if not is_index(ticker):
        balance_sheet = get_cached_balance_sheet(ticker)
        income_statement = get_cached_financials(ticker)
        cashflow = get_cached_cashflow(ticker)
    else:
        balance_sheet = pd.DataFrame()
        income_statement = pd.DataFrame()
        cashflow = pd.DataFrame()
    
    return {
        'info': info,
        'hist': hist,
        'balance_sheet': balance_sheet,
        'income_statement': income_statement,
        'cashflow': cashflow,
        'is_index': is_index(ticker)
    }

def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_risk_free_rate():
    try:
        treasury = yf.Ticker("^TNX")
        info = get_cached_stock_info("^TNX")
        rate = info.get('regularMarketPrice', info.get('previousClose', 4.5))
        return rate / 100
    except:
        return 0.045

def get_dividend_yield(ticker):
    """Get dividend yield with sanity check"""
    try:
        info = get_cached_stock_info(ticker)
        dividend_yield = info.get('dividendYield', 0)
        
        # Sanity check - dividend yield should be between 0% and 15% (0 to 0.15)
        if dividend_yield and 0 < dividend_yield < 0.15:
            return dividend_yield
        
        # If yield is > 0.15 (15%), it's likely an error - try to calculate from dividend rate
        dividend_rate = info.get('dividendRate', 0)
        current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
        if dividend_rate and current_price and dividend_rate > 0:
            calculated = dividend_rate / current_price
            if 0 < calculated < 0.15:
                return calculated
        
        return 0
    except:
        return 0

# ============================================================
# FORECASTING FUNCTIONS
# ============================================================

def build_financial_forecast(current_revenue, current_margin, revenue_growth, margin_expansion, years=5):
    projections = []
    revenue = current_revenue
    margin = current_margin
    
    for year in range(1, years + 1):
        revenue *= (1 + revenue_growth / 100)
        margin += margin_expansion
        ebit = revenue * (margin / 100)
        fcf = ebit * 0.7
        
        projections.append({
            'Year': year,
            'Revenue': revenue,
            'Margin %': margin,
            'EBIT': ebit,
            'FCF': fcf
        })
    
    return projections

def calculate_dcf(projections, wacc=0.08, terminal_growth=0.03):
    present_value = 0
    for i, data in enumerate(projections, 1):
        present_value += data['FCF'] / (1 + wacc) ** i
    
    terminal_fcf = projections[-1]['FCF']
    terminal_value = terminal_fcf * (1 + terminal_growth) / (wacc - terminal_growth)
    present_terminal = terminal_value / (1 + wacc) ** len(projections)
    
    return present_value + present_terminal

# ============================================================
# CATALYST DETECTION
# ============================================================

def detect_catalysts(ticker, info):
    """Detect potential bull and bear catalysts with sources and links"""
    bull_catalysts = []
    bear_catalysts = []
    
    # 1. Get actual news with links
    catalyst_news = get_catalyst_news(ticker, max_articles=15)
    
    # 2. Analyst rating changes - add source link
    if info.get('recommendationKey'):
        rec = info.get('recommendationKey', '').lower()
        if rec in ['strong_buy', 'buy']:
            bull_catalysts.append({
                'title': f"Analyst consensus: {rec.upper()} rating",
                'source': 'Yahoo Finance Analyst Data',
                'link': f"https://finance.yahoo.com/quote/{ticker}/analysts",
                'type': 'analyst'
            })
        elif rec in ['strong_sell', 'sell']:
            bear_catalysts.append({
                'title': f"Analyst consensus: {rec.upper()} rating",
                'source': 'Yahoo Finance Analyst Data',
                'link': f"https://finance.yahoo.com/quote/{ticker}/analysts",
                'type': 'analyst'
            })
    
    # 3. Target price changes
    target_mean = info.get('targetMeanPrice', 0)
    current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
    if target_mean and current_price:
        upside = ((target_mean - current_price) / current_price) * 100
        if upside > 20:
            bull_catalysts.append({
                'title': f"Analyst target price: ${target_mean:.2f} ({upside:+.0f}% upside)",
                'source': 'Analyst Consensus',
                'link': f"https://finance.yahoo.com/quote/{ticker}/analysts",
                'type': 'price_target'
            })
        elif upside < -10:
            bear_catalysts.append({
                'title': f"Analyst target price: ${target_mean:.2f} ({upside:+.0f}% downside)",
                'source': 'Analyst Consensus',
                'link': f"https://finance.yahoo.com/quote/{ticker}/analysts",
                'type': 'price_target'
            })
    
    # 4. Earnings surprises
    eps_surprise = info.get('earningsQuarterlyGrowth', 0)
    if eps_surprise and eps_surprise > 10:
        bull_catalysts.append({
            'title': f"EPS surprise: +{eps_surprise:.1f}% in last quarter",
            'source': 'Yahoo Finance Earnings',
            'link': f"https://finance.yahoo.com/quote/{ticker}/earnings",
            'type': 'earnings'
        })
    elif eps_surprise and eps_surprise < -10:
        bear_catalysts.append({
            'title': f"EPS surprise: {eps_surprise:.1f}% in last quarter",
            'source': 'Yahoo Finance Earnings',
            'link': f"https://finance.yahoo.com/quote/{ticker}/earnings",
            'type': 'earnings'
        })
    
    # 5. Earnings date
    next_earnings = get_next_earnings(ticker)
    if next_earnings:
        days_until = (next_earnings.date() - date.today()).days
        if 0 < days_until <= 30:
            bull_catalysts.append({
                'title': f"Earnings report in {days_until} days",
                'source': 'Earnings Calendar',
                'link': f"https://finance.yahoo.com/calendar/earnings?symbol={ticker}",
                'type': 'earnings_date'
            })
    
    # 6. News articles with links
    for article in catalyst_news:
        title = article['title']
        link = article.get('link', '#')
        source = article.get('source', 'News')
        
        title_lower = title.lower()
        bull_keywords = ['upgrade', 'buy', 'outperform', 'beat', 'surprise', 'acquisition', 'merger', 
                         'partnership', 'contract', 'approval', 'launch', 'record', 'high', 'bullish', 'strong']
        bear_keywords = ['downgrade', 'sell', 'underperform', 'miss', 'disappoint', 'lawsuit', 
                         'investigation', 'delay', 'rejection', 'decline', 'drop', 'loss', 'bearish', 'warning']
        
        bull_score = sum(2 for kw in bull_keywords if kw in title_lower)
        bear_score = sum(2 for kw in bear_keywords if kw in title_lower)
        
        if bull_score > bear_score and bull_score >= 2:
            bull_catalysts.append({
                'title': title[:120] + ('...' if len(title) > 120 else ''),
                'source': source,
                'link': link,
                'type': 'news'
            })
        elif bear_score > bull_score and bear_score >= 2:
            bear_catalysts.append({
                'title': title[:120] + ('...' if len(title) > 120 else ''),
                'source': source,
                'link': link,
                'type': 'news'
            })
    
    # Remove duplicates by title
    seen_titles = set()
    unique_bull = []
    for item in bull_catalysts:
        if item['title'] not in seen_titles:
            seen_titles.add(item['title'])
            unique_bull.append(item)
    
    seen_titles = set()
    unique_bear = []
    for item in bear_catalysts:
        if item['title'] not in seen_titles:
            seen_titles.add(item['title'])
            unique_bear.append(item)
    
    return unique_bull[:5], unique_bear[:5]

# ============================================================
# WATCHLIST FUNCTIONS
# ============================================================

def validate_ticker(ticker):
    """Check if ticker is valid by trying to get basic info"""
    try:
        stock = yf.Ticker(ticker)
        price = stock.info.get('regularMarketPrice', None)
        if price and price > 0:
            return True
        return False
    except:
        return False

def add_to_watchlist(ticker):
    """Add ticker to watchlist only if valid"""
    if not ticker or ticker == '':
        return False, "No ticker entered"
    
    ticker = ticker.upper()
    
    if ticker in st.session_state.watchlist:
        return False, f"{ticker} already in watchlist"
    
    # Validate ticker
    with st.spinner(f"Validating {ticker}..."):
        is_valid = validate_ticker(ticker)
    
    if is_valid:
        st.session_state.watchlist.append(ticker)
        return True, f"Added {ticker} to watchlist"
    else:
        return False, f"Invalid ticker: {ticker}. Please check the symbol."

def remove_from_watchlist(ticker):
    if ticker in st.session_state.watchlist:
        st.session_state.watchlist.remove(ticker)

# ============================================================
# OPTIONS CALCULATION
# ============================================================

def calculate_option_price(S, K, T, r, v, q, option_type):
    if v <= 0 or T <= 0:
        return 0, 0, 0, 0, 0
    d1 = (log(S / K) + (r - q + v**2 / 2) * T) / (v * sqrt(T))
    d2 = d1 - v * sqrt(T)
    if option_type == "Call":
        price = S * exp(-q * T) * norm.cdf(d1) - K * exp(-r * T) * norm.cdf(d2)
        delta = exp(-q * T) * norm.cdf(d1)
        gamma = norm.pdf(d1) * exp(-q * T) / (S * v * sqrt(T))
        theta = - (S * v * norm.pdf(d1) * exp(-q * T)) / (2 * sqrt(T)) - r * K * exp(-r * T) * norm.cdf(d2) + q * S * norm.cdf(d1) * exp(-q * T)
        vega = S * sqrt(T) * norm.pdf(d1) * exp(-q * T) / 100
    else:
        price = K * exp(-r * T) * norm.cdf(-d2) - S * exp(-q * T) * norm.cdf(-d1)
        delta = -exp(-q * T) * norm.cdf(-d1)
        gamma = norm.pdf(d1) * exp(-q * T) / (S * v * sqrt(T))
        theta = - (S * v * norm.pdf(d1) * exp(-q * T)) / (2 * sqrt(T)) + r * K * exp(-r * T) * norm.cdf(-d2) - q * S * norm.cdf(-d1) * exp(-q * T)
        vega = S * sqrt(T) * norm.pdf(d1) * exp(-q * T) / 100
    return price, delta, gamma, theta, vega

# ============================================================
# SIDEBAR WITH THEME
# ============================================================

with st.sidebar:
    st.header("🎨 Appearance")
    theme = st.selectbox(
        "Theme:",
        ["Dark", "Light"],
        index=0,
        help="Select dark or light mode"
    )
    
    if theme == "Light":
        st.markdown("""
        <style>
        .stApp { background-color: #ffffff !important; }
        .stApp, .stApp * { color: #000000 !important; }
        
        div[data-testid="stMetricValue"] {
            color: #000000 !important;
            font-weight: bold;
            font-size: 1.2rem !important;
        }
        
        div[data-testid="stMetricLabel"] {
            color: #333333 !important;
            font-size: 0.8rem !important;
            white-space: normal !important;
            word-wrap: break-word !important;
        }
        
        div[data-testid="stMetric"] {
            min-width: 120px !important;
        }
        
        .stSidebar { background-color: #f0f2f6 !important; }
        .stSidebar .stMarkdown, .stSidebar p, .stSidebar label { color: #000000 !important; }
        
        header, .stApp header, [data-testid="stHeader"] {
            background-color: #ffffff !important;
            color: #000000 !important;
        }
        
        .stTextInput input, .stNumberInput input, .stSelectbox select {
            background-color: #ffffff !important;
            color: #000000 !important;
            border: 1px solid #cccccc !important;
        }
        
        .stNumberInput button {
            background-color: #f0f0f0 !important;
            color: #000000 !important;
        }
        
        .stDateInput input {
            background-color: #ffffff !important;
            color: #000000 !important;
        }
        
        .stSelectbox div[data-baseweb="select"] div {
            color: #000000 !important;
            background-color: #ffffff !important;
        }
        
        div[role="listbox"] div {
            color: #000000 !important;
            background-color: #ffffff !important;
        }
        
        div[role="listbox"] div:hover { background-color: #e0e0e0 !important; }
        
        .stMetric {
            background-color: #f8f9fa !important;
            border: 1px solid #e9ecef !important;
            border-radius: 10px;
            padding: 10px;
        }
        
        .stTabs [data-baseweb="tab-list"] button {
            color: #000000 !important;
            font-size: 0.9rem !important;
        }
        
        .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
            background-color: #e0e0e0 !important;
        }
        </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <style>
        .stApp { background-color: #1e1e2e !important; }
        .stApp, .stApp * { color: #e0e0e0 !important; }
        
        div[data-testid="stMetricValue"] {
            color: #a6e3a1 !important;
            font-weight: bold;
            font-size: 1.2rem !important;
        }
        
        div[data-testid="stMetricLabel"] {
            color: #cdd6f4 !important;
            font-size: 0.8rem !important;
            white-space: normal !important;
            word-wrap: break-word !important;
        }
        
        div[data-testid="stMetric"] {
            min-width: 120px !important;
        }
        
        .stSidebar { background-color: #181825 !important; }
        
        .stTextInput input, .stNumberInput input, .stSelectbox select {
            background-color: #313244 !important;
            color: #cdd6f4 !important;
            border: 1px solid #45475a !important;
        }
        
        .stMetric {
            background-color: #313244 !important;
            border: 1px solid #45475a !important;
            border-radius: 10px;
            padding: 10px;
        }
        
        .stTabs [data-baseweb="tab-list"] button {
            font-size: 0.9rem !important;
        }
        </style>
        """, unsafe_allow_html=True)

risk_free_rate = get_risk_free_rate()

with st.sidebar:
    if request_count > 20:
        st.warning(f"📊 API requests this minute: {request_count}")
    if check_rate_limit():
        st.error("⏳ Rate limited - using cached data")
    
    st.header("🔍 Input")
    ticker = st.text_input(
        "Stock / Index Ticker:",
        "SPY",
        help="Type a ticker symbol (e.g., AAPL, MSFT, GME)"
    ).upper()
    st.caption("📝 Type a ticker symbol (e.g., AAPL, MSFT, GME)")
    
    st.markdown("---")
    st.header("💰 Rates")
    auto_rate = st.checkbox("Auto-fetch Risk-Free Rate (10-Year Treasury)", value=True)
    if auto_rate:
        risk_free_rate = get_risk_free_rate()
        st.success(f"📊 10-Year Treasury Yield: {risk_free_rate*100:.2f}%")
        manual_override = st.checkbox("Manually override risk-free rate", value=False)
        if manual_override:
            manual_rate = st.number_input("Manual Risk-Free Rate (%):", value=risk_free_rate*100, step=0.1) / 100
            risk_free_rate = manual_rate
            st.info(f"Using manual rate: {risk_free_rate*100:.2f}%")
    else:
        risk_free_rate = st.number_input("Risk-Free Rate (%):", value=4.5, step=0.1) / 100
    
    st.markdown("---")
    st.header("⚙️ Options Calculator")
    
    expiration_date = st.date_input(
        "Expiration Date:",
        value=date.today(),
        min_value=date.today(),
        help="📅 Click calendar to select date"
    )
    
    today = date.today()
    if expiration_date >= today:
        days = (expiration_date - today).days
        st.caption(f"📅 Days to Expiration: **{days} days**")
    else:
        days = 0
        st.error("Expiration date must be in the future")
    
    strike = st.number_input(
        "Strike Price:",
        value=100.0,
        step=1.0,
        help="🔢 Use arrows or type a number"
    )
    
    option_type = st.selectbox(
        "Option Type:",
        ["Call", "Put"],
        index=0,
        help="📋 Click to select Call or Put"
    )
    
    st.markdown("---")
    st.header("📊 Volatility Setting")
    
    volatility_source = st.radio(
        "Volatility Source:",
        ["Historical Volatility (from price data)", "Implied Volatility (from option chain)"],
        index=0,
        help="🖱️ Click to select volatility source"
    )
    
    st.markdown("---")
    st.header("🔄 Auto-Refresh")
    auto_refresh = st.checkbox("Auto-refresh data", value=False)
    
    if auto_refresh:
        refresh_interval = st.selectbox(
            "Refresh interval:",
            ["120 sec", "300 sec", "600 sec"],
            index=1,
            help="🖱️ Click to select interval"
        )
        interval_seconds = int(refresh_interval.split()[0])
        st.caption(f"🔄 Refreshing every {interval_seconds} seconds")
        st.caption(f"⚠️ Frequent refreshes may cause rate limits")
    else:
        interval_seconds = 0
    
    st.caption(f"📅 Last update: {format_local_time()}")

# ============================================================
# MAIN APP TABS (4 Tabs - Simplified)
# ============================================================

tab1, tab2, tab3, tab4 = st.tabs(["📊 Analysis", "📈 Watchlist", "📰 News", "📉 Historical Data"])

# ============================================================
# TAB 1: ANALYSIS
# ============================================================

with tab1:
    if ticker:
        try:
            with st.spinner(f"Loading data for {ticker}..."):
                data = get_stock_data(ticker)
                info = data['info']
                hist = data['hist']
                balance_sheet = data['balance_sheet']
                income_statement = data['income_statement']
                cashflow = data['cashflow']
                is_index_ticker = data['is_index']
            
            dividend_yield = get_dividend_yield(ticker)
            current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            previous_close = info.get('previousClose', 0)
            price_change = current_price - previous_close
            price_change_pct = (price_change / previous_close * 100) if previous_close else 0
            
            # Earnings alerts
            next_earnings = get_next_earnings(ticker)
            if next_earnings:
                days_until = (next_earnings.date() - date.today()).days
                if 0 < days_until <= 7:
                    st.warning(f"📅 **EARNINGS ALERT:** {ticker} reports earnings in {days_until} days! IV likely elevated.")
            
            hist_6mo = hist.tail(130)
            if len(hist_6mo) > 1:
                six_month_return = ((hist_6mo['Close'].iloc[-1] - hist_6mo['Close'].iloc[0]) / hist_6mo['Close'].iloc[0]) * 100
            else:
                six_month_return = 0
            
            # Volatility calculation
            if volatility_source == "Historical Volatility (from price data)":
                if len(hist) > 20:
                    daily_returns = hist['Close'].pct_change().dropna()
                    volatility = daily_returns.std() * (252 ** 0.5) * 100
                else:
                    volatility = 30
                vol_to_use = volatility / 100
                vol_source_text = f"Historical Volatility: {volatility:.1f}%"
            else:
                implied_vol = get_implied_volatility(ticker, current_price, option_type)
                if implied_vol and implied_vol > 0:
                    volatility = implied_vol
                    vol_to_use = volatility / 100
                    vol_source_text = f"Implied Volatility: {volatility:.1f}% (from option chain)"
                else:
                    if len(hist) > 20:
                        daily_returns = hist['Close'].pct_change().dropna()
                        volatility = daily_returns.std() * (252 ** 0.5) * 100
                    else:
                        volatility = 30
                    vol_to_use = volatility / 100
                    vol_source_text = f"Historical Volatility: {volatility:.1f}% (implied not available)"
            
            manual_vol = st.sidebar.checkbox("Manually override volatility", value=False)
            if manual_vol:
                volatility = st.sidebar.number_input("Manual Volatility (%):", value=volatility, step=1.0)
                vol_to_use = volatility / 100
            
            rsi = calculate_rsi(hist['Close'])
            current_rsi = rsi.iloc[-1] if not rsi.empty else 50
            asset_type = "Index/ETF" if is_index_ticker else "Stock"
            
            # HEADER METRICS
            st.subheader(f"📊 {ticker} - {info.get('longName', ticker)} ({asset_type})")
            col1, col2, col3, col4, col5, col6 = st.columns(6)
            with col1:
                st.metric("Current Price", format_currency(current_price), delta=f"{price_change:+.2f} ({price_change_pct:+.1f}%)")
            with col2:
                st.metric("Day High", format_currency(info.get('dayHigh', 0)))
            with col3:
                st.metric("Day Low", format_currency(info.get('dayLow', 0)))
            with col4:
                st.metric("52-Week High", format_currency(info.get('fiftyTwoWeekHigh', 0)))
            with col5:
                st.metric("52-Week Low", format_currency(info.get('fiftyTwoWeekLow', 0)))
            with col6:
                st.metric("Volume", format_volume(info.get('volume', 0)))
            st.markdown("---")
            
            # KEY METRICS ROW
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                pe = info.get('trailingPE', 0)
                st.metric("P/E Ratio", f"{pe:,.2f}" if pe else "N/A")
            with col2:
                st.metric("6-Month Return", f"{six_month_return:+.1f}%")
            with col3:
                st.metric("Volatility", vol_source_text)
            with col4:
                st.metric("RSI (14)", f"{current_rsi:.1f}")
            with col5:
                if not is_index_ticker:
                    st.metric("Dividend Yield", format_percentage(dividend_yield*100) if dividend_yield > 0 else "N/A")
                else:
                    st.metric("Dividend Yield", "N/A")
            st.markdown("---")
            
            # RATES ROW
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Risk-Free Rate", f"{risk_free_rate*100:.2f}%")
            with col2:
                st.metric("Updated", format_local_time())
            with col3:
                st.metric("Auto-Refresh", "OFF" if not auto_refresh else f"{interval_seconds}s")
            st.markdown("---")
            
            # EARNINGS CALENDAR
            if not is_index_ticker:
                st.subheader("📅 Earnings Calendar")
                next_earnings = get_next_earnings(ticker)
                earnings_history = get_earnings_history(ticker)
                
                col1, col2 = st.columns(2)
                with col1:
                    if next_earnings:
                        next_earnings_date = pd.to_datetime(next_earnings).date()
                        days_until = (next_earnings_date - date.today()).days
                        st.metric("Next Earnings Date", next_earnings_date.strftime('%Y-%m-%d'))
                        st.caption(f"{days_until} days from today")
                        if days_until <= 30:
                            st.warning("⚠️ Earnings within 30 days - options may have elevated IV")
                    else:
                        st.info("Earnings date not available")
                with col2:
                    if earnings_history:
                        st.write("**Recent Earnings:**")
                        for earnings in earnings_history[:4]:
                            date_str = earnings['date'].strftime('%Y-%m-%d') if isinstance(earnings['date'], (datetime, pd.Timestamp)) else str(earnings['date'])
                            if earnings.get('surprise_pct') is not None:
                                surprise = earnings['surprise_pct']
                                color = "🟢" if surprise > 0 else "🔴" if surprise < 0 else "⚪"
                                st.write(f"{color} {date_str}: {surprise:+.1f}% surprise")
                            else:
                                st.write(f"📊 {date_str}")
                    else:
                        st.info("Historical earnings data not available")
                st.markdown("---")
            
            # POTENTIAL CATALYSTS
            st.markdown("---")
            st.subheader("🚀 Potential Catalysts")
            
            with st.spinner("Analyzing potential catalysts..."):
                bull_catalysts, bear_catalysts = detect_catalysts(ticker, info)
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("### 🟢 Bull Catalysts")
                if bull_catalysts:
                    for catalyst in bull_catalysts:
                        icon = "📊" if catalyst['type'] == 'analyst' else "💰" if catalyst['type'] == 'earnings' else "🎯" if catalyst['type'] == 'price_target' else "📰"
                        st.markdown(f"""
                        <div style="background-color: rgba(46, 139, 86, 0.1); border-left: 3px solid #2e8b57; padding: 8px; margin-bottom: 8px; border-radius: 4px;">
                            <p style="margin: 0;">{icon} <a href="{catalyst['link']}" target="_blank" style="color: #2e8b57; text-decoration: none;"><strong>{catalyst['title']}</strong></a></p>
                            <p style="margin: 2px 0 0 0; font-size: 10px; color: #666;">Source: {catalyst['source']}</p>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("No significant bull catalysts detected")
            with col2:
                st.markdown("### 🔴 Bear Catalysts")
                if bear_catalysts:
                    for catalyst in bear_catalysts:
                        icon = "📊" if catalyst['type'] == 'analyst' else "💰" if catalyst['type'] == 'earnings' else "🎯" if catalyst['type'] == 'price_target' else "📰"
                        st.markdown(f"""
                        <div style="background-color: rgba(220, 20, 60, 0.1); border-left: 3px solid #dc143c; padding: 8px; margin-bottom: 8px; border-radius: 4px;">
                            <p style="margin: 0;">{icon} <a href="{catalyst['link']}" target="_blank" style="color: #dc143c; text-decoration: none;"><strong>{catalyst['title']}</strong></a></p>
                            <p style="margin: 2px 0 0 0; font-size: 10px; color: #666;">Source: {catalyst['source']}</p>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("No significant bear catalysts detected")
            st.caption("💡 Click any catalyst link for more details.")
            st.markdown("---")
            
            # TRADINGVIEW CHART
            st.subheader("📉 TradingView Chart")
            chart_option = st.radio("Choose Chart Mode:", ["Embedded Chart (View Only)", "Launch Full TradingView (Save Drawings)"], horizontal=True)
            chart_theme = "dark" if theme == "Dark" else "light"
            if chart_option == "Launch Full TradingView (Save Drawings)":
                tv_link = tradingview_direct_link(ticker)
                st.markdown(f"""
                <div style="text-align: center; padding: 40px; background-color: #1e1e2e; border-radius: 10px; border: 1px solid #89b4fa;">
                    <h3>📈 Open TradingView for Full Analysis</h3>
                    <a href="{tv_link}" target="_blank"><button style="background-color: #89b4fa; color: #1e1e2e; padding: 12px 30px; font-size: 16px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">🚀 Launch TradingView for {ticker}</button></a>
                    <p style="font-size: 12px; margin-top: 20px;">Create a free TradingView account to save your drawings</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                timeframe_options = {"1 Minute": "1", "5 Minutes": "5", "15 Minutes": "15", "30 Minutes": "30", "1 Hour": "60", "4 Hours": "240", "Daily": "D", "Weekly": "W", "Monthly": "M"}
                selected_timeframe = st.selectbox("Select Timeframe:", list(timeframe_options.keys()))
                timeframe_value = timeframe_options[selected_timeframe]
                tradingview_full_chart(ticker, timeframe_value, chart_theme)
            st.markdown("---")
            
            # COMPANY INFORMATION
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("🏢 Asset Information")
                st.write(f"**Name:** {info.get('longName', 'N/A')}")
                if not is_index_ticker:
                    st.write(f"**Sector:** {info.get('sector', 'N/A')}")
                    st.write(f"**Industry:** {info.get('industry', 'N/A')}")
                st.write(f"**Country:** {info.get('country', 'N/A')}")
                st.write(f"**Asset Type:** {asset_type}")
                st.write(f"**Volume:** {format_volume(info.get('volume', 0))}")
                st.write(f"**Avg Volume:** {format_volume(info.get('averageVolume', 0))}")
                st.write(f"**Market Cap:** {format_large_number(info.get('marketCap', 0))}")
            with col2:
                st.subheader("📈 Key Metrics")
                if not is_index_ticker:
                    st.write(f"**P/E Ratio:** {info.get('trailingPE', 0):,.2f}" if info.get('trailingPE') else "N/A")
                    st.write(f"**Forward P/E:** {info.get('forwardPE', 0):,.2f}" if info.get('forwardPE') else "N/A")
                    st.write(f"**PEG Ratio:** {info.get('pegRatio', 0):,.2f}" if info.get('pegRatio') else "N/A")
                    st.write(f"**Price/Book:** {info.get('priceToBook', 0):,.2f}" if info.get('priceToBook') else "N/A")
                    st.write(f"**Price/Sales:** {info.get('priceToSalesTrailing12Months', 0):,.2f}" if info.get('priceToSalesTrailing12Months') else "N/A")
                    st.write(f"**Dividend Yield:** {format_percentage(dividend_yield*100) if dividend_yield > 0 else 'N/A'}")
                st.write(f"**Beta:** {info.get('beta', 'N/A')}")
            st.markdown("---")
            
            # FINANCIAL STATEMENTS
            if not is_index_ticker and not income_statement.empty:
                st.subheader("💰 Key Financials")
                
                # Income Statement Data
                if not income_statement.empty:
                    latest_income = income_statement.iloc[:, 0] if len(income_statement.columns) > 0 else None
                    if latest_income is not None:
                        total_revenue = latest_income.get('Total Revenue', info.get('totalRevenue', 0))
                        gross_profit = latest_income.get('Gross Profit', info.get('grossProfit', 0))
                        operating_income = latest_income.get('Operating Income', info.get('operatingIncome', 0))
                        net_income = latest_income.get('Net Income', info.get('netIncomeToCommon', 0))
                    else:
                        total_revenue = info.get('totalRevenue', 0)
                        gross_profit = info.get('grossProfit', 0)
                        operating_income = info.get('operatingIncome', 0)
                        net_income = info.get('netIncomeToCommon', 0)
                else:
                    total_revenue = info.get('totalRevenue', 0)
                    gross_profit = info.get('grossProfit', 0)
                    operating_income = info.get('operatingIncome', 0)
                    net_income = info.get('netIncomeToCommon', 0)
                
                # Balance Sheet Data
                if not balance_sheet.empty:
                    latest_balance = balance_sheet.iloc[:, 0] if len(balance_sheet.columns) > 0 else None
                    if latest_balance is not None:
                        total_assets = latest_balance.get('Total Assets', info.get('totalAssets', 0))
                        total_debt = latest_balance.get('Total Debt', info.get('totalDebt', 0))
                        total_equity = latest_balance.get('Total Equity Gross Minority Interest', info.get('totalShareholderEquity', 0))
                        current_assets = latest_balance.get('Current Assets', info.get('totalCurrentAssets', 0))
                        current_liabilities = latest_balance.get('Current Liabilities', info.get('totalCurrentLiabilities', 0))
                    else:
                        total_assets = info.get('totalAssets', 0)
                        total_debt = info.get('totalDebt', 0)
                        total_equity = info.get('totalShareholderEquity', 0)
                        current_assets = info.get('totalCurrentAssets', 0)
                        current_liabilities = info.get('totalCurrentLiabilities', 0)
                else:
                    total_assets = info.get('totalAssets', 0)
                    total_debt = info.get('totalDebt', 0)
                    total_equity = info.get('totalShareholderEquity', 0)
                    current_assets = info.get('totalCurrentAssets', 0)
                    current_liabilities = info.get('totalCurrentLiabilities', 0)
                
                # Cash Flow Data
                if not cashflow.empty:
                    latest_cashflow = cashflow.iloc[:, 0] if len(cashflow.columns) > 0 else None
                    if latest_cashflow is not None:
                        operating_cashflow = latest_cashflow.get('Operating Cash Flow', info.get('operatingCashflow', 0))
                        free_cashflow = latest_cashflow.get('Free Cash Flow', info.get('freeCashflow', 0))
                    else:
                        operating_cashflow = info.get('operatingCashflow', 0)
                        free_cashflow = info.get('freeCashflow', 0)
                else:
                    operating_cashflow = info.get('operatingCashflow', 0)
                    free_cashflow = info.get('freeCashflow', 0)
                
                # Calculate additional metrics
                current_ratio = current_assets / current_liabilities if current_liabilities > 0 else 0
                
                # Income Statement Row
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Revenue", format_large_number(total_revenue))
                with col2:
                    st.metric("Gross Profit", format_large_number(gross_profit))
                with col3:
                    st.metric("Operating Income", format_large_number(operating_income))
                with col4:
                    st.metric("Net Income", format_large_number(net_income))
                
                st.markdown("---")
                
                # Balance Sheet Row
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Assets", format_large_number(total_assets))
                with col2:
                    st.metric("Total Debt", format_large_number(total_debt))
                with col3:
                    st.metric("Total Equity", format_large_number(total_equity))
                with col4:
                    st.metric("Current Ratio", f"{current_ratio:.2f}")
                
                st.markdown("---")
                
                # Cash Flow Row
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Operating Cash Flow", format_large_number(operating_cashflow))
                with col2:
                    st.metric("Free Cash Flow", format_large_number(free_cashflow))
                
                st.markdown("---")
            
            # OPTIONS CALCULATOR
            if days > 0:
                st.subheader("🎯 Options Price Calculator (Black-Scholes)")
                
                implied_vol_strike = get_implied_volatility_for_strike(ticker, strike, expiration_date, option_type)
                if implied_vol_strike and implied_vol_strike > 0:
                    st.info(f"📊 Using Implied Volatility: {implied_vol_strike:.1f}% (from option chain for strike ${strike})")
                    vol_used = implied_vol_strike / 100
                else:
                    st.warning(f"📊 Using Volatility: {vol_to_use*100:.1f}% (implied volatility not available for this strike)")
                    vol_used = vol_to_use
                
                option_price, delta, gamma, theta, vega = calculate_option_price(
                    current_price, strike, days/365, risk_free_rate, vol_used, dividend_yield, option_type
                )
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**Current Price:** {format_currency(current_price)}")
                    st.write(f"**Strike Price:** {format_currency(strike)}")
                    st.write(f"**Expiration:** {expiration_date.strftime('%Y-%m-%d')} ({days} days)")
                with col2:
                    st.write(f"**Volatility Used:** {vol_used*100:.1f}%")
                    st.write(f"**Risk-Free Rate:** {risk_free_rate*100:.2f}%")
                    st.write(f"**Dividend Yield:** {format_percentage(dividend_yield*100)}")
                with col3:
                    st.write(f"**Option Type:** {option_type}")
                st.markdown("---")
                col1, col2, col3, col4, col5 = st.columns(5)
                with col1:
                    st.metric("Theoretical Price", format_currency(option_price))
                with col2:
                    st.metric("Delta", f"{delta:.4f}")
                with col3:
                    st.metric("Gamma", f"{gamma:.4f}")
                with col4:
                    st.metric("Theta (Daily)", f"{theta/365:.4f}")
                with col5:
                    st.metric("Vega (per 1%)", f"{vega:.4f}")
                
                # PROBABILITY CALCULATOR
                st.markdown("---")
                st.subheader("📊 Probability Calculator")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**Probability of Closing Above/Below**")
                    close_price = st.number_input("Price at Expiration ($):", value=current_price, step=1.0, key="close_target", format="%.2f")
                    close_direction = st.radio("Direction:", ["Above", "Below"], index=0, key="close_direction", horizontal=True)
                    
                    if close_price > 0 and days > 0 and vol_used > 0:
                        sigma = vol_used
                        T_years = days / 365
                        try:
                            if sigma * sqrt(T_years) == 0:
                                prob_close = 0.5
                            else:
                                d2 = (log(current_price / close_price) + (risk_free_rate - dividend_yield - 0.5 * sigma**2) * T_years) / (sigma * sqrt(T_years))
                                prob_close = norm.cdf(-d2) if close_direction == "Above" else norm.cdf(d2)
                            prob_close = max(0.0001, min(0.9999, prob_close))
                            st.metric(f"Probability to close {close_direction} ${close_price:,.2f}", f"{prob_close*100:.1f}%")
                        except:
                            st.error("Calculation error")
                    else:
                        st.info("Enter a valid price")
                
                with col2:
                    st.write("**Expected Move**")
                    expected_move = current_price * vol_used * sqrt(days/365)
                    st.metric("1 Standard Deviation Move (±)", format_currency(expected_move))
                    st.caption(f"68% probability stock stays within ±${expected_move:.2f}")
                    
                    st.markdown("---")
                    st.write("**Option ITM Probability**")
                    itm_option_type = st.radio("Option Type:", ["Call", "Put"], index=0 if option_type == "Call" else 1, key="itm_option_type", horizontal=True)
                    try:
                        sigma = vol_used
                        T_years = days / 365
                        d2 = (log(current_price / strike) + (risk_free_rate - dividend_yield - 0.5 * sigma**2) * T_years) / (sigma * sqrt(T_years))
                        prob_itm = norm.cdf(d2) if itm_option_type == "Call" else norm.cdf(-d2)
                        prob_itm = max(0.0001, min(0.9999, prob_itm))
                        st.metric(f"Probability {itm_option_type} is ITM", f"{prob_itm*100:.1f}%")
                    except:
                        st.error("Calculation error")
                
                # ANALYST FORECAST
                st.markdown("---")
                st.subheader("📈 Analyst Financial Forecast")
                with st.expander("📊 5-Year Financial Forecast & DCF Valuation", expanded=False):
                    st.write("**Assumptions**")
                    col1, col2 = st.columns(2)
                    with col1:
                        forecast_revenue_growth = st.number_input("Revenue Growth (% per year)", value=10.0, step=1.0, key="forecast_growth")
                        forecast_margin_expansion = st.number_input("Margin Expansion (% per year)", value=0.5, step=0.1, key="forecast_margin")
                    with col2:
                        forecast_wacc = st.number_input("WACC (%)", value=8.0, step=0.5, key="forecast_wacc") / 100
                        forecast_terminal_growth = st.number_input("Terminal Growth (%)", value=3.0, step=0.5, key="forecast_terminal") / 100
                    
                    if st.button("Run Forecast", key="run_forecast"):
                        current_revenue = info.get('totalRevenue', 0)
                        current_margin = info.get('profitMargins', 0) * 100 if info.get('profitMargins') else 0
                        
                        if current_revenue > 0:
                            projections = build_financial_forecast(current_revenue, current_margin, forecast_revenue_growth, forecast_margin_expansion, 5)
                            df_projections = pd.DataFrame(projections)
                            df_projections['Revenue'] = df_projections['Revenue'].apply(format_large_number)
                            df_projections['EBIT'] = df_projections['EBIT'].apply(format_large_number)
                            df_projections['FCF'] = df_projections['FCF'].apply(format_large_number)
                            df_projections['Margin %'] = df_projections['Margin %'].apply(lambda x: f"{x:.1f}%")
                            st.dataframe(df_projections, use_container_width=True, hide_index=True)
                            
                            enterprise_value = calculate_dcf(projections, forecast_wacc, forecast_terminal_growth)
                            net_debt = info.get('totalDebt', 0) - info.get('totalCash', 0)
                            equity_value = enterprise_value - net_debt
                            shares_outstanding = info.get('sharesOutstanding', 0)
                            
                            if shares_outstanding > 0:
                                intrinsic_value = equity_value / shares_outstanding
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Enterprise Value", format_large_number(enterprise_value))
                                with col2:
                                    st.metric("Intrinsic Value per Share", format_currency(intrinsic_value))
                                with col3:
                                    upside = ((intrinsic_value - current_price) / current_price * 100) if current_price > 0 else 0
                                    st.metric("Upside to Fair Value", f"{upside:+.1f}%")
                                
                                if intrinsic_value > current_price * 1.2:
                                    st.success(f"✅ Stock appears UNDERVALUED (Current: {format_currency(current_price)} vs Fair: {format_currency(intrinsic_value)})")
                                elif intrinsic_value < current_price * 0.8:
                                    st.error(f"⚠️ Stock appears OVERVALUED (Current: {format_currency(current_price)} vs Fair: {format_currency(intrinsic_value)})")
                                else:
                                    st.info(f"📊 Stock appears FAIRLY VALUED (Current: {format_currency(current_price)} vs Fair: {format_currency(intrinsic_value)})")
                            else:
                                st.warning("Shares outstanding data not available")
                        else:
                            st.warning("Revenue data not available for this ticker")
                
                # TRADE MANAGEMENT
                st.markdown("---")
                st.subheader("🎯 Trade Management")
                col1, col2 = st.columns(2)
                with col1:
                    profit_target_pct = st.number_input("Profit Target (%)", value=50.0, step=10.0, key="profit_target")
                    profit_target_price = option_price * (1 + profit_target_pct / 100)
                    st.metric("Profit Target Price", format_currency(profit_target_price))
                with col2:
                    stop_loss_pct = st.number_input("Stop Loss (%)", value=25.0, step=5.0, key="stop_loss")
                    stop_loss_price = option_price * (1 - stop_loss_pct / 100)
                    st.metric("Stop Loss Price", format_currency(stop_loss_price))
                
                # TRADING SIGNAL
                st.markdown("---")
                st.subheader("📊 Trading Signal & Recommendation")
                col1, col2 = st.columns(2)
                with col1:
                    market_price_input = st.number_input("Enter Actual Option Market Price ($):", value=None, step=0.05, format="%.2f", key="market_price_input")
                with col2:
                    if market_price_input is not None and market_price_input > 0 and option_price > 0:
                        price_diff = market_price_input - option_price
                        diff_percent = (price_diff / option_price * 100)
                        st.metric("Price Difference", format_currency(price_diff), delta=f"{diff_percent:+.1f}%")
                    else:
                        st.info("Enter market price to see difference")
                
                if market_price_input is not None and market_price_input > 0 and option_price > 0:
                    if diff_percent < -15:
                        recommendation = "🔥 STRONG BUY"
                        rec_color = "#a6e3a1"
                        rec_reason = f"Option is significantly undervalued ({abs(diff_percent):.0f}% below theoretical)"
                        action = "Consider buying - market is underpricing this opportunity"
                        risk_level = "HIGH" if diff_percent < -30 else "MODERATE"
                    elif diff_percent < -5:
                        recommendation = "✅ BUY"
                        rec_color = "#a6e3a1"
                        rec_reason = f"Option is undervalued ({abs(diff_percent):.0f}% below theoretical)"
                        action = "Good opportunity to buy - market is offering a discount"
                        risk_level = "LOW"
                    elif diff_percent > 15:
                        recommendation = "⚠️ STRONG SELL"
                        rec_color = "#f38ba8"
                        rec_reason = f"Option is significantly overvalued ({diff_percent:.0f}% above theoretical)"
                        action = "Consider selling or avoiding - market is overpricing"
                        risk_level = "HIGH"
                    elif diff_percent > 5:
                        recommendation = "❌ SELL / AVOID"
                        rec_color = "#f9e2af"
                        rec_reason = f"Option is overvalued ({diff_percent:.0f}% above theoretical)"
                        action = "Premium is expensive - wait for better entry"
                        risk_level = "MODERATE"
                    else:
                        recommendation = "⏸️ HOLD / MONITOR"
                        rec_color = "#f9e2af"
                        rec_reason = f"Option is fairly priced ({abs(diff_percent):.0f}% from theoretical)"
                        action = "Wait for better opportunity or enter small position"
                        risk_level = "LOW"
                    
                    st.markdown(f"""
                    <div style="background-color: #1e1e2e; border-radius: 10px; padding: 20px; border-left: 5px solid {rec_color};">
                        <h3 style="margin: 0; color: {rec_color};">{recommendation}</h3>
                        <p><strong>Reason:</strong> {rec_reason}</p>
                        <p><strong>Action:</strong> {action}</p>
                        <p><strong>Risk Level:</strong> {risk_level}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    st.markdown("---")
                    st.subheader("📈 Trade Analysis")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.write("**Price Comparison**")
                        st.write(f"📊 Theoretical: **{format_currency(option_price)}**")
                        st.write(f"💵 Market: **{format_currency(market_price_input)}**")
                        if market_price_input < option_price:
                            discount = option_price - market_price_input
                            st.write(f"💰 Discount: **{format_currency(discount)}** ({discount/option_price*100:.0f}%)")
                    with col2:
                        st.write("**Profit Scenarios**")
                        if market_price_input < option_price:
                            potential_gain = (option_price - market_price_input) / market_price_input * 100
                            st.metric("Upside to Fair Value", f"+{potential_gain:.0f}%")
                    with col3:
                        st.write("**Suggested Trade**")
                        if "BUY" in recommendation:
                            st.write("✅ **BUY** this option")
                            st.write(f"💰 Risk per contract: **{format_currency(market_price_input * 100)}**")
                        elif "SELL" in recommendation:
                            st.write("❌ **AVOID** buying")
                        else:
                            st.write("⏸️ **WAIT** for better price")
                    
                    # Position Size Calculator
                    with st.expander("💰 Position Size Calculator"):
                        account_size = st.number_input("Account Size ($):", value=10000, step=1000, key="account_size", format="%d")
                        risk_percent = st.number_input("Risk Per Trade (%):", value=2.0, step=0.5, key="risk_percent")
                        risk_percent_decimal = risk_percent / 100
                        max_risk = account_size * risk_percent_decimal
                        
                        st.metric("Max Risk per Trade", format_currency(max_risk))
                        st.caption(f"Based on {risk_percent:.1f}% of {format_currency(account_size)} account")
                        
                        st.markdown("---")
                        
                        if market_price_input and market_price_input > 0:
                            option_cost = market_price_input * 100
                            max_contracts = int(max_risk / option_cost) if option_cost > 0 else 0
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Option Cost per Contract", format_currency(option_cost))
                            with col2:
                                st.metric("Max Contracts (by risk)", max_contracts)
                            with col3:
                                total_risk = max_contracts * option_cost
                                st.metric("Total Risk", format_currency(total_risk))
                            
                            st.markdown("---")
                            
                            if max_contracts > 0:
                                suggested_contracts = min(max_contracts, 10)
                                if max_contracts > 10:
                                    st.info(f"📊 Based on risk management, you could buy up to **{max_contracts} contracts**, but consider starting with **{suggested_contracts} contracts** for better risk control.")
                                elif max_contracts >= 5:
                                    st.success(f"✅ Recommended position: **{max_contracts} contract(s)**")
                                else:
                                    st.warning(f"⚠️ Account size limits you to **{max_contracts} contract(s)**")
                            else:
                                st.warning(f"⚠️ Account too small for 1 contract. Minimum required: {format_currency(option_cost)}")
                        else:
                            st.info("📝 Enter the option market price above to calculate position size")
                else:
                    st.info("📝 Enter the actual option market price to get a trading recommendation")
            else:
                st.error("Please select a future expiration date")
        except Exception as e:
            st.error(f"Error fetching data for {ticker}: {e}")
    else:
        st.info("Enter a stock or index ticker in the sidebar to begin.")

# ============================================================
# TAB 2: WATCHLIST (Compact Display)
# ============================================================

with tab2:
    st.header("📈 My Watchlist")
    
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        new_watch_ticker = st.text_input(
            "Add new ticker to watchlist:", 
            key="new_watch_ticker",
            placeholder="e.g., AAPL, MSFT, NVDA"
        )
    with col2:
        add_button = st.button("➕ Add", key="add_watch", use_container_width=True)
    with col3:
        clear_button = st.button("🗑️ Clear All", key="clear_watch", use_container_width=True)
    
    if add_button:
        if new_watch_ticker:
            success, message = add_to_watchlist(new_watch_ticker.strip())
            if success:
                st.success(message)
            else:
                st.error(message)
            st.rerun()
    
    if clear_button:
        if st.session_state.watchlist:
            st.session_state.watchlist = []
            st.success("Watchlist cleared")
            st.rerun()
    
    st.markdown("---")
    
    if st.session_state.watchlist:
        st.caption(f"📊 {len(st.session_state.watchlist)} tickers in watchlist")
        
        # Compact table header
        col1, col2, col3, col4, col5, col6 = st.columns([1.2, 1.2, 1.8, 1.8, 1.2, 0.6])
        with col1:
            st.markdown("**Ticker**")
        with col2:
            st.markdown("**Price**")
        with col3:
            st.markdown("**Change**")
        with col4:
            st.markdown("**Market Cap**")
        with col5:
            st.markdown("**Earnings**")
        with col6:
            st.markdown("")
        
        st.markdown("---")
        
        watchlist_data = []
        invalid_tickers = []
        
        for w_ticker in st.session_state.watchlist:
            try:
                info = get_cached_stock_info(w_ticker)
                price = info.get('currentPrice', info.get('regularMarketPrice', 0))
                if price and price > 0:
                    change = price - info.get('previousClose', price)
                    change_pct = (change / info.get('previousClose', 1) * 100) if info.get('previousClose') else 0
                    market_cap = info.get('marketCap', 0)
                    
                    next_earnings = get_next_earnings(w_ticker)
                    days_until = 0
                    if next_earnings:
                        days_until = (next_earnings.date() - date.today()).days
                    
                    watchlist_data.append({
                        'Ticker': w_ticker,
                        'Price': format_currency(price),
                        'Change': f"{change:+.2f} ({change_pct:+.1f}%)",
                        'Change_Color': 'green' if change >= 0 else 'red',
                        'Market Cap': format_large_number(market_cap),
                        'Earnings': f"{days_until}d" if 0 < days_until <= 7 else "—",
                        'Earnings_Warning': 0 < days_until <= 7
                    })
                else:
                    invalid_tickers.append(w_ticker)
            except:
                invalid_tickers.append(w_ticker)
        
        # Remove invalid tickers
        for invalid in invalid_tickers:
            if invalid in st.session_state.watchlist:
                st.session_state.watchlist.remove(invalid)
                st.warning(f"Removed invalid ticker: {invalid}")
        
        # Display compact rows
        if watchlist_data:
            for item in watchlist_data:
                col1, col2, col3, col4, col5, col6 = st.columns([1.2, 1.2, 1.8, 1.8, 1.2, 0.6])
                with col1:
                    st.write(f"**{item['Ticker']}**")
                with col2:
                    st.write(item['Price'])
                with col3:
                    if item['Change_Color'] == 'green':
                        st.markdown(f"🟢 {item['Change']}")
                    else:
                        st.markdown(f"🔴 {item['Change']}")
                with col4:
                    st.write(item['Market Cap'])
                with col5:
                    if item['Earnings_Warning']:
                        st.warning(f"⚠️ {item['Earnings']}")
                    else:
                        st.write(item['Earnings'])
                with col6:
                    if st.button("✖️", key=f"remove_{item['Ticker']}", help=f"Remove {item['Ticker']}"):
                        remove_from_watchlist(item['Ticker'])
                        st.rerun()
                # No divider - just compact rows
    else:
        st.info("Your watchlist is empty. Add tickers above to track them.")
# ============================================================
# TAB 3: NEWS
# ============================================================

with tab3:
    st.header("📰 Latest Market News")
    news_ticker = st.text_input("Ticker for news:", value=ticker if ticker else "AAPL", key="news_ticker")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"Pulling news from: Yahoo Finance, Google News")
    with col2:
        if st.button("🔄 Refresh News", key="refresh_news"):
            st.cache_data.clear()
            st.rerun()
    
    with st.spinner(f"Fetching latest news for {news_ticker}... (this may take a few seconds)"):
        news = get_high_quality_news(news_ticker, max_articles=20)
    
    if news:
        st.success(f"Found {len(news)} recent news articles for {news_ticker}")
        
        for i, article in enumerate(news):
            title = article.get('title', 'No title')
            link = article.get('link', '#')
            publisher = article.get('publisher', 'Unknown')
            source = article.get('source', 'Unknown')
            importance = article.get('importance', 0)
            pub_date = article.get('date', None)
            
            if pub_date:
                try:
                    date_str = datetime.fromtimestamp(pub_date).strftime('%Y-%m-%d %H:%M')
                except:
                    date_str = "Recently"
            else:
                date_str = "Recently"
            
            bg_color = "#f8f9fa" if theme == "Light" else "#2d2d3a"
            link_color = "#1e1e2e" if theme == "Light" else "#cdd6f4"
            
            if importance >= 70:
                badge = "🔴 HIGH IMPORTANCE"
                badge_color = "#f38ba8"
            elif importance >= 50:
                badge = "🟡 MEDIUM IMPORTANCE"
                badge_color = "#f9e2af"
            else:
                badge = "🟢 LOW IMPORTANCE"
                badge_color = "#a6e3a1"
            
            st.markdown(f"""
            <div style="background-color: {bg_color}; border-radius: 8px; padding: 12px; margin-bottom: 10px; border-left: 4px solid {badge_color};">
                <p style="margin: 0; font-weight: bold;">
                    <a href="{link}" target="_blank" style="text-decoration: none; color: {link_color};">{title}</a>
                </p>
                <p style="margin: 5px 0 0 0; font-size: 12px; color: {'#666' if theme == 'Light' else '#aaa'};">
                    📰 {publisher} | 🕐 {date_str} | 📍 {source}
                </p>
                <p style="margin: 3px 0 0 0; font-size: 11px; color: {badge_color};">
                    {badge}
                </p>
            </div>
            """, unsafe_allow_html=True)
            st.caption(f"➡️ Click the title to read full article (opens in new tab)")
            st.divider()
    else:
        st.warning(f"No recent news found for {news_ticker}. Try:")
        st.markdown("""
        - A different ticker symbol
        - Checking the ticker is correct
        - Refreshing the page
        - Trying again later
        """)
        
        st.markdown(f"""
        ---
        **Alternative:** Search manually on Google News:
        [🔍 Search {news_ticker} on Google News](https://news.google.com/search?q={news_ticker}%20stock&hl=en-US&gl=US&ceid=US:en)
        """)

# ============================================================
# TAB 4: HISTORICAL DATA
# ============================================================

with tab4:
    st.header("📉 Historical Data")
    
    if ticker:
        try:
            hist = get_cached_stock_history(ticker, '2y')
            
            if not hist.empty:
                st.subheader("Price History (2 Years)")
                chart_data = pd.DataFrame({
                    'Date': hist.index,
                    'Close': hist['Close']
                })
                st.line_chart(chart_data.set_index('Date')['Close'], height=400)
                
                st.subheader("Volume History")
                st.bar_chart(chart_data.set_index('Date')['Volume'], height=200)
                
                st.markdown("---")
            
            st.subheader("📊 Earnings History")
            earnings_history = get_earnings_history(ticker)
            
            if earnings_history:
                earnings_data = []
                for earnings in earnings_history[:8]:
                    date_str = earnings['date'].strftime('%Y-%m-%d') if isinstance(earnings['date'], (datetime, pd.Timestamp)) else str(earnings['date'])
                    
                    if earnings.get('surprise_pct') is not None:
                        earnings_data.append({
                            'Date': date_str,
                            'Surprise %': f"{earnings['surprise_pct']:+.1f}%"
                        })
                    else:
                        earnings_data.append({
                            'Date': date_str,
                            'Surprise %': 'N/A'
                        })
                
                if earnings_data:
                    df_earnings = pd.DataFrame(earnings_data)
                    st.dataframe(df_earnings, use_container_width=True, hide_index=True)
                else:
                    st.info("Detailed earnings data not available")
            else:
                st.info("Historical earnings data not available")
            
            st.markdown("---")
            
            st.subheader("💰 Financial Trends")
            
            income_statement = get_cached_financials(ticker)
            if income_statement is not None and not income_statement.empty:
                if 'Total Revenue' in income_statement.index:
                    revenue = income_statement.loc['Total Revenue']
                    if not revenue.empty:
                        st.write("**Revenue Trend**")
                        revenue_data = pd.DataFrame({
                            'Date': revenue.index,
                            'Revenue': revenue.values / 1e9
                        })
                        st.bar_chart(revenue_data.set_index('Date')['Revenue'], height=300)
                
                if 'Net Income' in income_statement.index:
                    net_income = income_statement.loc['Net Income']
                    if not net_income.empty:
                        st.write("**Net Income Trend**")
                        income_data = pd.DataFrame({
                            'Date': net_income.index,
                            'Net Income': net_income.values / 1e9
                        })
                        st.bar_chart(income_data.set_index('Date')['Net Income'], height=300)
            
            balance_sheet = get_cached_balance_sheet(ticker)
            if balance_sheet is not None and not balance_sheet.empty:
                st.subheader("📋 Balance Sheet Highlights")
                
                highlights = []
                if 'Total Assets' in balance_sheet.index:
                    assets = balance_sheet.loc['Total Assets'].iloc[0] if not balance_sheet.loc['Total Assets'].empty else 0
                    highlights.append(("Total Assets", format_large_number(assets)))
                
                if 'Total Debt' in balance_sheet.index:
                    debt = balance_sheet.loc['Total Debt'].iloc[0] if not balance_sheet.loc['Total Debt'].empty else 0
                    highlights.append(("Total Debt", format_large_number(debt)))
                
                if 'Total Equity' in balance_sheet.index:
                    equity = balance_sheet.loc['Total Equity'].iloc[0] if not balance_sheet.loc['Total Equity'].empty else 0
                    highlights.append(("Total Equity", format_large_number(equity)))
                
                if highlights:
                    col1, col2 = st.columns(2)
                    for i, (label, value) in enumerate(highlights):
                        if i % 2 == 0:
                            with col1:
                                st.metric(label, value)
                        else:
                            with col2:
                                st.metric(label, value)
            
        except Exception as e:
            st.error(f"Error loading historical data: {e}")
    else:
        st.info("Enter a stock ticker in the sidebar to view historical data")

# ============================================================
# AUTO-REFRESH
# ============================================================

if auto_refresh and interval_seconds > 0:
    time.sleep(interval_seconds)
    st.rerun()
