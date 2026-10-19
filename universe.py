import pandas as pd
import urllib.request
import io

# Central asset registry for Indian Equities and Commodities.
ASSET_UNIVERSES = {
    "COMMODITIES_GLOBAL": [
        "GC=F",      # COMEX Gold Continuous Futures
        "SI=F",      # COMEX Silver Continuous Futures
        "CL=F",      # WTI Crude Oil Continuous Futures
        "BZ=F",      # Brent Crude Oil Continuous Futures
        "HG=F",      # Copper Continuous Futures
        "NG=F",      # Natural Gas Continuous Futures
    ],
    
    "COMMODITIES_DOMESTIC_INR": [
        "SILVERBEES.NS",  # Nippon India Silver ETF
        "GOLDBEES.NS",    # Nippon India Gold ETF 
    ],
    
    "NIFTY_50_CORE": [
        "RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "TCS.NS", 
        "INFY.NS", "LT.NS", "SBIN.NS", "BHARTIARTL.NS", "ITC.NS"
    ]
}

def get_all_nse_tickers() -> list:
    """Dynamically fetches all ~2,200+ listed NSE tickers directly from the NSE India registry."""
    try:
        url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
        # Mimic a browser so the NSE server doesn't block the request
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            csv_data = response.read().decode('utf-8')
            
        df = pd.read_csv(io.StringIO(csv_data))
        # Filter out ETFs and mutual funds if necessary, or just keep all 'EQ' series
        if 'SERIES' in df.columns:
            df = df[df['SERIES'] == 'EQ']
            
        # Append .NS for Yahoo Finance compatibility
        tickers = [str(sym) + ".NS" for sym in df['SYMBOL']]
        print(f"[+] Successfully loaded {len(tickers)} live equities from NSE registry.")
        return tickers
    except Exception as e:
        print(f"[!] Could not fetch live NSE list from server: {e}")
        print("[!] Falling back to Nifty 50 Core.")
        return ASSET_UNIVERSES["NIFTY_50_CORE"]

def get_tickers_by_category(category: str) -> list:
    """Returns list of tickers for a given category name."""
    if category == "NSE_ALL":
        print("[*] Fetching the master list of ALL listed NSE stocks...")
        return get_all_nse_tickers()
        
    return ASSET_UNIVERSES.get(category, [])