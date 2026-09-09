"""Technical signals computed from daily OHLCV bars. Pure Python, no extra dependencies.

Rules follow the most-used usethinkscript.com indicators (see docs/planning/ta-signals.md):
  - Supply/demand zones: impulse -> base candle(s) -> impulse; wicks test, closes break.
  - EMAs: 8/21 cross state, 50 and 200 for context.
  - Bollinger Bands: %B, bandwidth, TTM squeeze (BB inside Keltner), band walk.
  - RSI(14), ATR-based stop.
Version 1.0 · 2026-09-08
"""
from __future__ import annotations

import math


# ---------- basic math ----------

def sma(vals, n):
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(vals, n):
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    k = 2 / (n + 1)
    e = sum(vals[:n]) / n
    out[n - 1] = e
    for i in range(n, len(vals)):
        e = vals[i] * k + e * (1 - k)
        out[i] = e
    return out


def stdev(vals, n):
    out = [None] * len(vals)
    for i in range(n - 1, len(vals)):
        w = vals[i - n + 1:i + 1]
        m = sum(w) / n
        out[i] = math.sqrt(sum((x - m) ** 2 for x in w) / n)
    return out


def true_range(bars):
    tr = []
    for i, b in enumerate(bars):
        if i == 0:
            tr.append(b["high"] - b["low"])
        else:
            pc = bars[i - 1]["close"]
            tr.append(max(b["high"] - b["low"], abs(b["high"] - pc), abs(b["low"] - pc)))
    return tr


def wilder(vals, n):
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    a = sum(vals[:n]) / n
    out[n - 1] = a
    for i in range(n, len(vals)):
        a = (a * (n - 1) + vals[i]) / n
        out[i] = a
    return out


def rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = wilder(gains, n)[-1]
    al = wilder(losses, n)[-1]
    if ag is None or al is None:
        return None
    if al == 0:
        return 100.0
    rs = ag / al
    return 100 - 100 / (1 + rs)


def linreg_last(vals):
    """Value of the least-squares line at the last point."""
    n = len(vals)
    if n < 2:
        return vals[-1] if vals else None
    xs = range(n)
    mx = (n - 1) / 2
    my = sum(vals) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, vals))
    slope = sxy / sxx if sxx else 0.0
    return my + slope * (n - 1 - mx)


# ---------- supply / demand zones ----------

