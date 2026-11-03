import requests
import json

WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbyf-YG6oFtUE9Ot4O5MwHWVIoGWXLcsleCyOVrzSKtE8Wc0ookE64K3oOgtE1O1zxtJQw/exec"

def push_mock_data():
    print("Pushing mock test data to Google Sheets...")
    
    # Fake alert data
    alerts_payload = {
        "sheetName": "Alerts", 
        "data": [{"Ticker": "RELIANCE.NS", "Signal": "BULLISH_FVG", "Price": 2500.0}]
    }
    res1 = requests.post(WEBHOOK_URL, data=json.dumps(alerts_payload))
    print(f"Alerts Response: {res1.text}")

    # Fake radar data
    radar_payload = {
        "sheetName": "Radar", 
        "data": [{"Ticker": "TCS.NS", "Status": "NEAR_ZONE", "Proximity": "1.2%"}]
    }
    res2 = requests.post(WEBHOOK_URL, data=json.dumps(radar_payload))
    print(f"Radar Response: {res2.text}")

if __name__ == "__main__":
    push_mock_data()
