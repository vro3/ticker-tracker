"""Unit tests for tracker.ta on synthetic bars. Run: .venv/bin/python -m tests.test_ta"""
import math, random
from datetime import date, timedelta
from tracker import ta

def bars_from_closes(closes, start=date(2025, 1, 1), spread=0.01, vol=1_000_000):
    out, d = [], start
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        hi, lo = max(o, c) * (1 + spread), min(o, c) * (1 - spread)
        out.append({"date": d.isoformat(), "open": o, "high": hi, "low": lo, "close": c, "volume": vol})
        d += timedelta(days=1)
    return out

def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1.0, abs(b))

def test_ema_sma_flat():
    v = [10.0] * 50
    assert approx(ta.ema(v, 8)[-1], 10.0) and approx(ta.sma(v, 20)[-1], 10.0)
    assert ta.ema(v, 100)[-1] is None

def test_rsi_bounds():
    up = [float(i) for i in range(1, 40)]
    assert approx(ta.rsi(up, 14), 100.0)
    down = [float(i) for i in range(40, 1, -1)]
    assert ta.rsi(down, 14) < 1e-9
    series = ta.rsi_series(up, 2)
    assert series[0] is None and series[-1] == 100.0

def test_linreg_last():
    assert approx(ta.linreg_last([1, 2, 3, 4, 5]), 5.0)

def test_compute_uptrend():
    closes = [100 * (1.003 ** i) for i in range(260)]
    s = ta.compute(bars_from_closes(closes))
    assert s["ok"] and s["ema"]["state"] == "bull" and s["ema"]["above_200"] is True
    assert s["bb"]["pctb"] is not None and s["stop_long"] < closes[-1]

def test_compute_too_short():
    s = ta.compute(bars_from_closes([1.0] * 10))
    assert s["ok"] is False

def test_zone_detection_and_break():
    # calm base, then an impulse up (demand zone at the base), then price stays above: zone fresh
    closes = [10.0] * 30 + [10.0, 10.05, 9.98, 10.02] + [12.0, 12.5, 13.0] + [13.0] * 10
    bars = bars_from_closes(closes, spread=0.002)
    # make the impulse candle body large relative to range
    for b in bars[34:37]:
        b["open"] = b["close"] * 0.9; b["low"] = b["open"] * 0.999; b["high"] = b["close"] * 1.001
    zones = ta.find_zones(bars)
    demand = [z for z in zones if z["type"] == "demand"]
    assert demand, zones
    near = ta.nearest_zones(zones, 13.0)
    assert near["demand"] is not None and near["demand"]["top"] < 13.0
    # now break it with a close below the bottom -> zone dropped
    bars2 = bars + bars_from_closes([9.0, 9.0], start=date(2026, 1, 1), spread=0.002)
    assert not [z for z in ta.find_zones(bars2) if z["type"] == "demand" and z["top"] >= 9.9]

def test_gap_zones_bear_and_fill():
    # three red candles where first low > third high
    b = bars_from_closes([10, 10, 10, 10], spread=0.0)
    b += [{"date": "2025-02-01", "open": 10.0, "high": 10.0, "low": 9.6, "close": 9.6, "volume": 1},
          {"date": "2025-02-02", "open": 9.5, "high": 9.5, "low": 9.1, "close": 9.1, "volume": 1},
          {"date": "2025-02-03", "open": 9.0, "high": 9.0, "low": 8.6, "close": 8.6, "volume": 1}]
    z = ta.gap_zones(b)
    assert len(z) == 1 and z[0]["type"] == "bear" and approx(z[0]["top"], 9.6) and approx(z[0]["bottom"], 9.0) and z[0]["state"] == "open"
    b2 = b + [{"date": "2025-02-04", "open": 8.7, "high": 9.3, "low": 8.6, "close": 9.2, "volume": 1}]
    assert ta.gap_zones(b2)[0]["state"] == "partly filled"
    b3 = b + [{"date": "2025-02-04", "open": 8.7, "high": 9.7, "low": 8.6, "close": 9.6, "volume": 1}]
    assert ta.gap_zones(b3) == []

def test_ema_vwma_state_and_cross():
    closes = [10.0] * 40 + [11.0, 12.0, 13.0]
    st = ta.ema_vwma_state(bars_from_closes(closes))
    assert st["state"] == "above" and st["bars_since_cross"] <= 2

def test_ftfc():
    f = ta.ftfc(10.0, {"1h": 9.0, "2h": 9.5, "4h": 9.8})
    assert f["full"] == "green" and f["top"] == 9.8
    f = ta.ftfc(10.0, {"1h": 9.0, "2h": 10.5})
    assert f["full"] == "mixed"
    f = ta.ftfc(10.0, {"1h": None})
    assert f["full"] is None

def test_period_opens_daily():
    bars = bars_from_closes([1.0] * 100, start=date(2025, 1, 1))
    o = ta.period_opens_daily(bars, 1.0)
    assert set(o) == {"D", "W", "M", "Q"} and all(v == 1.0 for v in o.values())

def test_grade_oversold_liquid_is_green():
    closes = [100.0] * 250 + [90.0, 80.0]  # sharp drop: below lower band, RSI low, big down day
    bars = bars_from_closes(closes, vol=5_000_000)
    g = ta.grade(bars)
    assert g["speculative"] is False and g["grade"] in ("green", "yellow") and g["score"] >= 2

def test_grade_speculative_flag():
    bars = bars_from_closes([2.0] * 250, vol=100)
    g = ta.grade(bars)
    assert g["speculative"] is True and g["grade"] == "red"

def test_pivot_ladder():
    closes = [10.0] * 30 + [9.0, 8.5, 8.0, 8.5, 9.0, 9.5, 10.5, 11.0] + [11.0] * 10
    lad = ta.pivot_ladder(bars_from_closes(closes, spread=0.001))
    assert lad and lad["status"] == "active" and lad["stop"] < lad["entry"] < lad["add"] < lad["target"]

def test_volume_split():
    b = bars_from_closes([10.0] * 70)
    for i, x in enumerate(b):
        x["volume"] = 1_000_000 + (i % 7) * 50_000
    b[-1].update(open=9.0, low=9.0, high=11.0, close=11.0, volume=10_000_000)
    v = ta.volume_split(b)
    assert approx(v["buy_pct"], 100.0) and v["spike"] is True

def test_rsi2_reversal():
    closes = [100.0] * 60 + [95.0, 90.0]
    r = ta.rsi2_reversal(bars_from_closes(closes))
    assert r["rsi2"] < 10 and r["signal"] is None  # below EMA34 so no bull signal
    closes = [100 + i for i in range(60)] + [150.0, 149.0]
    r = ta.rsi2_reversal(bars_from_closes(closes))
    assert r["signal"] == "bull"

if __name__ == "__main__":
    import sys
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("ok  ", name)
            except Exception as e:
                fails += 1; print("FAIL", name, "->", repr(e))
    print("ALL PASS" if not fails else f"{fails} FAILED"); sys.exit(1 if fails else 0)