def find_zones(bars, atr_len=20, sensitivity=1.2, max_base=4, max_age=250, ob_periods=3, ob_threshold_pct=3.0):
    """Two detectors, results merged:
      1. Impulse -> base candle(s) -> impulse (usethinkscript thread 652). Impulse = range >= sensitivity*ATR
         and body > 55% of range; the leg-in may be merely 'strong' (body >= 0.8*ATR).
      2. Order blocks (thread 12162): last opposite-color candle before ob_periods same-color candles that
         together move price >= ob_threshold_pct.
    Zones are dropped once a daily close goes through them (wicks test, closes break)."""
    bars = [b for b in bars if all(b.get(k) is not None for k in ("open", "high", "low", "close"))]
    n = len(bars)
    if n < atr_len + 5:
        return []
    tr = true_range(bars)
    atr = sma(tr, atr_len)
    boring, exciting, strong, up = [False] * n, [False] * n, [False] * n, [False] * n
    for i, b in enumerate(bars):
        rng = b["high"] - b["low"]
        body = abs(b["close"] - b["open"])
        up[i] = b["close"] > b["open"]
        if rng <= 0 or not atr[i]:
            continue
        ratio = body / rng
        boring[i] = ratio <= 0.5
        exciting[i] = ratio > 0.55 and rng >= sensitivity * atr[i]
        strong[i] = body >= 0.8 * atr[i]
    raw = []
    # detector 1: impulse - base - impulse
    for i in range(atr_len, n):
        if not exciting[i]:
            continue
        base = []
        j = i - 1
        while j >= 0 and boring[j] and len(base) < max_base:
            base.append(j)
            j -= 1
        if not base or j < 0 or not (exciting[j] or strong[j]):
            continue
        top = max(bars[k]["high"] for k in base)
        bottom = min(bars[k]["low"] for k in base)
        leg_in_up, leg_out_up = up[j], up[i]
        if leg_in_up and not leg_out_up:
            kind, pattern = "supply", "RBD"
        elif not leg_in_up and leg_out_up:
            kind, pattern = "demand", "DBR"
        elif leg_in_up and leg_out_up:
            kind, pattern = "demand", "RBR"
        else:
            kind, pattern = "supply", "DBD"
        raw.append((kind, pattern, top, bottom, i))
    # detector 2: order blocks
    for i in range(ob_periods, n):
        ob = i - ob_periods
        run = range(ob + 1, i + 1)
        if not up[ob] and all(up[k] for k in run):
            move = (bars[i]["close"] - bars[ob]["close"]) / bars[ob]["close"] * 100 if bars[ob]["close"] else 0
            if move >= ob_threshold_pct:
                raw.append(("demand", "OB", max(bars[ob]["open"], bars[ob]["close"]), bars[ob]["low"], i))
        if up[ob] and all(not up[k] for k in run):
            move = (bars[ob]["close"] - bars[i]["close"]) / bars[ob]["close"] * 100 if bars[ob]["close"] else 0
            if move >= ob_threshold_pct:
                raw.append(("supply", "OB", bars[ob]["high"], min(bars[ob]["open"], bars[ob]["close"]), i))
    zones = []
    for kind, pattern, top, bottom, i in raw:
        if top <= bottom or n - 1 - i > max_age:
            continue
        z = {"type": kind, "pattern": pattern, "top": top, "bottom": bottom, "created": bars[i]["date"],
             "created_idx": i, "state": "fresh", "tests": 0}
        broken = False
        for k in range(i + 1, n):
            b = bars[k]
            if kind == "demand":
                if b["close"] < bottom:
                    broken = True
                    break
                if b["low"] <= top:
                    z["tests"] += 1
                    z["state"] = "tested"
            else:
                if b["close"] > top:
                    broken = True
                    break
                if b["high"] >= bottom:
                    z["tests"] += 1
                    z["state"] = "tested"
        if broken:
            continue
        z["age"] = n - 1 - i
        zones.append(z)
    # overlapping zones of the same type: keep the most recent
    zones.sort(key=lambda z: -z["created_idx"])
    kept = []
    for z in zones:
        if any(o["type"] == z["type"] and o["bottom"] <= z["top"] and o["top"] >= z["bottom"] for o in kept):
            continue
        kept.append(z)
    return kept


def nearest_zones(zones, price):
    inside = None
    demand = supply = None
    for z in zones:
        if z["bottom"] <= price <= z["top"]:
            inside = inside or z
    below = [z for z in zones if z["type"] == "demand" and z["top"] < price]
    above = [z for z in zones if z["type"] == "supply" and z["bottom"] > price]
    if below:
        demand = max(below, key=lambda z: z["top"])
    if above:
        supply = min(above, key=lambda z: z["bottom"])

    def pack(z):
        if not z:
            return None
        return {"type": z["type"], "pattern": z["pattern"], "top": z["top"], "bottom": z["bottom"],
                "state": z["state"], "tests": z["tests"], "age": z["age"], "created": z["created"],
                "dist_pct": ((z["bottom"] if z["type"] == "supply" else z["top"]) - price) / price * 100}
    return {"demand": pack(demand), "supply": pack(supply), "inside": pack(inside), "count": len(zones)}


# ---------- everything for one ticker ----------

