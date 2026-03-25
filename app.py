import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from math import log, sqrt, exp
from scipy.stats import norm
import time

st.set_page_config(page_title="Stock Analysis Dashboard", layout="wide")

# ============================================================
# FORMATTING FUNCTIONS
# ============================================================

def format_currency(value):
    """Format number as currency with commas"""
    if value is None or value == 0:
        return "$0.00"
    return f"${value:,.2f}"

def format_number(value):
    """Format number with commas (no decimals)"""
    if value is None or value == 0:
        return "0"
    return f"{value:,.0f}"

def format_number_decimal(value, decimals=2):
    """Format number with commas and decimals"""
    if value is None or value == 0:
        return "0"
    return f"{value:,.{decimals}f}"

def format_percentage(value):
    """Format percentage with commas"""
    if value is None:
        return "0%"
    return f"{value:,.2f}%"

def format_large_number(value):
    """Format large numbers with abbreviations (M, B)"""
    if value is None or value == 0:
        return "$0"
    if value >= 1_000_000_000:
        return f"${value/1_000_000_000:,.2f}B"
    elif value >= 1_000_000:
        return f"${value/1_000_000:,.2f}M"
    else:
        return f"${value:,.2f}"

def format_volume(value):
    """Format volume with abbreviations"""
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
# SESSION STATE FOR WATCHLIST
# ============================================================
if 'watchlist' not in st.session_state:
    st.session_state.watchlist = []
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}

# ============================================================
# FUNCTIONS
# ============================================================

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

