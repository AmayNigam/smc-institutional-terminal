import os
import sys
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from universe import get_tickers_by_category

# Ensure current working directory is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_loader import load_positional_data
from smc_engine import SMCEngine
from smc_state_machine import SMCMitigationTracker
from charting_engine import SMCChartEngine

# --- SMART IMPORT FOR BACKTESTER ---
try:
    from advanced_backtester import ClientSMCBacktester
except ImportError:
    try:
        from backtester import ClientSMCBacktester
    except ImportError:
        try:
            from backtester import AdvancedSMCBacktester as ClientSMCBacktester
        except ImportError:
            ClientSMCBacktester = None

from universe import ASSET_UNIVERSES, get_tickers_by_category
from master_scanner import run_master_market_scan

# ==============================================================================
# STREAMLIT PAGE CONFIGURATION
# ==============================================================================
st.set_page_config(
    page_title="SMC Quantitative Institutional Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling for Sleek Institutional Look
st.markdown("""
    <style>
        .main {
            background-color: #0e1117;
        }
        .metric-card {
            background-color: #1a1e24;
            padding: 16px;
            border-radius: 8px;
            border: 1px solid #2a2e39;
            margin-bottom: 12px;
        }
        .metric-label {
            font-size: 0.82rem;
            color: #878b94;
            text-transform: uppercase;
            font-weight: 600;
        }
        .metric-val {
            font-size: 1.4rem;
            font-weight: 700;
            color: #ffffff;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            background-color: #1a1e24;
            border-radius: 6px;
            padding: 8px 18px;
            border: 1px solid #2a2e39;
        }
        .stTabs [aria-selected="true"] {
            background-color: #2157f3 !important;
            border-color: #2157f3 !important;
        }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# SIDEBAR CONTROLS
# ==============================================================================
st.sidebar.title("Institutional SMC")
st.sidebar.caption("High-Probability Execution & Market Architecture")

st.sidebar.divider()
st.sidebar.subheader("Scanner Settings")
proximity_slider = st.sidebar.slider("Strike Zone Window (%)", min_value=1.0, max_value=10.0, value=5.0, step=0.5) / 100.0

scan_commodities_sel = st.sidebar.checkbox("Include Global Commodities", value=True)
scan_nifty_sel = st.sidebar.checkbox("Include Nifty 50 Core", value=True)
scan_nse_all_sel = st.sidebar.checkbox("Full NSE Universe (~2,200 Equities)", value=False)

if st.sidebar.button("Run Full Market Scan", use_container_width=True):
    with st.spinner("Executing quantitative SMC scan across universe..."):
        run_master_market_scan(
            scan_commodities=scan_commodities_sel,
            scan_nifty_core=scan_nifty_sel,
            scan_all_nse=scan_nse_all_sel,
            proximity_pct=proximity_slider
        )
    st.sidebar.success("Market Scan Complete! Feeds updated.")

st.sidebar.divider()
st.sidebar.info(
    "Architecture: 200 EMA Macro Trend + 0.5x ATR Momentum Displacement + "
    "Dealing Range Premium/Discount Array + Candle Reversal Confirmation."
)

# ==============================================================================
# MAIN DASHBOARD TABS
# ==============================================================================
tabs = st.tabs([
    "Actionable Strike Alerts", 
    "Master Radar Board", 
    "Interactive Chart Inspector", 
    "Strategy Backtest Audit"
])

# ------------------------------------------------------------------------------
# TAB 1: ACTIONABLE STRIKE ALERTS
# ------------------------------------------------------------------------------
with tabs[0]:
    st.subheader("🎯 Actionable Strike Setups")
    st.caption("Confirmed entries meeting structural reversal rules within the immediate institutional strike zone.")
    
    alerts_file = "SMC_ACTIONABLE_ALERTS.csv"
    if os.path.exists(alerts_file):
        alerts_df = pd.read_csv(alerts_file)
        if not alerts_df.empty:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Confirmed Setups", len(alerts_df))
            with col2:
                longs_count = len(alerts_df[alerts_df['Direction'].str.contains('LONG', na=False)])
                st.metric("Long Setups", longs_count)
            with col3:
                shorts_count = len(alerts_df[alerts_df['Direction'].str.contains('SHORT', na=False)])
                st.metric("Short Setups", shorts_count)
            with col4:
                top_rr = alerts_df['R:R'].max() if 'R:R' in alerts_df.columns else 0.0
                st.metric("Peak R:R Available", f"1 : {top_rr}")

            def highlight_direction(val):
                if 'LONG' in str(val):
                    return 'background-color: rgba(8, 153, 129, 0.25); color: #089981; font-weight: bold;'
                elif 'SHORT' in str(val):
                    return 'background-color: rgba(242, 54, 69, 0.25); color: #f23645; font-weight: bold;'
                return ''

            # FIX: Pandas >= 2.1.0 replaced .applymap() with .map()
            styled_df = alerts_df.style.map(highlight_direction, subset=['Direction'])
            st.dataframe(styled_df, use_container_width=True, height=380)
        else:
            st.warning("No assets currently in confirmed strike zone. Prices are floating between zones.")
    else:
        st.info("No alert feed generated yet. Click 'Run Full Market Scan' in the sidebar.")

# ------------------------------------------------------------------------------
# TAB 2: MASTER RADAR BOARD
# ------------------------------------------------------------------------------
with tabs[1]:
    st.subheader("📡 Global Asset Structure Radar")
    st.caption("Complete structural mapping of every scanned asset relative to nearest Supply and Demand blocks.")
    
    radar_file = "SMC_MASTER_RADAR_FEED.csv"
    if os.path.exists(radar_file):
        radar_df = pd.read_csv(radar_file)
        if not radar_df.empty:
            search_query = st.text_input("Filter Ticker / Asset Class:", placeholder="e.g. RELIANCE, GC=F, COMMODITY...")
            if search_query:
                filtered_radar = radar_df[
                    radar_df['Ticker'].str.contains(search_query, case=False, na=False) |
                    radar_df['Asset_Class'].str.contains(search_query, case=False, na=False)
                ]
            else:
                filtered_radar = radar_df

            def highlight_trend(val):
                if val == 'BULLISH':
                    return 'color: #089981; font-weight: 600;'
                elif val == 'BEARISH':
                    return 'color: #f23645; font-weight: 600;'
                return ''

            # FIX: Pandas >= 2.1.0 replaced .applymap() with .map()
            styled_radar = filtered_radar.style.map(highlight_trend, subset=['Trend'])
            st.dataframe(styled_radar, use_container_width=True, height=500)
        else:
            st.warning("Radar feed is empty.")
    else:
        st.info("Radar feed not found. Run the market scan to compile current data.")

# ------------------------------------------------------------------------------
# TAB 3: INTERACTIVE CHART INSPECTOR
# ------------------------------------------------------------------------------
with tabs[2]:
    st.subheader("📊 Interactive Institutional Chart Inspector")
    st.caption("TradingView-grade Plotly visualization showing live Order Blocks (+OB/-OB), Dealing Range, and BOS breaks.")
    
    # Fetch all commodities, Nifty 50, and the broad NSE universe, then sort alphabetically
    available_tickers = sorted(list(set(
        ASSET_UNIVERSES.get("COMMODITIES_GLOBAL", []) +
        ASSET_UNIVERSES.get("NIFTY_50_CORE", []) +
        ASSET_UNIVERSES.get("NSE_ALL", [])
        )))
    
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        selected_ticker = st.selectbox("Select Asset to Inspect:", available_tickers, index=0)
    with c2:
        bars_count = st.slider("Lookback Bars:", min_value=60, max_value=350, value=180, step=20)
    with c3:
        chart_theme = st.selectbox("Theme:", ["light", "dark"], index=0)

    if selected_ticker:
        with st.spinner(f"Computing SMC structure and rendering chart for {selected_ticker}..."):
            data = load_positional_data(selected_ticker, start_date="2022-01-01")
            if not data['daily'].empty and len(data['daily']) >= 50:
                engine = SMCEngine(data['daily'], swing_length=3)
                smc_df = engine.run_all()
                
                tracker = SMCMitigationTracker(smc_df)
                tracker.run_tracking()
                
                chart_engine = SMCChartEngine(smc_df, tracker, selected_ticker)
                fig = chart_engine.render_chart(num_bars=bars_count, save_html=False, theme=chart_theme)
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.error(f"Insufficient data to generate chart for {selected_ticker}.")

# ------------------------------------------------------------------------------
# TAB 4: STRATEGY BACKTEST AUDIT
# ------------------------------------------------------------------------------
with tabs[3]:
    st.subheader("🔬 Client Performance & Backtest Audit")
    st.caption("Run institutional walk-forward backtests with confirmation rules, dynamic ATR stops, and breakeven trailing.")
    
    # Load all 2,200+ tickers dynamically from the scanned radar feed
    try:
        import pandas as pd
        feed_df = pd.read_csv("SMC_MASTER_RADAR_FEED.csv")
        full_ticker_list = sorted([str(t) for t in feed_df["Ticker"].dropna().unique() if str(t).strip()])
    except Exception:
        full_ticker_list = available_tickers

    b_col1, b_col2, b_col3 = st.columns([2, 1, 1])
    with b_col1:
        custom_input = st.text_input("Enter Any Ticker:", placeholder="e.g. PCJEWELLER.NS")
        selected_dropdown = st.selectbox("Or Pick From Scanned Universe:", full_ticker_list, index=0)
        bt_ticker = custom_input.strip().upper() if custom_input.strip() else selected_dropdown
    with b_col2:
        bt_start = st.selectbox("Historical Start Date:", ["2020-01-01", "2021-01-01", "2022-01-01"], index=0)
    with b_col3:
        bt_min_rr = st.number_input("Minimum R:R Threshold:", min_value=1.0, max_value=5.0, value=1.0, step=0.5)

    if st.button("Run Performance Audit", use_container_width=True):
        if ClientSMCBacktester is None:
            st.error("Could not find the backtester code. Please make sure your backtester file is saved as 'advanced_backtester.py' or 'backtester.py'.")
        else:
            with st.spinner(f"Backtesting {bt_ticker} on daily timeframe..."):
                tester = ClientSMCBacktester(
                    ticker=bt_ticker,
                    start_date=bt_start,
                    min_rr=bt_min_rr,
                    risk_per_trade_pct=0.01,
                    initial_capital=100000.0
                )
                tester.run_backtest()
                
                if tester.trades:
                    trades_df = pd.DataFrame(tester.trades)
                    wins = len(trades_df[trades_df['pnl_r'] > 0])
                    losses = len(trades_df[trades_df['pnl_r'] < 0])
                    scratches = len(trades_df[trades_df['pnl_r'] == 0])
                    total = len(trades_df)
                    client_accuracy = ((wins + scratches) / total) * 100
                    
                    k1, k2, k3, k4, k5 = st.columns(5)
                    with k1:
                        st.metric("Total Trades", total)
                    with k2:
                        st.metric("Trade Accuracy (Win+BE)", f"{client_accuracy:.2f}%")
                    with k3:
                        tot_prof = trades_df[trades_df['pnl_cash'] > 0]['pnl_cash'].sum()
                        tot_loss = abs(trades_df[trades_df['pnl_cash'] < 0]['pnl_cash'].sum())
                        pf = tot_prof / tot_loss if tot_loss > 0 else 0
                        st.metric("Profit Factor", f"{pf:.2f}")
                    with k4:
                        eq_df = pd.DataFrame(tester.equity_curve).set_index('Date')
                        tot_ret = ((eq_df['Capital'].iloc[-1] - 100000.0) / 100000.0) * 100
                        st.metric("Net Portfolio Return", f"+{tot_ret:.2f}%")
                    with k5:
                        eq_df['Peak'] = eq_df['Capital'].cummax()
                        eq_df['DD'] = (eq_df['Capital'] - eq_df['Peak']) / eq_df['Peak']
                        max_dd = eq_df['DD'].min() * 100
                        st.metric("Max Peak Drawdown", f"{max_dd:.2f}%")

                    st.markdown("#### Portfolio Equity Curve")
                    fig_eq = go.Figure()
                    fig_eq.add_trace(go.Scatter(
                        x=eq_df.index, y=eq_df['Capital'],
                        mode='lines', line=dict(color='#2157f3', width=2.5),
                        name='Capital ($)'
                    ))
                    fig_eq.update_layout(
                        template="plotly_dark",
                        height=350,
                        margin=dict(l=20, r=20, t=30, b=20),
                        yaxis=dict(tickformat=',.0f')
                    )
                    st.plotly_chart(fig_eq, use_container_width=True)

                    st.markdown("#### Executed Trades Ledger")
                    ledger_cols = ['signal_date', 'direction', 'entry_price', 'exit_price', 'exit_reason', 'pnl_r', 'pnl_pct', 'capital_after']
                    st.dataframe(trades_df[ledger_cols].tail(25), use_container_width=True)
                else:
                    st.warning("No trades met the criteria during this historical window.")
