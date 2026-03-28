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
import functools
import random

st.set_page_config(page_title="Stock Analysis Dashboard", layout="wide")

# ============================================================
# RATE LIMIT PROTECTION
# ============================================================

# Global rate limit state
rate_limit_active = False
rate_limit_until = 0
request_count = 0
request_window_start = time.time()

def check_rate_limit():
    """Check if currently rate limited"""
    global rate_limit_active, rate_limit_until
    if rate_limit_active and time.time() < rate_limit_until:
        return True
    rate_limit_active = False
    return False

def set_rate_limit(seconds=300):
    """Set rate limit"""
    global rate_limit_active, rate_limit_until
    rate_limit_active = True
    rate_limit_until = time.time() + seconds

def track_request():
    """Track request count for warning"""
    global request_count, request_window_start
    request_count += 1
    if time.time() - request_window_start > 60:
        request_count = 0
        request_window_start = time.time()

def safe_api_call(func, *args, **kwargs):
    """Make a rate-limited API call"""
    if check_rate_limit():
        return None
    
    track_request()
    
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if "Too Many Requests" in str(e) or "Rate limited" in str(e):
            set_rate_limit(300)
        return None

# ============================================================
# CACHING DECORATORS
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_stock_info(ticker):
    """Get stock info with 5-minute cache"""
    try:
        stock = yf.Ticker(ticker)
        return stock.info
    except:
        return {}

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_stock_history(ticker, period='1y'):
    """Get stock history with 5-minute cache"""
    try:
        stock = yf.Ticker(ticker)
        return stock.history(period=period)
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_balance_sheet(ticker):
    """Get balance sheet with 5-minute cache"""
    try:
        stock = yf.Ticker(ticker)
        return stock.balance_sheet
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_financials(ticker):
    """Get financials with 5-minute cache"""
    try:
        stock = yf.Ticker(ticker)
        return stock.financials
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_cashflow(ticker):
    """Get cashflow with 5-minute cache"""
    try:
        stock = yf.Ticker(ticker)
        return stock.cashflow
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_options(ticker):
    """Get options expirations with 5-minute cache"""
    try:
        stock = yf.Ticker(ticker)
        return stock.options
    except:
        return []

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_option_chain(ticker, expiration):
    """Get option chain with 5-minute cache"""
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
# SESSION STATE INITIALIZATION
# ============================================================

if 'watchlist' not in st.session_state:
    st.session_state.watchlist = ['AAPL', 'MSFT', 'SPY', 'QQQ']

if 'positions' not in st.session_state:
    st.session_state.positions = {}

if 'paper_balance' not in st.session_state:
    st.session_state.paper_balance = 10000.0

if 'paper_positions' not in st.session_state:
    st.session_state.paper_positions = {}

if 'trade_history' not in st.session_state:
    st.session_state.trade_history = []

if 'price_alerts' not in st.session_state:
    st.session_state.price_alerts = {}

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
    if value is None or value == 0:
        return "$0"
    if value >= 1_000_000_000:
        return f"${value/1_000_000_000:,.2f}B"
    elif value >= 1_000_000:
        return f"${value/1_000_000:,.2f}M"
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
# IMPROVED NEWS FUNCTION
# ============================================================

