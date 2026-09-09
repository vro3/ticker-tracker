# thinkScript export vs dashboard
Version 1.0 · 2026-09-08 · export lives at ~/thinkscripts on the Mac mini (not in the repo, it is Vince's private code)

I've read the full INDEX and the code for every study cited below. Report follows (no files were modified).

# thinkScript Export vs. Dashboard — Gap Report

Source: `/Users/m4mini/thinkscripts/thinkscripts-export/` (398 files, INDEX.md read fully; ~75 .ts files opened).

## 1. ALREADY COVERED

**TTM squeeze** — `TTMScanner.ts`, `Squeezewfire.ts`, `SqueezeMobiusMomentum.ts`, `AdvancedSqueezeBullBreakout.ts`, `shared_SQ_MTF.ts`, `Squeeze_30min.ts`, `TTM_Multi.ts`. All use BB 20/2.0 vs KC 20/1.5 (SMA ATR), squeeze = `Avg+2*SD < Avg+1.5*ATR`, fired = squeeze[1] and !squeeze. Momentum is `Inertia(close - ((Highest(h,20)+Lowest(l,20))/2 + EMA(close,20))/2, 20)` (linear regression, not raw close - midline; check ours). `SqueezeProGray.ts` adds three KC factors 1.0/1.5/2.0 (pro-style low/mid/high compression). `TTM_Multi.ts` counts bars in squeeze and bars since fire (useful label; trivial to add). `Squeeze_30min.ts` counts consecutive squeeze dots (1-7).

**EMA8 vs VWMA26** — `EMA8VIZ.ts`: identical to ours (`ExpAverage(close,8)` vs `Sum(v*c,26)/Sum(v,26)`, cross up/down).

**EMA 8/21 state, 50/200** — `ChartLabels_vr_op.ts` uses EMA13 and SMA 20/50/100/200 (SMA, not EMA, for 50/200 golden cross). `Saty_ATR_Levels.ts` uses EMA 8/21/34 stack for trend.

**Full time frame continuity** — `FTFCContinuity_D.ts` (D/2D/3D/W/M/Q), `shared_Continuity_600.ts` (1h/2h/4h), `shared_Continuity_*`, `Strat_Time_Frame_Continuity.ts`, `shared_STRAT_DAY_TRADE_1_5_15_30_60.ts`. Rule: `top = max(open across TFs)`, `bottom = min(open across TFs)`; FullUp = close >= top; FullDown = close <= bottom. Same as ours. They also include 2D/3D, which we don't.

**Supply/demand & order blocks** — `IV_RBR_ZONE.ts`, `IV_RBD_Zone.ts`, `IV_DBR_Zone.ts`, `IV_DBD_Zone.ts`, `*_scalp.ts` (3-4 candle color sequences: e.g. RBR-zone = up[3], down[2], up[1], up[0], open[3]<open[1], open[2]<close[1], high[1]==Highest(high[1],3)); `DynamicOrderBlocks.ts` (10-bar swing lookback); `SupplyDemandZones.ts`; `SupplyDemandAreas.ts`. Ours is impulse-base-impulse, so covered conceptually; theirs are strictly candle-color based without body-size filter.

**Gaps** — `FVG.ts`: bullish = 3 up candles and `high[2] < low[0]`; bearish mirror. Same as our three-candle gap. `GapFill.ts` (yesterday close vs today open, percent remaining) is intraday overlap.

**ATR trailing stop** — `shared_ACBStrat.ts` (3 Hull ATR stops: 0.7x/4, 1.5x/3, 3.0x/5), `SuperTrend.ts` (HL2 ± 1.0*HullATR(4)), `shared_STOP_TRAILING_PERCENTAGE1.ts` (Highest(high,10) - 1.0*WildersATR(17)). Our chandelier covers the concept; their multipliers are much tighter.

**RSI14, Bollinger %B, bandwidth, Keltner** — standard everywhere (`vr_MovingAverageCrossoverRSIIndicator.ts`, `KeltnerMomenturm.ts` 34/0.5).

## 2. VINCE'S OWN

| File | What it does | Computable? |
|---|---|---|
| `aaaPivotWithConfirmation.ts` | Pivot-low (5-bar) confirmed when close crosses above the pivot bar's high; then plots BTO, stop (pivot low), StDev trail (2.0x), add level (75% StDev), risk-out target. A full scale-in/scale-out ladder. | Yes, daily or 5m |
| `aaaVwapReversalBounce.ts` / `...2.ts` | Hammer/star at 10-bar low/high, on correct side of VWAP, IMI(21) <30/>70, TR filter. v2 forces 3m aggregation. Attribution RCONNER7, edited by Vince. | 5m only (needs VWAP) |
| `AveragePriceMovements_uts.ts` (aaaAveragePriceMovement) | Open ± ADR5/2 and ADR10/2 zones. | Yes, daily |
| `Artificial_Intelligence_Technical_Analysis_vr_op.ts` | 766 lines: 1st/2nd/3rd order pivot highs/lows (fractal recursion), zig-zag lines between them. Swing-structure mapper. | Yes, any TF; heavy |
| `ChartLabels_vr_op.ts` | HUD: daily RSI, VWAP, EMA13, SMA20/50/100/200, golden cross, earnings countdown. | Yes except earnings/PM price |
| `EnhancedVolume_vr_op.ts` | Buy vol = V*(C-L)/(H-L), sell vol = V*(H-C)/(H-L); highlight when RelativeVolumeStDev(60) >= 2. | Yes |
| `MultipeMACD_VR.ts` | MACD 12/26/9 across three aggregations (default D/W/M). | Yes, daily (W/M resampled) |
| `ORB_Breakout.ts` (ORBBreakout_vr) | 9:30-10:00 high/low; label Above/Below/Inside. | Yes, 5m |
| `vr_2PeriodRSITradingIndicator.ts` | RSI(2, Wilders) < 10 and close > EMA34 = bull; > 90 and close < EMA34 = bear. Connors-style. | Yes |
| `vr_MovAvgCrossoverPercentR.ts` | Williams %R(14) with SMA5 of %R, 30/70 crosses. | Yes |
| `vr_MovingAverageCrossoverRSIIndicator.ts` | RSI14 + SMA5 of RSI, 30/70 crosses. | Yes |
| `vr_TrueMomentumOscillator.ts` | TMO: sum over 14 bars of sign(close - open[i]), EMA5 then EMA3, signal EMA3; OB/OS at ±10. | Yes |
| `vr_VWAPVolumeBreakoutIndicator.ts` | close crosses VWAP while volume crosses above SMA20(volume). | 5m only |
| `vr_VWAP_study.ts` | VWAP ± 2 SD bands with labels. | 5m only |
| `vr_MobiusMACD_FREMA.ts` | MACD on Gaussian-smoothed price + forward/reverse EMA. | Yes; exotic |
| `vr_EhlersMAMABuyandSellSignalIndicator.ts` | MAMA/FAMA cross. | Yes; exotic |
| `vr_IchimokuHybrid_RSI_Laguerre.ts` | Ichimoku 8/21 on a nonlinear-filtered price + Laguerre RSI with fractal energy. | Yes; exotic |
| `vr_TOSstudy_charts.ts` | Earnings-date labels + Market Maker Move. | No (options/earnings data) |

## 3. TOP 10 TO ADD

**1. Strat bar type** — `Strat_bar_numbers.ts` (Pelonsax v2.0). Any TF.
```
inside  = H <= H[1] and L >= L[1]          # ties count as inside
outside = H >  H[1] and L <  L[1]
twoUp   = H >  H[1] and L >= L[1]
twoDown = H <= H[1] and L <  L[1]
type = 1 | 2U | 2D | 3 ; direction suffix from close vs open (Stratt.ts: 1U/1D/3U/3D)
```

**2. Strat reversal combos** — `shared_Strat_Reversal_BasicFour.ts`, `shared_REMIX_NO_PAINT0.ts`. Any TF.
```
2-1-2 bull: twoUp and inside[1] and twoDown[2]     (bear mirror)
2-2 bull:   twoUp and twoDown[1]
3 bull:     outside and C>O and (twoDown[1] or inside[1] or (outside[1] and C[1]<O[1]))
3-1-2 bull: twoUp and inside[1] and outsideDown[2] [BasicFour adds pivot_low[2]: low[2] <= Lowest(low,6) prior]
RevStrat bull: (twoUp and twoDown[1] and inside[2] and C > H[1]) or (outsideUp and inside[1] and C > H[1])
```

**3. Strat actionable signals** — `shared_REMIX_NO_PAINT0.ts`. Any TF.
```
InsideUp   = inside[1] and C crosses above H[1]
KickingBull= O >= H[1] and C > O and C[1] < O[1]
HammerRev  = Hammer[1] and C crosses above H[1]
MeasuredUp = TR[2] > 0.5*ATR(13) and L >= L[1]+ATR[1]/2 and inside[1] and C crosses above H[1]
Hammer: IsDescending(C,3)[1], body <= 0.3*avgBody(30), upper wick <= 0.25*avgBody, lower wick > 2.0*body
```

**4. Failed to Return** — `Failed_to_Return.ts`. Any TF (daily best).
```
Bull FTR: up[4],up[3],up[2],down[1],up[0], high[2]>high[1], close[3]<close[2], open[1]<close[0],
          low[2]<low[1], open[4]<open[3], close[4]<high[3], open[3]<open[2]
Bear FTR: down[4],down[3],down[2],up[1],down[0], close[4]>close[3], open[1]>close[0], close[1]>open[0],
          open[2]>close[1], open[4]>open[3], open[3]>open[2], close[3]>close[2], close[2]<open[1]
```

**5. Saty ATR Levels** — `Saty_ATR_Levels.ts`. Daily (also W/M/Q via period switch).
```
atr = WildersATR(14) of prior period; pc = prior close
trigger ±0.236*atr ; midrange ±0.618*atr ; ±1 atr ; extensions +0.236/+0.618/+1.0 beyond ±1atr
range_used = (period_high - period_low)/atr * 100     # "% of ATR used" label
trend: bullish = C>=EMA8>=EMA21>=EMA34 ; bearish mirror
```

**6. Minervini trend template + RS score** — `shared_Minervini_scan.ts`. Daily.
```
pass = SMA200 > SMA200[60] and SMA150>SMA200 and SMA50>SMA150 and SMA50>SMA200
       and C>SMA200 and C>SMA150 and C>SMA50 and C >= 1.3*Lowest(low,252) and C >= 0.75*Highest(high,252)
RS = 40*(C-lr63)/lr63 + 20*(C-lr126)/lr126 + 20*(C-lr189)/lr189 + 20*(C-lr252)/lr252  # lr = Inertia (linreg value)
```

**7. EMA stack 8/21/34/55/89** — `EMA_Stack.ts`. Any TF. `stackedUp = EMA8>EMA21>EMA34>EMA55>EMA89`; mirror for down. Extends our 8/21 state.

**8. Opening range breakout + targets** — `ORB_Breakout.ts`, `ORB_OG.ts`, `From_useThinkScript_on_Oct_15.ts`. 5m.
```
OR = high/low of 9:30-10:00 (ORB_OG: mean of first 5m bar as reference; targets = OR ± AtrTargetMult(2.0)*ATR(4))
Fib targets: mid=(ORH+ORL)/2 ; ext = ORH + width*(1.382-1), ORH + width*(1.621-1)  (mirror below)
state = Above / Inside / Below
```

**9. Relative-volume pivots (S/R)** — `shared_SuperPivots_AI.ts`, `MobiusSR.ts`, `PreviousSupportResistance.ts`. Daily or 5m.
```
fractal high: 2 lower highs each side (sequenceCount=2); fractal low mirror
relVol = (V - SMA(V,60))/StDev(V,60) ; SuperPivot = fractal and relVol >= 2.0
MobiusSR: swing high where h == Highest(h,13) AND that bar has Highest(volume,13) -> S/R line at high and low of that bar
PreviousSupportResistance: high >= Highest(high[1],5) and high >= Highest(high[-5],5) (needs 5-bar confirmation lag)
```

**10. Volume classification** — `EnhancedVolume_vr_op.ts`, `CriticalVolumeBars.ts`, `UnusualVolume.ts`, `BlastOff.ts`, `shared_shared_SupportCandlesUnclouded.ts`. Any TF.
```
buyVol = V*(C-L)/(H-L); sellVol = V*(H-C)/(H-L); spike when relVolStDev(60) >= 2
Critical: v% = V/Highest(V,89)*80 ; hv = v% - EMA(v%,21) ; critical = hv > 0 and hv >= 0.618*Highest(hv,89)
Unusual: V >= 1.10 * SMA(V,50)[1]
BlastOff (indecision): |C-O|/(H-L)*100 < 20
SupportCandle: min(C,O) > HL2 and (C-L)/(H-L) > 0.5 and V == Highest(V,10)  -> support at that bar's low
```

Honorable mentions (cheap, computable): `Three_Bar_Breakout_TOS.ts` (bars 1-2 inside bar 3's range, close breaks high[1]), `shared_ConnorsRSI_Indicator.ts` (RSI3 + streak RSI2 + 100-day ROC rank), `ConsecutiveBarCount.ts`, `NearHighOfYear.ts` (within 9% of 252-day high/low), `shared_PercentFromATH2.ts`, `SidewaysChoppy.ts` (|DI+ - DI-| < 5), `HahnTech_AlertColor_HA.ts` (Heikin-Ashi flip), `shared_R_ZIGZAG.ts` (3.2*ATR(5) reversal zig-zag), `FloorPivots.ts`, `HDWM_levels.ts`.

## 4. NOT FEASIBLE HERE

- **Market internals / breadth**: `shared_*TICK*`, `shared_CummTick_V3`, `shared_CU_NYSE*`, `shared_TRIN_Label`, `shared_ADD/ADNDD/ADSPD_Label`, `Hindenburg.ts`, `Spy___Vxx_Labels`, `VIX.ts`, `VixOrios`.
- **Options / IV / earnings**: `HotZoneRSI`, `HotZonePercentage`, `shared_IV_Rank_*`, `vr_TOSstudy_charts` (Market Maker Move, earnings dates), `ChartLabels_vr_op` earnings portion, `shared_EstimatedEarnings`, `shared_shared_dynamicpricelinewithatrIV`.
- **Futures / session-specific**: `ES_Algo`, `NextHourESTrading`, `SPX2ES`, `HiLowAuto` and `shared_PMThreeLine_*` (Globex overnight), `From_ripster_on_Jun_10` (8-10am premarket volume), `AH_chg`, `PM_chg`, `pop` (bid/ask), `thinkScript_quote`, `ZangerVolume` (per-bar RTH volume across days works on 5m but needs extended-hours flags).
- **Sizing / cosmetic / labels only**: `SizingCalculator`, `PositionCalcStudy_Kory`, `Mobius_DaysOnChart`, `shared_shared_DanielBones`, `tenandten30`, `Strat_Overlay*` (HTF candle cloud rendering), `NEWEMACLOUDS`, `PistolPeteEMA`, `SMA*.ts`, `InvestiTradeKeyLevels`/`Stoo_*` (hard-coded levels).
- **Relative strength vs SPX** (`Scan_RelativeStrength`, `MustBeOver20/40`, `TicTokTOP`): feasible only if a benchmark series is fetched alongside each ticker; not OHLCV-of-ticker alone.

Parameter note for the squeeze: every squeeze file in the export uses BB 20/2.0 and KC 20/1.5 with SMA-smoothed true range and Inertia-based momentum, so if ours uses EMA-ATR or raw close-minus-midline momentum it will drift from what Vince sees in TOS.