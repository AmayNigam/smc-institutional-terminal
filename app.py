import os
import sys
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go

# Ensure current working directory is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_loader import load_positional_data
from smc_engine import SMCEngine
from smc_state_machine import SMCMitigationTracker
from charting_engine import SMCChartEngine
from universe import ASSET_UNIVERSES, get_tickers_by_category
from master_scanner import run_master_market_scan

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

# ==============================================================================
# STREAMLIT PAGE CONFIGURATION
# ==============================================================================
st.set_page_config(
    page_title="Alpha Flow | SMC Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling for Sleek Institutional Look
st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .main {background-color: #0e1117;}
        
        /* Metric HUD Styling */
        div[data-testid="metric-container"] {
            background-color: #1a1e24;
            border: 1px solid #2a2e39;
            padding: 15px 20px;
            border-radius: 8px;
            box-shadow: 0px 4px 6px rgba(0, 0, 0, 0.3);
        }
        
        .stTabs [data-baseweb="tab-list"] {gap: 8px;}
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
# PROFESSIONAL HEADER & PERSISTENT HUD
# ==============================================================================
st.title("⚡ Alpha Flow Quantitative Terminal")
st.markdown("**Institutional Smart Money Concepts (SMC) State-Machine Engine** | 🟢 Live Market Data")

# Pre-load alerts to build the persistent HUD
alerts_file = "SMC_ACTIONABLE_ALERTS.csv"
hud_total, hud_longs, hud_shorts, hud_rr = 0, 0, 0, 0.0
alerts_df = pd.DataFrame()

if os.path.exists(alerts_file):
    try:
        alerts_df = pd.read_csv(alerts_file)
        if not alerts_df.empty:
            hud_total = len(alerts_df)
            hud_longs = len(alerts_df[alerts_df['Direction'].str.contains('LONG', na=False)])
            hud_shorts = len(alerts_df[alerts_df['Direction'].str.contains('SHORT', na=False)])
            hud_rr = alerts_df['R:R'].max() if 'R:R' in alerts_df.columns else 0.0
    except pd.errors.EmptyDataError:
        pass

st.markdown("---")
h1, h2, h3, h4 = st.columns(4)
h1.metric("Active Strike Alerts", hud_total)
h2.metric("Long Bias Setups", hud_longs)
h3.metric("Short Bias Setups", hud_shorts)
h4.metric("Peak Target R:R", f"1 : {hud_rr}")
st.markdown("<br>", unsafe_allow_html=True)

# ==============================================================================
# SIDEBAR CONTROLS (STRICT ISOLATION)
# ==============================================================================
st.sidebar.title("Terminal Controls")
st.sidebar.divider()

# 1. Scanner Settings
st.sidebar.subheader("📡 Market Scanner")
proximity_slider = st.sidebar.slider("Strike Zone Window (%)", min_value=1.0, max_value=10.0, value=5.0, step=0.5) / 100.0
scan_commodities_sel = st.sidebar.checkbox("Include Global Commodities", value=True)
scan_nifty_sel = st.sidebar.checkbox("Include Nifty 50 Core", value=True)
scan_nse_all_sel = st.sidebar.checkbox("Full NSE Universe", value=False)

if st.sidebar.button("Run Master Scan", use_container_width=True, type="primary"):
    with st.spinner("Executing quantitative SMC scan..."):
        run_master_market_scan(
            scan_commodities=scan_commodities_sel,
            scan_nifty_core=scan_nifty_sel,
            scan_all_nse=scan_nse_all_sel,
            proximity_pct=proximity_slider
        )
    st.sidebar.success("Scan Complete!")

st.sidebar.divider()

# 2. Backtester Settings
st.sidebar.subheader("🔬 Backtest Engine")
try:
    feed_df = pd.read_csv("SMC_MASTER_RADAR_FEED.csv")
    full_ticker_list = sorted([str(t) for t in feed_df["Ticker"].dropna().unique() if str(t).strip()])
except Exception:
    full_ticker_list = ["RELIANCE.NS", "HDFCBANK.NS", "TRUALT.NS"]

bt_ticker = st.sidebar.selectbox("Target Asset:", full_ticker_list, index=0)
bt_start = st.sidebar.selectbox("Historical Start:", ["2020-01-01", "2021-01-01", "2022-01-01"], index=0)
bt_min_rr = st.sidebar.number_input("Min R:R Threshold:", min_value=1.0, max_value=5.0, value=1.0, step=0.5)

run_bt = st.sidebar.button("Audit Historical Performance", use_container_width=True)

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
# TAB 1: ACTIONABLE STRIKE ALERTS (Visual Upgrades)
# ------------------------------------------------------------------------------
with tabs[0]:
    st.subheader("🎯 Actionable Strike Setups")
    st.caption("Confirmed entries meeting structural reversal rules within the immediate institutional strike zone.")
    
    if not alerts_df.empty:
        def highlight_direction(val):
            if 'LONG' in str(val): return 'background-color: rgba(8, 153, 129, 0.25); color: #089981; font-weight: bold;'
            elif 'SHORT' in str(val): return 'background-color: rgba(242, 54, 69, 0.25); color: #f23645; font-weight: bold;'
            return ''
        
        styled_df = alerts_df.style.map(highlight_direction, subset=['Direction'])
        
        # VISUAL DATA UPGRADE: Formatting columns as currency and progress bars
        st.dataframe(
            styled_df, 
            use_container_width=True, 
            height=380, 
            hide_index=True,
            column_config={
                "Live_Price": st.column_config.NumberColumn("Live Price", format="₹ %.2f"),
                "Entry": st.column_config.NumberColumn("Entry", format="₹ %.2f"),
                "Stop_Loss": st.column_config.NumberColumn("Stop Loss", format="₹ %.2f"),
                "Target": st.column_config.NumberColumn("Target", format="₹ %.2f"),
                "R:R": st.column_config.ProgressColumn("Risk/Reward", format="1:%.2f", min_value=0, max_value=5),
            }
        )
    else:
        st.warning("No assets currently in confirmed strike zone. Engine is waiting for structural shifts.")

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
            filtered_radar = radar_df if not search_query else radar_df[
                radar_df['Ticker'].str.contains(search_query, case=False, na=False) |
                radar_df['Asset_Class'].str.contains(search_query, case=False, na=False)
            ]

            def highlight_trend(val):
                if val == 'BULLISH': return 'color: #089981; font-weight: 600;'
                elif val == 'BEARISH': return 'color: #f23645; font-weight: 600;'
                return ''

            styled_radar = filtered_radar.style.map(highlight_trend, subset=['Trend'])
            
            st.dataframe(
                styled_radar, 
                use_container_width=True, 
                height=500, 
                hide_index=True,
                column_config={
                    "Live_Price": st.column_config.NumberColumn("Price", format="₹ %.2f"),
                    "Nearest_Demand_OB": st.column_config.NumberColumn("Nearest Demand", format="₹ %.2f"),
                    "Nearest_Supply_OB": st.column_config.NumberColumn("Nearest Supply", format="₹ %.2f"),
                    "Demand_Dist_%": st.column_config.NumberColumn("Demand Dist.", format="%.2f %%"),
                    "Supply_Dist_%": st.column_config.NumberColumn("Supply Dist.", format="%.2f %%"),
                }
            )
        else:
            st.warning("Radar feed is empty.")
    else:
        st.info("Radar feed not found. Run the market scan to compile current data.")

# ------------------------------------------------------------------------------
# TAB 3: INTERACTIVE CHART INSPECTOR
# ------------------------------------------------------------------------------
with tabs[2]:
    st.subheader("📊 Interactive Institutional Chart Inspector")
    st.caption("Plotly visualization showing live Order Blocks (+OB/-OB), Dealing Range, and BOS breaks.")
    
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        selected_ticker = st.selectbox("Search & Select Asset:", full_ticker_list, index=0)
    with c2:
        bars_count = st.slider("Lookback Bars:", min_value=60, max_value=350, value=180, step=20)
    with c3:
        chart_theme = st.selectbox("Theme:", ["light", "dark"], index=0)

    if selected_ticker:
        with st.spinner(f"Computing SMC structure for {selected_ticker}..."):
            data = load_positional_data(selected_ticker, start_date="2022-01-01")
            if data is not None and 'daily' in data and not data['daily'].empty and len(data['daily']) >= 50:
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
# TAB 4: STRATEGY BACKTEST AUDIT (Isolated Outputs)
# ------------------------------------------------------------------------------
with tabs[3]:
    st.subheader("🔬 Client Performance & Backtest Audit")
    st.caption("Historical performance logic using dynamic ATR stops and walk-forward confirmation rules.")
    
    if run_bt:
        if ClientSMCBacktester is None:
            st.error("Backtester module not found.")
        else:
            with st.spinner(f"Backtesting {bt_ticker} on daily timeframe..."):
                tester = ClientSMCBacktester(
                    ticker=bt_ticker, start_date=bt_start, min_rr=bt_min_rr,
                    risk_per_trade_pct=0.01, initial_capital=100000.0
                )
                tester.run_backtest()
                
                if tester.trades:
                    trades_df = pd.DataFrame(tester.trades)
                    wins = len(trades_df[trades_df['pnl_r'] > 0])
                    scratches = len(trades_df[trades_df['pnl_r'] == 0])
                    total = len(trades_df)
                    
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("Total Trades", total)
                    k2.metric("Trade Accuracy (Win+BE)", f"{((wins + scratches) / total) * 100:.2f}%")
                    
                    tot_prof = trades_df[trades_df['pnl_cash'] > 0]['pnl_cash'].sum()
                    tot_loss = abs(trades_df[trades_df['pnl_cash'] < 0]['pnl_cash'].sum())
                    k3.metric("Profit Factor", f"{tot_prof / tot_loss if tot_loss > 0 else 0:.2f}")
                    
                    eq_df = pd.DataFrame(tester.equity_curve).set_index('Date')
                    tot_ret = ((eq_df['Capital'].iloc[-1] - 100000.0) / 100000.0) * 100
                    k4.metric("Net Portfolio Return", f"+{tot_ret:.2f}%")

                    fig_eq = go.Figure()
                    fig_eq.add_trace(go.Scatter(x=eq_df.index, y=eq_df['Capital'], mode='lines', line=dict(color='#2157f3', width=2.5)))
                    fig_eq.update_layout(template="plotly_dark", height=350, margin=dict(l=20, r=20, t=30, b=20))
                    st.plotly_chart(fig_eq, use_container_width=True)

                    st.markdown("#### Executed Trades Ledger")
                    st.dataframe(trades_df[['signal_date', 'direction', 'entry_price', 'exit_price', 'pnl_r', 'capital_after']].tail(25), use_container_width=True, hide_index=True)
                else:
                    st.warning(f"No trades met the {bt_min_rr} R:R criteria for {bt_ticker} since {bt_start}.")
    else:
        st.info("Configure the backtest parameters in the sidebar and click 'Audit Historical Performance' to begin.")
