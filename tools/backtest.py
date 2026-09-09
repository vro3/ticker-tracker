"""Backtest the signals the dashboard shows against real history.

Usage: .venv/bin/python tools/backtest.py [--years 4] [--universe tools/universe.txt] [--out docs/planning/backtest.md]

For every ticker and every day, flags each signal condition, then measures the close-to-close return
5, 10 and 20 trading days later. Reports per-signal win rate, mean and median return, and the edge over
the same universe's baseline (all days). Then tests two-signal combinations among the best singles.
Nothing here is advice; it is a count of what happened after each condition, survivorship bias and all.
Version 1.0 · 2026-09-08
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HORIZONS = (5, 10, 20)


def ema(s, n):
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def features(df: pd.DataFrame) -> pd.DataFrame:
    """df: columns Open High Low Close Volume, DatetimeIndex ascending."""
    o, h, l, c, v = df["Open"], df["High"], df["Low"], df["Close"], df["Volume"].fillna(0)
    f = pd.DataFrame(index=df.index)
    e8, e21, e50, e200 = ema(c, 8), ema(c, 21), ema(c, 50), ema(c, 200)
    f["ema_bull"] = e8 > e21
    f["ema_cross_up"] = (e8 > e21) & (e8.shift() <= e21.shift())
    f["above_200"] = c > e200
    f["below_200"] = c < e200
    f["ema_stack_bull"] = (e8 > e21) & (e21 > e50) & (e50 > e200)
    f["ema_stack_bear"] = (e8 < e21) & (e21 < e50) & (e50 < e200)
    f["pullback_21"] = (e8 > e21) & (e50 > e200) & (l <= e21) & (c > e21)
    # VWMA26 vs EMA8 (Vince's 5m script, applied to daily)
    vwma = (c * v).rolling(26).sum() / v.rolling(26).sum().replace(0, np.nan)
    f["ema8_gt_vwma26"] = e8 > vwma
    f["ema8_x_up_vwma26"] = (e8 > vwma) & (e8.shift() <= vwma.shift())
    f["ema8_x_dn_vwma26"] = (e8 < vwma) & (e8.shift() >= vwma.shift())
    # Bollinger / Keltner / squeeze
    mid = c.rolling(20).mean()
    sd = c.rolling(20).std(ddof=0)
    up, dn = mid + 2 * sd, mid - 2 * sd
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr20 = tr.rolling(20).mean()
    sq = (up < mid + 1.5 * atr20) & (dn > mid - 1.5 * atr20)
    f["squeeze_on"] = sq
    fired = (~sq) & sq.shift().fillna(False).astype(bool)
    hh, ll = h.rolling(20).max(), l.rolling(20).min()
    k = ((hh + ll) / 2 + ema(c, 20)) / 2
    diff = c - k
    # momentum: linreg value at last point over 20 bars ~ approximated by (diff - diff.rolling(20).mean()) sign via slope
    x = np.arange(20)
    def lr(w):
        if np.isnan(w).any():
            return np.nan
        b = np.polyfit(x, w, 1)
        return b[0] * 19 + b[1]
    momo = diff.rolling(20).apply(lr, raw=True)
    f["squeeze_fired_up"] = fired & (momo > 0)
    f["squeeze_fired_dn"] = fired & (momo < 0)
    pctb = (c - dn) / (up - dn)
    f["close_below_lower_bb"] = c < dn
    f["close_above_upper_bb"] = c > up
    walk_up = (pctb > 0.8).rolling(5).sum() >= 3
    walk_dn = (pctb < 0.2).rolling(5).sum() >= 3
    f["band_walk_up"] = walk_up
    f["band_walk_dn"] = walk_dn
    # RSI
    d = c.diff()
    g = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    ls = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rsi = 100 - 100 / (1 + g / ls.replace(0, np.nan))
    f["rsi_lt_30"] = rsi < 30
    f["rsi_gt_70"] = rsi > 70
    f["bb_low_rsi30"] = (c < dn) & (rsi <= 30)
    # Vince's 3-bar gaps (applied daily): three red with low[2] > high[0]  /  three green with high[2] < low[0]
    red = c < o
    green = c > o
    f["gap3_bear"] = red & red.shift() & red.shift(2) & (l.shift(2) > h)
    f["gap3_bull"] = green & green.shift() & green.shift(2) & (h.shift(2) < l)
    # Strat bar types
    inside = (h <= h.shift()) & (l >= l.shift())
    outside = (h > h.shift()) & (l < l.shift())
    two_up = (h > h.shift()) & (l >= l.shift()) & ~outside
    two_dn = (l < l.shift()) & (h <= h.shift()) & ~outside
    f["strat_inside"] = inside
    f["strat_outside"] = outside
    f["strat_2u"] = two_up
    f["strat_2d"] = two_dn
    f["strat_2d_2u"] = two_up & two_dn.shift().fillna(False).astype(bool)          # reversal: 2 down then 2 up
    f["strat_1_2u"] = two_up & inside.shift().fillna(False).astype(bool)           # inside bar then break up
    f["strat_3_2u"] = two_up & outside.shift().fillna(False).astype(bool)
    f["strat_2u_2d"] = two_dn & two_up.shift().fillna(False).astype(bool)
    # Full time frame continuity from daily bars: close vs open of day, week, month
    idx = df.index
    wk_open = o.groupby([idx.isocalendar().year, idx.isocalendar().week]).transform("first")
    mo_open = o.groupby([idx.year, idx.month]).transform("first")
    q_open = o.groupby([idx.year, idx.quarter]).transform("first")
    f["ftfc_green"] = (c > o) & (c > wk_open) & (c > mo_open) & (c > q_open)
    f["ftfc_red"] = (c < o) & (c < wk_open) & (c < mo_open) & (c < q_open)
    f["ftfc_green_dwm"] = (c > o) & (c > wk_open) & (c > mo_open)
    # Big moves / volume
    ret1 = c.pct_change()
    f["up_7pct_day"] = ret1 >= 0.07
    f["dn_7pct_day"] = ret1 <= -0.07
    f["vol_2x_avg_up"] = (v > 2 * v.rolling(30).mean()) & (c > o)
    f["vol_2x_avg_dn"] = (v > 2 * v.rolling(30).mean()) & (c < o)
    f["new_20d_high"] = c >= c.rolling(20).max()
    f["new_20d_low"] = c <= c.rolling(20).min()
    # Minervini-ish trend template
    sma50, sma150, sma200 = c.rolling(50).mean(), c.rolling(150).mean(), c.rolling(200).mean()
    lo52, hi52 = c.rolling(252).min(), c.rolling(252).max()
    f["minervini"] = (c > sma150) & (c > sma200) & (sma150 > sma200) & (sma50 > sma150) & (c > sma50) & \
                     (c > 1.3 * lo52) & (c > 0.75 * hi52) & (sma200 > sma200.shift(21))
    # forward returns
    for hz in HORIZONS:
        f[f"fwd{hz}"] = c.shift(-hz) / c - 1
    f["baseline"] = True
    return f


def load_universe(path):
    return [x.strip() for x in Path(path).read_text().split() if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=4)
    ap.add_argument("--universe", default=str(Path(__file__).parent / "universe.txt"))
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "docs/planning/backtest.md"))
    ap.add_argument("--min-price", type=float, default=1.0, help="skip days where close < this (penny noise)")
    a = ap.parse_args()
    import yfinance as yf
    syms = load_universe(a.universe)
    t0 = time.time()
    frames = []
    for i in range(0, len(syms), 100):
        chunk = syms[i:i + 100]
        df = yf.download(chunk, period=f"{a.years}y", interval="1d", group_by="ticker", progress=False,
                         threads=True, auto_adjust=False)
        for tk in chunk:
            try:
                d = df[tk].dropna(subset=["Close"])
            except KeyError:
                continue
            if len(d) < 260:
                continue
            f = features(d)
            f["ticker"] = tk
            f["close"] = d["Close"]
            frames.append(f)
        print(f"  {min(i+100, len(syms))}/{len(syms)} tickers, {time.time()-t0:.0f}s", flush=True)
    allf = pd.concat(frames)
    allf = allf[allf["close"] >= a.min_price]
    allf = allf.dropna(subset=[f"fwd{h}" for h in HORIZONS])
    sig_cols = [c for c in allf.columns if allf[c].dtype == bool]
    rows = []
    base = {h: allf[f"fwd{h}"] for h in HORIZONS}
    for s in sig_cols:
        m = allf[s].fillna(False).astype(bool)
        n = int(m.sum())
        if n < 200:
            continue
        r = {"signal": s, "n": n, "pct_days": n / len(allf) * 100}
        for h in HORIZONS:
            x = allf.loc[m, f"fwd{h}"]
            r[f"win{h}"] = (x > 0).mean() * 100
            r[f"mean{h}"] = x.mean() * 100
            r[f"med{h}"] = x.median() * 100
            r[f"edge{h}"] = (x.mean() - base[h].mean()) * 100
        rows.append(r)
    res = pd.DataFrame(rows).sort_values("edge10", ascending=False)
    # combos among top singles (long side) and worst singles (short side / avoid)
    top = [s for s in res["signal"].head(10) if s != "baseline"]
    combos = []
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            m = allf[top[i]].fillna(False).astype(bool) & allf[top[j]].fillna(False).astype(bool)
            n = int(m.sum())
            if n < 150:
                continue
            r = {"signal": f"{top[i]} + {top[j]}", "n": n}
            for h in HORIZONS:
                x = allf.loc[m, f"fwd{h}"]
                r[f"win{h}"] = (x > 0).mean() * 100
                r[f"mean{h}"] = x.mean() * 100
                r[f"edge{h}"] = (x.mean() - base[h].mean()) * 100
            combos.append(r)
    comb = pd.DataFrame(combos).sort_values("edge10", ascending=False) if combos else pd.DataFrame()

    def table(d, cols):
        return d[cols].to_markdown(index=False, floatfmt=".1f")
    cols = ["signal", "n", "win5", "edge5", "win10", "edge10", "win20", "edge20", "med10"]
    out = ["# Signal backtest", f"Universe: {len(frames)} tickers, {a.years} years of daily bars, closes >= ${a.min_price:g}. "
           f"{len(allf):,} ticker-days. Generated {time.strftime('%Y-%m-%d %H:%M')}.",
           "", "win = % of times the close N trading days later was higher. edge = mean return minus the baseline mean for "
           "every day in the universe (percentage points). med10 = median 10-day return. Long side only; a negative edge on a "
           "signal is a reason to stay out or look for the short.", "",
           f"Baseline: win5 {(base[5]>0).mean()*100:.1f}%, win10 {(base[10]>0).mean()*100:.1f}%, win20 {(base[20]>0).mean()*100:.1f}%; "
           f"mean10 {base[10].mean()*100:.2f}%.", "", "## Single signals", table(res, cols), ""]
    if len(comb):
        out += ["## Two-signal combinations (among the top ten singles)", table(comb, ["signal", "n", "win5", "edge5", "win10", "edge10", "win20", "edge20"]), ""]
    Path(a.out).write_text("\n".join(out))
    print("\n".join(out))
    print(f"\nwrote {a.out} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
