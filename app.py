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
# TIMEZONE FUNCTIONS (Chicago/Central Time)
# ============================================================

def get_local_time():
    """Get current Chicago/Central time"""
    central = pytz.timezone('America/Chicago')
    return datetime.now(central)

def format_local_time(dt=None):
    """Format datetime in Central Time"""
    if dt is None:
        dt = get_local_time()
    return dt.strftime('%I:%M:%S %p').lstrip('0').replace(' 0', ' ')

def format_local_date(dt=None):
    """Format date in Central Time"""
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
# NEWS FUNCTION
# ============================================================

def get_news(ticker, max_articles=15):
    news_items = []
    
    try:
        stock = yf.Ticker(ticker)
        yf_news = stock.news
        if yf_news:
            for article in yf_news[:max_articles]:
                importance = 50
                title = article.get('title', '')
                publisher = article.get('publisher', '')
                
                if 'bloomberg' in publisher.lower():
                    importance += 30
                elif 'reuters' in publisher.lower():
                    importance += 25
                elif 'wsj' in publisher.lower() or 'wall street' in publisher.lower():
                    importance += 25
                elif 'cnbc' in publisher.lower():
                    importance += 20
                
                important_keywords = ['earnings', 'acquisition', 'merger', 'ceo', 'lawsuit', 'fda', 'approval', 'bankruptcy', 'dividend', 'stock split']
                for keyword in important_keywords:
                    if keyword in title.lower():
                        importance += 15
                
                news_items.append({
                    'title': title,
                    'link': article.get('link', '#'),
                    'publisher': publisher,
                    'date': article.get('providerPublishTime', None),
                    'source': 'Yahoo Finance',
                    'importance': importance
                })
    except:
        pass
    
    seen_titles = set()
    unique_news = []
    for item in news_items:
        if item['title'] not in seen_titles:
            seen_titles.add(item['title'])
            unique_news.append(item)
    
    unique_news.sort(key=lambda x: (x['importance'], x['date'] if x['date'] else 0), reverse=True)
    return unique_news[:max_articles]

# ============================================================
# EARNINGS FUNCTION
# ============================================================

