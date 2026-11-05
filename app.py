import sys
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import os

# Ensure current working directory is in sys.path
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
    initial_sidebar_state="expanded"
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
# 1. ENTERPRISE DATA INGESTION 
# ==============================================================================
@st.cache_data(ttl=3600)
def fetch_enterprise_data():
    """Reads pre-computed EOD data directly from the GitHub repository."""
    radar_url = "https://raw.githubusercontent.com/AmayNigam/smc-institutional-terminal/main/SMC_MASTER_RADAR_FEED.csv"
    alerts_url = "https://raw.githubusercontent.com/AmayNigam/smc-institutional-terminal/main/SMC_ACTIONABLE_ALERTS.csv"
    
    try:
        r_df = pd.read_csv(radar_url)
        a_df = pd.read_csv(alerts_url)
        
        if not a_df.empty and 'Direction' not in a_df.columns:
            a_df = pd.DataFrame(columns=['Ticker', 'Asset_Class', 'Direction', 'Live_Price', 'Entry', 'Stop_Loss', 'Target', 'R:R', 'OB_Date'])
        if not r_df.empty and 'Trend' not in r_df.columns:
            r_df = pd.DataFrame(columns=['Ticker', 'Asset_Class', 'Live_Price', 'Trend', 'Nearest_Demand_OB', 'Demand_Dist_%', 'Nearest_Supply_OB', 'Supply_Dist_%'])
            
        if not a_df.empty and 'Asset_Class' in a_df.columns:
            a_df = a_df.sort_values(by=['Asset_Class', 'Ticker'], ascending=[True, True])
        if not r_df.empty and 'Asset_Class' in r_df.columns:
            r_df = r_df.sort_values(by=['Asset_Class', 'Ticker'], ascending=[True, True])
            
        return r_df, a_df
    except Exception:
        return pd.DataFrame(columns=['Ticker', 'Asset_Class', 'Direction', 'Live_Price', 'Entry', 'Stop_Loss', 'Target', 'R:R', 'OB_Date']), \
               pd.DataFrame(columns=['Ticker', 'Asset_Class', 'Live_Price', 'Trend', 'Nearest_Demand_OB', 'Demand_Dist_%', 'Nearest_Supply_OB', 'Supply_Dist_%'])

# ==============================================================================
# 2. INITIALIZE SESSION STATE (The Gatekeeper)
# ==============================================================================
if "is_registered" not in st.session_state:
    st.session_state.is_registered = False