def compute(bars, last_price=None):
    """bars: list of dicts (date, open, high, low, close, volume) sorted by date ascending."""
    bars = [b for b in bars if all(b.get(k) is not None for k in ("open", "high", "low", "close"))]
    n = len(bars)
    if n < 25:
        return {"bars": n, "ok": False, "why": f"only {n} daily bars; need 25+"}
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    price = last_price if last_price else closes[-1]

    e8, e21, e50, e200 = ema(closes, 8), ema(closes, 21), ema(closes, 50), ema(closes, 200)
    state = None
    bars_since = None
    if e8[-1] is not None and e21[-1] is not None:
        state = "bull" if e8[-1] > e21[-1] else "bear"
        bars_since = 0
        for i in range(n - 1, 0, -1):
            if e8[i] is None or e21[i] is None:
                break
            if (e8[i] > e21[i]) != (e8[-1] > e21[-1]):
                break
            bars_since = n - 1 - i
    ema_out = {"e8": e8[-1], "e21": e21[-1], "e50": e50[-1], "e200": e200[-1], "state": state,
               "bars_since_cross": bars_since,
               "above_50": (price > e50[-1]) if e50[-1] else None,
               "above_200": (price > e200[-1]) if e200[-1] else None}

    mid = sma(closes, 20)
    sd = stdev(closes, 20)
    tr = true_range(bars)
    atr20 = sma(tr, 20)
    bb_up = [m + 2 * s if m is not None else None for m, s in zip(mid, sd)]
    bb_dn = [m - 2 * s if m is not None else None for m, s in zip(mid, sd)]
    squeeze = []
    for i in range(n):
        if mid[i] is None or atr20[i] is None:
            squeeze.append(False)
            continue
        kc_up, kc_dn = mid[i] + 1.5 * atr20[i], mid[i] - 1.5 * atr20[i]
        squeeze.append(bb_up[i] < kc_up and bb_dn[i] > kc_dn)
    squeeze_bars = 0
    for i in range(n - 1, -1, -1):
        if not squeeze[i]:
            break
        squeeze_bars += 1
    fired = (not squeeze[-1]) and n > 1 and squeeze[-2]
    momo = None
    if n >= 40 and e21[-1] is not None:
        s20 = sma(closes, 20)                       # TTM uses the simple 20 average for the midline
        diffs = []
        for i in range(n - 20, n):
            hh, ll = max(highs[i - 19:i + 1]), min(lows[i - 19:i + 1])
            k = ((hh + ll) / 2 + s20[i]) / 2
            diffs.append(closes[i] - k)
        momo = linreg_last(diffs)
    pctb = bandwidth = None
    if bb_up[-1] is not None and bb_up[-1] != bb_dn[-1]:
        pctb = (price - bb_dn[-1]) / (bb_up[-1] - bb_dn[-1])
        bandwidth = (bb_up[-1] - bb_dn[-1]) / mid[-1] if mid[-1] else None
    walk = None
    recent = [(closes[i], bb_up[i], bb_dn[i]) for i in range(max(0, n - 5), n) if bb_up[i] is not None]
    if len(recent) >= 5:
        hi_walk = sum(1 for c, u, d in recent if (c - d) / (u - d) > 0.8) if all(u != d for _, u, d in recent) else 0
        lo_walk = sum(1 for c, u, d in recent if (c - d) / (u - d) < 0.2) if all(u != d for _, u, d in recent) else 0
        walk = "up" if hi_walk >= 3 else "down" if lo_walk >= 3 else None
    bw_low = None
    bws = [(bb_up[i] - bb_dn[i]) / mid[i] for i in range(n) if bb_up[i] is not None and mid[i]]
    if bandwidth is not None and len(bws) >= 60:
        bw_low = bandwidth <= min(bws[-120:]) * 1.0001
    bb_out = {"upper": bb_up[-1], "lower": bb_dn[-1], "mid": mid[-1], "pctb": pctb, "bandwidth": bandwidth,
              "squeeze_on": squeeze[-1], "squeeze_bars": squeeze_bars, "fired": fired, "momo": momo,
              "walk": walk, "bandwidth_at_low": bw_low}

    r = rsi(closes, 14)
    atr10 = sma(tr, 10)[-1]
    stop_long = max(highs[-10:]) - 3 * atr10 if atr10 else None
    stop_short = min(lows[-10:]) + 3 * atr10 if atr10 else None

    zones = nearest_zones(find_zones(bars), price)

    return {"bars": n, "ok": True, "price": price, "as_of": bars[-1]["date"], "ema": ema_out, "bb": bb_out,
            "rsi": r, "atr": atr10, "stop_long": stop_long, "stop_short": stop_short, "zones": zones}


