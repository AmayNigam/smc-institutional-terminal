import pandas as pd
import numpy as np

class SMCEngine:
    """
    High-Accuracy Institutional SMC Engine.
    Optimized for Client-Presentable Win Rates (55-65%+).
    """
    def __init__(self, df: pd.DataFrame, swing_length: int = 3):
        self.df = df.copy()
        self.swing_length = swing_length
        self.length = len(df)
        
    def _add_institutional_filters(self):
        # 1. Macro Trends (200 & 50 EMA)
        self.df['EMA_200'] = self.df['Close'].ewm(span=200, adjust=False).mean()
        self.df['EMA_50'] = self.df['Close'].ewm(span=50, adjust=False).mean()
        
        # 2. Volatility Baseline (ATR)
        tr1 = self.df['High'] - self.df['Low']
        tr2 = (self.df['High'] - self.df['Close'].shift()).abs()
        tr3 = (self.df['Low'] - self.df['Close'].shift()).abs()
        self.df['ATR'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean().bfill()
        
        # 3. Momentum Displacement (0.5x ATR allows healthy trends)
        self.df['Body_Size'] = (self.df['Close'] - self.df['Open']).abs()
        self.df['Is_Displacement'] = self.df['Body_Size'] >= (0.5 * self.df['ATR'])

    def detect_swings(self):
        window_size = (2 * self.swing_length) + 1
        
        # 1. Vectorized rolling max/min (center=True aligns the window around the target)
        rolling_max = self.df['High'].rolling(window=window_size, center=True).max()
        rolling_min = self.df['Low'].rolling(window=window_size, center=True).min()
        
        # 2. Identify swings without looping
        self.df['Swing_High'] = np.where(self.df['High'] == rolling_max, self.df['High'], np.nan)
        self.df['Swing_Low'] = np.where(self.df['Low'] == rolling_min, self.df['Low'], np.nan)
        
        # 3. Shift forward by swing_length to simulate real-time "confirmation" delay
        self.df['Confirmed_Swing_High'] = self.df['Swing_High'].shift(self.swing_length)
        self.df['Confirmed_Swing_Low'] = self.df['Swing_Low'].shift(self.swing_length)
        
        # 4. Forward fill to maintain the last known swing
        self.df['Last_Swing_High'] = self.df['Confirmed_Swing_High'].ffill()
        self.df['Last_Swing_Low'] = self.df['Confirmed_Swing_Low'].ffill()
        
        # 5. Premium & Discount Dealing Range Matrix
        self.df['Dealing_Range_Mid'] = (self.df['Last_Swing_High'] + self.df['Last_Swing_Low']) / 2.0
        self.df['In_Discount'] = self.df['Low'] < self.df['Dealing_Range_Mid']
        self.df['In_Premium'] = self.df['High'] > self.df['Dealing_Range_Mid']

    def detect_fair_value_gaps(self):
        # Valid Bullish FVG requires momentum displacement
        self.df['Bullish_FVG'] = (self.df['Low'] > self.df['High'].shift(2)) & self.df['Is_Displacement'].shift(1) & (self.df['Close'].shift(1) > self.df['Open'].shift(1))
        self.df['Bullish_FVG_Top'] = np.where(self.df['Bullish_FVG'], self.df['Low'], np.nan)
        self.df['Bullish_FVG_Bottom'] = np.where(self.df['Bullish_FVG'], self.df['High'].shift(2), np.nan)
        self.df['Bullish_FVG_Eq'] = (self.df['Bullish_FVG_Top'] + self.df['Bullish_FVG_Bottom']) / 2
        
        # Valid Bearish FVG requires momentum displacement
        self.df['Bearish_FVG'] = (self.df['High'] < self.df['Low'].shift(2)) & self.df['Is_Displacement'].shift(1) & (self.df['Close'].shift(1) < self.df['Open'].shift(1))
        self.df['Bearish_FVG_Top'] = np.where(self.df['Bearish_FVG'], self.df['Low'].shift(2), np.nan)
        self.df['Bearish_FVG_Bottom'] = np.where(self.df['Bearish_FVG'], self.df['High'], np.nan)
        self.df['Bearish_FVG_Eq'] = (self.df['Bearish_FVG_Top'] + self.df['Bearish_FVG_Bottom']) / 2

    def run_all(self) -> pd.DataFrame:
        self._add_institutional_filters()
        self.detect_swings()
        self.detect_fair_value_gaps()
        return self.df
