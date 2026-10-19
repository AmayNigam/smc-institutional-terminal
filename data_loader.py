import os
import pandas as pd
import yfinance as yf
from datetime import datetime

def clean_ohlcv_data(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Cleans raw OHLCV DataFrame, fixes MultiIndex issues, and drops corrupted data.
    """
    # 1. Fix the MultiIndex Bug (yfinance sometimes nests the ticker name in the column headers)
    if isinstance(df_raw.columns, pd.MultiIndex):
        if 'Close' in df_raw.columns.get_level_values(0):
            df_raw.columns = df_raw.columns.get_level_values(0)
        elif 'Close' in df_raw.columns.get_level_values(1):
            df_raw.columns = df_raw.columns.get_level_values(1)

    expected_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    
    # If the API returned junk data missing standard columns, halt.
    missing_cols = [col for col in expected_cols if col not in df_raw.columns]
    if missing_cols:
        raise ValueError(f"[!] Missing required columns in data: {missing_cols}")
        
    df = df_raw[expected_cols].copy()
    
    # 2. Timezone-naive index (Crucial for Multi-Timeframe alignment)
    df.index = pd.to_datetime(df.index).tz_localize(None)

    # 3. Handle Missing Data (NaNs) & Zero Volume
    # Forward-fill missing prices (never fill with 0) to maintain market structure
    df[expected_cols[:-1]] = df[expected_cols[:-1]].ffill()
    df['Volume'] = df['Volume'].fillna(0)
    
    # 4. Strict Type Casting (Prevents silent rounding errors in FVG Equilibrium math)
    df = df.astype({
        'Open': 'float64', 
        'High': 'float64', 
        'Low': 'float64', 
        'Close': 'float64', 
        'Volume': 'int64'
    })
    
    # 5. Data Integrity Assertions (Drop physically impossible candles)
    valid_ticks = (df['Low'] <= df['High']) & (df['Open'] <= df['High']) & (df['Close'] >= df['Low']) & (df['Volume'] >= 0)
    
    invalid_count = len(df) - valid_ticks.sum()
    if invalid_count > 0:
        print(f"[WARNING] Purged {invalid_count} anomalous ticks where Low > High.")
        
    return df[valid_ticks]

def fetch_timeframe_data(ticker: str, interval: str, start_date: str) -> pd.DataFrame:
    """
    Handles local caching and incremental updates to bypass API limits and speed up execution.
    """
    # Create a local cache directory in your project folder
    CACHE_DIR = "data_cache"
    os.makedirs(CACHE_DIR, exist_ok=True)
    file_path = os.path.join(CACHE_DIR, f"{ticker}_{interval}.csv")
    
    df = pd.DataFrame()
    
    # 1. Try to load cached data
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index)
            
            if not df.empty:
                last_cached_date = df.index[-1].strftime('%Y-%m-%d')
                print(f"[*] Checking for new {interval} data for {ticker} since {last_cached_date}...")
                
                # Fetch only the missing days (Incremental Sync)
                delta_raw = yf.download(ticker, start=last_cached_date, interval=interval, progress=False)
                
                if not delta_raw.empty:
                    delta_clean = clean_ohlcv_data(delta_raw)
                    prev_len = len(df)
                    
                    # Merge old data with new data and drop duplicates
                    df = pd.concat([df, delta_clean])
                    df = df[~df.index.duplicated(keep='last')].sort_index()
                    
                    if len(df) > prev_len:
                        print(f"[+] Added {len(df) - prev_len} new {interval} candles.")
                        df.to_csv(file_path)
                    else:
                        print(f"[-] Local {interval} data is already up-to-date.")
                return df
        except Exception as e:
            print(f"[!] Cache read error for {ticker} {interval}: {e}. Forcing fresh download...")
    
    # 2. Fresh Download Fallback (If no cache exists)
    print(f"[*] Downloading full historical {interval} data for {ticker} (since {start_date})...")
    raw_df = yf.download(ticker, start=start_date, interval=interval, progress=False)
    
    if raw_df.empty:
        raise ValueError(f"[!] No data returned for {ticker} ({interval}). Check the ticker symbol.")
        
    df = clean_ohlcv_data(raw_df)
    
    # Save to cache for the next run
    df.to_csv(file_path)
    print(f"[+] Saved {len(df)} {interval} bars to local cache.")
    
    return df

def load_positional_data(ticker: str, start_date: str = "2012-01-01") -> dict:
    """
    Master function to load both Daily and Weekly timeframes for Positional SMC analysis.
    """
    print(f"\n--- INITIALIZING POSITIONAL DATA ENGINE FOR {ticker} ---")
    
    # Fetch Daily Data
    daily_df = fetch_timeframe_data(ticker, interval="1d", start_date=start_date)
    
    # Fetch Weekly Data
    weekly_df = fetch_timeframe_data(ticker, interval="1wk", start_date=start_date)
    
    return {"daily": daily_df, "weekly": weekly_df}

# --- Execution Test ---
if __name__ == "__main__":
    # Test it by running this file in your VS Code terminal
    ticker_symbol = "RELIANCE.NS"
    
    try:
        # Requesting data starting from 2012 gives us roughly 14 years of structure
        data = load_positional_data(ticker_symbol, start_date="2012-01-01")
        
        print("\n--- Engine Output Summary ---")
        print(f"Daily Bars Loaded:  {len(data['daily'])} candles")
        print(f"Weekly Bars Loaded: {len(data['weekly'])} candles")
        
        print("\n--- Recent Daily Candles ---")
        print(data['daily'].tail(3))
        
    except Exception as e:
        print(f"\n[CRITICAL ERROR] Pipeline failed: {e}")