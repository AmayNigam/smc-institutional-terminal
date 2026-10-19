import os
import sys
import time
import pandas as pd
import numpy as np

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from data_loader import load_positional_data
from smc_engine import SMCEngine
from smc_state_machine import SMCMitigationTracker
from universe import get_tickers_by_category

def scan_single_ticker(ticker: str, asset_class: str, proximity_pct: float = 0.05):
    try:
        data = load_positional_data(ticker, start_date="2022-01-01")
        if data['daily'].empty or len(data['daily']) < 200:
            return None, []

        engine = SMCEngine(data['daily'], swing_length=3)
        smc_df = engine.run_all()

        tracker = SMCMitigationTracker(smc_df)
        tracker.run_tracking()

        current_row = smc_df.iloc[-1]
        current_price = current_row['Close']
        c_open = current_row['Open']
        c_high = current_row['High']
        c_low = current_row['Low']
        c_ema200 = current_row['EMA_200']
        current_date = smc_df.index[-1].strftime('%Y-%m-%d')
        
        is_uptrend = current_price > c_ema200 if not np.isnan(c_ema200) else True
        is_downtrend = current_price < c_ema200 if not np.isnan(c_ema200) else True

        bull_obs_below = [ob for ob in tracker.active_bullish_obs if ob.top <= current_price]
        nearest_demand_ob = max(bull_obs_below, key=lambda x: x.top) if bull_obs_below else None
        bear_obs_above = [ob for ob in tracker.active_bearish_obs if ob.bottom >= current_price]
        nearest_supply_ob = min(bear_obs_above, key=lambda x: x.bottom) if bear_obs_above else None

        dist_demand_pct = round(((current_price - nearest_demand_ob.top) / current_price) * 100, 2) if nearest_demand_ob else None
        dist_supply_pct = round(((nearest_supply_ob.bottom - current_price) / current_price) * 100, 2) if nearest_supply_ob else None

        radar_record = {
            'Ticker': ticker,
            'Asset_Class': asset_class,
            'Live_Price': round(current_price, 2),
            'Date': current_date,
            'Nearest_Demand_OB': round(nearest_demand_ob.top, 2) if nearest_demand_ob else None,
            'Demand_Dist_%': dist_demand_pct,
            'Nearest_Supply_OB': round(nearest_supply_ob.bottom, 2) if nearest_supply_ob else None,
            'Supply_Dist_%': dist_supply_pct,
            'Trend': 'BULLISH' if is_uptrend else 'BEARISH'
        }

        actionable_setups = []

        # LONG ALERTS (Requires Price in OB + Bullish Daily Candle + Discount Matrix)
        if is_uptrend:
            for ob in tracker.active_bullish_obs:
                if ob.pd_matrix != 'DISCOUNT':
                    continue
                # Price is inside the OB AND Candle is Bullish today
                if c_low <= ob.top and current_price > c_open:
                    entry = current_price
                    stop = ob.bottom - (0.5 * ob.atr_at_creation)
                    target = ob.swing_target
                    risk = entry - stop
                    if pd.isna(target) or target <= entry:
                        target = entry + (1.5 * risk)
                        
                    rr = (target - entry) / risk if risk > 0 else 0
                    if rr >= 1.0:
                        actionable_setups.append({
                            'Ticker': ticker, 'Asset_Class': asset_class, 'Direction': 'LONG_CONFIRMED',
                            'Live_Price': round(current_price, 2), 'Entry': round(entry, 2),
                            'Stop_Loss': round(stop, 2), 'Target': round(target, 2),
                            'R:R': round(rr, 2), 'OB_Date': str(ob.created_at.date())
                        })
                        break # Only take the best/first valid one

        # SHORT ALERTS (Requires Price in OB + Bearish Daily Candle + Premium Matrix)
        if is_downtrend:
            for ob in tracker.active_bearish_obs:
                if ob.pd_matrix != 'PREMIUM':
                    continue
                # Price is inside the OB AND Candle is Bearish today
                if c_high >= ob.bottom and current_price < c_open:
                    entry = current_price
                    stop = ob.top + (0.5 * ob.atr_at_creation)
                    target = ob.swing_target
                    risk = stop - entry
                    if pd.isna(target) or target >= entry:
                        target = entry - (1.5 * risk)
                        
                    rr = (entry - target) / risk if risk > 0 else 0
                    if rr >= 1.0:
                        actionable_setups.append({
                            'Ticker': ticker, 'Asset_Class': asset_class, 'Direction': 'SHORT_CONFIRMED',
                            'Live_Price': round(current_price, 2), 'Entry': round(entry, 2),
                            'Stop_Loss': round(stop, 2), 'Target': round(target, 2),
                            'R:R': round(rr, 2), 'OB_Date': str(ob.created_at.date())
                        })
                        break

        return radar_record, actionable_setups

    except Exception as e:
        print(f"[!] Warning: Error scanning {ticker}: {e}")
        return None, []