def get_news(ticker, max_articles=20):
    """Fetch news from multiple sources"""
    news_items = []
    
    # SOURCE 1: Yahoo Finance API
    try:
        stock = yf.Ticker(ticker)
        yf_news = stock.news
        if yf_news:
            for article in yf_news[:max_articles]:
                importance = 50
                title = article.get('title', '')
                publisher = article.get('publisher', '')
                link = article.get('link', '')
                
                if link and not link.startswith('http'):
                    link = f"https://finance.yahoo.com{link}"
                
                if 'bloomberg' in publisher.lower():
                    importance += 30
                elif 'reuters' in publisher.lower():
                    importance += 25
                elif 'wsj' in publisher.lower() or 'wall street' in publisher.lower():
                    importance += 25
                elif 'cnbc' in publisher.lower():
                    importance += 20
                
                important_keywords = ['earnings', 'acquisition', 'merger', 'ceo', 'lawsuit', 'fda', 'approval', 'bankruptcy', 'dividend', 'stock split', 'crash', 'rally', 'upgrade', 'downgrade']
                for keyword in important_keywords:
                    if keyword in title.lower():
                        importance += 15
                
                news_items.append({
                    'title': title,
                    'link': link,
                    'publisher': publisher,
                    'date': article.get('providerPublishTime', None),
                    'source': 'Yahoo Finance',
                    'importance': importance
                })
    except:
        pass
    
    # SOURCE 2: Google News RSS
    try:
        import feedparser
        search_term = ticker
        google_url = f"https://news.google.com/rss/search?q={search_term}+stock&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(google_url)
        
        for entry in feed.entries[:max_articles]:
            publisher = entry.get('source', {}).get('title', 'Google News') if hasattr(entry, 'source') else 'Google News'
            pub_date = None
            if hasattr(entry, 'published_parsed'):
                pub_date = time.mktime(entry.published_parsed)
            
            title = entry.title
            link = entry.link
            importance = 40
            
            if 'bloomberg' in publisher.lower():
                importance += 30
            elif 'reuters' in publisher.lower():
                importance += 25
            elif 'wsj' in publisher.lower() or 'wall street' in publisher.lower():
                importance += 25
            
            news_items.append({
                'title': title,
                'link': link,
                'publisher': publisher,
                'date': pub_date,
                'source': 'Google News',
                'importance': importance
            })
    except:
        pass
    
    # SOURCE 3: Yahoo Finance RSS
    try:
        import feedparser
        yahoo_rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        feed = feedparser.parse(yahoo_rss_url)
        
        for entry in feed.entries[:max_articles]:
            title = entry.title
            link = entry.link
            importance = 30
            
            important_keywords = ['earnings', 'acquisition', 'merger', 'ceo', 'lawsuit']
            for keyword in important_keywords:
                if keyword in title.lower():
                    importance += 15
            
            news_items.append({
                'title': title,
                'link': link,
                'publisher': 'Yahoo Finance',
                'date': None,
                'source': 'Yahoo Finance RSS',
                'importance': importance
            })
    except:
        pass
    
    # Remove duplicates
    seen_titles = set()
    unique_news = []
    for item in news_items:
        clean_title = item['title'].lower().strip()
        if clean_title not in seen_titles and len(clean_title) > 10:
            seen_titles.add(clean_title)
            unique_news.append(item)
    
    # Sort by importance and date
    unique_news.sort(key=lambda x: (x['importance'], x['date'] if x['date'] else 0), reverse=True)
    
    return unique_news[:max_articles]

# ============================================================
# EARNINGS FUNCTIONS
# ============================================================

