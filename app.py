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
    page_title="Alpha Flow | SMC Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling for Sleek Institutional Look
st.markdown("""
    <style>
        /* Hide Streamlit default menus and footers */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}

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
# PROFESSIONAL HEADER
# ==============================================================================
st.title("⚡ Alpha Flow Quantitative Terminal")
st.markdown("**Institutional Smart Money Concepts (SMC) State-Machine Engine** | 🟢 Live Market Data")
st.markdown("---")

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

            styled_df = alerts_df.style.map(highlight_direction, subset=['Direction'])
            # HIDE INDEX ADDED HERE
            st.dataframe(styled_df, use_container_width=True, height=380, hide_index=True)
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

            styled_radar = filtered_radar.style.map(highlight_trend, subset=['Trend'])
            # HIDE INDEX ADDED HERE
            st.dataframe(styled_radar, use_container_width=True, height=500, hide_index=True)
        else:
            st.warning("Radar feed is empty.")
    else:
        st.info("Radar feed not found. Run the market scan to compile current data.")

# ------------------------------------------------
