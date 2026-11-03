import pandas as pd
import concurrent.futures
import os
import requests
import json
from data_loader import load_positional_data
from master_scanner import scan_single_ticker
from universe import get_tickers_by_category

WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbyf-YG6oFtUE9Ot4O5MwHWVIoGWXLcsleCyOVrzSKtE8Wc0ookE64K3oOgtE1O1zxtJQw/exec"

def push_to_sheets(records, sheet_name):
    print(f"Attempting to push {len(records)} records to {sheet_name}...")
    if not records:
        print(f"Skipped {sheet_name} push: No records generated.")
        return
    df = pd.DataFrame(records)
    payload = {"sheetName": sheet_name, "data": df.to_dict(orient="records")}
    try:
        response = requests.post(WEBHOOK_URL, data=json.dumps(payload))
        print(f"Google Sheets Response for {sheet_name}: {response.text}")
    except Exception as e:
        print(f"Failed to push to Google Sheets: {e}")

def run_enterprise_batch():
    print("Initiating Enterprise Multi-Threaded SMC Scan...")
    
  target_universe = [
        ("RELIANCE.NS", "EQUITY_NIFTY50"),
        ("TCS.NS", "EQUITY_NIFTY50"),
        ("GC=F", "COMMODITY")
    ]
        
    print(f"Target Universe Size: {len(target_universe)} tickers.")
    if len(target_universe) == 0:
        print("Aborting scan: No tickers loaded.")
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
                else:
                    print(f"No market data fetched for {ticker}")
            except Exception as e:
                print(f"Failed to load data for {ticker}: {e}")
                
        print(f"Submitted {len(future_to_ticker)} valid tickers to thread pool.")
        
        for future in concurrent.futures.as_completed(future_to_ticker):
            try:
                radar_rec, actionable_recs = future.result()
                if radar_rec: radar_records.append(radar_rec)
                if actionable_recs: actionable_records.extend(actionable_recs)
            except Exception as e:
                print(f"Error processing {future_to_ticker[future]}: {e}")

    print("Uploading data to Google Sheets Database...")
    push_to_sheets(actionable_records, "Alerts")
    push_to_sheets(radar_records, "Radar")

if __name__ == "__main__":
    run_enterprise_batch()
