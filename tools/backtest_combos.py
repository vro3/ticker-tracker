"""Second pass: the evidence-backed combinations, split by universe (large caps vs speculative names).
Usage: .venv/bin/python tools/backtest_combos.py    Version 1.0 · 2026-09-08"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from backtest import features, load_universe, HORIZONS
import yfinance as yf

spec = set("PLTR SOFI RIVN LCID NIO MARA RIOT BBAI SOUN IONQ RGTI QUBT HOOD COIN GME AMC PLUG FCEL RUN CHPT NKLA SNDL TLRY ACB CGC OPEN CLOV WISH SPCE ASTS RKLB LUNR ACHR JOBY BITF CLSK HUT CIFR WULF IREN NNOX RIME OZSC SMCI ARM MSTR UPST AFRM DKNG RBLX U SNAP PINS LYFT DASH NU GRAB HIMS OSCR ROOT LMND".split())
syms = load_universe(Path(__file__).parent / "universe.txt")
frames = []
for i in range(0, len(syms), 100):
    chunk = syms[i:i+100]
    df = yf.download(chunk, period="4y", interval="1d", group_by="ticker", progress=False, threads=True, auto_adjust=False)
    for tk in chunk:
        try: d = df[tk].dropna(subset=["Close"])
        except KeyError: continue
        if len(d) < 260: continue
        f = features(d)
        c, o, h, l = d["Close"], d["Open"], d["High"], d["Low"]
        dd = c.diff()
        g = dd.clip(lower=0).ewm(alpha=1/2, adjust=False, min_periods=2).mean()
        ls = (-dd.clip(upper=0)).ewm(alpha=1/2, adjust=False, min_periods=2).mean()
        rsi2 = 100 - 100/(1 + g/ls.replace(0, np.nan))
        f["rsi2_lt_10"] = rsi2 < 10
        f["ibs_lt_0_2"] = ((c - l)/(h - l).replace(0, np.nan)) < 0.2
        f["ticker"] = tk; f["close"] = c; f["spec"] = tk in spec
        frames.append(f)
allf = pd.concat(frames)
allf = allf[allf["close"] >= 1].dropna(subset=[f"fwd{h}" for h in HORIZONS])
B = lambda s: allf[s].fillna(False).astype(bool)
combos = {
  "above_200 + rsi2<10 (Connors pullback)": B("above_200") & B("rsi2_lt_10"),
  "above_200 + rsi2<10 + ibs<0.2": B("above_200") & B("rsi2_lt_10") & B("ibs_lt_0_2"),
  "above_200 + close below lower BB + RSI14<=30": B("above_200") & B("bb_low_rsi30"),
  "below_200 + close below lower BB + RSI14<=30 (no trend filter)": B("below_200") & B("bb_low_rsi30"),
  "above_200 + down 7% day": B("above_200") & B("dn_7pct_day"),
  "below_200 + down 7% day": B("below_200") & B("dn_7pct_day"),
  "above_200 + strat 2d-2u reversal": B("above_200") & B("strat_2d_2u"),
  "above_200 + ftfc green (all frames)": B("above_200") & B("ftfc_green"),
  "above_200 + squeeze fired up": B("above_200") & B("squeeze_fired_up"),
  "above_200 + ema8 crosses above vwma26": B("above_200") & B("ema8_x_up_vwma26"),
  "ema stack bull + pullback to 21 EMA": B("ema_stack_bull") & B("pullback_21"),
  "above_200 + 3-bar bear gap (Vince gap rule, long)": B("above_200") & B("gap3_bear"),
  "baseline": B("baseline"),
}
rows = []
for name, m in combos.items():
    for label, sub in (("large caps", ~allf["spec"]), ("speculative", allf["spec"])):
        mm = m & sub
        n = int(mm.sum())
        if n < 100: continue
        base = allf.loc[sub]
        r = {"rule": name, "universe": label, "n": n}
        for hz in HORIZONS:
            x = allf.loc[mm, f"fwd{hz}"]
            r[f"win{hz}"] = (x > 0).mean()*100
            r[f"edge{hz}"] = (x.mean() - base[f"fwd{hz}"].mean())*100
        r["med10"] = allf.loc[mm, "fwd10"].median()*100
        rows.append(r)
res = pd.DataFrame(rows)
out = ["# Evidence-backed combinations, by universe", f"Generated {time.strftime('%Y-%m-%d %H:%M')}. 4 years daily, closes >= $1. edge = mean return minus that universe's own baseline, in percentage points.", "",
       res.to_markdown(index=False, floatfmt=".1f")]
Path(__file__).resolve().parents[1].joinpath("docs/planning/backtest-combos.md").write_text("\n".join(out))
print("\n".join(out))