# ---------- Vince's setups (ported from his thinkscript) ----------

def vwma(closes, vols, n):
    out = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        v = sum(vols[i - n + 1:i + 1])
        out[i] = sum(c * x for c, x in zip(closes[i - n + 1:i + 1], vols[i - n + 1:i + 1])) / v if v else None
    return out


def ema_vwma_state(bars, ema_len=8, vwma_len=26):
    """EMA8 vs VWMA26: state ('above'/'below'), bars since the last cross, and whether the cross is on the last bar."""
    closes = [b["close"] for b in bars]
    vols = [b.get("volume") or 0.0 for b in bars]
    if len(closes) < max(ema_len, vwma_len) + 1:
        return None
    e = ema(closes, ema_len)
    v = vwma(closes, vols, vwma_len)
    rel = [None if (a is None or b is None) else (a > b) for a, b in zip(e, v)]
    if rel[-1] is None:
        return None
    since = 0
    for i in range(len(rel) - 2, -1, -1):
        if rel[i] is None or rel[i] != rel[-1]:
            break
        since += 1
    return {"state": "above" if rel[-1] else "below", "bars_since_cross": since,
            "crossed_now": since == 0 and len(rel) > 1 and rel[-2] is not None,
            "ema": e[-1], "vwma": v[-1], "as_of": bars[-1].get("ts") or bars[-1].get("date")}


def gap_zones(bars, max_zones=6):
    """Three-candle gaps (gaps_alt_3bar, thinkscript indexing where [0] is the newest bar): three straight red
    candles where the oldest one's low is above the newest one's high leaves a bear gap between them; three
    straight green where the oldest one's high is below the newest one's low leaves a bull gap. A gap is dropped
    once a later bar trades across its far edge (filled). Returns the newest max_zones gaps, newest first."""
    bars = [b for b in bars if all(b.get(k) is not None for k in ("open", "high", "low", "close"))]
    n = len(bars)
    zones = []
    for i in range(2, n):
        a, b, c = bars[i - 2], bars[i - 1], bars[i]
        down = all(x["close"] < x["open"] for x in (a, b, c))
        up = all(x["close"] > x["open"] for x in (a, b, c))
        if down and a["low"] > c["high"]:
            zones.append({"type": "bear", "top": a["low"], "bottom": c["high"], "created": c.get("ts") or c.get("date"), "idx": i})
        elif up and a["high"] < c["low"]:
            zones.append({"type": "bull", "top": c["low"], "bottom": a["high"], "created": c.get("ts") or c.get("date"), "idx": i})
    open_zones = []
    for z in zones:
        filled = False
        touched = False
        for k in range(z["idx"] + 1, n):
            bk = bars[k]
            if z["type"] == "bear":          # price fell away; filled when it rallies back through the top
                if bk["high"] >= z["top"]:
                    filled = True
                    break
                if bk["high"] > z["bottom"]:
                    touched = True
            else:                            # price gapped up; filled when it drops back through the bottom
                if bk["low"] <= z["bottom"]:
                    filled = True
                    break
                if bk["low"] < z["top"]:
                    touched = True
        if not filled:
            z["state"] = "partly filled" if touched else "open"
            z["age"] = n - 1 - z["idx"]
            del z["idx"]
            open_zones.append(z)
    open_zones.sort(key=lambda z: z["age"])      # newest (smallest age) first
    return open_zones[:max_zones]


