import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from math import log, sqrt, exp
from scipy.stats import norm
import time

st.set_page_config(page_title="Stock Analysis Dashboard", layout="wide")

st.title("📈 Stock Analysis Dashboard")
st.markdown("---")

# ============================================================
# FUNCTIONS
# ============================================================

# Function to get current risk-free rate
def get_risk_free_rate():
    try:
        treasury = yf.Ticker("^TNX")
        info = treasury.info
        rate = info.get('regularMarketPrice', info.get('previousClose', 4.5))
        return rate / 100
    except:
        return 0.045

# Function to get dividend yield
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

# TradingView Chart function
def tradingview_full_chart(ticker, timeframe="D"):
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
            "theme": "dark",
            "style": "1",
            "locale": "en",
            "toolbar_bg": "#f1f3f6",
            "enable_publishing": true,
            "allow_symbol_change": true,
            "save_image": true,
            "calendar": true,
            "container_id": "tradingview_full_chart",
            "studies": ["MASimple@tv-basicstudies", "RSI@tv-basicstudies", "MACD@tv-basicstudies"],
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

def calculate_macd(data, fast=12, slow=26, signal=9):
    ema_fast = data.ewm(span=fast, adjust=False).mean()
    ema_slow = data.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

# ============================================================
# SIDEBAR
# ============================================================

