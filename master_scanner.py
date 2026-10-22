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

def scan_single_ticker(ticker: str, asset_class: str, ticker_df: pd.DataFrame, proximity_pct: float = 0.05):
    try:
        # Evaluate the pre-loaded dataframe instead of fetching it
        if ticker_df is None or ticker_df.empty or len(ticker_df) < 200:
            return None, []

        # --- NEW LIQUIDITY & CIRCUIT FILTER ---
        is_comm = ("=" in ticker) or ticker.endswith("=F")
        if not is_liquid_and_tradable(ticker_df, is_commodity=is_comm):
            return None, []
        # --------------------------------------

        engine = SMCEngine(ticker_df, swing_length=3)
        smc_df = engine.run_all()

        tracker = SMCMitigationTracker(smc_df)
        tracker.run_tracking()

        current_row = smc_df.iloc[-1]
        current_price = current_row['Close']
        c_open = current_row['Open']
        c_high = current_row['High']
        c_low = current_row['Low']
        c_ema200 = current_row.get('EMA_200', np.nan)
        current_date = smc_df.index[-1].strftime('%Y-%m-%d')
        
        is_uptrend = current_price > c_ema200 if not pd.isna(c_ema200) else True
        is_downtrend = current_price < c_ema200 if not pd.isna(c_ema200) else True

        bull_obs_below = [ob for ob in tracker.active_bullish_obs if ob.top <= current_price]
        nearest_demand_ob = max(bull_obs_below, key=lambda x: x.top) if bull_obs_below else None
        
        bear_obs_above = [ob for ob in tracker.active_bearish_obs if ob.bottom >= current_price]
        nearest_supply_ob = min(bear_obs_above, key=lambda x: x.bottom) if bear_obs_above else None

        dist_demand_pct = round(((current_price - nearest_demand_ob.top) / current_price) * 100, 2) if nearest_demand_ob else None
        dist_supply_pct = round(((nearest_supply_ob.bottom - current_price) / current_price) * 100, 2) if nearest_supply_ob else None

        radar_record = {
            'Ticker': ticker,
            'Asset_Class': asset_class,
            'Live_Price': round(current_price, 2),
            'Date': current_date,
            'Nearest_Demand_OB': round(nearest_demand_ob.top, 2) if nearest_demand_ob else None,
            'Demand_Dist_%': dist_demand_pct,
            'Nearest_Supply_OB': round(nearest_supply_ob.bottom, 2) if nearest_supply_ob else None,
            'Supply_Dist_%': dist_supply_pct,
            'Trend': 'BULLISH' if is_uptrend else 'BEARISH'
        }

        actionable_setups = []

        # ==========================================
        # INSTITUTIONAL LIQUIDITY SWEEP LOGIC
        # ==========================================
        # Instead of 1 bar, we look at the last 3 days to see if the market swept the zone
        trigger_window = ticker_df.tail(3) 

        # 1. LONG ALERTS (Bullish Strike Zone)
        if is_uptrend:
            for ob in tracker.active_bullish_obs:
                
                # --- NEW: FVG CONFLUENCE RULE ---
                # A high-probability OB must create an FVG within the next 4 candles
                try:
                    ob_idx = smc_df.index.get_loc(ob.created_at)
                    has_fvg = smc_df['Bullish_FVG'].iloc[ob_idx : min(ob_idx + 5, len(smc_df))].any()
                except KeyError:
                    has_fvg = True 
                    
                if not has_fvg:
                    continue # Skip this setup: the Order Block lacks FVG displacement
                    
                # Retest: Did price dip into the OB during the last 3 days?
                ob_retested = trigger_window['Low'].min() <= ob.top
                
                # Liquidity Sweep: Did price wick BELOW the OB bottom, but current close is safely ABOVE it?
                liquidity_swept = (trigger_window['Low'].min() < ob.bottom) and (current_price >= ob.bottom)
                
                # Reversal: Did current candle close green (buyers stepped in)?
                bullish_rejection = current_price > c_open
                
                if ob_retested and liquidity_swept and bullish_rejection:
                    
                    # Target and SL Math
                    entry = current_price
                    stop = trigger_window['Low'].min() * 0.998 # SL slightly below the sweep wick
                    
                    target = getattr(ob, 'swing_target', np.nan)
                    # Fallback target if swing target is missing
                    if pd.isna(target) or target <= entry:
                        target = smc_df['Last_Swing_High'].iloc[-1] if 'Last_Swing_High' in smc_df.columns else np.nan
                        if pd.isna(target) or target <= entry:
                             target = entry + (1.5 * (entry - stop))
                        
                    risk = entry - stop
                    rr = (target - entry) / risk if risk > 0 else 0
                    
                    # EXECUTION & LOGGING
                    if rr >= 1.0:
                        actionable_setups.append({
                            'Ticker': ticker,
                            'Asset_Class': asset_class,
                            'Direction': '🟢 LONG (OB+FVG Sweep)',
                            'Live_Price': round(current_price, 2),
                            'Entry': round(entry, 2),
                            'Stop_Loss': round(stop, 2),
                            'Target': round(target, 2),
                            'R:R': round(rr, 2),
                            'OB_Date': str(ob.created_at.date() if hasattr(ob.created_at, 'date') else ob.created_at)
                        })
                        break 

        # 2. SHORT ALERTS (Bearish Strike Zone)
        if is_downtrend:
            for ob in tracker.active_bearish_obs:
                
                # --- NEW: FVG CONFLUENCE RULE ---
                try:
                    ob_idx = smc_df.index.get_loc(ob.created_at)
                    has_fvg = smc_df['Bearish_FVG'].iloc[ob_idx : min(ob_idx + 5, len(smc_df))].any()
                except KeyError:
                    has_fvg = True 
                    
                if not has_fvg:
                    continue # Skip this setup: the Order Block lacks FVG displacement
                    
                # Retest: Did price spike into the OB during the last 3 days?
                ob_retested = trigger_window['High'].max() >= ob.bottom
                
                # Liquidity Sweep: Did price wick ABOVE the OB top, but current close is safely BELOW it?
                liquidity_swept = (trigger_window['High'].max() > ob.top) and (current_price <= ob.top)
                
                # Reversal: Did current candle close red (sellers stepped in)?
                bearish_rejection = current_price < c_open
                
                if ob_retested and liquidity_swept and bearish_rejection:
                    
                    entry = current_price
                    stop = trigger_window['High'].max() * 1.002 # SL slightly above the sweep wick
                    
                    target = getattr(ob, 'swing_target', np.nan)
                    if pd.isna(target) or target >= entry:
                        target = smc_df['Last_Swing_Low'].iloc[-1] if 'Last_Swing_Low' in smc_df.columns else np.nan
                        if pd.isna(target) or target >= entry:
                             target = entry - (1.5 * (stop - entry))
                             
                    risk = stop - entry
                    rr = (entry - target) / risk if risk > 0 else 0
                    
                    if rr >= 1.0:
                        actionable_setups.append({
                            'Ticker': ticker,
                            'Asset_Class': asset_class,
                            'Direction': '🔴 SHORT (OB+FVG Sweep)',
                            'Live_Price': round(current_price, 2),
                            'Entry': round(entry, 2),
                            'Stop_Loss': round(stop, 2),
                            'Target': round(target, 2),
                            'R:R': round(rr, 2),
                            'OB_Date': str(ob.created_at.date() if hasattr(ob.created_at, 'date') else ob.created_at)
                        })
                        break

        return radar_record, actionable_setups

    except Exception as e:
        print(f"[!] Warning: Error scanning {ticker}: {e}")
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

    # 1. Pre-fetch all data in one multithreaded network call BEFORE the loop
    tickers = [t[0] for t in scan_queue]
    print(f"[*] Pre-fetching batch market data for {len(tickers)} assets...")
    batch_raw = yf.download(tickers, start="2022-01-01", interval="1d", group_by="ticker", threads=True)

    # 2. Iterate through the in-memory batch instead of making network calls
    for idx, (ticker, asset_class) in enumerate(scan_queue):
        # Extract and clean data for the specific ticker safely
        try:
            raw_df = batch_raw[ticker].dropna(how='all') if len(tickers) > 1 else batch_raw.dropna(how='all')
            ticker_df = clean_ohlcv_data(raw_df)
        except Exception:
            ticker_df = None

        # Pass the pre-loaded dataframe directly into the scanner
        radar_rec, alerts = scan_single_ticker(ticker, asset_class, ticker_df, proximity_pct=proximity_pct)
        
        if radar_rec:
            all_radar_records.append(radar_rec)
        if alerts:
            all_actionable_alerts.extend(alerts)

    radar_df = pd.DataFrame(all_radar_records)
    alerts_df = pd.DataFrame(all_actionable_alerts)

    print(f"\n{'='*75}")
    print(" [RADAR] MASTER ASSET RADAR BOARD (Current Location & Nearest Key Zones)")
    print(f"{'='*75}\n")
    if radar_df.empty:
        radar_df = pd.DataFrame(columns=RADAR_SCHEMA)
    else:
        display_cols = ['Ticker', 'Asset_Class', 'Live_Price', 'Trend', 'Nearest_Demand_OB', 'Demand_Dist_%', 'Nearest_Supply_OB', 'Supply_Dist_%']
        print(radar_df[display_cols].to_string(index=False))

    radar_df.to_csv("SMC_MASTER_RADAR_FEED.csv", index=False)

    print(f"\n{'='*75}")
    print(f" [STRIKE] HIGH-PROBABILITY CONFIRMED ALERTS")
    print(f"{'='*75}\n")

    if alerts_df.empty:
        print("[!] No assets currently show a confirmed reversal inside a strike zone.")
        alerts_df = pd.DataFrame(columns=ALERT_SCHEMA)
    else:
        alerts_df = alerts_df.sort_values(by='R:R', ascending=False)
        print(alerts_df.to_string(index=False))

    alerts_df.to_csv("SMC_ACTIONABLE_ALERTS.csv", index=False)
    print(f"\n[+] Saved confirmed setups to SMC_ACTIONABLE_ALERTS.csv")
    print(f"\n{'='*75}")
    print(" SCAN RUN COMPLETE. DATA IS CACHED & DASHBOARD-READY.")
    print(f"{'='*75}\n")

if __name__ == "__main__":
    run_master_market_scan(
        scan_commodities=True,
        scan_nifty_core=True,
        scan_all_nse=False,
        proximity_pct=0.05
    )