# ==============================================================================
# 3. ONBOARDING & REGISTRATION PAGE
# ==============================================================================
def show_registration_page():
    st.markdown("<h1 style='text-align: center; color: #58a6ff; margin-top: 50px;'>⚡ Welcome to Alpha Flow</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #8b949e; font-size: 1.2rem;'>Institutional Smart Money Concepts (SMC) Terminal</p><br><br>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.info("**What does this tool do?**\n\nAlpha Flow is an automated quantitative engine. Every day after market close, it scans over 2,600+ assets on the National Stock Exchange (NSE) and global commodities. It uses institutional algorithms to detect Fair Value Gaps (FVGs), Order Blocks, and Liquidity Sweeps, filtering the noise to show you only the highest-probability strike zones.")
        st.markdown("<br>", unsafe_allow_html=True)
        
        with st.form("registration_form"):
            st.markdown("#### Request Terminal Access")
            name = st.text_input("Full Name")
            email = st.text_input("Professional Email Address")
            submit = st.form_submit_button("Unlock Live Terminal", use_container_width=True, type="primary")
            
            if submit:
                if name and email:
                    st.session_state.is_registered = True
                    st.rerun()
                else:
                    st.error("Please provide both your name and email to access the quantitative data.")

# ==============================================================================
# 4. MAIN TERMINAL & NAVIGATION PANEL
# ==============================================================================
def show_main_terminal():
    st.sidebar.markdown("<h2 style='color: #58a6ff;'>⚡ Alpha Flow</h2>", unsafe_allow_html=True)
    st.sidebar.caption("SMC Terminal v1.0")
    st.sidebar.divider()
    
    nav_choice = st.sidebar.radio("Navigation Menu", ["Live Market Dashboard", "📖 How to Trade Setups"], index=0)
    
    st.sidebar.divider()
    st.sidebar.success(f"🟢 Connected to GitHub Data Lake")
    
    if nav_choice == "📖 How to Trade Setups":
        st.title("📖 Standard Operating Procedure")
        st.markdown("""
        ### Institutional SMC Execution Guide
        
        **1. Check the Actionable Strikes Tab**
        * Assets listed here have triggered a structural reversal within a confirmed institutional supply/demand block. 
        * Do not execute blindly. This is a watchlist of high-probability zones.
        
        **2. Verify the Structure (Chart Inspector)**
        * Navigate to the 'Interactive Chart Inspector' tab.
        * Search for the triggered asset.
        * Ensure the price has swept liquidity and created a valid Fair Value Gap (FVG) in your intended direction.
        
        **3. Risk Management Engine**
        * Never risk more than 1% of your total equity on a single strike.
        * Ensure the R:R (Risk/Reward) profile on the dashboard is at least 1:2.0 before placing orders.
        * Stop losses must be placed strictly behind the originating Order Block (-OB for shorts, +OB for longs).
        """)
        return 

    if nav_choice == "Live Market Dashboard":
        st.markdown("<h1 style='text-align: center; color: #58a6ff;'>⚡ Alpha Flow Quantitative Terminal</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #8b949e; font-size: 1.2rem;'>Institutional Smart Money Concepts (SMC) State-Machine Engine | <span style='color: #2ea043;'>🟢 Live Market Data</span></p>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        radar_df, alerts_df = fetch_enterprise_data()

        hud_total = len(alerts_df) if not alerts_df.empty else 0
        hud_longs = len(alerts_df[alerts_df['Direction'].str.contains('LONG', na=False)]) if hud_total > 0 else 0
        hud_shorts = len(alerts_df[alerts_df['Direction'].str.contains('SHORT', na=False)]) if hud_total > 0 else 0
        
        # BUG FIX: Safely calculate R:R without throwing NaN errors when empty
        if hud_total > 0 and 'R:R' in alerts_df.columns and not alerts_df['R:R'].dropna().empty:
            hud_rr = round(float(alerts_df['R:R'].max()), 2)
        else:
            hud_rr = 0.0

        if not radar_df.empty:
            full_ticker_list = sorted([str(t) for t in radar_df["Ticker"].dropna().unique() if str(t).strip()])
        else:
            full_ticker_list = ["RELIANCE.NS", "HDFCBANK.NS", "TRUALT.NS"]

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
                        {'range': [0, 45], 'color': "rgba(242, 54, 69, 0.8)"},
                        {'range': [45, 55], 'color': "rgba(139, 148, 158, 0.4)"},
                        {'range': [55, 100], 'color': "rgba(46, 160, 67, 0.8)"}
                    ]
                }
            ))
            fig_gauge.update_layout(height=250, margin=dict(l=20, r=20, t=40, b=20), paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_gauge, use_container_width=True)

        with c3:
            st.metric("🟢 Long Bias Setups", hud_longs)
            st.metric("🔴 Short Bias Setups", hud_shorts)

        st.markdown("---")

        COMMODITY_MAP = {
            "GC=F": "Gold (USD)", "SI=F": "Silver (USD)", "CL=F": "Crude Oil (USD)",
            "BZ=F": "Brent Crude (USD)", "HG=F": "Copper (USD)", "NG=F": "Natural Gas (USD)",
            "PA=F": "Palladium (USD)", "PL=F": "Platinum (USD)"
        }

        def format_price(row, col_name):
            val = row.get(col_name, "None")
            if pd.isna(val) or val == 'None' or str(val).strip() == '': return "None"
            try:
                val_float = float(val)
                if "COMMODITY" in str(row.get('Asset_Class', '')): return f"$ {val_float:,.2f}"
                else: return f"₹ {val_float:,.2f}"
            except:
                return val

        tabs = st.tabs(["🎯 Actionable Strike Alerts", "📡 Master Radar Board", "📊 Interactive Chart Inspector", "🔬 Strategy Backtest Audit"])

        with tabs[0]:
            st.subheader("Actionable Strike Setups")
            st.caption("Confirmed entries meeting structural reversal rules within the immediate institutional strike zone.")
            
            if hud_total > 0:
                alerts_display = alerts_df.copy()
                alerts_display['Asset'] = alerts_display['Ticker'].map(lambda x: COMMODITY_MAP.get(x, str(x).replace('.NS', '')))
                
                for col in ['Live_Price', 'Entry', 'Stop_Loss', 'Target']:
                    if col in alerts_display.columns:
                        alerts_display[col] = alerts_display.apply(lambda row: format_price(row, col), axis=1)

                def highlight_direction(val):
                    if 'LONG' in str(val): return 'background-color: rgba(46, 160, 67, 0.2); color: #2ea043; font-weight: bold; border-left: 4px solid #2ea043;'
                    elif 'SHORT' in str(val): return 'background-color: rgba(242, 54, 69, 0.2); color: #f23645; font-weight: bold; border-left: 4px solid #f23645;'
                    return ''
                
                styled_df = alerts_display.style.map(highlight_direction, subset=['Direction'])
                
                st.dataframe(
                    styled_df, use_container_width=True, height=400, hide_index=True,
                    column_order=["Asset", "Asset_Class", "Direction", "Live_Price", "Entry", "Stop_Loss", "Target", "R:R", "OB_Date"],
                    column_config={
                        "Asset": st.column_config.TextColumn("Asset", width="medium"),
                        "Live_Price": st.column_config.TextColumn("Live Price"),
                        "Entry": st.column_config.TextColumn("Entry"),
                        "Stop_Loss": st.column_config.TextColumn("Stop Loss"),
                        "Target": st.column_config.TextColumn("Target"),
                        "R:R": st.column_config.ProgressColumn("Risk/Reward Profile", format="1:%.2f", min_value=0, max_value=5),
                    }
                )
            else:
                st.info("No assets currently in confirmed strike zone. Engine is waiting for structural shifts.")

        with tabs[1]:
            st.subheader("Global Asset Structure Radar")
            st.caption("Complete structural mapping of every scanned asset relative to nearest Supply and Demand blocks.")
            
            if not radar_df.empty:
                search_query = st.text_input("Filter Asset / Class:", placeholder="e.g. RELIANCE, Gold, COMMODITY...")
                
                radar_display = radar_df.copy()
                radar_display['Asset'] = radar_display['Ticker'].map(lambda x: COMMODITY_MAP.get(x, str(x).replace('.NS', '')))
                
                filtered_radar = radar_display if not search_query else radar_display[
                    radar_display['Asset'].str.contains(search_query, case=False, na=False) |
                    radar_display['Asset_Class'].str.contains(search_query, case=False, na=False)
                ]

                for col in ['Live_Price', 'Nearest_Demand_OB', 'Nearest_Supply_OB']:
                    if col in filtered_radar.columns:
                        filtered_radar[col] = filtered_radar.apply(lambda row: format_price(row, col), axis=1)

                # BUG FIX: Safely handle 'None' strings before converting to float
                def heatmap_distance(val):
                    if pd.isna(val) or val == 'None' or str(val).strip() == '': return ''
                    try:
                        v = float(val)
                        if abs(v) <= 1.5: return 'background-color: rgba(210, 153, 34, 0.4); color: #d29922; font-weight: bold;' 
                        elif v > 1.5 and v <= 5.0: return 'color: #8b949e;' 
                        else: return 'color: #484f58;' 
                    except:
                        return ''

                def highlight_trend(val):
                    if val == 'BULLISH' or 'LONG' in str(val): return 'color: #2ea043; font-weight: bold;'
                    elif val == 'BEARISH' or 'SHORT' in str(val): return 'color: #f23645; font-weight: bold;'
                    return 'color: #8b949e;'

                styled_radar = filtered_radar.style\
                    .map(highlight_trend, subset=['Trend'])\
                    .map(heatmap_distance, subset=['Demand_Dist_%', 'Supply_Dist_%'])
                
                st.dataframe(
                    styled_radar, use_container_width=True, height=500, hide_index=True,
                    column_order=["Asset", "Asset_Class", "Live_Price", "Trend", "Nearest_Demand_OB", "Demand_Dist_%", "Nearest_Supply_OB", "Supply_Dist_%"],
                    column_config={
                        "Asset": st.column_config.TextColumn("Asset", width="medium"),
                        "Live_Price": st.column_config.TextColumn("Price"),
                        "Nearest_Demand_OB": st.column_config.TextColumn("Nearest Demand"),
                        "Nearest_Supply_OB": st.column_config.TextColumn("Nearest Supply"),
                        "Demand_Dist_%": st.column_config.NumberColumn("Demand Dist. (Gold = Hot)", format="%.2f %%"),
                        "Supply_Dist_%": st.column_config.NumberColumn("Supply Dist. (Gold = Hot)", format="%.2f %%"),
                    }
                )
            else:
                st.info("Radar feed not found in cloud cache. Wait for next automated backend scan.")

        with tabs[2]:
            st.subheader("Interactive Institutional Chart Inspector")
            st.caption("Plotly visualization showing live Order Blocks (+OB/-OB), Dealing Range, and BOS breaks.")
            
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1: selected_ticker = st.selectbox("Search & Select Asset:", full_ticker_list, index=0)
            with c2: bars_count = st.slider("Lookback Bars:", min_value=60, max_value=350, value=180, step=20)
            with c3: chart_theme = st.selectbox("Theme:", ["dark", "light"], index=0)

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

        with tabs[3]:
            st.subheader("Client Performance & Backtest Audit")
            st.caption("Historical performance logic using dynamic ATR stops and walk-forward confirmation rules.")
            
            st.markdown("###### Audit Configuration")
            bt_col1, bt_col2, bt_col3, bt_col4 = st.columns([2, 2, 2, 2])

            with bt_col1: bt_ticker = st.selectbox("Target Asset:", full_ticker_list, index=0, key="bt_ticker")
            with bt_col2: bt_start = st.selectbox("Historical Start:", ["2020-01-01", "2021-01-01", "2022-01-01"], index=0)
            with bt_col3: bt_min_rr = st.number_input("Min R:R Threshold:", min_value=1.0, max_value=5.0, value=1.0, step=0.5)
            with bt_col4: 
                st.markdown("<br>", unsafe_allow_html=True)
                run_bt = st.button("⚙️ Audit Historical Performance", use_container_width=True, type="primary")
                
            st.divider()
            
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
                            k2.metric("Trade Accuracy", f"{((wins + scratches) / total) * 100:.2f}%")
                            
                            tot_prof = trades_df[trades_df['pnl_cash'] > 0]['pnl_cash'].sum()
                            tot_loss = abs(trades_df[trades_df['pnl_cash'] < 0]['pnl_cash'].sum())
                            k3.metric("Profit Factor", f"{tot_prof / tot_loss if tot_loss > 0 else 0:.2f}")
                            
                            eq_df = pd.DataFrame(tester.equity_curve).set_index('Date')
                            tot_ret = ((eq_df['Capital'].iloc[-1] - 100000.0) / 100000.0) * 100
                            k4.metric("Net Portfolio Return", f"+{tot_ret:.2f}%")

                            chart_col1, chart_col2 = st.columns(2)
                            
                            with chart_col1:
                                st.markdown("**Cumulative Equity Curve**")
                                fig_eq = go.Figure()
                                fig_eq.add_trace(go.Scatter(x=eq_df.index, y=eq_df['Capital'], mode='lines', fill='tozeroy', line=dict(color='#1f6feb', width=2), fillcolor='rgba(31, 111, 235, 0.1)'))
                                fig_eq.update_layout(template="plotly_dark", height=300, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                                st.plotly_chart(fig_eq, use_container_width=True)

                            with chart_col2:
                                st.markdown("**Historical Drawdown Profile**")
                                eq_df['Peak'] = eq_df['Capital'].cummax()
                                eq_df['Drawdown'] = (eq_df['Capital'] - eq_df['Peak']) / eq_df['Peak'] * 100
                                fig_dd = go.Figure()
                                fig_dd.add_trace(go.Scatter(x=eq_df.index, y=eq_df['Drawdown'], mode='lines', fill='tozeroy', line=dict(color='#f23645', width=1), fillcolor='rgba(242, 54, 69, 0.2)'))
                                fig_dd.update_layout(template="plotly_dark", height=300, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis=dict(title="% Drawdown"))
                                st.plotly_chart(fig_dd, use_container_width=True)

                            st.markdown("#### Executed Trades Ledger")
                            st.dataframe(trades_df[['signal_date', 'direction', 'entry_price', 'exit_price', 'pnl_r', 'capital_after']].tail(25), use_container_width=True, hide_index=True)
                        else:
                            st.warning(f"No trades met the {bt_min_rr} R:R criteria for {bt_ticker} since {bt_start}.")

# ==============================================================================
# 5. APP ROUTER
# ==============================================================================
if not st.session_state.is_registered:
    show_registration_page()
else:
    show_main_terminal()
