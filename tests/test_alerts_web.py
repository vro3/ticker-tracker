"""Alerts dedupe + payload/health build against a temp home. Run: .venv/bin/python -m tests.test_alerts_web"""
import os, tempfile, json
from datetime import date, timedelta
os.environ["TICKER_TRACKER_HOME"] = tempfile.mkdtemp(prefix="tt-test-")
from tracker import config, db, alerts, web, ta

def seed(con):
    today = date.today()
    con.execute("INSERT INTO submissions(msg_rowid,sent_at,sent_date,sender_handle,sender_name,ticker,price_seen,note,direction,target_price,status,created_at) "
                "VALUES (1,?,?,'+1','Brian','TEST',10,'up','up',12,'ok',?)", (today.isoformat(), today.isoformat(), today.isoformat()))
    d = today - timedelta(days=300)
    rows = []
    for i in range(300):
        dd = d + timedelta(days=i)
        if dd.weekday() < 5:
            rows.append(("TEST", dd.isoformat(), 10, 10.2, 9.8, 10, 1_000_000))
    con.executemany("INSERT OR REPLACE INTO prices(ticker,date,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)", rows)
    con.execute("INSERT OR REPLACE INTO latest(ticker,price,as_of,name) VALUES ('TEST', 11.0, ?, 'Test Co')", (today.isoformat(),))
    con.commit()

def test_alert_move_dedupe_and_hit():
    with db.tx() as con:
        seed(con)
        cfg = dict(config.DEFAULTS); cfg["alert_move_pct"] = 7
        new = alerts.check(con, cfg)
        kinds = sorted(a["kind"] for a in new)
        assert "move" in kinds, new
        again = alerts.check(con, cfg)
        assert again == [], again
        # target 12 hit -> judge then alert
        con.execute("UPDATE latest SET price=12.5 WHERE ticker='TEST'")
        con.execute("INSERT OR REPLACE INTO prices(ticker,date,open,high,low,close,volume) VALUES ('TEST', ?, 12, 12.6, 11.9, 12.5, 1000000)", (date.today().isoformat(),))
        from tracker import judge
        judge.judge_all(con)
        new = alerts.check(con, cfg)
        assert any(a["kind"] == "hit" for a in new), new
        assert alerts.check(con, cfg) == []

def test_payload_and_health():
    p = web.build_payload()
    assert p["summary"]["count"] == 1 and p["submissions"][0]["ticker"] == "TEST"
    s = p["submissions"][0]
    assert s["ta"] and s["ta"]["ok"] and s["setups"]["grade"]["grade"] in ("green", "yellow", "red")
    json.dumps(p)  # serializable
    h = web.health()
    assert h["ok"] is False and h["counts"]["submissions"] == 1  # no poll yet -> stale flagged

def test_unknown_ticker_grade_none():
    g = ta.grade([], None)
    assert g["grade"] is None

if __name__ == "__main__":
    import sys
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try: fn(); print("ok  ", name)
            except Exception as e:
                import traceback; traceback.print_exc(); fails += 1; print("FAIL", name, "->", repr(e))
    print("ALL PASS" if not fails else f"{fails} FAILED"); sys.exit(1 if fails else 0)
