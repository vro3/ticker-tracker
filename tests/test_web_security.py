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

def test_ingest_failure_paths():
    """Staging failure -> recorded as status=error (not lost). Recording failure -> message unclaimed and retried."""
    from tracker import pipeline, db as _db
    from datetime import datetime
    class M:  # minimal stand-in for imessage.Message
        rowid = 424242; handle = "+1"; images = ["/nonexistent/path.png"]; caption = "x"; chat_name = "t"
        sent_at = datetime.now().astimezone()
    orig_collect, orig_stage, orig_record = pipeline.imessage.collect_new, pipeline.imessage.stage_image, pipeline.record_submission
    pipeline.imessage.collect_new = lambda cfg, after: ([M()], 424242)
    def boom(*a, **k): raise RuntimeError("stage failed")
    pipeline.imessage.stage_image = boom
    cfg = {"chat_db": "/dev/null", "timezone": "America/Chicago", "people": {}, "vision_backend": "cli"}
    try:
        with _db.tx() as con:
            _db.set_meta(con, "last_msg_rowid", 1)
            con.execute("DELETE FROM seen_messages WHERE msg_rowid=424242")
        n = pipeline.ingest(cfg)
        with _db.tx() as con:
            row = con.execute("SELECT status FROM submissions WHERE msg_rowid=424242").fetchone()
        assert n == 1 and row and row["status"] == "error", (n, row)
        # now a hard failure inside record_submission: must unclaim and hold the high-water mark
        with _db.tx() as con:
            con.execute("DELETE FROM submissions WHERE msg_rowid=424242")
            con.execute("DELETE FROM seen_messages WHERE msg_rowid=424242")
            _db.set_meta(con, "last_msg_rowid", 1)
        pipeline.record_submission = boom
        n = pipeline.ingest(cfg)
        with _db.tx() as con:
            seen = con.execute("SELECT 1 FROM seen_messages WHERE msg_rowid=424242").fetchone()
            hw = int(_db.get_meta(con, "last_msg_rowid"))
        assert n == 0 and seen is None and hw < 424242, (n, seen, hw)
    finally:
        pipeline.imessage.collect_new, pipeline.imessage.stage_image, pipeline.record_submission = orig_collect, orig_stage, orig_record

def test_delete_is_soft_and_restorable():
    from tracker import db as _db
    from datetime import date
    today = date.today().isoformat()
    with _db.tx() as con:
        cur = con.execute("INSERT INTO submissions(sent_at,sent_date,sender_handle,sender_name,ticker,status,created_at) VALUES (?,?,'+1','T','AAPL','ok',?)", (today, today, today))
        sid = cur.lastrowid
    code, r = req(f"/api/submissions/{sid}", "POST", {"delete": True})
    assert code == 200
    with _db.tx() as con:
        row = con.execute("SELECT hidden FROM submissions WHERE id=?", (sid,)).fetchone()
        assert row and row["hidden"] == 1
    web.invalidate_payload()
    assert all(s["id"] != sid for s in web.build_payload()["submissions"])
    with _db.tx() as con:
        con.execute("UPDATE submissions SET hidden=0 WHERE id=?", (sid,))
    web.invalidate_payload()
    assert any(s["id"] == sid for s in web.build_payload()["submissions"])

def test_retry_cap_gives_up_after_three():
    from tracker import pipeline, db as _db
    from datetime import datetime
    class M:
        rowid = 535353; handle = "+1"; images = []; caption = "$AAPL x"; chat_name = "t"; caption_rowid = None
        sent_at = datetime.now().astimezone()
    orig_collect, orig_record = pipeline.imessage.collect_new, pipeline.record_submission
    pipeline.imessage.collect_new = lambda cfg, after: ([M()], 535353)
    def boom(*a, **k): raise RuntimeError("db exploded")
    pipeline.record_submission = boom
    cfg = {"chat_db": "/dev/null", "timezone": "America/Chicago", "people": {}}
    try:
        with _db.tx() as con:
            _db.set_meta(con, "last_msg_rowid", 1); con.execute("DELETE FROM meta WHERE key='retries:535353'")
            con.execute("DELETE FROM seen_messages WHERE msg_rowid=535353")
        for i in range(3):
            pipeline.ingest(cfg)
        with _db.tx() as con:
            seen = con.execute("SELECT 1 FROM seen_messages WHERE msg_rowid=535353").fetchone()
            hw = int(_db.get_meta(con, "last_msg_rowid"))
        assert seen is not None and hw == 535353, (seen, hw)   # given up: stays claimed, mark advanced
    finally:
        pipeline.imessage.collect_new, pipeline.record_submission = orig_collect, orig_record


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