def get_next_earnings(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        earnings_date = info.get('earningsDate', None)
        if earnings_date:
            if isinstance(earnings_date, list):
                return earnings_date[0]
            return earnings_date
        return None
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

def get_news(ticker):
    try:
        stock = yf.Ticker(ticker)
        news = stock.news
        if news:
            return news[:10]
        return []
    except:
        return []

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
            "timezone": "America/New_York",
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

# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.header("🎨 Appearance")
    theme = st.selectbox("Theme:", ["Dark", "Light"], index=0)
    
    if theme == "Light":
        st.markdown("""
        <style>
        .stApp { background-color: #ffffff; }
        .stMarkdown { color: #1e1e2e; }
        </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <style>
        .stApp { background-color: #1e1e2e; }
        .stMarkdown { color: #cdd6f4; }
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
    refresh_interval = st.selectbox("Refresh interval:", ["30 sec", "60 sec", "120 sec", "300 sec"], index=1) if auto_refresh else None
    
    if auto_refresh:
        interval_seconds = int(refresh_interval.split()[0])
        st.caption(f"🔄 Refreshing every {interval_seconds} seconds")
        st.caption(f"⚠️ Frequent refreshes may cause rate limits")
    
    st.caption(f"📅 Last update: {datetime.now().strftime('%H:%M:%S')}")

# ============================================================
# MAIN APP
# ============================================================

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
        
        hist_6mo = hist.tail(130)
        if len(hist_6mo) > 1:
            six_month_return = ((hist_6mo['Close'].iloc[-1] - hist_6mo['Close'].iloc[0]) / hist_6mo['Close'].iloc[0]) * 100
        else:
            six_month_return = 0
        
        # Volatility calculation based on user selection
        if volatility_source == "Historical Volatility (from price data)":
            if len(hist) > 20:
                daily_returns = hist['Close'].pct_change().dropna()
                volatility = daily_returns.std() * (252 ** 0.5) * 100
            else:
                volatility = 30
            st.sidebar.caption(f"📊 Historical Volatility: {volatility:.1f}%")
        else:
            implied_vol = get_implied_volatility(ticker, current_price, option_type)
            if implied_vol and implied_vol > 0:
                volatility = implied_vol
                st.sidebar.caption(f"📊 Implied Volatility: {volatility:.1f}% (from option chain)")
            else:
                if len(hist) > 20:
                    daily_returns = hist['Close'].pct_change().dropna()
                    volatility = daily_returns.std() * (252 ** 0.5) * 100
                else:
                    volatility = 30
                st.sidebar.warning("Could not fetch implied volatility, using historical")
        
        manual_vol = st.sidebar.checkbox("Manually override volatility", value=False)
        if manual_vol:
            volatility = st.sidebar.number_input("Manual Volatility (%):", value=volatility, step=1.0)
        
        rsi = calculate_rsi(hist['Close'])
        current_rsi = rsi.iloc[-1] if not rsi.empty else 50
        asset_type = "Index/ETF" if is_index_ticker else "Stock"
        
        # ============================================================
        # HEADER METRICS (FULLY FORMATTED)
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
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Risk-Free Rate", f"{risk_free_rate*100:.2f}%")
        with col2:
            st.metric("Updated", datetime.now().strftime('%H:%M:%S'))
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
        # COMPANY INFORMATION (FULLY FORMATTED)
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
        # FINANCIAL STATEMENTS (FULLY FORMATTED)
        # ============================================================
        if not is_index_ticker and not income_statement.empty:
            st.subheader("💰 Key Financials (in Millions)")
            latest_income = income_statement.iloc[:, 0] if len(income_statement.columns) > 0 else None
            if latest_income is not None:
                total_revenue = latest_income.get('Total Revenue', info.get('totalRevenue', 0))
                gross_profit = latest_income.get('Gross Profit', info.get('grossProfit', 0))
                net_income = latest_income.get('Net Income', info.get('netIncomeToCommon', 0))
            else:
                total_revenue = info.get('totalRevenue', 0)
                gross_profit = info.get('grossProfit', 0)
                net_income = info.get('netIncomeToCommon', 0)
            
            if not balance_sheet.empty:
                latest_balance = balance_sheet.iloc[:, 0] if len(balance_sheet.columns) > 0 else None
                if latest_balance is not None:
                    total_assets = latest_balance.get('Total Assets', info.get('totalAssets', 0))
                    total_debt = latest_balance.get('Total Debt', info.get('totalDebt', 0))
                    total_equity = latest_balance.get('Total Equity Gross Minority Interest', info.get('totalShareholderEquity', 0))
                else:
                    total_assets = info.get('totalAssets', 0)
                    total_debt = info.get('totalDebt', 0)
                    total_equity = info.get('totalShareholderEquity', 0)
            else:
                total_assets = info.get('totalAssets', 0)
                total_debt = info.get('totalDebt', 0)
                total_equity = info.get('totalShareholderEquity', 0)
            
            financials = {
                "Total Revenue": total_revenue / 1e6 if total_revenue else 0,
                "Gross Profit": gross_profit / 1e6 if gross_profit else 0,
                "Net Income": net_income / 1e6 if net_income else 0,
                "Total Assets": total_assets / 1e6 if total_assets else 0,
                "Total Debt": total_debt / 1e6 if total_debt else 0,
                "Total Equity": total_equity / 1e6 if total_equity else 0,
            }
            df = pd.DataFrame(list(financials.items()), columns=["Metric", "Value"])
            df["Value"] = df["Value"].apply(lambda x: f"${x:,.2f}M" if x > 0 else "N/A")
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.markdown("---")
        
        # ============================================================
        # OPTIONS CALCULATOR
        # ============================================================
        if days > 0:
            st.subheader("🎯 Options Price Calculator (Black-Scholes)")
            
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
            
            S = current_price
            K = strike
            T = days / 365
            r = risk_free_rate
            v = volatility / 100
            q = dividend_yield
            
            if v > 0 and T > 0:
                d1 = (log(S / K) + (r - q + v**2 / 2) * T) / (v * sqrt(T))
                d2 = d1 - v * sqrt(T)
                
                if option_type == "Call":
                    option_price = S * exp(-q * T) * norm.cdf(d1) - K * exp(-r * T) * norm.cdf(d2)
                    delta = exp(-q * T) * norm.cdf(d1)
                    gamma = norm.pdf(d1) * exp(-q * T) / (S * v * sqrt(T))
                    theta = - (S * v * norm.pdf(d1) * exp(-q * T)) / (2 * sqrt(T)) - r * K * exp(-r * T) * norm.cdf(d2) + q * S * norm.cdf(d1) * exp(-q * T)
                    vega = S * sqrt(T) * norm.pdf(d1) * exp(-q * T) / 100
                else:
                    option_price = K * exp(-r * T) * norm.cdf(-d2) - S * exp(-q * T) * norm.cdf(-d1)
                    delta = -exp(-q * T) * norm.cdf(-d1)
                    gamma = norm.pdf(d1) * exp(-q * T) / (S * v * sqrt(T))
                    theta = - (S * v * norm.pdf(d1) * exp(-q * T)) / (2 * sqrt(T)) + r * K * exp(-r * T) * norm.cdf(-d2) - q * S * norm.cdf(-d1) * exp(-q * T)
                    vega = S * sqrt(T) * norm.pdf(d1) * exp(-q * T) / 100
                
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
                    target_price = st.number_input("Target Price ($):", value=current_price, step=1.0, key="prob_target", format="%.2f")
                    if target_price > current_price:
                        z_score = (log(target_price / current_price)) / (volatility / 100 * sqrt(days/365))
                        prob_up = norm.cdf(z_score) * 100
                        st.metric(f"Probability to reach {format_currency(target_price)}", f"{prob_up:.1f}%")
                    elif target_price < current_price:
                        z_score = (log(current_price / target_price)) / (volatility / 100 * sqrt(days/365))
                        prob_down = norm.cdf(z_score) * 100
                        st.metric(f"Probability to reach {format_currency(target_price)}", f"{prob_down:.1f}%")
                    else:
                        st.info("Enter a different target price")
                
                with col2:
                    st.write("**Expected Move**")
                    expected_move = current_price * (volatility / 100) * sqrt(days/365)
                    st.metric("Expected Move (±)", format_currency(expected_move))
                    st.caption(f"Based on {volatility:.0f}% volatility over {days} days")
                    if option_type == "Call":
                        prob_itm = norm.cdf(d2) * 100
                    else:
                        prob_itm = norm.cdf(-d2) * 100
                    st.metric("Probability ITM at Expiration", f"{prob_itm:.1f}%")
                
                # ============================================================
                # TRADING SIGNAL & RECOMMENDATION SECTION
                # ============================================================
                st.markdown("---")
                st.subheader("📊 Trading Signal & Recommendation")
                
                col1, col2 = st.columns(2)
                with col1:
                    market_price_input = st.number_input("Enter Actual Option Market Price ($):", value=None, step=0.05, format="%.2f", help="Enter the current market price from your broker")
                
                with col2:
                    if market_price_input is not None and market_price_input > 0 and option_price > 0:
                        price_diff = market_price_input - option_price
                        diff_percent = (price_diff / option_price * 100)
                        st.metric("Price Difference", format_currency(price_diff), delta=f"{diff_percent:+.1f}%", delta_color="normal")
                    else:
                        st.info("Enter market price to see difference")
                        price_diff = 0
                        diff_percent = 0
                
                if market_price_input is not None and market_price_input > 0 and option_price > 0:
                    if diff_percent < -15:
                        recommendation = "🔥 STRONG BUY"
                        rec_reason = f"Option is significantly undervalued ({abs(diff_percent):.0f}% below theoretical)"
                        action = "Consider buying - market is underpricing this opportunity"
                        risk_level = "HIGH" if diff_percent < -30 else "MODERATE"
                    elif diff_percent < -5:
                        recommendation = "✅ BUY"
                        rec_reason = f"Option is undervalued ({abs(diff_percent):.0f}% below theoretical)"
                        action = "Good opportunity to buy - market is offering a discount"
                        risk_level = "LOW"
                    elif diff_percent > 15:
                        recommendation = "⚠️ STRONG SELL"
                        rec_reason = f"Option is significantly overvalued ({diff_percent:.0f}% above theoretical)"
                        action = "Consider selling or avoiding - market is overpricing"
                        risk_level = "HIGH"
                    elif diff_percent > 5:
                        recommendation = "❌ SELL / AVOID"
                        rec_reason = f"Option is overvalued ({diff_percent:.0f}% above theoretical)"
                        action = "Premium is expensive - wait for better entry"
                        risk_level = "MODERATE"
                    else:
                        recommendation = "⏸️ HOLD / MONITOR"
                        rec_reason = f"Option is fairly priced ({abs(diff_percent):.0f}% from theoretical)"
                        action = "Wait for better opportunity or enter small position"
                        risk_level = "LOW"
                    
                    st.markdown(f"""
                    <div style="background-color: #1e1e2e; border-radius: 10px; padding: 20px; border-left: 5px solid {'#a6e3a1' if 'BUY' in recommendation else '#f38ba8' if 'SELL' in recommendation else '#f9e2af'};">
                        <h3 style="margin: 0; color: {'#a6e3a1' if 'BUY' in recommendation else '#f38ba8' if 'SELL' in recommendation else '#f9e2af'};">{recommendation}</h3>
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
                            discount_pct = discount / option_price * 100
                            st.write(f"💰 Discount: **{format_currency(discount)}** ({discount_pct:.0f}%)")
                        elif market_price_input > option_price:
                            premium = market_price_input - option_price
                            premium_pct = premium / option_price * 100
                            st.write(f"💸 Premium: **{format_currency(premium)}** ({premium_pct:.0f}%)")
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
                            st.write("💡 Consider selling if you own")
                        else:
                            st.write("⏸️ **WAIT** for better price")
                    
                    # ============================================================
                    # POSITION SIZE CALCULATOR (FULLY FORMATTED)
                    # ============================================================
                    with st.expander("💰 Position Size Calculator"):
                        st.subheader("Risk Management")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            account_size = st.number_input("Account Size ($):", value=10000, step=1000, key="account_size", format="%d")
                        with col2:
                            risk_percent = st.number_input("Risk Per Trade (%):", value=2.0, step=0.5, key="risk_percent")
                        
                        risk_percent_decimal = risk_percent / 100
                        max_risk = account_size * risk_percent_decimal
                        
                        st.metric("Max Risk per Trade", format_currency(max_risk))
                        st.caption(f"Based on {risk_percent:.1f}% of {format_currency(account_size)} account")
                        
                        st.markdown("---")
                        
                        if market_price_input and market_price_input > 0:
                            contracts = int(max_risk / (market_price_input * 100))
                            total_risk = contracts * market_price_input * 100
                            total_position_value = contracts * market_price_input * 100
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Max Contracts", contracts)
                            with col2:
                                st.metric("Total Risk", format_currency(total_risk))
                            with col3:
                                st.metric("Position Value", format_currency(total_position_value))
                            
                            st.markdown("---")
                            
                            if contracts > 0:
                                st.success(f"✅ **Recommended Position:** Buy **{contracts} contract(s)** at {format_currency(market_price_input)} each")
                                st.caption(f"• Total cost: {format_currency(total_position_value)}")
                                st.caption(f"• Risk: {format_currency(total_risk)} ({risk_percent:.1f}% of account)")
                                
                                if contracts > 5:
                                    st.warning(f"⚠️ {contracts} contracts is a large position - consider reducing size")
                            else:
                                st.warning(f"⚠️ Account too small for 1 contract")
                                st.caption(f"Minimum required: {format_currency(market_price_input * 100)}")
                        else:
                            st.info("📝 Enter the option market price above to calculate position size")
                else:
                    st.info("📝 Enter the actual option market price to get a trading recommendation")
        else:
            st.error("Please select a future expiration date")
        
        # ============================================================
        # REAL-TIME NEWS
        # ============================================================
        st.markdown("---")
        st.subheader("📰 Real-Time News")
        news = get_news(ticker)
        if news:
            for i, article in enumerate(news[:10]):
                title = article.get('title', 'No title')
                link = article.get('link', '#')
                publisher = article.get('publisher', 'Unknown')
                pub_date = article.get('providerPublishTime', None)
                date_str = datetime.fromtimestamp(pub_date).strftime('%Y-%m-%d %H:%M') if pub_date else "Recently"
                st.markdown(f"**{i+1}. [{title}]({link})**")
                st.caption(f"📰 {publisher} | 🕐 {date_str}")
                st.markdown("---")
        else:
            st.info(f"No recent news found for {ticker}")
        
        # ============================================================
        # AUTO-REFRESH LOGIC
        # ============================================================
        if auto_refresh:
            time.sleep(interval_seconds)
            st.rerun()
        
    except Exception as e:
        if "Too Many Requests" in str(e) or "Rate limited" in str(e):
            st.error("⚠️ **Rate Limit Exceeded**")
            st.info("""
            Yahoo Finance has temporarily limited your requests.
            
            **What to do:**
            - Turn OFF auto-refresh in the sidebar
            - Wait 10-15 minutes
            - Refresh manually (F5)
            
            **To prevent this:**
            - Keep auto-refresh OFF
            - Use manual refresh sparingly
            """)
        else:
            st.error(f"Error fetching data for {ticker}: {e}")
            st.info("Please check the ticker symbol and try again.")
else:
    st.info("Enter a stock or index ticker (e.g., AAPL, MSFT, SPY, QQQ, GME) in the sidebar to begin.")
