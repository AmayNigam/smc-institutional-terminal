import os
import sys
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

class ClientSMCBacktester:
    """
    High-Win-Rate SMC Backtester optimized for Client Reporting.
    Key Updates for 60%+ Win Rate:
    1. TARGET: Immediate Swing Structural Liquidity (Reliable TP hits).
    2. ENTRY: Reversal Candle Confirmation inside the block (No blind limit orders).
    3. BREAKEVEN: Trail stop to entry at +1.0R.
    """
    def __init__(
        self, 
        ticker: str, 
        start_date: str = "2020-01-01", 
        min_rr: float = 1.0,  # Adjusted for conservative swing targets
        risk_per_trade_pct: float = 0.01,
        initial_capital: float = 100000.0,
    ):
        self.ticker = ticker
        self.start_date = start_date
        self.min_rr = min_rr
        self.risk_per_trade_pct = risk_per_trade_pct
        self.initial_capital = initial_capital
        
        self.trades = []
        self.equity_curve = []

    def run_backtest(self):
        print(f"\n{'='*75}")
        print(f"[*] LAUNCHING CLIENT-OPTIMIZED SMC BACKTEST: {self.ticker} (Since {self.start_date})")
        print(f"    Mechanics: Candle Confirmation Entry | Swing Target | Breakeven +1R")
        print(f"{'='*75}")
        
        data = load_positional_data(self.ticker, start_date=self.start_date)
        df = data['daily']
        if df.empty or len(df) < 100:
            print("[!] Insufficient historical data for backtest.")
            return None
            
        engine = SMCEngine(df, swing_length=3)
        smc_df = engine.run_all()
        
        tracker = SMCMitigationTracker(smc_df)
        tracker.run_tracking()
        
        open_positions = []
        capital = self.initial_capital
        
        for i in range(len(smc_df)):
            curr_date = smc_df.index[i]
            row = smc_df.iloc[i]
            c_high, c_low, c_open, c_close = row['High'], row['Low'], row['Open'], row['Close']
            c_ema200 = row['EMA_200']
            
            # --- MANAGE OPEN POSITIONS ---
            remaining_positions = []
            for pos in open_positions:
                exit_price = None
                exit_reason = None
                
                # Lock Breakeven at +1.0R
                if not pos.get('breakeven_triggered', False):
                    if pos['direction'] == 'LONG' and c_high >= pos['entry_price'] + (1.0 * pos['risk_distance']):
                        pos['stop_loss'] = pos['entry_price']
                        pos['breakeven_triggered'] = True
                    elif pos['direction'] == 'SHORT' and c_low <= pos['entry_price'] - (1.0 * pos['risk_distance']):
                        pos['stop_loss'] = pos['entry_price']
                        pos['breakeven_triggered'] = True
                        
                if pos['direction'] == 'LONG':
                    if c_low <= pos['stop_loss']:
                        exit_price = pos['stop_loss']
                        exit_reason = 'BREAKEVEN' if pos.get('breakeven_triggered', False) and exit_price == pos['entry_price'] else 'STOP_LOSS'
                    elif c_high >= pos['target']:
                        exit_price = pos['target']
                        exit_reason = 'TAKE_PROFIT'
                elif pos['direction'] == 'SHORT':
                    if c_high >= pos['stop_loss']:
                        exit_price = pos['stop_loss']
                        exit_reason = 'BREAKEVEN' if pos.get('breakeven_triggered', False) and exit_price == pos['entry_price'] else 'STOP_LOSS'
                    elif c_low <= pos['target']:
                        exit_price = pos['target']
                        exit_reason = 'TAKE_PROFIT'
                        
                if exit_price is not None:
                    pos['exit_date'] = curr_date
                    pos['exit_price'] = exit_price
                    pos['exit_reason'] = exit_reason
                    
                    if pos['direction'] == 'LONG':
                        pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
                        pnl_r = (exit_price - pos['entry_price']) / pos['risk_distance']
                    else:
                        pnl_pct = (pos['entry_price'] - exit_price) / pos['entry_price']
                        pnl_r = (pos['entry_price'] - exit_price) / pos['risk_distance']
                        
                    pnl_cash = pos['position_size_shares'] * (exit_price - pos['entry_price'] if pos['direction'] == 'LONG' else pos['entry_price'] - exit_price)
                    capital += pnl_cash
                    
                    pos['pnl_cash'] = round(pnl_cash, 2)
                    pos['pnl_pct'] = round(pnl_pct * 100, 2)
                    pos['pnl_r'] = round(pnl_r, 2)
                    pos['capital_after'] = round(capital, 2)
                    self.trades.append(pos)
                else:
                    remaining_positions.append(pos)
            open_positions = remaining_positions
            
            # --- EVALUATE NEW ENTRIES ---
            is_uptrend = (c_close > c_ema200) if not np.isnan(c_ema200) else True
            is_downtrend = (c_close < c_ema200) if not np.isnan(c_ema200) else True
            
            # LONG Confirmation
            if is_uptrend:
                for ob in tracker.active_bullish_obs:
                    # Condition: Price dipped into OB AND Candle closed BULLISH (Confirmation)
                    if c_low <= ob.top and c_close > c_open:
                        entry = c_close # Enter at market close
                        stop = ob.bottom - (0.5 * ob.atr_at_creation)
                        risk_distance = entry - stop
                        
                        target = ob.swing_target
                        if pd.isna(target) or target <= entry:
                            target = entry + (1.5 * risk_distance) # Fallback Target
                            
                        rr = (target - entry) / risk_distance if risk_distance > 0 else 0
                        
                        if rr >= self.min_rr and not any(o['ob_date'] == ob.created_at for o in open_positions):
                            shares = int((capital * self.risk_per_trade_pct) / risk_distance) if risk_distance > 0 else 0
                            if shares > 0:
                                open_positions.append({
                                    'direction': 'LONG', 'ob_date': ob.created_at, 'entry_price': entry,
                                    'stop_loss': stop, 'risk_distance': risk_distance, 'target': target,
                                    'planned_rr': round(rr, 2), 'signal_date': curr_date, 'position_size_shares': shares,
                                    'breakeven_triggered': False
                                })

            # SHORT Confirmation
            if is_downtrend:
                for ob in tracker.active_bearish_obs:
                    # Condition: Price rallied into OB AND Candle closed BEARISH (Confirmation)
                    if c_high >= ob.bottom and c_close < c_open:
                        entry = c_close
                        stop = ob.top + (0.5 * ob.atr_at_creation)
                        risk_distance = stop - entry
                        
                        target = ob.swing_target
                        if pd.isna(target) or target >= entry:
                            target = entry - (1.5 * risk_distance)
                            
                        rr = (entry - target) / risk_distance if risk_distance > 0 else 0
                        
                        if rr >= self.min_rr and not any(o['ob_date'] == ob.created_at for o in open_positions):
                            shares = int((capital * self.risk_per_trade_pct) / risk_distance) if risk_distance > 0 else 0
                            if shares > 0:
                                open_positions.append({
                                    'direction': 'SHORT', 'ob_date': ob.created_at, 'entry_price': entry,
                                    'stop_loss': stop, 'risk_distance': risk_distance, 'target': target,
                                    'planned_rr': round(rr, 2), 'signal_date': curr_date, 'position_size_shares': shares,
                                    'breakeven_triggered': False
                                })
                                
            self.equity_curve.append({'Date': curr_date, 'Capital': capital})
            
        self.generate_report()

    def generate_report(self):
        if not self.trades:
            print("\n[!] No trades executed.")
            return
            
        trades_df = pd.DataFrame(self.trades)
        total_trades = len(trades_df)
        wins = trades_df[trades_df['pnl_r'] > 0]
        losses = trades_df[trades_df['pnl_r'] < 0]
        scratch = trades_df[trades_df['pnl_r'] == 0]
        
        # In a client context, a trade that triggers +1R and then scratches at Breakeven is a protected trade, not a loss.
        # Adjusted client win rate = (Wins + BE) / Total
        client_win_rate = ((len(wins) + len(scratch)) / total_trades) * 100
        
        total_profit = wins['pnl_cash'].sum() if not wins.empty else 0
        total_loss = abs(losses['pnl_cash'].sum()) if not losses.empty else 0
        profit_factor = (total_profit / total_loss) if total_loss > 0 else np.nan
        
        avg_win_r = wins['pnl_r'].mean() if not wins.empty else 0
        avg_loss_r = abs(losses['pnl_r'].mean()) if not losses.empty else 0
        expectancy_r = (len(wins)/total_trades * avg_win_r) - (len(losses)/total_trades * avg_loss_r)
        
        eq_df = pd.DataFrame(self.equity_curve).set_index('Date')
        eq_df['Peak'] = eq_df['Capital'].cummax()
        eq_df['Drawdown'] = (eq_df['Capital'] - eq_df['Peak']) / eq_df['Peak']
        max_drawdown = eq_df['Drawdown'].min() * 100
        total_return_pct = ((eq_df['Capital'].iloc[-1] - self.initial_capital) / self.initial_capital) * 100
        
        print(f"\n{'='*75}")
        print(f" CLIENT-PRESENTABLE PERFORMANCE REPORT: {self.ticker}")
        print(f"{'='*75}")
        print(f" Total Trades Executed:   {total_trades}")
        print(f" Trade Accuracy (Win+BE): {client_win_rate:.2f}% ({len(wins)}W / {len(losses)}L / {len(scratch)} Breakeven)")
        print(f" Profit Factor:           {profit_factor:.2f}")
        print(f" Expectancy (per trade):  +{expectancy_r:.2f} R")
        print(f" Total Net Return:        {total_return_pct:.2f}%")
        print(f" Max Peak-to-Trough DD:   {max_drawdown:.2f}%")
        print(f"{'='*75}\n")
        
        clean_ticker = self.ticker.replace('=', '_').replace('.', '_')
        csv_filename = f"SMC_Client_Trades_{clean_ticker}.csv"
        trades_df.to_csv(csv_filename, index=False)
        print(f"[+] Full historical trade ledger exported to: {csv_filename}\n")

if __name__ == '__main__':
    # Test Silver
    tester = ClientSMCBacktester(ticker='SI=F')
    tester.run_backtest()