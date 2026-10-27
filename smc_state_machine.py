import pandas as pd
import numpy as np

class SMCZone:
    def __init__(self, zone_type: str, direction: str, created_at, top: float, bottom: float, eq: float, atr: float, pd_matrix: str, swing_target: float):
        self.zone_type = zone_type      
        self.direction = direction      
        self.created_at = created_at    
        self.top = top
        self.bottom = bottom
        self.eq = eq
        self.atr_at_creation = atr
        self.pd_matrix = pd_matrix 
        self.swing_target = swing_target # NEW: Immediate Structural Liquidity Target
        
        self.is_mitigated = False
        self.mitigated_at = None
        self.mitigation_type = None

class SMCMitigationTracker:
    def __init__(self, df: pd.DataFrame, inplace: bool = True):
        self.df = df if inplace else df.copy()
        self.active_bullish_obs = []
        self.active_bearish_obs = []
        self.mitigated_zones = []
        
    def _find_order_block(self, current_idx: int, direction: str):
        start_scan = current_idx - 2
        for i in range(start_scan, max(-1, start_scan - 5), -1):
            row = self.df.iloc[i]
            is_down_candle = row['Close'] < row['Open']
            is_up_candle = row['Close'] > row['Open']
            
            if direction == 'BULLISH' and is_down_candle:
                # --- NEW: LIQUIDITY SWEEP CHECK ---
                # Check the 5 candles prior to this candidate to ensure it swept a local low
                local_lows = self.df['Low'].iloc[max(0, i - 5):i]
                if not local_lows.empty and row['Low'] > local_lows.min():
                    continue  # Discard: Did not sweep liquidity, keep looking
                return (self.df.index[i], row['High'], row['Low'])
                
            elif direction == 'BEARISH' and is_up_candle:
                # --- NEW: LIQUIDITY SWEEP CHECK ---
                # Check the 5 candles prior to this candidate to ensure it swept a local high
                local_highs = self.df['High'].iloc[max(0, i - 5):i]
                if not local_highs.empty and row['High'] < local_highs.max():
                    continue  # Discard: Did not sweep liquidity, keep looking
                return (self.df.index[i], row['High'], row['Low'])
                
        return None, None, None

    def run_tracking(self) -> pd.DataFrame:
        # Pre-allocate columns directly in the existing memory block
        self.df['Active_Bull_OB_Count'] = 0
        self.df['Active_Bear_OB_Count'] = 0
        
        for i in range(len(self.df)):
            current_date = self.df.index[i]
            row = self.df.iloc[i]
            c_high, c_low, c_atr = row['High'], row['Low'], row['ATR']
            
            # Evaluate Mitigation
            remaining_bull_obs = []
            for zone in self.active_bullish_obs:
                if c_low < zone.bottom:
                    zone.is_mitigated, zone.mitigated_at, zone.mitigation_type = True, current_date, 'INVALIDATED'
                    self.mitigated_zones.append(zone)
                elif c_low <= zone.top:
                    zone.is_mitigated, zone.mitigated_at, zone.mitigation_type = True, current_date, 'TOUCHED'
                    self.mitigated_zones.append(zone)
                else:
                    remaining_bull_obs.append(zone)
            self.active_bullish_obs = remaining_bull_obs

            remaining_bear_obs = []
            for zone in self.active_bearish_obs:
                if c_high > zone.top:
                    zone.is_mitigated, zone.mitigated_at, zone.mitigation_type = True, current_date, 'INVALIDATED'
                    self.mitigated_zones.append(zone)
                elif c_high >= zone.bottom:
                    zone.is_mitigated, zone.mitigated_at, zone.mitigation_type = True, current_date, 'TOUCHED'
                    self.mitigated_zones.append(zone)
                else:
                    remaining_bear_obs.append(zone)
            self.active_bearish_obs = remaining_bear_obs
            
            # Register New Zones
            pd_state = 'DISCOUNT' if row.get('In_Discount', False) else ('PREMIUM' if row.get('In_Premium', False) else 'UNKNOWN')
            
            if row.get('Bullish_FVG', False):
                ob_date, ob_top, ob_bottom = self._find_order_block(i, 'BULLISH')
                if ob_date:
                    if not any(existing.created_at == ob_date for existing in self.active_bullish_obs):
                        ob_eq = (ob_top + ob_bottom) / 2
                        swing_target = row.get('Last_Swing_High', np.nan)
                        ob = SMCZone('ORDER_BLOCK', 'BULLISH', ob_date, ob_top, ob_bottom, ob_eq, c_atr, pd_state, swing_target)
                        self.active_bullish_obs.append(ob)
                        
            if row.get('Bearish_FVG', False):
                ob_date, ob_top, ob_bottom = self._find_order_block(i, 'BEARISH')
                if ob_date:
                    if not any(existing.created_at == ob_date for existing in self.active_bearish_obs):
                        ob_eq = (ob_top + ob_bottom) / 2
                        swing_target = row.get('Last_Swing_Low', np.nan)
                        ob = SMCZone('ORDER_BLOCK', 'BEARISH', ob_date, ob_top, ob_bottom, ob_eq, c_atr, pd_state, swing_target)
                        self.active_bearish_obs.append(ob)
            
           # Assign directly using fast integer indexing
            self.df.iat[i, self.df.columns.get_loc('Active_Bull_OB_Count')] = len(self.active_bullish_obs)
            self.df.iat[i, self.df.columns.get_loc('Active_Bear_OB_Count')] = len(self.active_bearish_obs)
            
        return self.df
