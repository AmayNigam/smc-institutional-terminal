import sys
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go

# Ensure current working directory is in sys.path
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_loader import load_positional_data
from smc_engine import SMCEngine
from smc_state_machine import SMCMitigationTracker
from charting_engine import SMCChartEngine
from universe import ASSET_UNIVERSES, get_tickers_by_category

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
# STREAMLIT PAGE CONFIGURATION & HIGH-END CSS
# ==============================================================================
st.set_page_config(
    page_title="Alpha Flow | SMC Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom Styling for Premium Institutional Dark Mode
st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        .main {background-color: #0b0f19;}
        
        div[data-testid="metric-container"] {
            background: linear-gradient(145deg, #161b22, #0d1117);
            border: 1px solid #30363d;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
            text-align: center;
        }
        
        div[data-testid="metric-container"] label {
            color: #8b949e !important;
            font-size: 1.1rem !important;
            font-weight: 600 !important;
            letter-spacing: 0.5px;
        }
        
        div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
            color: #e6edf3 !important;
            font-size: 2.5rem !important;
            font-weight: 700 !important;
        }

        .stTabs [data-baseweb="tab-list"] {gap: 12px;}
        .stTabs [data-baseweb="tab"] {
            background-color: #161b22;
            border-radius: 8px 8px 0px 0px;
            padding: 10px 24px;
            border: 1px solid #30363d;
            border-bottom: none;
            color: #8b949e;
            font-weight: 600;
        }
        .stTabs [aria-selected="true"] {
            background-color: #1f6feb !important;
            color: #ffffff !important;
        }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# PROFESSIONAL HEADER 
# ==============================================================================
st.markdown("<h1 style='text-align: center; color: #58a6ff;'>⚡ Alpha Flow Quantitative Terminal</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #8b949e; font-size: 1.2rem;'>Institutional Smart Money Concepts (SMC) State-Machine Engine | <span style='color: #2ea043;'>🟢 Live Market Data</span></p>", unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

# ==============================================================================
# ENTERPRISE DATA INGESTION (READ-ONLY CLOUD CACHE)
# ==============================================================================
@st.cache_data(ttl=3600) # Caches the data in RAM for 1 hour
def fetch_enterprise_data():
    """Reads pre-computed EOD data directly from the GitHub repository."""
    radar_url = "https://raw.githubusercontent.com/AmayNigam/smc-institutional-terminal/main/SMC_MASTER_RADAR_FEED.csv"
    alerts_url = "https://raw.githubusercontent.com/AmayNigam/smc-institutional-terminal/main/SMC_ACTIONABLE_ALERTS.csv"
    
    try:
        r_df = pd.read_csv(radar_url)
        a_df = pd.read_csv(alerts_url)
        return r_df, a_df
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

# Fetch data instantly from GitHub cloud
radar_df, alerts_df = fetch_enterprise_data()

# ------------------------------------------------------------------------------
# DYNAMIC VARIABLE ASSIGNMENT (Feeds HUD, Charts, and Backtester)
# ------------------------------------------------------------------------------
hud_total = len(alerts_df) if not alerts_df.empty else 0
hud_longs = len(alerts_df[alerts_df['Direction'].str.contains('LONG', na=False)]) if not alerts_df.empty else 0
hud_shorts = len(alerts_df[alerts_df['Direction'].str.contains('SHORT', na=False)]) if not alerts_df.empty else 0
hud_rr = alerts_df['R:R'].max() if (not alerts_df.empty and 'R:R' in alerts_df.columns) else 0.0

if not radar_df.empty:
    full_ticker_list = sorted([str(t) for t in radar_df["Ticker"].dropna().unique() if str(t).strip()])
else:
    full_ticker_list = ["RELIANCE.NS", "HDFCBANK.NS", "TRUALT.NS"]

# ==============================================================================
# THE MACRO DASHBOARD HUD
# ==============================================================================
c1, c2, c3 = st.columns([1, 2, 1])

with c1:
    st.metric("🎯 Total Active Strikes", hud_total, delta="Awaiting Execution" if hud_total > 0 else "Scanning...")
    st.metric("💎 Peak Available R:R", f"1 : {hud_rr}", delta="Optimized" if hud_rr >= 2.0 else "Sub-optimal")

with c2:
    bias_score = (hud_longs / hud_total * 100) if hud_total > 0 else 50
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = bias_score,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "Market Liquidity Bias", 'font': {'size': 18, 'color': '#8b949e'}},
        number = {'suffix': "% Long", 'font': {'color': '#e6edf3'}},
        gauge = {
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#30363d"},
            'bar': {'color': "rgba(255,255,255,0.3)", 'thickness': 0.2},
            'bgcolor': "#0b0f19",
            'borderwidth': 2,
            'bordercolor': "#30363d",
            'steps': [
                {'range': [0, 45], 'color': "rgba(242, 54, 69, 0.8)"},   # Bearish Red
                {'range': [45, 55], 'color': "rgba(139, 148, 158, 0.4)"}, # Neutral Gray
                {'range': [55, 100], 'color': "rgba(46, 160, 67, 0.8)"}   # Bullish Green
            ]
        }
    ))
    fig_gauge.update_layout(height=250, margin=dict(l=20, r=20, t=40, b=20), paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_gauge, use_container_width=True)

with c3:
    st.metric("🟢 Long Bias Setups", hud_longs)
    st.metric("🔴 Short Bias Setups", hud_shorts)

st.markdown("---")

# ------------------------------------------------------------------------------
# HELPER DICTIONARY FOR COMMODITIES
# ------------------------------------------------------------------------------
COMMODITY_MAP = {
    "GC=F": "Gold (USD)",
    "SI=F": "Silver (USD)",
    "CL=F": "Crude Oil (USD)",
    "BZ=F": "Brent Crude (USD)",
    "HG=F": "Copper (USD)",
    "NG=F": "Natural Gas (USD)",
    "PA=F": "Palladium (USD)",
    "PL=F": "Platinum (USD)"
}

def format_price(row, col_name):
    """Dynamically formats price based on asset class"""
    val = row[col_name]
    if pd.isna(val) or val == 'None':
        return "None"
    try:
        val_float = float(val)
        if "COMMODITY" in str(row['Asset_Class']):
            return f"$ {val_float:,.2f}"
        else:
            return f"₹ {val_float:,.2f}"
    except:
        return val

# ==============================================================================
# MAIN DASHBOARD TABS
# ==============================================================================
tabs = st.tabs([
    "🎯 Actionable Strike Alerts", 
    "📡 Master Radar Board", 
    "📊 Interactive Chart Inspector", 
    "🔬 Strategy Backtest Audit"
])

# ------------------------------------------------------------------------------
# TAB 1: ACTIONABLE STRIKE ALERTS 
# ------------------------------------------------------------------------------
with tabs[0]:
    st.subheader("Actionable Strike Setups")
    st.caption("Confirmed entries meeting structural reversal rules within the immediate institutional strike zone.")
    
    if not alerts_df.empty:
        alerts_display = alerts_df.copy()
        alerts