# Get initial risk-free rate
initial_rate = get_risk_free_rate()

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
    strike = st.number_input("Strike Price:", value=100.0, step=1.0)
    days = st.number_input("Days to Expiration:", value=30, step=1)
    option_type = st.selectbox("Option Type:", ["Call", "Put"])
    
    st.markdown("---")
    st.header("🔄 Auto-Refresh")
    auto_refresh = st.checkbox("Auto-refresh data", value=False)
    refresh_interval = st.selectbox("Refresh interval:", ["30 sec", "60 sec", "120 sec", "300 sec"], index=1) if auto_refresh else None
    
    if auto_refresh:
        interval_seconds = int(refresh_interval.split()[0])
        st.caption(f"🔄 Refreshing every {interval_seconds} seconds")
        st.caption(f"⚠️ Frequent refreshes may cause rate limits")
    
    st.caption(f"📅 Last update: {datetime.now().strftime('%H:%M:%S')}")
    st.markdown("---")
    st.caption("💡 Tip: Turn off auto-refresh to avoid rate limits")

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
        
        if len(hist) > 20:
            daily_returns = hist['Close'].pct_change().dropna()
            volatility = daily_returns.std() * (252 ** 0.5) * 100
        else:
            volatility = 30
        
        rsi = calculate_rsi(hist['Close'])
        current_rsi = rsi.iloc[-1] if not rsi.empty else 50
        
        asset_type = "Index/ETF" if is_index_ticker else "Stock"
        
        # ============================================================
        # HEADER METRICS
        # ============================================================
        st.subheader(f"📊 {ticker} - {info.get('longName', ticker)} ({asset_type})")
        
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            st.metric("Current Price", f"${current_price:.2f}", delta=f"{price_change:+.2f} ({price_change_pct:+.1f}%)")
        with col2:
            st.metric("Day High", f"${info.get('dayHigh', 0):.2f}")
        with col3:
            st.metric("Day Low", f"${info.get('dayLow', 0):.2f}")
        with col4:
            st.metric("52-Week High", f"${info.get('fiftyTwoWeekHigh', 0):.2f}")
        with col5:
            st.metric("52-Week Low", f"${info.get('fiftyTwoWeekLow', 0):.2f}")
        with col6:
            st.metric("Volume", f"{info.get('volume', 0):,}")
        
        st.markdown("---")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            pe = info.get('trailingPE', 0)
            st.metric("P/E Ratio", f"{pe:.2f}" if pe else "N/A")
        with col2:
            st.metric("6-Month Return", f"{six_month_return:.1f}%")
        with col3:
            st.metric("Volatility", f"{volatility:.1f}%")
        with col4:
            st.metric("RSI (14)", f"{current_rsi:.1f}")
        with col5:
            if not is_index_ticker:
                st.metric("Dividend Yield", f"{dividend_yield*100:.2f}%" if dividend_yield > 0 else "N/A")
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
        # TRADINGVIEW CHART
        # ============================================================
        st.subheader("📉 TradingView Chart")
        
        chart_option = st.radio(
            "Choose Chart Mode:",
            ["Embedded Chart (View Only)", "Launch Full TradingView (Save Drawings)"],
            horizontal=True
        )
        
        if chart_option == "Launch Full TradingView (Save Drawings)":
            tv_link = tradingview_direct_link(ticker)
            st.markdown(f"""
            <div style="text-align: center; padding: 40px; background-color: #1e1e2e; border-radius: 10px; border: 1px solid #89b4fa;">
                <h3>📈 Open TradingView for Full Analysis</h3>
                <a href="{tv_link}" target="_blank">
                    <button style="background-color: #89b4fa; color: #1e1e2e; padding: 12px 30px; font-size: 16px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">
                        🚀 Launch TradingView for {ticker}
                    </button>
                </a>
                <p style="font-size: 12px; margin-top: 20px;">Create a free TradingView account to save your drawings</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            timeframe_options = {"1 Minute": "1", "5 Minutes": "5", "15 Minutes": "15", "30 Minutes": "30", "1 Hour": "60", "4 Hours": "240", "Daily": "D", "Weekly": "W", "Monthly": "M"}
            selected_timeframe = st.selectbox("Select Timeframe:", list(timeframe_options.keys()))
            timeframe_value = timeframe_options[selected_timeframe]
            tradingview_full_chart(ticker, timeframe_value)
        
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
            st.write(f"**Volume:** {info.get('volume', 0):,}")
        
        with col2:
            st.subheader("📈 Key Metrics")
            if not is_index_ticker:
                st.write(f"**P/E Ratio:** {info.get('trailingPE', 0):.2f}")
                st.write(f"**Forward P/E:** {info.get('forwardPE', 0):.2f}")
                st.write(f"**Price/Book:** {info.get('priceToBook', 0):.2f}")
                st.write(f"**Dividend Yield:** {dividend_yield*100:.2f}%" if dividend_yield > 0 else "N/A")
            st.write(f"**Beta:** {info.get('beta', 'N/A')}")
        
        st.markdown("---")
        
        # ============================================================
        # FINANCIAL STATEMENTS
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
            df = pd.DataFrame(list(financials.items()), columns=["Metric", "Value ($M)"])
            df["Value ($M)"] = df["Value ($M)"].apply(lambda x: f"{x:,.2f}" if x > 0 else "N/A")
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.markdown("---")
        
        # ============================================================
        # OPTIONS CALCULATOR
        # ============================================================
        st.subheader("🎯 Options Price Calculator (Black-Scholes)")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.write(f"**Current Price:** ${current_price:.2f}")
            st.write(f"**Strike Price:** ${strike:.2f}")
            st.write(f"**Time to Expiration:** {days} days ({days/365:.4f} years)")
        with col2:
            st.write(f"**Volatility:** {volatility:.1f}%")
            st.write(f"**Risk-Free Rate:** {risk_free_rate*100:.2f}%")
            st.write(f"**Dividend Yield:** {dividend_yield*100:.2f}%")
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
                st.metric("Theoretical Price", f"${option_price:.2f}")
            with col2:
                st.metric("Delta", f"{delta:.4f}")
            with col3:
                st.metric("Gamma", f"{gamma:.4f}")
            with col4:
                st.metric("Theta (Daily)", f"{theta/365:.4f}")
            with col5:
                st.metric("Vega (per 1%)", f"{vega:.4f}")
            
            # ============================================================
            # TRADING SIGNAL & RECOMMENDATION SECTION
            # ============================================================
            st.markdown("---")
            st.subheader("📊 Trading Signal & Recommendation")
            
            # Input for actual market price
            col1, col2 = st.columns(2)
            
            with col1:
                market_price = st.number_input(
                    "Enter Actual Option Market Price ($):", 
                    value=float(option_price),
                    step=0.05,
                    format="%.2f",
                    help="Enter the current market price of the option from your broker"
                )
            
            with col2:
                # Calculate difference
                price_diff = market_price - option_price
                diff_percent = (price_diff / option_price * 100) if option_price > 0 else 0
                
                st.metric(
                    "Price Difference", 
                    f"${price_diff:.2f}", 
                    delta=f"{diff_percent:+.1f}%",
                    delta_color="normal"
                )
            
            # Create recommendation logic
            if option_price > 0:
                if diff_percent < -15:
                    recommendation = "🔥 STRONG BUY"
                    rec_color = "green"
                    rec_reason = f"Option is significantly undervalued ({abs(diff_percent):.0f}% below theoretical value)"
                    action = "Consider buying this option - market is underpricing this opportunity"
                    risk_level = "HIGH" if diff_percent < -30 else "MODERATE"
                elif diff_percent < -5:
                    recommendation = "✅ BUY"
                    rec_color = "lightgreen"
                    rec_reason = f"Option is undervalued ({abs(diff_percent):.0f}% below theoretical value)"
                    action = "Good opportunity to buy - market is offering a discount"
                    risk_level = "LOW"
                elif diff_percent > 15:
                    recommendation = "⚠️ STRONG SELL"
                    rec_color = "red"
                    rec_reason = f"Option is significantly overvalued ({diff_percent:.0f}% above theoretical value)"
                    action = "Consider selling or avoiding - market is overpricing this option"
                    risk_level = "HIGH"
                elif diff_percent > 5:
                    recommendation = "❌ SELL / AVOID"
                    rec_color = "orange"
                    rec_reason = f"Option is overvalued ({diff_percent:.0f}% above theoretical value)"
                    action = "Premium is expensive - consider selling or waiting for better entry"
                    risk_level = "MODERATE"
                else:
                    recommendation = "⏸️ HOLD / MONITOR"
                    rec_color = "yellow"
                    rec_reason = f"Option is fairly priced ({abs(diff_percent):.0f}% from theoretical value)"
                    action = "Wait for better opportunity or enter small position"
                    risk_level = "LOW"
                
                # Display recommendation card
                st.markdown(f"""
                <div style="background-color: #1e1e2e; border-radius: 10px; padding: 20px; border-left: 5px solid {'#a6e3a1' if 'BUY' in recommendation else '#f38ba8' if 'SELL' in recommendation else '#f9e2af'};">
                    <h3 style="margin: 0; color: {'#a6e3a1' if 'BUY' in recommendation else '#f38ba8' if 'SELL' in recommendation else '#f9e2af'};">{recommendation}</h3>
                    <p style="margin: 10px 0 5px 0;"><strong>Reason:</strong> {rec_reason}</p>
                    <p style="margin: 5px 0;"><strong>Action:</strong> {action}</p>
                    <p style="margin: 5px 0;"><strong>Risk Level:</strong> {risk_level}</p>
                </div>
                """, unsafe_allow_html=True)
                
                # Additional metrics
                st.markdown("---")
                st.subheader("📈 Trade Analysis")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.write("**Price Comparison**")
                    st.write(f"📊 Theoretical: **${option_price:.2f}**")
                    st.write(f"💵 Market: **${market_price:.2f}**")
                    if market_price < option_price:
                        st.write(f"💰 Discount: **${option_price - market_price:.2f}** ({(option_price - market_price)/option_price*100:.0f}%)")
                    elif market_price > option_price:
                        st.write(f"💸 Premium: **${market_price - option_price:.2f}** ({(market_price - option_price)/option_price*100:.0f}%)")
                    else:
                        st.write(f"⚖️ Fair Value")
                
                with col2:
                    st.write("**Profit Scenarios**")
                    if market_price < option_price:
                        potential_gain = (option_price - market_price) / market_price * 100
                        st.write(f"📈 Upside to Fair Value: **+{potential_gain:.0f}%**")
                        st.write(f"🎯 Target: **${option_price:.2f}**")
                    else:
                        st.write(f"⚠️ Currently overvalued by **{((market_price - option_price)/option_price*100):.0f}%**")
                
                with col3:
                    st.write("**Suggested Trade**")
                    if "BUY" in recommendation:
                        st.write("✅ **BUY** this option")
                        st.write(f"💰 Risk per contract: **${market_price * 100:.2f}**")
                    elif "SELL" in recommendation:
                        st.write("❌ **AVOID** buying")
                        st.write("💡 Consider selling if you own")
                    else:
                        st.write("⏸️ **WAIT** for better price")
                        st.write("💡 Enter at fair value or below")
                
                st.markdown("---")
                
                # Optional trade notes
                with st.expander("📝 Trade Notes & Checklist"):
                    st.write("**Before entering the trade:**")
                    st.write("- [ ] Verify the option chain (bid/ask spread)")
                    st.write("- [ ] Check volume and open interest")
                    st.write("- [ ] Confirm days to expiration")
                    st.write("- [ ] Review your risk management rules")
                    st.write("- [ ] Set a stop loss or profit target")
                    st.write("- [ ] Consider position size (recommended: 1-2% of account)")
                    
                    if market_price < option_price:
                        st.success(f"✅ This option is undervalued by {abs(diff_percent):.0f}%")
                        st.write(f"💡 Consider buying if the theoretical value of ${option_price:.2f} is realistic")
                    elif market_price > option_price:
                        st.warning(f"⚠️ This option is overvalued by {diff_percent:.0f}%")
                        st.write(f"💡 Wait for the price to drop closer to ${option_price:.2f}")
        
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