def get_next_earnings(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
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
# IMPLIED VOLATILITY
# ============================================================

def get_implied_volatility(ticker, current_price, option_type):
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        if not expirations:
            return None
        
        nearest_exp = expirations[0]
        opt_chain = stock.option_chain(nearest_exp)
        
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
    stock = yf.Ticker(ticker)
    info = stock.info
    hist = stock.history(period='1y')
    
    if not is_index(ticker):
        balance_sheet = stock.balance_sheet
        income_statement = stock.financials
        cashflow = stock.cashflow
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
        info = treasury.info
        rate = info.get('regularMarketPrice', info.get('previousClose', 4.5))
        return rate / 100
    except:
        return 0.045

def get_dividend_yield(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
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
# SIDEBAR WITH THEME
# ============================================================

with st.sidebar:
    st.header("🎨 Appearance")
    theme = st.selectbox("Theme:", ["Dark", "Light"], index=0)
    
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
        .stCaption, .stCaption p {
            color: #000000 !important;
        }
        .stSidebar, .stSidebar .stMarkdown {
            background-color: #f5f5f5;
        }
        input, .stTextInput input, .stNumberInput input, .stSelectbox select {
            background-color: #ffffff !important;
            color: #000000 !important;
            border: 1px solid #cccccc !important;
        }
        .stMetric {
            background-color: #f8f9fa;
            border-radius: 10px;
            padding: 10px;
            border: 1px solid #e9ecef;
        }
        div[data-testid="stMetricValue"] {
            color: #000000 !important;
            font-weight: bold;
        }
        div[data-testid="stMetricLabel"] {
            color: #555555 !important;
        }
        h1, h2, h3, h4, h5, h6 {
            color: #000000 !important;
        }
        </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <style>
        .stApp { background-color: #1e1e2e; }
        .stMarkdown { color: #cdd6f4; }
        .stMetric { background-color: #313244; }
        div[data-testid="stMetricValue"] { color: #a6e3a1; }
        </style>
        """, unsafe_allow_html=True)

risk_free_rate = get_risk_free_rate()

with st.sidebar:
    st.header("🔍 Input")
    ticker = st.text_input("Stock / Index Ticker:", "SPY").upper()
    st.caption("Examples: Stocks: AAPL, MSFT, GME | Indices: SPY, QQQ, DIA, IWM")
    
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
        help="Select the option's expiration date"
    )
    
    today = date.today()
    if expiration_date >= today:
        days = (expiration_date - today).days
        st.caption(f"📅 Days to Expiration: **{days} days**")
    else:
        days = 0
        st.error("Expiration date must be in the future")
    
    strike = st.number_input("Strike Price:", value=100.0, step=1.0)
    option_type = st.selectbox("Option Type:", ["Call", "Put"])
    
    st.markdown("---")
    st.header("📊 Volatility Setting")
    
    volatility_source = st.radio(
        "Volatility Source:",
        ["Historical Volatility (from price data)", "Implied Volatility (from option chain)"],
        index=0,
    )
    
    st.markdown("---")
    st.header("🔄 Auto-Refresh")
    auto_refresh = st.checkbox("Auto-refresh data", value=False)
    refresh_interval = st.selectbox("Refresh interval:", ["60 sec", "120 sec", "300 sec"], index=1) if auto_refresh else None
    
    if auto_refresh:
        interval_seconds = int(refresh_interval.split()[0])
        st.caption(f"🔄 Refreshing every {interval_seconds} seconds")
        st.caption(f"⚠️ Frequent refreshes may cause rate limits")
    
    st.caption(f"📅 Last update: {format_local_time()}")

# ============================================================
# MAIN APP TABS
# ============================================================

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Analysis", "📈 Watchlist", "💰 Portfolio", "📝 Paper Trading", "⏰ Alerts", "📰 News"])

# ============================================================
# TAB 1: ANALYSIS (Complete with all financials)
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
            
            if volatility_source == "Historical Volatility (from price data)":
                if len(hist) > 20:
                    daily_returns = hist['Close'].pct_change().dropna()
                    volatility = daily_returns.std() * (252 ** 0.5) * 100
                else:
                    volatility = 30
            else:
                implied_vol = get_implied_volatility(ticker, current_price, option_type)
                if implied_vol and implied_vol > 0:
                    volatility = implied_vol
                else:
                    if len(hist) > 20:
                        daily_returns = hist['Close'].pct_change().dropna()
                        volatility = daily_returns.std() * (252 ** 0.5) * 100
                    else:
                        volatility = 30
            
            manual_vol = st.sidebar.checkbox("Manually override volatility", value=False)
            if manual_vol:
                volatility = st.sidebar.number_input("Manual Volatility (%):", value=volatility, step=1.0)
            
            rsi = calculate_rsi(hist['Close'])
            current_rsi = rsi.iloc[-1] if not rsi.empty else 50
            asset_type = "Index/ETF" if is_index_ticker else "Stock"
            
            # ============================================================
            # HEADER METRICS
            # ============================================================
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
            
            # ============================================================
            # KEY METRICS ROW
            # ============================================================
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                pe = info.get('trailingPE', 0)
                st.metric("P/E Ratio", f"{pe:,.2f}" if pe else "N/A")
            with col2:
                st.metric("6-Month Return", f"{six_month_return:+.1f}%")
            with col3:
                st.metric("Volatility", f"{volatility:.1f}%")
            with col4:
                st.metric("RSI (14)", f"{current_rsi:.1f}")
            with col5:
                if not is_index_ticker:
                    st.metric("Dividend Yield", format_percentage(dividend_yield*100) if dividend_yield > 0 else "N/A")
                else:
                    st.metric("Dividend Yield", "N/A")
            
            st.markdown("---")
            
            # ============================================================
            # RATES ROW
            # ============================================================
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Risk-Free Rate", f"{risk_free_rate*100:.2f}%")
            with col2:
                st.metric("Updated", format_local_time())
            with col3:
                st.metric("Auto-Refresh", "OFF" if not auto_refresh else f"{interval_seconds}s")
            
            st.markdown("---")
            
            # ============================================================
            # EARNINGS CALENDAR
            # ============================================================
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
            
            # ============================================================
            # TRADINGVIEW CHART
            # ============================================================
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
            
            # ============================================================
            # COMPANY INFORMATION
            # ============================================================
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
            
            # ============================================================
            # FINANCIAL STATEMENTS (Key Financials in Millions)
            # ============================================================
            if not is_index_ticker and not income_statement.empty:
                st.subheader("💰 Key Financials (in Millions)")
                
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
                working_capital = current_assets - current_liabilities
                current_ratio = current_assets / current_liabilities if current_liabilities > 0 else 0
                
                # Convert to millions for display
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
            
            # ============================================================
            # OPTIONS CALCULATOR
            # ============================================================
            if days > 0:
                st.subheader("🎯 Options Price Calculator (Black-Scholes)")
                
                S = current_price
                K = strike
                T = days / 365
                r = risk_free_rate
                v = volatility / 100
                q = dividend_yield
                
                option_price, delta, gamma, theta, vega = calculate_option_price(S, K, T, r, v, q, option_type)
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**Current Price:** {format_currency(current_price)}")
                    st.write(f"**Strike Price:** {format_currency(strike)}")
                    st.write(f"**Expiration:** {expiration_date.strftime('%Y-%m-%d')} ({days} days)")
                with col2:
                    st.write(f"**Volatility:** {volatility:.1f}%")
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
                
                # ============================================================
                # PROBABILITY CALCULATOR
                # ============================================================
                st.markdown("---")
                st.subheader("📊 Probability Calculator")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**Probability of Touching a Price**")
                    st.caption("The probability that the stock will touch this price at any time before expiration")
                    
                    target_price = st.number_input("Target Price ($):", value=current_price, step=1.0, key="prob_target", format="%.2f")
                    
                    if target_price != current_price and target_price > 0:
                        mu = risk_free_rate - dividend_yield
                        sigma = volatility / 100
                        T_years = days / 365
                        
                        if T_years > 0 and sigma > 0:
                            try:
                                if target_price > current_price:
                                    d1 = (log(current_price / target_price) + mu * T_years) / (sigma * sqrt(T_years))
                                    term1 = norm.cdf(d1)
                                    exponent = (2 * mu) / (sigma ** 2)
                                    factor = (target_price / current_price) ** exponent
                                    d2 = (log(current_price / target_price) - mu * T_years) / (sigma * sqrt(T_years))
                                    term2 = factor * norm.cdf(d2)
                                    prob_touch = term1 + term2
                                else:
                                    d1 = (log(current_price / target_price) + mu * T_years) / (sigma * sqrt(T_years))
                                    term1 = norm.cdf(-d1)
                                    exponent = (2 * mu) / (sigma ** 2)
                                    factor = (target_price / current_price) ** exponent
                                    d2 = (log(current_price / target_price) - mu * T_years) / (sigma * sqrt(T_years))
                                    term2 = factor * norm.cdf(-d2)
                                    prob_touch = term1 + term2
                                
                                prob_touch = max(0, min(prob_touch, 1.0))
                                st.metric(f"Probability to touch ${target_price:,.2f}", f"{prob_touch*100:.1f}%")
                            except:
                                st.error("Calculation error - try a different price")
                    else:
                        st.info("Enter a different target price")
                
                with col2:
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
                    
                    if close_price > 0:
                        T_years = days / 365
                        sigma = volatility / 100
                        
                        if T_years > 0 and sigma > 0:
                            try:
                                if close_price == current_price:
                                    prob_close = 50.0
                                    st.metric(f"Probability to close {close_direction} ${close_price:,.2f}", f"{prob_close:.1f}%")
                                else:
                                    d2_close = (log(current_price / close_price) + (risk_free_rate - dividend_yield - sigma**2 / 2) * T_years) / (sigma * sqrt(T_years))
                                    if close_direction == "Above":
                                        prob_close = norm.cdf(-d2_close) * 100
                                    else:
                                        prob_close = norm.cdf(d2_close) * 100
                                    prob_close = max(0.01, min(99.99, prob_close))
                                    st.metric(f"Probability to close {close_direction} ${close_price:,.2f}", f"{prob_close:.1f}%")
                            except:
                                st.error("Calculation error - try a different price")
                    else:
                        st.info("Enter a different price")
                
                st.markdown("---")
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**Expected Move**")
                    T_years = days / 365
                    expected_move = current_price * (volatility / 100) * sqrt(T_years)
                    st.metric("1 Standard Deviation Move (±)", format_currency(expected_move))
                
                with col2:
                    st.write("**Option Expiration Probability**")
                    option_direction = st.radio(
                        "Option Type for ITM:",
                        ["Call (Price > Strike)", "Put (Price < Strike)"],
                        index=0 if option_type == "Call" else 1,
                        key="option_itm_direction",
                        horizontal=True
                    )
                    
                    if option_direction == "Call (Price > Strike)":
                        prob_itm = norm.cdf(d2) * 100
                        st.metric(f"Probability Call is ITM (Price > ${strike:,.2f})", f"{prob_itm:.1f}%")
                    else:
                        prob_itm = norm.cdf(-d2) * 100
                        st.metric(f"Probability Put is ITM (Price < ${strike:,.2f})", f"{prob_itm:.1f}%")
                
                # ============================================================
                # TRADE MANAGEMENT (Profit Targets & Stop Loss)
                # ============================================================
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
        watchlist_data = []
        for w_ticker in st.session_state.watchlist:
            try:
                stock = yf.Ticker(w_ticker)
                info = stock.info
                price = info.get('currentPrice', info.get('regularMarketPrice', 0))
                change = price - info.get('previousClose', price)
                change_pct = (change / info.get('previousClose', 1) * 100) if info.get('previousClose') else 0
                
                earnings = get_next_earnings(w_ticker)
                earnings_soon = False
                days_until = 0
                if earnings:
                    days_until = (earnings.date() - date.today()).days
                    if 0 < days_until <= 7:
                        earnings_soon = True
                
                watchlist_data.append({
                    'Ticker': w_ticker,
                    'Price': format_currency(price),
                    'Change': f"{change:+.2f} ({change_pct:+.1f}%)",
                    'Earnings': f"{days_until}d" if earnings_soon else "N/A",
                    'Remove': w_ticker
                })
            except:
                watchlist_data.append({
                    'Ticker': w_ticker,
                    'Price': 'N/A',
                    'Change': 'N/A',
                    'Earnings': 'N/A',
                    'Remove': w_ticker
                })
        
        for item in watchlist_data:
            col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])
            with col1:
                st.write(f"**{item['Ticker']}**")
            with col2:
                st.write(item['Price'])
            with col3:
                st.write(item['Change'])
            with col4:
                if item['Earnings'] != 'N/A':
                    st.warning(f"⚠️ Earnings in {item['Earnings']}")
                else:
                    st.write("-")
            with col5:
                if st.button("❌ Remove", key=f"remove_{item['Ticker']}"):
                    remove_from_watchlist(item['Ticker'])
                    st.rerun()
            st.divider()
    else:
        st.info("Your watchlist is empty. Add tickers above to track them.")

# ============================================================
# TAB 3: REAL PORTFOLIO
# ============================================================

with tab3:
    st.header("💰 Real Portfolio")
    
    if st.session_state.positions:
        portfolio_data = []
        total_value = 0
        total_cost = 0
        
        for pos_id, pos in st.session_state.positions.items():
            # Get current price for the option (simplified)
            current_option_price = 0
            current_value = current_option_price * pos['quantity'] * 100
            cost = pos['entry_price'] * pos['quantity'] * 100
            pnl = current_value - cost
            pnl_pct = (pnl / cost * 100) if cost > 0 else 0
            
            total_value += current_value
            total_cost += cost
            
            portfolio_data.append({
                'ID': pos_id[:20],
                'Ticker': pos['ticker'],
                'Strike': pos['strike'],
                'Type': pos['type'],
                'Entry': format_currency(pos['entry_price']),
                'Qty': pos['quantity'],
                'Cost': format_currency(cost),
                'Current': format_currency(current_value),
                'P&L': f"{pnl:+.2f} ({pnl_pct:+.1f}%)",
                'Expiration': pos['expiration'],
                'Status': pos['status'],
                'Close': pos_id
            })
        
        st.metric("Total Portfolio Value", format_currency(total_value))
        st.metric("Total Cost Basis", format_currency(total_cost))
        st.metric("Total P&L", format_currency(total_value - total_cost), delta=f"{((total_value - total_cost)/total_cost*100):+.1f}%" if total_cost > 0 else "")
        
        st.markdown("---")
        
        for pos in portfolio_data:
            with st.expander(f"{pos['Ticker']} {pos['Strike']} {pos['Type']} - Entry: {pos['Entry']}"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**Quantity:** {pos['Qty']} contracts")
                    st.write(f"**Cost Basis:** {pos['Cost']}")
                    st.write(f"**Current Value:** {pos['Current']}")
                with col2:
                    st.write(f"**P&L:** {pos['P&L']}")
                    st.write(f"**Expiration:** {pos['Expiration']}")
                    st.write(f"**Status:** {pos['Status']}")
                with col3:
                    exit_price = st.number_input(f"Exit Price ($):", value=0.0, step=0.05, key=f"exit_{pos['ID']}")
                    if st.button(f"Close Position", key=f"close_{pos['ID']}"):
                        if exit_price > 0:
                            close_position(pos['Close'], exit_price, is_paper=False)
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
                    # Calculate current theoretical price
                    S = info.get('currentPrice', info.get('regularMarketPrice', 0)) if 'info' in locals() else 0
                    T = max(0.01, (datetime.strptime(pos['expiration'], '%Y-%m-%d').date() - date.today()).days / 365)
                    current_opt_price, _, _, _, _ = calculate_option_price(
                        S, pos['strike'], T, risk_free_rate, volatility/100, dividend_yield, pos['type']
                    )
                    st.write(f"**Current Value:** {format_currency(current_opt_price * pos['quantity'] * 100)}")
                with col3:
                    exit_price = st.number_input(f"Exit Price ($):", value=0.0, step=0.05, key=f"paper_exit_{pos_id}")
                    if st.button(f"Close Paper Position", key=f"paper_close_{pos_id}"):
                        if exit_price > 0:
                            close_position(pos_id, exit_price, is_paper=True)
                            st.success(f"Paper position closed at ${exit_price:.2f}")
                            st.rerun()
    else:
        st.info("No paper trading positions. Add positions from the Analysis tab using the 'Add to Paper Trading' button.")
    
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
    
    news_ticker = st.text_input("Ticker for news:", value="AAPL", key="news_ticker")
    
    with st.spinner(f"Fetching latest news for {news_ticker}..."):
        news = get_news(news_ticker, max_articles=15)
    
    if news:
        st.caption(f"Found {len(news)} recent news articles for {news_ticker}")
        
        for article in news[:15]:
            title = article.get('title', 'No title')
            link = article.get('link', '#')
            publisher = article.get('publisher', 'Unknown')
            source = article.get('source', 'Unknown')
            importance = article.get('importance', 0)
            pub_date = article.get('date', None)
            
            if pub_date:
                date_str = datetime.fromtimestamp(pub_date).strftime('%Y-%m-%d %H:%M')
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
                <p style="margin: 5px 0 0 0; font-size: 12px; color: {'#555' if theme == 'Light' else '#999'};">
                    📰 {publisher} | 🕐 {date_str} | 📍 {source}
                </p>
                <p style="margin: 3px 0 0 0; font-size: 11px; color: {badge_color};">
                    {badge}
                </p>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info(f"No recent news found for {news_ticker}. Try a different ticker.")

# ============================================================
# AUTO-REFRESH
# ============================================================

if auto_refresh and 'interval_seconds' in locals():
    time.sleep(interval_seconds)
    st.rerun()
