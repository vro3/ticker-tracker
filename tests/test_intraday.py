"""Run: .venv/bin/python -m tests.test_intraday"""
from tracker import intraday

def mk(ts, o, h, l, c, v=100):
    return {"ts": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}

def test_bucket_anchor():
    assert intraday._bucket("2026-09-08T09:35:00-04:00", 15).isoformat() == "2026-09-08T09:30:00-04:00"
    assert intraday._bucket("2026-09-08T09:45:00-04:00", 15).isoformat() == "2026-09-08T09:45:00-04:00"
    assert intraday._bucket("2026-09-08T10:25:00-04:00", 60).isoformat() == "2026-09-08T09:30:00-04:00"
    assert intraday._bucket("2026-09-08T10:30:00-04:00", 60).isoformat() == "2026-09-08T10:30:00-04:00"
    assert intraday._bucket("2026-09-08T13:29:00-04:00", 240).isoformat() == "2026-09-08T09:30:00-04:00"
    assert intraday._bucket("2026-09-08T13:30:00-04:00", 240).isoformat() == "2026-09-08T13:30:00-04:00"

def test_resample_ohlcv():
    b = [mk("2026-09-08T09:30:00-04:00", 1, 2, 0.5, 1.5), mk("2026-09-08T09:35:00-04:00", 1.5, 3, 1, 2),
         mk("2026-09-08T09:40:00-04:00", 2, 2.5, 1.8, 2.2), mk("2026-09-08T09:45:00-04:00", 2.2, 2.3, 2.1, 2.2)]
    r = intraday.resample(b, 15)
    assert len(r) == 2 and r[0]["open"] == 1 and r[0]["high"] == 3 and r[0]["low"] == 0.5 and r[0]["close"] == 2.2 and r[0]["volume"] == 300
    # missing bars (illiquid) still bucket by clock, not count
    b2 = [mk("2026-09-08T09:30:00-04:00", 1, 1, 1, 1), mk("2026-09-08T11:05:00-04:00", 2, 2, 2, 2)]
    assert len(intraday.resample(b2, 60)) == 2

def test_setups_short():
    assert intraday.setups([])["ok"] is False

def test_setups_shape():
    bars = [mk(f"2026-09-08T{9 + (i*5+30)//60:02d}:{(i*5+30)%60:02d}:00-04:00", 10, 10.1, 9.9, 10 + i * 0.01) for i in range(60)]
    s = intraday.setups(bars)
    assert s["ok"] and set(s) >= {"m5", "m15_gaps", "ftfc"} and s["ftfc"]["full"] in ("green", "red", "mixed", None)

if __name__ == "__main__":
    import sys
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try: fn(); print("ok  ", name)
            except Exception as e: fails += 1; print("FAIL", name, "->", repr(e))
    print("ALL PASS" if not fails else f"{fails} FAILED"); sys.exit(1 if fails else 0)