def ftfc(price, opens):
    """Full time frame continuity: price vs the open of each higher time frame.
    opens: ordered dict-like of {label: open}. Returns per-frame direction and the overall read."""
    frames = {}
    for label, o in opens.items():
        if o is None:
            frames[label] = None
        else:
            frames[label] = "up" if price > o else "down" if price < o else "flat"
    vals = [v for v in frames.values() if v]
    full = "green" if vals and all(v == "up" for v in vals) else "red" if vals and all(v == "down" for v in vals) else "mixed" if vals else None
    top = max((o for o in opens.values() if o is not None), default=None)
    bottom = min((o for o in opens.values() if o is not None), default=None)
    return {"frames": frames, "full": full, "top": top, "bottom": bottom}


def period_opens_daily(bars, price):
    """Opens of the current week, month, and quarter from daily bars (for FTFC on the daily)."""
    from datetime import date as _d
    if not bars:
        return {}
    last = _d.fromisoformat(bars[-1]["date"])
    def first_open(pred):
        for b in bars:
            if pred(_d.fromisoformat(b["date"])):
                return b["open"]
        return None
    week_start = last.fromordinal(last.toordinal() - last.weekday())
    q_month = 3 * ((last.month - 1) // 3) + 1
    return {"D": bars[-1]["open"],
            "W": first_open(lambda d: d >= week_start),
            "M": first_open(lambda d: d.year == last.year and d.month == last.month),
            "Q": first_open(lambda d: d.year == last.year and d.month >= q_month)}


# ---------- grade + Vince's own scripts ----------

def rsi_series(closes, n):
    """Wilder RSI as a full series (None where undefined)."""
    out = [None] * len(closes)
    if len(closes) < n + 1:
        return out
    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
    ag, al = wilder(gains, n), wilder(losses, n)
    for i in range(len(gains)):
        if ag[i] is None or al[i] is None:
            continue
        out[i + 1] = 100.0 if al[i] == 0 else 100 - 100 / (1 + ag[i] / al[i])
    return out


def rsi2_reversal(bars):
    """vr_2PeriodRSITradingIndicator: RSI(2) < 10 with close > EMA34 = bull; RSI(2) > 90 with close < EMA34 = bear."""
    closes = [b["close"] for b in bars]
    if len(closes) < 40:
        return None
    r2 = rsi_series(closes, 2)[-1]
    e34 = ema(closes, 34)[-1]
    if r2 is None or e34 is None:
        return None
    sig = "bull" if (r2 < 10 and closes[-1] > e34) else "bear" if (r2 > 90 and closes[-1] < e34) else None
    return {"rsi2": r2, "ema34": e34, "signal": sig}


def volume_split(bars, lookback=60):
    """EnhancedVolume_vr_op: buy volume = V*(C-L)/(H-L), sell = V*(H-C)/(H-L); spike when relative volume is 2+ st dev."""
    if len(bars) < lookback + 1:
        return None
    b = bars[-1]
    rng = b["high"] - b["low"]
    v = b.get("volume") or 0.0
    buy = v * (b["close"] - b["low"]) / rng if rng else v / 2
    sell = v - buy
    vols = [x.get("volume") or 0.0 for x in bars[-lookback - 1:-1]]
    m = sum(vols) / len(vols)
    sd = math.sqrt(sum((x - m) ** 2 for x in vols) / len(vols)) if vols else 0.0
    rel = (v - m) / sd if sd else 0.0
    vs_avg = (v / m) if m else None
    return {"buy": buy, "sell": sell, "buy_pct": (buy / v * 100) if v else None, "rel_vol_sd": rel,
            "vs_avg": vs_avg, "spike": rel >= 2.0 or (vs_avg is not None and vs_avg >= 3.0)}


def pivot_ladder(bars, width=5, lookback=60, stdev_len=20, stdev_mult=2.0, add_frac=0.75):
    """aaaPivotWithConfirmation: a pivot low (lowest low with `width` bars each side) is confirmed when a later close
    goes above the pivot bar's high. Then: entry = that confirming close, stop = pivot low, add = entry + add_frac*stdev,
    trail/target = entry + stdev_mult*stdev. Returns the most recent confirmed ladder, with status active (price above stop) or stopped."""
    n = len(bars)
    if n < width * 2 + stdev_len + 2:
        return None
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    sd = stdev(closes, stdev_len)
    result = None
    start = max(width, n - lookback)
    for i in range(start, n - width):
        if lows[i] != min(lows[i - width:i + width + 1]):
            continue
        pivot_low, pivot_high = bars[i]["low"], bars[i]["high"]
        for k in range(i + 1, n):
            if closes[k] > pivot_high:
                if sd[k] is None:
                    break
                result = {"pivot_date": bars[i]["date"], "confirmed": bars[k]["date"], "entry": closes[k],
                          "stop": pivot_low, "add": closes[k] + add_frac * sd[k], "target": closes[k] + stdev_mult * sd[k],
                          "risk_pct": (closes[k] - pivot_low) / closes[k] * 100}
                break
    if result and closes[-1] < result["stop"]:
        result["status"] = "stopped"
    elif result:
        result["status"] = "active"
    return result


def grade(bars, last_price=None, sig=None):
    """Evidence-based read of the current spot. Green = the setups that tested best are present in a liquid name.
    Red = the conditions that tested worst. Yellow = everything else. Returns dict with grade, reasons, speculative flag."""
    if len(bars) < 60:
        return {"grade": None, "reasons": ["not enough history"], "speculative": None}
    price = last_price or bars[-1]["close"]
    closes = [b["close"] for b in bars]
    vols = [b.get("volume") or 0.0 for b in bars[-30:]]
    avg_dollar_vol = sum(c * v for c, v in zip(closes[-30:], vols)) / len(vols)
    speculative = price < 5 or avg_dollar_vol < 2_000_000
    reasons, score = [], 0
    r2 = rsi_series(closes, 2)[-1]
    r14 = rsi(closes, 14)
    e200 = ema(closes, 200)[-1] if len(closes) >= 200 else None
    mid = sma(closes, 20)[-1]
    sd20 = stdev(closes, 20)[-1]
    lower = mid - 2 * sd20 if mid is not None else None
    prev_close = bars[-2]["close"]
    day_pct = (price - prev_close) / prev_close * 100 if prev_close else 0.0
    if lower is not None and r14 is not None and price < lower and r14 <= 30:
        score += 2
        reasons.append("closed below the lower Bollinger with RSI under 30 (tested 61% up in 10 days)")
    elif r2 is not None and r2 < 10:
        score += 1
        reasons.append("RSI(2) under 10, short-term washed out")
    if day_pct <= -7:
        score += 1
        reasons.append(f"down {abs(day_pct):.1f}% today; big down days averaged a bounce over 10-20 days")
    if e200 is not None:
        reasons.append("above the 200-day, trend filter on" if price > e200 else "below the 200-day, no trend filter")
        if price > e200 and score:
            score += 1
    if sig and sig.get("bb", {}).get("fired") and (sig["bb"].get("momo") or 0) > 0:
        reasons.append("squeeze just fired up (tested no edge; context only)")
    if sig and sig.get("ema", {}).get("state") == "bull" and (sig["ema"].get("bars_since_cross") or 0) <= 2:
        reasons.append("fresh 8/21 EMA cross (tested no edge; context only)")
    if speculative:
        reasons.append("speculative: under $5 or thin volume; baseline in this group tested negative")
        score -= 1
    g = "green" if score >= 2 else "red" if (speculative and score <= 0) else "yellow"
    return {"grade": g, "score": score, "reasons": reasons, "speculative": speculative,
            "avg_dollar_volume": avg_dollar_vol, "day_pct": day_pct, "rsi2": r2}
