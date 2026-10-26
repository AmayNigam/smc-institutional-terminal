import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import pyotp
import requests
from urllib.parse import parse_qs, urlparse
from fyers_apiv3 import fyersModel

# --- FYERS CREDENTIALS FROM ENVIRONMENT VARIABLES ---
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
FYERS_ID = os.getenv("FYERS_ID")
TOTP_SECRET = os.getenv("FYERS_TOTP_SECRET")
PIN = os.getenv("FYERS_PIN")
REDIRECT_URI = "https://127.0.0.1:5000/login"

def get_fyers_access_token():
    """Headless 2FA login for Fyers API using pyotp."""
    if not all([CLIENT_ID, SECRET_KEY, FYERS_ID, TOTP_SECRET, PIN]):
        return None

    try:
        session = fyersModel.SessionModel(
            client_id=CLIENT_ID, secret_key=SECRET_KEY, 
            redirect_uri=REDIRECT_URI, response_type="code", grant_type="authorization_code"
        )

        totp = pyotp.TOTP(TOTP_SECRET).now()
        
        # 1. Send Login
        res_send = requests.post("https://api-t2.fyers.in/vagator/v2/send_login_otp_v2", json={"fy_id": FYERS_ID, "app_id": "2"}).json()
        request_key = res_send.get("request_key")
        if not request_key: return None

        # 2. Verify TOTP
        res_verify = requests.post("https://api-t2.fyers.in/vagator/v2/verify_otp", json={"request_key": request_key, "otp": totp}).json()
        request_key = res_verify.get("request_key")
        
        # 3. Verify PIN
        res_pin = requests.post("https://api-t2.fyers.in/vagator/v2/verify_pin_v2", json={"request_key": request_key, "identity_type": "pin", "identifier": PIN}).json()
        access_token_temp = res_pin.get('data', {}).get('access_token')

        # 4. Final Auth Code
        headers = {"authorization": f"Bearer {access_token_temp}"}
        auth_code_res = requests.post("https://api-t1.fyers.in/api/v3/token", json={"fyers_id": FYERS_ID, "app_id": CLIENT_ID[:-4], "redirect_uri": REDIRECT_URI, "appType": "100"}, headers=headers).json()
        auth_code = parse_qs(urlparse(auth_code_res['Url']).query)['auth_code'][0]

        session.set_token(auth_code)
        return session.generate_token()["access_token"]
    except Exception as e:
        print(f"[!] Fyers Auth Failed: {e}")
        return None

def fetch_fyers_historical(ticker, fyers_token, days=120):
    """Fetches clean data from Fyers."""
    try:
        fyers = fyersModel.FyersModel(client_id=CLIENT_ID, is_async=False, token=fyers_token, log_path="")
        fyers_symbol = f"NSE:{ticker.replace('.NS', '')}-EQ"
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        data = {
            "symbol": fyers_symbol, "resolution": "1D", "date_format": "1",
            "range_from": start_date.strftime("%Y-%m-%d"), "range_to": end_date.strftime("%Y-%m-%d"), "cont_flag": "1"
        }
        
        res = fyers.history(data=data)
        if res['s'] != "ok": return None
        
        df = pd.DataFrame(res['candles'], columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df['Date'] = pd.to_datetime(df['Date'], unit='s').dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
        df.set_index('Date', inplace=True)
        return df
    except Exception:
        return None

def clean_ohlcv_data(df_raw: pd.DataFrame) -> pd.DataFrame:
    # (Keep your exact existing clean_ohlcv_data function here)
    if isinstance(df_raw.columns, pd.MultiIndex):
        if 'Close' in df_raw.columns.get_level_values(0): df_raw.columns = df_raw.columns.get_level_values(0)
        elif 'Close' in df_raw.columns.get_level_values(1): df_raw.columns = df_raw.columns.get_level_values(1)

    expected_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    df = df_raw[expected_cols].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df[expected_cols[:-1]] = df[expected_cols[:-1]].ffill()
    df['Volume'] = df['Volume'].fillna(0)
    df = df.astype({'Open': 'float64', 'High': 'float64', 'Low': 'float64', 'Close': 'float64', 'Volume': 'int64'})
    valid_ticks = (df['Low'] <= df['High']) & (df['Open'] <= df['High']) & (df['Close'] >= df['Low'])
    return df[valid_ticks]

def load_positional_data(ticker: str, start_date: str = "2022-01-01") -> dict:
    fyers_token = get_fyers_access_token()
    
    # Primary: Fyers API
    if fyers_token:
        df = fetch_fyers_historical(ticker, fyers_token)
        if df is not None and not df.empty:
            return {"daily": df, "weekly": pd.DataFrame()} # Weekly skipped for brevity in state machine
            
    # Fallback: yfinance
    print(f"[*] Falling back to yfinance for {ticker}")
    raw_df = yf.download(ticker, start=start_date, interval="1d", progress=False)
    df = clean_ohlcv_data(raw_df)
    return {"daily": df, "weekly": pd.DataFrame()}
