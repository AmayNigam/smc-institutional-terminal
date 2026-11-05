import pandas as pd
import concurrent.futures
import os
import time
import random
from data_loader import load_positional_data
from master_scanner import scan_single_ticker
from universe import get_tickers_by_category

def process_single_asset(ticker, asset_class):
    """Isolated worker function executing the network request and math simultaneously."""
    try:
        # ANTI-BAN JITTER: Micro-delay to prevent Yahoo Finance from blocking the GitHub IP
        time.sleep(random.uniform(0.5, 1.5))
        
        # The network request MUST happen inside the thread
        data = load_positional_data(ticker)
        if data and 'daily' in data and not data['daily'].empty:
            return scan_single_ticker(ticker, asset_class, data['daily'], 0.05)
            
    except Exception as e:
        print(f"[FAILED] {ticker}: {e}")
        
    return None, None

def run_enterprise_batch():
    print("Initiating Enterprise Multi-Threaded SMC Scan...")
    target_universe = []
    
    try:
        # Adjusted to match the exact keys exported by your new universe.py
        target_universe.extend([(t, "COMMODITY") for t in get_tickers_by_category("GLOBAL_COMMODITIES")])
        target_universe.extend([(t, "EQUITY") for t in get_tickers_by_category("NSE_ALL_EQUITY")])
    except Exception as e:
        print(f"Error loading universe: {e}")
        
    print(f"Target Universe Size: {len(target_universe)} tickers.")
    
    if len(target_universe) == 0:
        print("Universe is empty. Exiting.")
        return

    radar_records = []
    actionable_records = []
    
    # Strictly capped at 8 workers to evade rate limiting
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_ticker = {
            executor.submit(process_single_asset, ticker, asset_class): ticker 
            for ticker, asset_class in target_universe
        }
            
        for future in concurrent.futures.as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                radar_rec, actionable_recs = future.result()
                if radar_rec: 
                    radar_records.append(radar_rec)
                if actionable_recs: 
                    actionable_records.extend(actionable_recs)
            except Exception as e:
                print(f"[CRITICAL FAILURE] Thread exception for {ticker}: {e}")

    # Save directly to CSV
    if actionable_records:
        pd.DataFrame(actionable_records).to_csv("SMC_ACTIONABLE_ALERTS.csv", index=False)
    else:
        pd.DataFrame(columns=['Ticker', 'Asset_Class', 'Direction', 'Live_Price', 'Entry', 'Stop_Loss', 'Target', 'R:R', 'OB_Date']).to_csv("SMC_ACTIONABLE_ALERTS.csv", index=False)
        
    if radar_records:
        pd.DataFrame(radar_records).to_csv("SMC_MASTER_RADAR_FEED.csv", index=False)
    else:
        pd.DataFrame(columns=['Ticker', 'Asset_Class', 'Live_Price', 'Trend', 'Nearest_Demand_OB', 'Demand_Dist_%', 'Nearest_Supply_OB', 'Supply_Dist_%']).to_csv("SMC_MASTER_RADAR_FEED.csv", index=False)

    print("Data saved to CSVs successfully.")

if __name__ == "__main__":
    run_enterprise_batch()
