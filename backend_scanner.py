import pandas as pd
import concurrent.futures
import os
from data_loader import load_positional_data
from master_scanner import scan_single_ticker
from universe import get_tickers_by_category

def run_enterprise_batch():
    print("Initiating Enterprise Multi-Threaded SMC Scan...")
    
    # Define the universe (Commodities + Nifty 50 + Optional NSE)
    target_universe = []
    target_universe.extend([(t, "COMMODITY") for t in get_tickers_by_category("COMMODITIES")])
    target_universe.extend([(t, "EQUITY_NIFTY50") for t in get_tickers_by_category("NIFTY_50")])
    # Add NSE full universe here if desired, but keep it commented out for testing
    # target_universe.extend([(t, "EQUITY_NSE") for t in get_tickers_by_category("NSE_ALL")])

    radar_records = []
    actionable_records = []
    
    # 15 concurrent threads for maximum I/O speed
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        future_to_ticker = {}
        for ticker, asset_class in target_universe:
            data = load_positional_data(ticker)
            if data and 'daily' in data and not data['daily'].empty:
                # Hardcoded 5% proximity for the backend generation
                future = executor.submit(scan_single_ticker, ticker, asset_class, data['daily'], 0.05)
                future_to_ticker[future] = ticker
                
        for future in concurrent.futures.as_completed(future_to_ticker):
            try:
                radar_rec, actionable_recs = future.result()
                if radar_rec: radar_records.append(radar_rec)
                if actionable_recs: actionable_records.extend(actionable_recs)
            except Exception as e:
                print(f"Error processing {future_to_ticker[future]}: {e}")

    # Save outputs to the repository
    if radar_records:
        pd.DataFrame(radar_records).to_csv("SMC_MASTER_RADAR_FEED.csv", index=False)
        print("Radar feed updated.")
    if actionable_records:
        pd.DataFrame(actionable_records).to_csv("SMC_ACTIONABLE_ALERTS.csv", index=False)
        print("Actionable alerts updated.")

if __name__ == "__main__":
    run_enterprise_batch()
