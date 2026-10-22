import pandas as pd
import numpy as np
import plotly.graph_objects as go
from smc_state_machine import SMCMitigationTracker

class SMCChartEngine:
    """
    Ultra-Clean TradingView-Grade Visual Engine.
    Faithfully replicates the LuxAlgo SMC visual hierarchy:
    - Minimalist candle presentation with NO gridlines.
    - Soft, semi-transparent Order Blocks (+OB / -OB) with solid borders.
    - Borderless Fair Value Gaps (FVG).
    - Clean BOS / CHoCH structural break lines.
    - Premium, Equilibrium, and Discount dealing range bands.
    - Zero chart clutter.
    """
    def __init__(self, df: pd.DataFrame, tracker: SMCMitigationTracker, ticker: str):
        self.df = df
        self.tracker = tracker
        self.ticker = ticker

    def render_chart(self, num_bars: int = 180, save_html: bool = False, theme: str = 'light'):
        plot_df = self.df.tail(num_bars).copy()
        
        # Color palettes matching TradingView LuxAlgo
        if theme == 'light':
            bg_color = '#ffffff'
            text_color = '#131722'
            up_color = '#089981'     # TradingView Mint Green
            down_color = '#F23645'   # TradingView Coral Red
            bull_ob_fill = 'rgba(8, 153, 129, 0.12)'
            bull_ob_line = 'rgba(8, 153, 129, 0.60)'
            bear_ob_fill = 'rgba(242, 54, 69, 0.12)'
            bear_ob_line = 'rgba(242, 54, 69, 0.60)'
            prem_fill = 'rgba(242, 54, 69, 0.06)'
            disc_fill = 'rgba(8, 153, 129, 0.06)'
            eq_line_color = '#878b94'
            fvg_bull_fill = 'rgba(41, 98, 255, 0.15)' # TradingView FVG Blue
            fvg_bear_fill = 'rgba(255, 152, 0, 0.15)' # TradingView FVG Orange
        else:
            bg_color = '#131722'
            text_color = '#d1d4dc'
            up_color = '#089981'
            down_color = '#F23645'
            bull_ob_fill = 'rgba(8, 153, 129, 0.18)'
            bull_ob_line = 'rgba(8, 153, 129, 0.70)'
            bear_ob_fill = 'rgba(242, 54, 69, 0.18)'
            bear_ob_line = 'rgba(242, 54, 69, 0.70)'
            prem_fill = 'rgba(242, 54, 69, 0.08)'
            disc_fill = 'rgba(8, 153, 129, 0.08)'
            eq_line_color = '#787b86'
            fvg_bull_fill = 'rgba(41, 98, 255, 0.20)'
            fvg_bear_fill = 'rgba(255, 152, 0, 0.20)'

        fig = go.Figure()

        # -------------------------------------------------------------
        # 1. CANDLESTICK TRACE
        # -------------------------------------------------------------
        fig.add_trace(go.Candlestick(
            x=plot_df.index,
            open=plot_df['Open'],
            high=plot_df['High'],
            low=plot_df['Low'],
            close=plot_df['Close'],
            name=f'{self.ticker}',
            increasing_line_color=up_color,
            increasing_fillcolor=up_color,
            decreasing_line_color=down_color,
            decreasing_fillcolor=down_color,
            line=dict(width=1)
        ))

        shapes = []
        annotations = []
        last_date = plot_df.index[-1]
        start_date = plot_df.index[0]

        # -------------------------------------------------------------
        # 2. PREMIUM & DISCOUNT ZONES (Dealing Range)
        # -------------------------------------------------------------
        highest_p = plot_df['High'].max()
        lowest_p = plot_df['Low'].min()
        eq_p = (highest_p + lowest_p) / 2.0
        
        shapes.append(dict(
            type="rect",
            x0=start_date, y0=eq_p, x1=last_date, y1=highest_p,
            fillcolor=prem_fill, line=dict(width=0), layer="below"
        ))
        annotations.append(dict(
            x=last_date, y=highest_p, text="Premium", showarrow=False,
            xanchor="left", yanchor="top", font=dict(color=down_color, size=10)
        ))

        shapes.append(dict(
            type="line",
            x0=start_date, y0=eq_p, x1=last_date, y1=eq_p,
            line=dict(color=eq_line_color, width=1, dash="dot"), layer="below"
        ))
        annotations.append(dict(
            x=last_date, y=eq_p, text="Equilibrium", showarrow=False,
            xanchor="left", yanchor="middle", font=dict(color=eq_line_color, size=10)
        ))

        shapes.append(dict(
            type="rect",
            x0=start_date, y0=lowest_p, x1=last_date, y1=eq_p,
            fillcolor=disc_fill, line=dict(width=0), layer="below"
        ))
        annotations.append(dict(
            x=last_date, y=lowest_p, text="Discount", showarrow=False,
            xanchor="left", yanchor="bottom", font=dict(color=up_color, size=10)
        ))

        # -------------------------------------------------------------
        # 3. RECENT UNMITIGATED ORDER BLOCKS (Max 3 Bullish, 3 Bearish)
        # -------------------------------------------------------------
        recent_bull_obs = [ob for ob in self.tracker.active_bullish_obs if ob.top >= lowest_p * 0.90][-3:]
        recent_bear_obs = [ob for ob in self.tracker.active_bearish_obs if ob.bottom <= highest_p * 1.10][-3:]

        for ob in recent_bull_obs:
            ob_start = ob.created_at if ob.created_at >= start_date else start_date
            shapes.append(dict(
                type="rect",
                x0=ob_start, y0=ob.bottom, x1=last_date, y1=ob.top,
                fillcolor=bull_ob_fill,
                line=dict(color=bull_ob_line, width=2), # Upgraded width for bold border
                layer="below"
            ))
            annotations.append(dict(
                x=last_date, y=(ob.top + ob.bottom)/2, text="+OB", showarrow=False,
                xanchor="left", yanchor="middle", font=dict(color=up_color, size=9)
            ))

        for ob in recent_bear_obs:
            ob_start = ob.created_at if ob.created_at >= start_date else start_date
            shapes.append(dict(
                type="rect",
                x0=ob_start, y0=ob.bottom, x1=last_date, y1=ob.top,
                fillcolor=bear_ob_fill,
                line=dict(color=bear_ob_line, width=2), # Upgraded width for bold border
                layer="below"
            ))
            annotations.append(dict(
                x=last_date, y=(ob.top + ob.bottom)/2, text="-OB", showarrow=False,
                xanchor="left", yanchor="middle", font=dict(color=down_color, size=9)
            ))

        # -------------------------------------------------------------
        # 4. FAIR VALUE GAPS (FVGs)
        # -------------------------------------------------------------
        if 'Bullish_FVG' in plot_df.columns:
            bull_fvgs = plot_df[plot_df['Bullish_FVG'] == True].tail(3) # Get last 3 imbalances
            for idx, row in bull_fvgs.iterrows():
                shapes.append(dict(
                    type="rect",
                    x0=idx, y0=row.get('Bullish_FVG_Bottom', row['Low']), 
                    x1=last_date, y1=row.get('Bullish_FVG_Top', row['High']),
                    fillcolor=fvg_bull_fill, line_width=0, layer="below" # Borderless
                ))

        if 'Bearish_FVG' in plot_df.columns:
            bear_fvgs = plot_df[plot_df['Bearish_FVG'] == True].tail(3) # Get last 3 imbalances
            for idx, row in bear_fvgs.iterrows():
                shapes.append(dict(
                    type="rect",
                    x0=idx, y0=row.get('Bearish_FVG_Bottom', row['Low']), 
                    x1=last_date, y1=row.get('Bearish_FVG_Top', row['High']),
                    fillcolor=fvg_bear_fill, line_width=0, layer="below" # Borderless
                ))

        # -------------------------------------------------------------
        # 5. SUBTLE STRUCTURAL BREAKS (BOS & CHoCH)
        # -------------------------------------------------------------
        if 'Last_Swing_High' in plot_df.columns and 'Last_Swing_Low' in plot_df.columns:
            for i in range(1, len(plot_df)):
                curr_c = plot_df['Close'].iloc[i]
                prev_c = plot_df['Close'].iloc[i-1]
                last_sh = plot_df['Last_Swing_High'].iloc[i]
                last_sl = plot_df['Last_Swing_Low'].iloc[i]
                bar_date = plot_df.index[i]

                if pd.notna(last_sh) and prev_c <= last_sh < curr_c:
                    annotations.append(dict(
                        x=bar_date, y=last_sh, text="BOS", showarrow=False,
                        yanchor="bottom", font=dict(color=up_color, size=8, family="monospace")
                    ))
                    shapes.append(dict(
                        type="line",
                        x0=plot_df.index[max(0, i-6)], y0=last_sh, x1=bar_date, y1=last_sh,
                        line=dict(color=up_color, width=1, dash="dash"), layer="below"
                    ))

                if pd.notna(last_sl) and prev_c >= last_sl > curr_c:
                    annotations.append(dict(
                        x=bar_date, y=last_sl, text="BOS", showarrow=False,
                        yanchor="top", font=dict(color=down_color, size=8, family="monospace")
                    ))
                    shapes.append(dict(
                        type="line",
                        x0=plot_df.index[max(0, i-6)], y0=last_sl, x1=bar_date, y1=last_sl,
                        line=dict(color=down_color, width=1, dash="dash"), layer="below"
                    ))

        # -------------------------------------------------------------
        # 6. CURRENT LIVE PRICE LINE
        # -------------------------------------------------------------
        current_price = plot_df['Close'].iloc[-1]
        shapes.append(dict(
            type="line",
            x0=start_date, y0=current_price, x1=last_date, y1=current_price,
            line=dict(color=down_color if current_price < plot_df['Open'].iloc[-1] else up_color, width=1, dash="dot")
        ))

        # -------------------------------------------------------------
        # 7. TRADINGVIEW AESTHETIC LAYOUT CONFIGURATION (UPGRADED)
        # -------------------------------------------------------------
        fig.update_layout(
            title=dict(
                text=f"<b>{self.ticker}</b> • 1D • Smart Money Concepts",
                font=dict(color=text_color, size=15, family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"),
                x=0.03, y=0.96
            ),
            plot_bgcolor=bg_color,
            paper_bgcolor=bg_color,
            font=dict(color=text_color, family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"),
            xaxis=dict(
                showgrid=False,       # NO GRIDLINES
                zeroline=False,
                rangeslider=dict(visible=False), # HIDE BULKY SLIDER
                rangebreaks=[dict(bounds=["sat", "mon"])], # NATIVELY REMOVES WEEKENDS
                tickformat="%Y-%m-%d", # CLEAN DATE FORMAT
                nticks=10,            # PREVENTS CROWDING/OVERLAPPING
                tickangle=0,          # KEEPS TEXT HORIZONTAL
                tickfont=dict(color='#787b86', size=11)
            ),
            yaxis=dict(
                side='right',         # TRADINGVIEW STANDARD RIGHT SIDE
                showgrid=False,       # NO GRIDLINES
                zeroline=False,
                tickfont=dict(color='#787b86', size=11),
                tickformat=',.2f',
                range=[lowest_p * 0.98, highest_p * 1.02]
            ),
            shapes=shapes,
            annotations=annotations,
            height=700,
            margin=dict(l=20, r=80, t=50, b=30),
            showlegend=False,
            hovermode='x'
        )

        if save_html:
            clean_ticker = self.ticker.replace('=', '_').replace('.', '_')
            filename = f"SMC_Chart_{clean_ticker}.html"
            fig.write_html(
                filename, 
                include_plotlyjs='cdn', 
                full_html=True,
                config={'displayModeBar': False, 'scrollZoom': True}
            )
            print(f"[+] Clean TradingView-styled chart saved to: {filename}")

        return fig
