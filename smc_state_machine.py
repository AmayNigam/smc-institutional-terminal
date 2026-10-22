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
