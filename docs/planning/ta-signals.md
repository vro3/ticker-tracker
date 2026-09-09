# TA Signals for Ticker Tracker cards
Version 1.0 · 2026-09-08 · implemented in tracker/ta.py and tracker/alerts.py; research notes below

All rules use daily OHLCV already stored in `prices`. Intraday-only ideas (VWAP, multi-timeframe squeeze) are out of scope.

## 1. Supply & demand zones (Vince's strategy)
Sources: threads 12162 (Order Block Finder), 652 (S&D Candles), 19413 (LuxAlgo dynamic OBs), 19999 (AlgoAlpha), 172 (ZigZag S&D), 11941 (explainer: ToS has no real order-flow data; all forum S&D indicators are candle-pattern approximations).

Base/impulse classification (thread 652): body/range <= 0.50 = base ("boring"); body/range > 0.60 and range >= 1.5*ATR = impulse ("exciting"). Zone = high/low of the 1-5 base candles between two impulse candles.
- Rally-Base-Drop -> supply. Drop-Base-Rally -> demand. RBR -> demand (continuation). DBD -> supply.
Order-block variant (12162): last red candle before N=5 consecutive greens = demand (bounds open..low); mirror for supply.
Zone state (19413/19999): wicks test, closes break. Demand broken when close < bottom; tested when low <= top. Fresh = untouched. Discard after 2+ tests or ~120 bars. "Sweep" = low < bottom but close > bottom (strong hold).

## 2. EMAs
Sources: 229 (Mobius MA crossover), 7152 (8/21 exits). Most popular: 8/21. Also 9/20, 20/50/200.
Signals: bull/bear cross of 8 over 21, bars since cross, close vs 20/50/200, pullback-to-21 while 8>21 and 50>200.

## 3. Bollinger Bands
Sources: 1666, 15338 (Beardy Squeeze Pro), 19929, 762, 19071, 18779.
- TTM Squeeze: BB(20, 2.0) inside Keltner(20, 1.5 ATR) = squeeze on; first bar out = fired. Momentum = linreg of close minus midline of (20-bar donchian mid + EMA20), 20 bars.
- Bandwidth = (upper-lower)/mid; squeeze when at 120-bar low. %B = (close-lower)/(upper-lower).
- Mean reversion: close < lower and RSI14 <= 30 = buy signal; close > upper and RSI14 >= 70 = sell. Exit at midline.
- Band walk: 3 of last 5 bars with %B > 0.8 (or < 0.2) = trending, suppress mean-reversion signals.

## 4. Others
- RSI divergence (9626, Mobius): RSI14, pivots 7 bars each side, price lower low + RSI higher low = bullish.
- MACD 12/26/9 (7745, 558): signal cross, zero cross, histogram flip.
- ATR trailing stop (2095): 3.5 x Wilder ATR(5). Chandelier (177): highest(high,10) - 3*ATR(10), flip on close.
- "Buy the Dip" (3553) is paid, no code. Approximation: close near 20-day low, RSI14 < 30, above EMA200.

## Proposed card fields
zones[] {type, top, bottom, state, tests, age}; ema {8,21,50,200, cross, bars_since}; bb {pctB, bandwidth, squeeze_on, squeeze_bars, fired, momo, walk}; rsi14, rsi_div; macd {hist, cross}; atr_stop.
