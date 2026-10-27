import os
import sys
import time
import pandas as pd
import numpy as np

# ==============================================================================
# PRODUCTION GUARDRAILS: SCHEMAS, CIRCUITS & LIQUIDITY FILTERS
# ==============================================================================

ALERT_SCHEMA = [
    'Ticker', 'Asset_Class', 'Direction', 'Live_Price',
    'Entry', 'Stop_Loss', 'Target', 'R:R', 'OB_Date'
]

RADAR_SCHEMA = [
    'Ticker', 'Asset_Class', 'Live_Price', 'Trend',
    'Nearest_Demand_OB', 'Demand_Dist_%', 'Nearest_Supply_OB', 'Supply_Dist_%'
]

def is_liquid_and_tradable(df, is_commodity=False):
    """Filters out penny stocks, illiquid instruments, and circuit-locked candles."""
    if df is None or len(df) < 20:
        return False

    latest = df.iloc[-1]

    # 1. Circuit filter: High == Low indicates a locked upper/lower circuit
    if latest['High'] == latest['Low']:
        return False

    # 2. Zero volume check
    if latest['Volume'] <= 0:
        return False

    # 3. Liquidity filter for NSE equities (Minimum Average Daily Turnover of ₹50 Lakhs)
    if not is_commodity:
        recent_20 = df.tail(20)
        daily_turnover = recent_20['Close'] * recent_20['Volume']
        if daily_turnover.mean() < 5000000:  
            return False

    return True

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from data_loader import load_positional_data
from smc_engine import SMCEngine
from smc_state_machine import SMCMitigationTracker
from universe import get_tickers_by_category

from smc_state_machine import SMCMitigationTracker, ICTSweepAndShiftEngine

def scan_single_ticker(ticker: str, asset_class: str, ticker_df: pd.DataFrame, proximity_pct: float = 0.05):
    try:
        if ticker_df is None or len(ticker_df) < 100: return None, []
        if not is_liquid_and_tradable(ticker_df, is_commodity=("=" in ticker)): return None, []

        engine = SMCEngine(ticker_df, swing_length=3)
        smc_df = engine.run_all()
        current_price = smc_df['Close'].iloc[-1]

        # 1. Run the new ICT State Machine
        ict_engine = ICTSweepAndShiftEngine(smc_df)
        final_state = ict_engine.run_state_machine()

        # Calculate distances if the levels exist
        sweep_low = final_state.get('sweep_low', None)
        sweep_high = final_state.get('sweep_high', None)
        
        dist_demand_pct = round(((current_price - sweep_low) / current_price) * 100, 2) if pd.notna(sweep_low) and current_price > 0 else None
        dist_supply_pct = round(((sweep_high - current_price) / current_price) * 100, 2) if pd.notna(sweep_high) and current_price > 0 else None

        # 2. Basic Radar Record (Status of asset)
        radar_record = {
            'Ticker': ticker,
            'Asset_Class': asset_class,
            'Live_Price': round(current_price, 2),
            'Trend': final_state.get('current_state', 'SEARCHING'),
            'Nearest_Demand_OB': round(sweep_low, 2) if pd.notna(sweep_low) else None,
            'Demand_Dist_%': dist_demand_pct,
            'Nearest_Supply_OB': round(sweep_high, 2) if pd.notna(sweep_high) else None,
            'Supply_Dist_%': dist_supply_pct
        }

        actionable_setups = []

        # 3. Output strictly validated actionable alerts
        if final_state['current_state'] == "MSS_CONFIRMED":
            entry = final_state['entry_price']
            stop = final_state['stop_loss']
            target = final_state['target']
            
            # BUG FIX 2: Prevent ZeroDivisionError on flat candles
            risk = abs(entry - stop)
            if risk == 0:
                risk = 0.05  # Minimum tick size fallback
                
            reward = abs(target - entry)
            rr = round(reward / risk, 2)

            # Only output if price hasn't run away from the entry yet
            if (final_state['direction'] == 'LONG' and current_price <= entry * 1.02) or \
               (final_state['direction'] == 'SHORT' and current_price >= entry * 0.98):
                
                actionable_setups.append({
                    'Ticker': ticker,
                    'Asset_Class': asset_class,
                    'Direction': f"{'🟢 LONG' if final_state['direction'] == 'LONG' else '🔴 SHORT'} (Sweep & Shift)",
                    'Live_Price': round(current_price, 2),
                    'Entry': round(entry, 2),
                    'Stop_Loss': round(stop, 2),
                    'Target': round(target, 2),
                    'R:R': round(rr, 2),
                    'OB_Date': final_state['date']
                })

        return radar_record, actionable_setups
    except Exception as e:
        return None, []

def run_master_market_scan(
    scan_commodities: bool = True, 
    scan_nifty_core: bool = True, 
    scan_all_nse: bool = False,
    proximity_pct: float = 0.05
):
    scan_queue = []

    if scan_commodities:
        comm_tickers = get_tickers_by_category("COMMODITIES_GLOBAL")
        for t in comm_tickers:
            scan_queue.append((t, "COMMODITY"))

    if scan_nifty_core and not scan_all_nse:
        nifty_tickers = get_tickers_by_category("NIFTY_50_CORE")
        for t in nifty_tickers:
            scan_queue.append((t, "EQUITY_NIFTY50"))

    if scan_all_nse:
        all_nse_tickers = get_tickers_by_category("NSE_ALL")
        for t in all_nse_tickers:
            scan_queue.append((t, "EQUITY_NSE"))

    print(f"\n{'='*75}")
    print(f" LAUNCHING CLIENT-READY SMC SCAN: {len(scan_queue)} Total Assets In Queue")
    print(f" Filters: Reversal Confirmation | Swing Targets | FVG Confluence")
    print(f"{'='*75}\n")

    all_radar_records = []
    all_actionable_alerts = []

    import yfinance as yf
    from data_loader import clean_ohlcv_data

   # 1. Pre-fetch all data in chunked batches to prevent Yahoo Finance rate limits
    import time
    tickers = [t[0] for t in scan_queue]
    print(f"[*] Pre-fetching batch market data for {len(tickers)} assets in chunks...")
    
    batch_raw = pd.DataFrame()
    chunk_size = 100
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        print(f"    -> Fetching chunk {i//chunk_size + 1} ({len
