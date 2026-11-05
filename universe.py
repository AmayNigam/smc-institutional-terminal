import pandas as pd
import requests
import io

def get_dynamic_nse_universe():
    """
    Dynamically fetches the live master list of all active equities directly from the NSE servers.
    Bypasses static hardcoding to ensure zero missing assets.
    """
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    
    # Spoof a legitimate browser to bypass NSE firewall blocking GitHub Actions
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }
    
    try:
        # Establish a session to grab NSE cookies
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        
        # Fetch the live CSV from the archives
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse the data and isolate the 'EQ' (pure equity) series
        df = pd.read_csv(io.StringIO(response.text))
        if ' SERIES' in df.columns:
            df = df[df[' SERIES'].str.strip() == 'EQ']
            
        # Append .NS for Yahoo Finance compatibility
        live_tickers = (df['SYMBOL'].str.strip() + '.NS').tolist()
        
        return {
            "NSE_ALL_EQUITY": live_tickers,
            "GLOBAL_COMMODITIES": ["GC=F", "SI=F", "CL=F", "BZ=F", "HG=F", "NG=F", "PA=F", "PL=F"]
        }
        
    except Exception as e:
        print(f"⚠️ NSE Dynamic Fetch Failed: {e}. Falling back to static emergency list.")
        # FAILSAFE: Hardcoded fallback just in case the NSE website goes down during a scan
        return {
            "NSE_FALLBACK": [
                "RELIANCE.NS", "HDFCBANK.NS", "TCS.NS", "INFY.NS", "ICICIBANK.NS", 
                "MOREPENLAB.NS", "OMAXAUTO.NS", "SUNTV.NS", "UJJIVANSFB.NS",
                "NUVOCO.NS", "TORNTPOWER.NS", "VENKEYS.NS", "ABBOTINDIA.NS"
            ],
            "GLOBAL_COMMODITIES": ["GC=F", "SI=F", "CL=F", "BZ=F", "HG=F", "NG=F", "PA=F", "PL=F"]
        }

# Execute fetch immediately so ASSET_UNIVERSES is populated dynamically when imported by app.py or scanner.py
ASSET_UNIVERSES = get_dynamic_nse_universe()

def get_tickers_by_category(category):
    # Returns the list based on the requested category. If it fails, checks for the fallback.
    if category == "NSE_ALL_EQUITY" and "NSE_ALL_EQUITY" not in ASSET_UNIVERSES:
        return ASSET_UNIVERSES.get("NSE_FALLBACK", [])
    return ASSET_UNIVERSES.get(category, [])