class ICTSweepAndShiftEngine:
    """
    Event-driven State Machine. Tracks the exact chronological sequence:
    Searching -> Swept Liquidity -> MSS Confirmed (with FVG) -> In Trade.
    """
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()

    def run_state_machine(self) -> dict:
        state = "SEARCHING"
        setup_data = {}
        
        for i in range(2, len(self.df)):
            current = self.df.iloc[i]
            prev = self.df.iloc[i-1]
            
            # --- 1. SEARCHING FOR A LIQUIDITY SWEEP ---
            if state == "SEARCHING":
                # Sell-side liquidity sweep (Bullish Setup)
                if current['Low'] < current.get('Last_Swing_Low', -1):
                    state = "SWEPT_BULLISH"
                    setup_data = {
                        'direction': 'LONG',
                        'sweep_low': current['Low'],
                        'mss_trigger': current.get('Last_Swing_High', 999999),
                        'target': current.get('Last_Swing_High', np.nan)
                    }
                # Buy-side liquidity sweep (Bearish Setup)
                elif current['High'] > current.get('Last_Swing_High', 999999):
                    state = "SWEPT_BEARISH"
                    setup_data = {
                        'direction': 'SHORT',
                        'sweep_high': current['High'],
                        'mss_trigger': current.get('Last_Swing_Low', -1),
                        'target': current.get('Last_Swing_Low', np.nan)
                    }

            # --- 2. WAITING FOR MARKET STRUCTURE SHIFT & FVG ---
            elif state == "SWEPT_BULLISH":
                # Invalidation: Drops lower than initial sweep
                if current['Low'] < setup_data['sweep_low']:
                    setup_data['sweep_low'] = current['Low'] 
                
                # MSS Triggered: Closed above prior swing high
                elif current['Close'] > setup_data['mss_trigger']:
                    if current.get('Bullish_FVG', False) or prev.get('Bullish_FVG', False):
                        state = "MSS_CONFIRMED"
                        setup_data['entry_price'] = current['Bullish_FVG_Top'] if current.get('Bullish_FVG') else prev['Bullish_FVG_Top']
                        setup_data['stop_loss'] = setup_data['sweep_low'] * 0.998
                        setup_data['date'] = self.df.index[i].strftime('%Y-%m-%d')
                    else:
                        state = "SEARCHING"

            elif state == "SWEPT_BEARISH":
                if current['High'] > setup_data['sweep_high']:
                    setup_data['sweep_high'] = current['High']
                
                elif current['Close'] < setup_data['mss_trigger']:
                    if current.get('Bearish_FVG', False) or prev.get('Bearish_FVG', False):
                        state = "MSS_CONFIRMED"
                        setup_data['entry_price'] = current['Bearish_FVG_Bottom'] if current.get('Bearish_FVG') else prev['Bearish_FVG_Bottom']
                        setup_data['stop_loss'] = setup_data['sweep_high'] * 1.002
                        setup_data['date'] = self.df.index[i].strftime('%Y-%m-%d')
                    else:
                        state = "SEARCHING"

            # --- 3. WAITING FOR ENTRY (RETRACEMENT) ---
            elif state == "MSS_CONFIRMED":
                # Invalidation: Stop loss hit before entry
                if setup_data['direction'] == 'LONG' and current['Low'] < setup_data['stop_loss']:
                    state = "SEARCHING"
                elif setup_data['direction'] == 'SHORT' and current['High'] > setup_data['stop_loss']:
                    state = "SEARCHING"
                
                # Triggered Entry
                elif setup_data['direction'] == 'LONG' and current['Low'] <= setup_data['entry_price']:
                    state = "IN_TRADE"
                elif setup_data['direction'] == 'SHORT' and current['High'] >= setup_data['entry_price']:
                    state = "IN_TRADE"

        # Return the final state of the asset on the current day
        setup_data['current_state'] = state
        return setup_data