def run_master_market_scan(
    scan_commodities: bool = True, 
    scan_nifty_core: bool = True, 
    scan_all_nse: bool = False,
    proximity_pct: float = 0.05
):
    scan_queue = []

    if scan_commodities:
        comm_tickers = get_tickers_by_category("COMMODITIES_GLOBAL")
        for t in comm_tickers:
            scan_queue.append((t, "COMMODITY"))

    if scan_nifty_core and not scan_all_nse:
        nifty_tickers = get_tickers_by_category("NIFTY_50_CORE")
        for t in nifty_tickers:
            scan_queue.append((t, "EQUITY_NIFTY50"))

    if scan_all_nse:
        all_nse_tickers = get_tickers_by_category("NSE_ALL")
        for t in all_nse_tickers:
            scan_queue.append((t, "EQUITY_NSE"))

    print(f"\n{'='*75}")
    print(f" LAUNCHING CLIENT-READY SMC SCAN: {len(scan_queue)} Total Assets In Queue")
    print(f" Filters: Reversal Confirmation | Swing Targets | PD Matrix | Trend")
    print(f"{'='*75}\n")

    all_radar_records = []
    all_actionable_alerts = []

    for idx, (ticker, asset_class) in enumerate(scan_queue):
        print(f"[{idx+1}/{len(scan_queue)}] Analyzing {ticker} ({asset_class})...")
        radar_rec, alerts = scan_single_ticker(ticker, asset_class, proximity_pct=proximity_pct)
        if radar_rec:
            all_radar_records.append(radar_rec)
        if alerts:
            all_actionable_alerts.extend(alerts)

        if len(scan_queue) > 50:
            time.sleep(0.25)

    radar_df = pd.DataFrame(all_radar_records)
    alerts_df = pd.DataFrame(all_actionable_alerts)

    print(f"\n{'='*75}")
    print(" [RADAR] MASTER ASSET RADAR BOARD (Current Location & Nearest Key Zones)")
    print(f"{'='*75}\n")
    if not radar_df.empty:
        display_cols = ['Ticker', 'Asset_Class', 'Live_Price', 'Trend', 'Nearest_Demand_OB', 'Demand_Dist_%', 'Nearest_Supply_OB', 'Supply_Dist_%']
        print(radar_df[display_cols].to_string(index=False))
        radar_df.to_csv("SMC_MASTER_RADAR_FEED.csv", index=False)

    print(f"\n{'='*75}")
    print(f" [STRIKE] HIGH-PROBABILITY CONFIRMED ALERTS")
    print(f"{'='*75}\n")
    if not alerts_df.empty:
        alerts_df = alerts_df.sort_values(by='R:R', ascending=False)
        print(alerts_df.to_string(index=False))
        alerts_df.to_csv("SMC_ACTIONABLE_ALERTS.csv", index=False)
        print(f"\n[+] Saved confirmed setups to SMC_ACTIONABLE_ALERTS.csv")
    else:
        print("[!] No assets currently show a confirmed reversal inside a strike zone.")

    print(f"\n{'='*75}")
    print(" SCAN RUN COMPLETE. DATA IS CACHED & DASHBOARD-READY.")
    print(f"{'='*75}\n")

if __name__ == "__main__":
    run_master_market_scan(
        scan_commodities=True,
        scan_nifty_core=True,
        scan_all_nse=False,
        proximity_pct=0.05
    )