import pandas as pd
import concurrent.futures
import os
from data_loader import load_positional_data
from master_scanner import scan_single_ticker
from universe import get_tickers_by_category

def run_enterprise_batch():
    print("Initiating Enterprise Multi-Threaded SMC Scan...")
    target_universe = []
    
    try:
        target_universe.extend([(t, "COMMODITY") for t in get_tickers_by_category("COMMODITIES_GLOBAL")])
        target_universe.extend([(t, "EQUITY") for t in get_tickers_by_category("NSE_ALL")])
    except Exception as e:
        print(f"Error loading universe: {e}")
        
    print(f"Target Universe Size: {len(target_universe)} tickers.")
    
    if len(target_universe) == 0:
        return

    radar_records = []
    actionable_records = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        future_to_ticker = {}
        for ticker, asset_class in target_universe:
            try:
                data = load_positional_data(ticker)
                if data and 'daily' in data and not data['daily'].empty:
                    future = executor.submit(scan_single_ticker, ticker, asset_class, data['daily'], 0.05)
                    future_to_ticker[future] = ticker
            except Exception:
                pass
                
        for future in concurrent.futures.as_completed(future_to_ticker):
            try:
                radar_rec, actionable_recs = future.result()
                if radar_rec: radar_records.append(radar_rec)
                if actionable_recs: actionable_records.extend(actionable_recs)
            except Exception:
                pass

    # Save directly to CSV
    if actionable_records:
        pd.DataFrame(actionable_records).to_csv("SMC_ACTIONABLE_ALERTS.csv", index=False)
    else:
        # Create empty template if no trades
        pd.DataFrame(columns=['Ticker', 'Asset_Class', 'Direction', 'Live_Price', 'Entry', 'Stop_Loss', 'Target', 'R:R', 'OB_Date']).to_csv("SMC_ACTIONABLE_ALERTS.csv", index=False)
        
    if radar_records:
        pd.DataFrame(radar_records).to_csv("SMC_MASTER_RADAR_FEED.csv", index=False)

    print("Data saved to CSVs successfully.")

if __name__ == "__main__":
    run_enterprise_batch()