def get_next_earnings(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = get_cached_stock_info(ticker)
        earnings_date = info.get('earningsDate', None)
        if earnings_date:
            if isinstance(earnings_date, list):
                return earnings_date[0]
            return earnings_date
        else:
            today = date.today()
            month = today.month
            if month <= 1:
                next_month = 4
                year = today.year
            elif month <= 4:
                next_month = 7
                year = today.year
            elif month <= 7:
                next_month = 10
                year = today.year
            elif month <= 10:
                next_month = 1
                year = today.year + 1
            else:
                next_month = 4
                year = today.year + 1
            estimated_date = date(year, next_month, 15)
            return datetime.combine(estimated_date, datetime.min.time())
    except:
        return None

def get_earnings_surprises(ticker):
    try:
        stock = yf.Ticker(ticker)
        earnings = stock.earnings
        if not earnings.empty:
            return earnings.tail(4)
        return None
    except:
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
    try:
        info = get_cached_stock_info(ticker)
        dividend_yield = info.get('dividendYield', 0)
        if dividend_yield:
            return dividend_yield
        dividend_rate = info.get('dividendRate', 0)
        current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
        if dividend_rate and current_price:
            return dividend_rate / current_price
        return 0
    except:
        return 0

# ============================================================
# FORECASTING FUNCTIONS
# ============================================================

def build_financial_forecast(current_revenue, current_margin, revenue_growth, margin_expansion, years=5):
    """Build 5-year financial forecast"""
    projections = []
    revenue = current_revenue
    margin = current_margin
    
    for year in range(1, years + 1):
        revenue *= (1 + revenue_growth / 100)
        margin += margin_expansion
        ebit = revenue * (margin / 100)
        fcf = ebit * 0.7  # Simplified: 70% of EBIT to FCF
        
        projections.append({
            'Year': year,
            'Revenue': revenue,
            'Margin %': margin,
            'EBIT': ebit,
            'FCF': fcf
        })
    
    return projections

def calculate_dcf(projections, wacc=0.08, terminal_growth=0.03):
    """Calculate DCF valuation"""
    present_value = 0
    for i, data in enumerate(projections, 1):
        present_value += data['FCF'] / (1 + wacc) ** i
    
    terminal_fcf = projections[-1]['FCF']
    terminal_value = terminal_fcf * (1 + terminal_growth) / (wacc - terminal_growth)
    present_terminal = terminal_value / (1 + wacc) ** len(projections)
    
    return present_value + present_terminal

# ============================================================
# PORTFOLIO MANAGEMENT FUNCTIONS
# ============================================================

def add_position(ticker, strike, option_type, entry_price, quantity, expiration, is_paper=False):
    position_id = f"{ticker}_{strike}_{option_type}_{expiration}_{get_local_time().timestamp()}"
    position = {
        'id': position_id,
        'ticker': ticker,
        'strike': strike,
        'type': option_type,
        'entry_price': entry_price,
        'quantity': quantity,
        'expiration': expiration,
        'entry_date': get_local_time().strftime('%Y-%m-%d %H:%M'),
        'status': 'open',
        'pnl': 0
    }
    if is_paper:
        st.session_state.paper_positions[position_id] = position
        total_cost = entry_price * quantity * 100
        st.session_state.paper_balance -= total_cost
    else:
        st.session_state.positions[position_id] = position

def close_position(position_id, exit_price, is_paper=False):
    if is_paper:
        position = st.session_state.paper_positions.get(position_id)
        if position:
            total_return = (exit_price - position['entry_price']) * position['quantity'] * 100
            st.session_state.paper_balance += position['entry_price'] * position['quantity'] * 100 + total_return
            st.session_state.trade_history.append({
                'date': get_local_time().strftime('%Y-%m-%d %H:%M'),
                'ticker': position['ticker'],
                'type': position['type'],
                'strike': position['strike'],
                'entry': position['entry_price'],
                'exit': exit_price,
                'quantity': position['quantity'],
                'pnl': total_return,
                'return_pct': (exit_price - position['entry_price']) / position['entry_price'] * 100
            })
            del st.session_state.paper_positions[position_id]
    else:
        position = st.session_state.positions.get(position_id)
        if position:
            del st.session_state.positions[position_id]

# ============================================================
# WATCHLIST FUNCTIONS
# ============================================================

def add_to_watchlist(ticker):
    if ticker not in st.session_state.watchlist:
        st.session_state.watchlist.append(ticker)

def remove_from_watchlist(ticker):
    if ticker in st.session_state.watchlist:
        st.session_state.watchlist.remove(ticker)

def check_price_alerts(ticker, current_price):
    alerts = st.session_state.price_alerts.get(ticker, [])
    triggered = []
    for alert in alerts:
        if alert['type'] == 'above' and current_price >= alert['price']:
            triggered.append(alert)
        elif alert['type'] == 'below' and current_price <= alert['price']:
            triggered.append(alert)
    st.session_state.price_alerts[ticker] = [a for a in alerts if a not in triggered]
    return triggered

def add_price_alert(ticker, price, alert_type):
    if ticker not in st.session_state.price_alerts:
        st.session_state.price_alerts[ticker] = []
    st.session_state.price_alerts[ticker].append({
        'price': price,
        'type': alert_type,
        'created': get_local_time().strftime('%Y-%m-%d %H:%M')
    })

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
# SIDEBAR WITH THEME (CLICK-ONLY DROPDOWNS)
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
        .stApp { background-color: #ffffff; }
        .stMarkdown, .stMarkdown p, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4,
        .stText, .stTextInput, .stTextArea, .stNumberInput, .stSelectbox,
        .stMetric, .stMetric label, .stMetric p,
        .stDataFrame, .stDataFrame div,
        .stExpander, .stExpander summary,
        .stButton button, .stButton button p,
        .stRadio label, .stCheckbox label,
        .stCaption, .stCaption p,
        .stInfo, .stWarning, .stError, .stSuccess {
            color: #000000 !important;
        }
        .stSidebar, .stSidebar .stMarkdown { background-color: #f5f5f5; }
        input, .stTextInput input, .stNumberInput input, .stSelectbox select {
            background-color: #ffffff !important;
            color: #000000 !important;
            border: 1px solid #cccccc !important;
        }
        .stMetric { background-color: #f8f9fa; border-radius: 10px; padding: 10px; border: 1px solid #e9ecef; }
        div[data-testid="stMetricValue"] { color: #000000 !important; font-weight: bold; }
        div[data-testid="stMetricLabel"] { color: #555555 !important; }
        h1, h2, h3, h4, h5, h6 { color: #000000 !important; }
        .stDataFrame, .dataframe, table, th, td { color: #000000 !important; background-color: #ffffff !important; }
        .stButton button { background-color: #e9ecef !important; color: #000000 !important; border: 1px solid #cccccc !important; }
        </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <style>
        .stApp { background-color: #1e1e2e; }
        .stMarkdown, .stMarkdown p, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4,
        .stText, .stTextInput, .stTextArea, .stNumberInput, .stSelectbox,
        .stMetric, .stMetric label, .stMetric p,
        .stDataFrame, .stDataFrame div,
        .stExpander, .stExpander summary,
        .stButton button, .stButton button p,
        .stRadio label, .stCheckbox label,
        .stCaption, .stCaption p,
        .stInfo, .stWarning, .stError, .stSuccess {
            color: #cdd6f4 !important;
        }
        .stSidebar, .stSidebar .stMarkdown { background-color: #181825; }
        input, .stTextInput input, .stNumberInput input, .stSelectbox select {
            background-color: #313244 !important;
            color: #cdd6f4 !important;
            border: 1px solid #45475a !important;
        }
        .stMetric { background-color: #313244; border-radius: 10px; padding: 10px; border: 1px solid #45475a; }
        div[data-testid="stMetricValue"] { color: #a6e3a1 !important; font-weight: bold; }
        div[data-testid="stMetricLabel"] { color: #cdd6f4 !important; }
        h1, h2, h3, h4, h5, h6 { color: #cdd6f4 !important; }
        .stDataFrame, .dataframe, table, th, td { color: #cdd6f4 !important; background-color: #313244 !important; }
        .stButton button { background-color: #45475a !important; color: #cdd6f4 !important; border: none !important; }
        .stButton button:hover { background-color: #585b70 !important; }
        </style>
        """, unsafe_allow_html=True)

risk_free_rate = get_risk_free_rate()

with st.sidebar:
    # Rate limit warning
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
# MAIN APP TABS
# ============================================================

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Analysis", "📈 Watchlist", "💰 Portfolio", "📝 Paper Trading", "⏰ Alerts", "📰 News"])

# ============================================================
# TAB 1: ANALYSIS (with Forecast)
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
            
            # Check price alerts
            triggered_alerts = check_price_alerts(ticker, current_price)
            for alert in triggered_alerts:
                st.warning(f"⚠️ **ALERT:** {ticker} is {alert['type']} ${alert['price']:.2f}!")
            
            # Check earnings alerts
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
            
            # Calculate volatility
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
                earnings_surprises = get_earnings_surprises(ticker)
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
                    if earnings_surprises is not None and not earnings_surprises.empty:
                        st.write("**Recent Earnings Surprises:**")
                        for idx, row in earnings_surprises.iterrows():
                            surprise_pct = row.get('Earnings Surprise', 0) * 100 if 'Earnings Surprise' in row else 0
                            color = "🟢" if surprise_pct > 0 else "🔴" if surprise_pct < 0 else "⚪"
                            st.write(f"{color} {idx.strftime('%Y-%m-%d')}: {surprise_pct:+.1f}%")
                    else:
                        st.info("Historical earnings data not available")
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
                st.subheader("💰 Key Financials (in Millions)")
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
                working_capital = current_assets - current_liabilities
                current_ratio = current_assets / current_liabilities if current_liabilities > 0 else 0
                financials = {
                    "Total Revenue": total_revenue / 1e6 if total_revenue else 0,
                    "Gross Profit": gross_profit / 1e6 if gross_profit else 0,
                    "Operating Income": operating_income / 1e6 if operating_income else 0,
                    "Net Income": net_income / 1e6 if net_income else 0,
                    "Operating Cash Flow": operating_cashflow / 1e6 if operating_cashflow else 0,
                    "Free Cash Flow": free_cashflow / 1e6 if free_cashflow else 0,
                    "Total Assets": total_assets / 1e6 if total_assets else 0,
                    "Total Debt": total_debt / 1e6 if total_debt else 0,
                    "Total Equity": total_equity / 1e6 if total_equity else 0,
                    "Current Assets": current_assets / 1e6 if current_assets else 0,
                    "Current Liabilities": current_liabilities / 1e6 if current_liabilities else 0,
                    "Working Capital": working_capital / 1e6 if working_capital else 0,
                    "Current Ratio": current_ratio,
                }
                df = pd.DataFrame(list(financials.items()), columns=["Metric", "Value ($M)"])
                df["Value ($M)"] = df["Value ($M)"].apply(lambda x: f"${x:,.2f}M" if x > 0 else "N/A")
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.markdown("---")
            
            # OPTIONS CALCULATOR
            if days > 0:
                st.subheader("🎯 Options Price Calculator (Black-Scholes)")
                
                # Try to get implied volatility for this specific strike
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
                
                # LEFT COLUMN: CLOSING PROBABILITY
                with col1:
                    st.write("**Probability of Closing Above/Below**")
                    st.caption("The probability that the stock closes above or below a price at expiration")
                    
                    close_price = st.number_input("Price at Expiration ($):", value=current_price, step=1.0, key="close_target", format="%.2f")
                    
                    close_direction = st.radio(
                        "Direction:",
                        ["Above", "Below"],
                        index=0,
                        key="close_direction",
                        horizontal=True
                    )
                    
                    if close_price > 0 and days > 0 and vol_used > 0:
                        sigma = vol_used
                        T_years = days / 365
                        
                        try:
                            if sigma * sqrt(T_years) == 0:
                                prob_close = 0.5
                            else:
                                d2 = (log(current_price / close_price) + (risk_free_rate - dividend_yield - 0.5 * sigma**2) * T_years) / (sigma * sqrt(T_years))
                                
                                if close_direction == "Above":
                                    prob_close = norm.cdf(-d2)
                                else:
                                    prob_close = norm.cdf(d2)
                            
                            prob_close = max(0.0001, min(0.9999, prob_close))
                            st.metric(f"Probability to close {close_direction} ${close_price:,.2f}", f"{prob_close*100:.1f}%")
                            st.caption(f"Stock finishes {close_direction} ${close_price:,.2f} at expiration")
                        except:
                            st.error("Calculation error - try a different price")
                    else:
                        st.info("Enter a valid price")
                
                # RIGHT COLUMN: EXPECTED MOVE & ITM
                with col2:
                    st.write("**Expected Move**")
                    expected_move = current_price * vol_used * sqrt(days/365)
                    st.metric("1 Standard Deviation Move (±)", format_currency(expected_move))
                    st.caption(f"68% probability stock stays within ±${expected_move:.2f} at expiration")
                    
                    st.markdown("---")
                    st.write("**Option ITM Probability**")
                    
                    itm_option_type = st.radio(
                        "Option Type:",
                        ["Call", "Put"],
                        index=0 if option_type == "Call" else 1,
                        key="itm_option_type",
                        horizontal=True
                    )
                    
                    try:
                        sigma = vol_used
                        T_years = days / 365
                        
                        if sigma * sqrt(T_years) == 0:
                            prob_itm = 0.5
                        else:
                            d2 = (log(current_price / strike) + (risk_free_rate - dividend_yield - 0.5 * sigma**2) * T_years) / (sigma * sqrt(T_years))
                            
                            if itm_option_type == "Call":
                                prob_itm = norm.cdf(d2)
                            else:
                                prob_itm = norm.cdf(-d2)
                        
                        prob_itm = max(0.0001, min(0.9999, prob_itm))
                        st.metric(f"Probability {itm_option_type} is ITM", f"{prob_itm*100:.1f}%")
                        st.caption(f"Stock must close { 'above' if itm_option_type == 'Call' else 'below' } ${strike:,.2f} at expiration")
                    except:
                        st.error("ITM probability calculation error")
                
                # ============================================================
                # ANALYST FORECAST SECTION
                # ============================================================
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
                        # Get current financials
                        current_revenue = info.get('totalRevenue', 0)
                        current_margin = info.get('profitMargins', 0) * 100 if info.get('profitMargins') else 0
                        
                        if current_revenue > 0:
                            # Build projections
                            projections = build_financial_forecast(
                                current_revenue, current_margin,
                                forecast_revenue_growth, forecast_margin_expansion, years=5
                            )
                            
                            # Display projections table
                            df_projections = pd.DataFrame(projections)
                            df_projections['Revenue'] = df_projections['Revenue'].apply(format_large_number)
                            df_projections['EBIT'] = df_projections['EBIT'].apply(format_large_number)
                            df_projections['FCF'] = df_projections['FCF'].apply(format_large_number)
                            df_projections['Margin %'] = df_projections['Margin %'].apply(lambda x: f"{x:.1f}%")
                            
                            st.write("**5-Year Projections**")
                            st.dataframe(df_projections, use_container_width=True, hide_index=True)
                            
                            # DCF Valuation
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
                    
                    # Add to Portfolio buttons
                    col1, col2 = st.columns(2)
                    with col1:
                        quantity = st.number_input("Quantity (contracts):", value=1, min_value=1, step=1, key="trade_quantity")
                        if st.button("📝 Add to Real Portfolio", key="add_real"):
                            add_position(ticker, strike, option_type, option_price, quantity, expiration_date.strftime('%Y-%m-%d'), is_paper=False)
                            st.success(f"Added {quantity} contract(s) to Real Portfolio")
                    with col2:
                        if st.button("🎮 Add to Paper Trading", key="add_paper"):
                            add_position(ticker, strike, option_type, option_price, quantity, expiration_date.strftime('%Y-%m-%d'), is_paper=True)
                            st.success(f"Added {quantity} contract(s) to Paper Trading")
                    
                    # Position Size Calculator
                    with st.expander("💰 Position Size Calculator"):
                        account_size = st.number_input("Account Size ($):", value=10000, step=1000, key="account_size", format="%d")
                        risk_percent = st.number_input("Risk Per Trade (%):", value=2.0, step=0.5, key="risk_percent")
                        max_risk = account_size * (risk_percent / 100)
                        st.metric("Max Risk per Trade", format_currency(max_risk))
                        if market_price_input and market_price_input > 0:
                            contracts = int(max_risk / (market_price_input * 100))
                            if contracts > 0:
                                st.success(f"✅ Recommended: Buy **{contracts} contract(s)**")
                            else:
                                st.warning(f"⚠️ Account too small for 1 contract")
                else:
                    st.info("📝 Enter the actual option market price to get a trading recommendation")
            else:
                st.error("Please select a future expiration date")
        except Exception as e:
            st.error(f"Error fetching data for {ticker}: {e}")
    else:
        st.info("Enter a stock or index ticker in the sidebar to begin.")

# ============================================================
# TAB 2: WATCHLIST
# ============================================================

with tab2:
    st.header("📈 My Watchlist")
    col1, col2 = st.columns([3, 1])
    with col1:
        new_watch_ticker = st.text_input("Add new ticker to watchlist:", key="new_watch_ticker")
    with col2:
        if st.button("➕ Add", key="add_watch"):
            if new_watch_ticker:
                add_to_watchlist(new_watch_ticker.upper())
                st.rerun()
    if st.session_state.watchlist:
        for w_ticker in st.session_state.watchlist:
            try:
                stock = yf.Ticker(w_ticker)
                info = get_cached_stock_info(w_ticker)
                price = info.get('currentPrice', info.get('regularMarketPrice', 0))
                change = price - info.get('previousClose', price)
                change_pct = (change / info.get('previousClose', 1) * 100) if info.get('previousClose') else 0
                earnings = get_next_earnings(w_ticker)
                days_until = 0
                if earnings:
                    days_until = (earnings.date() - date.today()).days
                col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])
                with col1:
                    st.write(f"**{w_ticker}**")
                with col2:
                    st.write(format_currency(price))
                with col3:
                    st.write(f"{change:+.2f} ({change_pct:+.1f}%)")
                with col4:
                    if 0 < days_until <= 7:
                        st.warning(f"⚠️ Earnings in {days_until}d")
                    else:
                        st.write("-")
                with col5:
                    if st.button("❌ Remove", key=f"remove_{w_ticker}"):
                        remove_from_watchlist(w_ticker)
                        st.rerun()
                st.divider()
            except:
                st.write(f"**{w_ticker}** - Error loading data")
    else:
        st.info("Your watchlist is empty. Add tickers above to track them.")

# ============================================================
# TAB 3: REAL PORTFOLIO
# ============================================================

with tab3:
    st.header("💰 Real Portfolio")
    if st.session_state.positions:
        total_cost = 0
        for pos in st.session_state.positions.values():
            total_cost += pos['entry_price'] * pos['quantity'] * 100
        st.metric("Total Cost Basis", format_currency(total_cost))
        st.markdown("---")
        for pos_id, pos in st.session_state.positions.items():
            with st.expander(f"{pos['ticker']} {pos['strike']} {pos['type']} - Entry: ${pos['entry_price']:.2f}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Quantity:** {pos['quantity']} contracts")
                    st.write(f"**Cost:** {format_currency(pos['entry_price'] * pos['quantity'] * 100)}")
                    st.write(f"**Entry Date:** {pos['entry_date']}")
                with col2:
                    st.write(f"**Expiration:** {pos['expiration']}")
                    exit_price = st.number_input(f"Exit Price ($):", value=0.0, step=0.05, key=f"exit_{pos_id}")
                    if st.button(f"Close Position", key=f"close_{pos_id}"):
                        if exit_price > 0:
                            close_position(pos_id, exit_price, is_paper=False)
                            st.success(f"Position closed at ${exit_price:.2f}")
                            st.rerun()
    else:
        st.info("No positions in your real portfolio. Add positions from the Analysis tab.")

# ============================================================
# TAB 4: PAPER TRADING
# ============================================================

with tab4:
    st.header("🎮 Paper Trading Account")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Account Balance", format_currency(st.session_state.paper_balance))
    with col2:
        total_paper_value = 0
        for pos in st.session_state.paper_positions.values():
            total_paper_value += pos['entry_price'] * pos['quantity'] * 100
        st.metric("Positions Value", format_currency(total_paper_value))
    with col3:
        st.metric("Total Account Value", format_currency(st.session_state.paper_balance + total_paper_value))
    st.markdown("---")
    if st.button("💰 Reset Paper Account ($10,000)"):
        st.session_state.paper_balance = 10000.0
        st.session_state.paper_positions = {}
        st.success("Paper account reset!")
        st.rerun()
    st.markdown("---")
    st.subheader("📊 Paper Trading Positions")
    if st.session_state.paper_positions:
        for pos_id, pos in st.session_state.paper_positions.items():
            with st.expander(f"{pos['ticker']} {pos['strike']} {pos['type']} - Entry: ${pos['entry_price']:.2f}"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**Quantity:** {pos['quantity']} contracts")
                    st.write(f"**Cost:** {format_currency(pos['entry_price'] * pos['quantity'] * 100)}")
                    st.write(f"**Entry Date:** {pos['entry_date']}")
                with col2:
                    st.write(f"**Expiration:** {pos['expiration']}")
                    exit_price = st.number_input(f"Exit Price ($):", value=0.0, step=0.05, key=f"paper_exit_{pos_id}")
                with col3:
                    if st.button(f"Close Paper Position", key=f"paper_close_{pos_id}"):
                        if exit_price > 0:
                            close_position(pos_id, exit_price, is_paper=True)
                            st.success(f"Paper position closed at ${exit_price:.2f}")
                            st.rerun()
    else:
        st.info("No paper trading positions. Add positions from the Analysis tab.")
    st.markdown("---")
    st.subheader("📜 Trade History")
    if st.session_state.trade_history:
        history_df = pd.DataFrame(st.session_state.trade_history)
        st.dataframe(history_df, use_container_width=True)
    else:
        st.info("No completed trades yet.")

# ============================================================
# TAB 5: ALERTS
# ============================================================

with tab5:
    st.header("⏰ Price Alerts")
    col1, col2 = st.columns(2)
    with col1:
        alert_ticker = st.text_input("Ticker for new alert:", key="alert_ticker")
    with col2:
        alert_price = st.number_input("Alert Price:", value=100.0, step=1.0, key="new_alert_price")
    col1, col2 = st.columns(2)
    with col1:
        alert_type = st.radio("Alert Type:", ["above", "below"], horizontal=True, key="alert_type_radio")
    with col2:
        if st.button("➕ Create Alert", key="create_alert"):
            if alert_ticker:
                add_price_alert(alert_ticker.upper(), alert_price, alert_type)
                st.success(f"Alert created for {alert_ticker.upper()} {alert_type} ${alert_price:.2f}")
                st.rerun()
    st.markdown("---")
    st.subheader("Active Alerts")
    if st.session_state.price_alerts:
        for ticker_alerts, alerts in st.session_state.price_alerts.items():
            for alert in alerts:
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.write(f"**{ticker_alerts}**")
                with col2:
                    st.write(f"{alert['type'].upper()} ${alert['price']:.2f}")
                with col3:
                    if st.button("❌", key=f"del_alert_{ticker_alerts}_{alert['price']}_{alert['type']}"):
                        st.session_state.price_alerts[ticker_alerts].remove(alert)
                        if not st.session_state.price_alerts[ticker_alerts]:
                            del st.session_state.price_alerts[ticker_alerts]
                        st.rerun()
    else:
        st.info("No active alerts. Create one above.")

# ============================================================
# TAB 6: NEWS
# ============================================================

with tab6:
    st.header("📰 Latest Market News")
    news_ticker = st.text_input("Ticker for news:", value=ticker if ticker else "AAPL", key="news_ticker")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"Pulling news from: Yahoo Finance, Google News, MarketWatch")
    with col2:
        if st.button("🔄 Refresh News", key="refresh_news"):
            st.cache_data.clear()
            st.rerun()
    
    with st.spinner(f"Fetching latest news for {news_ticker}... (this may take a few seconds)"):
        news = get_news(news_ticker, max_articles=20)
    
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
            <div style="background-color: {bg_color}; border-radius: 8px; padding: 12px; margin-bottom: 10px; border-left: 4px solid {badge_color}; transition: all 0.2s ease;">
                <p style="margin: 0; font-weight: bold; font-size: 16px;">
                    <a href="{link}" target="_blank" style="text-decoration: none; color: {link_color};">
                        {title}
                    </a>
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
        
        # Fallback: Show Google News search link
        st.markdown(f"""
        ---
        **Alternative:** Search manually on Google News:
        [🔍 Search {news_ticker} on Google News](https://news.google.com/search?q={news_ticker}%20stock&hl=en-US&gl=US&ceid=US:en)
        """)

# ============================================================
# AUTO-REFRESH
# ============================================================

if auto_refresh and interval_seconds > 0:
    time.sleep(interval_seconds)
    st.rerun()
