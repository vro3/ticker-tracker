"""HTTP-level tests against a live server on a random port with a temp DB. Run: .venv/bin/python -m tests.test_web_security"""
import os, tempfile, json, threading, socket, time, urllib.request, urllib.error
os.environ["TICKER_TRACKER_HOME"] = tempfile.mkdtemp(prefix="tt-sec-")
from tracker import db, web, ta

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

PORT = free_port()
srv = web.serve(PORT, block=False)
BASE = f"http://127.0.0.1:{PORT}"

def req(path, method="GET", body=None, headers=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers or {})
    if data is not None and "Content-Type" not in (headers or {}):
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")

def test_remote_post_rejected():
    code, _ = req("/api/refresh", "POST", {}, {"Cf-Connecting-Ip": "1.2.3.4"})
    assert code == 403
    code, _ = req("/api/ingest", "POST", {}, {"X-Forwarded-For": "10.0.0.5"})
    assert code == 403

def test_cross_site_post_rejected():
    code, _ = req("/api/submissions/1", "POST", {"delete": True}, {"Origin": "https://evil.example"})
    assert code == 403
    code, _ = req("/api/submissions/1", "POST", {"delete": True}, {"Origin": f"http://localhost:{PORT}"})
    assert code == 200

def test_body_limits_and_bad_json():
    r = urllib.request.Request(BASE + "/api/submissions/1", data=b"{}", method="POST", headers={"Content-Length": "100000", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(r, timeout=10); code = 200
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception:
        code = 413  # server closed after replying 413 before reading the body
    assert code == 413, code
    code, _ = req("/api/submissions/1", "POST", raw=b"notjson")
    assert code == 400
    code, _ = req("/api/submissions/1", "POST", raw=b"[1,2]")
    assert code == 400

def test_bad_ticker_rejected():
    code, r = req("/api/submissions/1", "POST", {"ticker": "<img src=x onerror=1>"})
    assert code == 400 and r["ok"] is False
    code, _ = req("/api/submissions/abc", "POST", {"delete": True})
    assert code == 404

def test_screenshot_traversal():
    code, _ = req("/screenshots/../config.json")
    assert code == 404

def test_health_and_data():
    code, h = req("/api/health")
    assert code in (200, 503) and "counts" in h
    code, d = req("/api/data")
    assert code == 200 and "submissions" in d

def test_payload_cache_and_invalidate():
    calls = {"n": 0}
    real = web.build_payload
    def counting():
        calls["n"] += 1; return real()
    web.build_payload = counting
    try:
        web.invalidate_payload(); web.cached_payload(); web.cached_payload()
        assert calls["n"] == 1
        web.invalidate_payload(); web.cached_payload()
        assert calls["n"] == 2
    finally:
        web.build_payload = real

def test_work_lock_busy():
    assert web._WORK_LOCK.acquire(blocking=False)
    try:
        code, r = req("/api/submissions/1", "POST", {"ticker": "AAPL"})
        assert code == 429
    finally:
        web._WORK_LOCK.release()

def test_ingest_path_cleans_ticker():
    from tracker import pipeline
    assert pipeline._clean_ticker("<img>") is None and pipeline._clean_ticker("$aapl") == "AAPL" and pipeline._clean_ticker("BRK.B") == "BRK.B"

def test_ta_helpers_survive_none():
    bars = [{"date": f"2025-01-{i%28+1:02d}", "open": 10, "high": 10.5, "low": 9.5, "close": 10, "volume": None} for i in range(70)]
    bars[5]["close"] = None
    for fn in (ta.grade, ta.volume_split, ta.pivot_ladder, ta.rsi2_reversal, ta.ema_vwma_state, ta.gap_zones, ta.find_zones):
        fn(bars)  # must not raise
    v = ta.volume_split(bars)
    assert v["buy_pct"] is None or isinstance(v["buy_pct"], float)

if __name__ == "__main__":
    import sys
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try: fn(); print("ok  ", name)
            except Exception as e:
                import traceback; traceback.print_exc(); fails += 1; print("FAIL", name, "->", repr(e))
    srv.shutdown()
    print("ALL PASS" if not fails else f"{fails} FAILED"); sys.exit(1 if fails else 0)
