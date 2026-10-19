import os
import sys
import pandas as pd
import requests
from datetime import datetime

# Import scanner logic
from master_scanner import run_master_market_scan

def send_telegram_alert(token: str, chat_id: str, message: str):
    """Dispatches a formatted markdown message to the Telegram channel/chat."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            print("[+] Telegram alert successfully delivered.")
        else:
            print(f"[-] Telegram dispatch error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[-] Failed to send Telegram alert: {e}")

def main():
    print("=" * 60)
    print(f"[*] Starting Automated SMC Daily Cron: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. Execute Market Scan (Nifty 50 Core + Global Commodities for speed & liquidity)
    print("[*] Running Institutional SMC Scanner...")
    run_master_market_scan(
        scan_commodities=True,
        scan_nifty_core=True,
        scan_all_nse=True,
        proximity_pct=0.05
    )

    # 2. Check for Actionable Setups
    alerts_file = "SMC_ACTIONABLE_ALERTS.csv"
    if not os.path.exists(alerts_file):
        print("[-] SMC_ACTIONABLE_ALERTS.csv not found.")
        return

    alerts_df = pd.read_csv(alerts_file)

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    # Exit cleanly if Telegram secrets aren't set yet (prevents workflow crashes)
    if not token or not chat_id:
        print("[!] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured in secrets.")
        print("[*] CSV feeds updated successfully. Exiting cleanly without Telegram notification.")
        return

    if alerts_df.empty:
        msg = (
            f"🏛 *INSTITUTIONAL SMC RADAR — MARKET CLOSE*\n"
            f"📅 *Date:* {datetime.now().strftime('%d %b %Y')}\n\n"
            f"⚪ *No Actionable Setups Detected Today.*\n"
            f"Market structure is currently between institutional strike zones. No orders triggered."
        )
        send_telegram_alert(token, chat_id, msg)
        return

    # 3. Format Actionable Signals into Clean Institutional Desk Message
    msg = (
        f"🏛 *INSTITUTIONAL SMC DESK — ACTIONABLE STRIKES*\n"
        f"📅 *Date:* {datetime.now().strftime('%d %b %Y')} | Close Update\n"
        f"🎯 *Active Setups:* {len(alerts_df)}\n"
        f"{'=' * 28}\n\n"
    )

    for _, row in alerts_df.iterrows():
        ticker = row.get('Ticker', 'N/A')
        direction = row.get('Direction', 'N/A')
        entry = row.get('Entry', 0.0)
        sl = row.get('Stop_Loss', 0.0)
        target = row.get('Target', 0.0)
        rr = row.get('R:R', 0.0)

        emoji = "🟢" if "LONG" in str(direction) else "🔴"

        msg += (
            f"{emoji} *{ticker}* | `{direction}`\n"
            f"• *Entry:* `{entry}`\n"
            f"• *Stop Loss:* `{sl}`\n"
            f"• *Target:* `{target}`\n"
            f"• *Risk/Reward:* `1 : {rr}`\n\n"
        )

    msg += (
        f"📊 *Live Terminal:* [smctoolbyamay.streamlit.app](https://smctoolbyamay.streamlit.app)\n"
        f"⚠️ _Strict risk management: 1% portfolio risk per trade._"
    )

    print("[*] Dispatching Actionable Setups to Telegram...")
    send_telegram_alert(token, chat_id, msg)
    print("[+] Daily Cron Execution Completed.")

if __name__ == "__main__":
    main()
