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
        self.swing_target = swing_target 
        
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
                local_lows = self.df['Low'].iloc[max(0, i - 5):i]
                if not local_lows.empty and row['Low'] > local_lows.min():
                    continue  
                return (self.df.index[i], row['High'], row['Low'])
                
            elif direction == 'BEARISH' and is_up_candle:
                local_highs = self.df['High'].iloc[max(0, i - 5):i]
                if not local_highs.empty and row['High'] < local_highs.max():
                    continue  
                return (self.df.index[i], row['High'], row['Low'])
                
        return None, None, None

    def run_tracking(self) -> pd.DataFrame:
        self.df['Active_Bull_OB_Count'] = 0
        self.df['Active_Bear_OB_Count'] = 0
        
        for i in range(len(self.df)):
            current_date = self.df.index[i]
            row = self.df.iloc[i]
            c_high, c_low, c_atr = row['High'], row['Low'], row['ATR']
            
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
            
            self.df.iat[i, self.df.columns.get_loc('Active_Bull_OB_Count')] = len(self.active_bullish_obs)
            self.df.iat[i, self.df.columns.get_loc('Active_Bear_OB_Count')] = len(self.active_bearish_obs)
            
        return self.df


class ICTSweepAndShiftEngine:
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
                # Sell-side liquidity sweep (Bullish Setup - LONG)
                if current['Low'] < current.get('Last_Swing_Low', -1):
                    state = "SWEPT_BULLISH"
                    
                    target = current.get('Last_Swing_High', np.nan)
                    for j in range(i-1, max(0, i-20), -1):
                        past_high = self.df['Confirmed_Swing_High'].iloc[j]
                        if pd.notna(past_high) and past_high > current['Low']:
                            target = past_high
                            break
                    if pd.isna(target):
                        target = current['Low'] * 1.03
                            
                    setup_data = {
                        'direction': 'LONG',
                        'sweep_low': current['Low'],
                        'mss_trigger': current.get('Last_Swing_High', 999999),
                        'target': target
                    }
                    
                # Buy-side liquidity sweep (Bearish Setup - SHORT)
                elif current['High'] > current.get('Last_Swing_High', 999999):
                    state = "SWEPT_BEARISH"
                    
                    target = current.get('Last_Swing_Low', np.nan)
                    for j in range(i-1, max(0, i-20), -1):
                        past_low = self.df['Confirmed_Swing_Low'].iloc[j]
                        if pd.notna(past_low) and past_low < current['High']:
                            target = past_low
                            break
                    if pd.isna(target):
                        target = current['High'] * 0.97
                            
                    setup_data = {
                        'direction': 'SHORT',
                        'sweep_high': current['High'],
                        'mss_trigger': current.get('Last_Swing_Low', -1),
                        'target': target
                    }

            # --- 2. WAITING FOR MARKET STRUCTURE SHIFT & FVG ---
            elif state == "SWEPT_BULLISH":
                if current['Low'] < setup_data['sweep_low']:
                    setup_data['sweep_low'] = current['Low'] 
                
                elif current['Close'] > setup_data['mss_trigger']:
                    if current.get('Bullish_FVG', False) or prev.get('Bullish_FVG', False):
                        state = "MSS_CONFIRMED"
                        entry = current['Bullish_FVG_Top'] if current.get('Bullish_FVG') else prev['Bullish_FVG_Top']
                        stop_loss = setup_data['sweep_low'] - (current.get('ATR', entry * 0.01) * 0.2)
                        
                        # Ensure target is strictly higher than entry for LONG
                        target = max(setup_data['target'], entry + (entry - stop_loss) * 2)
                        
                        setup_data['entry_price'] = entry
                        setup_data['stop_loss'] = stop_loss
                        setup_data['target'] = target
                        setup_data['date'] = self.df.index[i].strftime('%Y-%m-%d')
                    else:
                        state = "SEARCHING"

            elif state == "SWEPT_BEARISH":
                if current['High'] > setup_data['sweep_high']:
                    setup_data['sweep_high'] = current['High']
                
                elif current['Close'] < setup_data['mss_trigger']:
                    if current.get('Bearish_FVG', False) or prev.get('Bearish_FVG', False):
                        state = "MSS_CONFIRMED"
                        entry = current['Bearish_FVG_Bottom'] if current.get('Bearish_FVG') else prev['Bearish_FVG_Bottom']
                        stop_loss = setup_data['sweep_high'] + (current.get('ATR', entry * 0.01) * 0.2)
                        
                        # CORRECTION: For SHORT, target MUST be strictly LOWER than entry
                        target = min(setup_data['target'], entry - (stop_loss - entry) * 2)
                        if target >= entry:
                            target = entry * 0.97 # Absolute safety fallback
                        
                        setup_data['entry_price'] = entry
                        setup_data['stop_loss'] = stop_loss
                        setup_data['target'] = target
                        setup_data['date'] = self.df.index[i].strftime('%Y-%m-%d')
                    else:
                        state = "SEARCHING"

            # --- 3. WAITING FOR ENTRY (RETRACEMENT) ---
            elif state == "MSS_CONFIRMED":
                if setup_data['direction'] == 'LONG' and current['Low'] < setup_data['stop_loss']:
                    state = "SEARCHING"
                elif setup_data['direction'] == 'SHORT' and current['High'] > setup_data['stop_loss']:
                    state = "SEARCHING"
                
                elif setup_data['direction'] == 'LONG' and current['Low'] <= setup_data['entry_price']:
                    state = "IN_TRADE"
                elif setup_data['direction'] == 'SHORT' and current['High'] >= setup_data['entry_price']:
                    state = "IN_TRADE"

        setup_data['current_state'] = state
        return setup_data
