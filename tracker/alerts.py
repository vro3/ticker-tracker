"""'Something is moving' alerts: big intraday moves, targets hit, squeezes firing.

Alerts are always written to the alerts table (shown on the dashboard). Sending them to the
group text is opt-in: set "alert_imessage": true and "alert_chat_guid" in config.json.
Version 1.0 · 2026-09-08
"""
import logging
import math
import subprocess
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import db, ta

log = logging.getLogger("tracker.alerts")


def _today_ny():
    return datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def _fmt(p):
    return f"${p:,.2f}" if p >= 1 else f"${p:.4f}".rstrip("0").rstrip(".")


def _callers(con, ticker):
    rows = con.execute("SELECT sender_name, sent_date, direction FROM submissions WHERE ticker=? AND status='ok' "
                       "ORDER BY sent_at", (ticker,)).fetchall()
    names = []
    for r in rows:
        if r["sender_name"] not in names:
            names.append(r["sender_name"])
    return names


def _add(con, ticker, kind, message, dedupe_key):
    if db.get_meta(con, dedupe_key):
        return None
    now = datetime.now(timezone.utc).isoformat()
    cur = con.execute("INSERT INTO alerts(ticker, kind, message, created_at, sent) VALUES (?,?,?,?,0)",
                      (ticker, kind, message, now))
    db.set_meta(con, dedupe_key, now)
    log.info("alert: %s", message)
    return {"id": cur.lastrowid, "ticker": ticker, "kind": kind, "message": message}


def check(con, cfg):
    """Look at latest quotes and daily bars; write any new alerts. Returns list of new alerts."""
    thr = float(cfg.get("alert_move_pct", 7))
    today = _today_ny()
    new = []
    latest = {r["ticker"]: dict(r) for r in con.execute("SELECT * FROM latest")}
    tickers = [r["ticker"] for r in con.execute(
        "SELECT DISTINCT ticker FROM submissions WHERE ticker IS NOT NULL AND status='ok' AND hidden=0")]
    for tk in tickers:
        try:
            _check_ticker(con, cfg, tk, latest, thr, today, new)
        except Exception as e:
            log.warning("alerts: %s skipped: %s", tk, e)
    _check_hits(con, new)
    _prune_meta(con)
    con.commit()
    return new


def deliver(new, cfg):
    """Text new alerts to the group (if enabled). Call this AFTER the DB transaction has closed."""
    if not (new and cfg.get("alert_imessage") and cfg.get("alert_chat_guid")):
        return 0
    sent = 0
    for a in new:
        if send_imessage(cfg["alert_chat_guid"], a["message"]):
            sent += 1
            with db.tx() as con:
                con.execute("UPDATE alerts SET sent=1 WHERE id=?", (a["id"],))
    return sent


def _prune_meta(con):
    """Alert dedupe keys older than ~10 days are useless; keep the meta table small."""
    cutoff = (datetime.now(ZoneInfo("America/New_York")) - timedelta(days=10)).date().isoformat()
    old = []
    for r in con.execute("SELECT key FROM meta WHERE key LIKE 'alert:move:%' OR key LIKE 'alert:squeeze:%'"):
        parts = r["key"].split(":")           # alert:move:TK:YYYY-MM-DD[:step]  /  alert:squeeze:TK:YYYY-MM-DD
        if len(parts) >= 4 and parts[3] < cutoff:
            old.append((r["key"],))
    if old:
        con.executemany("DELETE FROM meta WHERE key=?", old)
    # hit keys: drop when the submission no longer exists (deleted from the dashboard)
    con.execute("DELETE FROM meta WHERE key LIKE 'alert:hit:%' AND CAST(substr(key, 11) AS INTEGER) NOT IN (SELECT id FROM submissions)")


def _check_ticker(con, cfg, tk, latest, thr, today, new):
    if True:  # body kept indented from the original inline loop
        lp = latest.get(tk, {}).get("price")
        bars = [dict(b) for b in con.execute(
            "SELECT date, open, high, low, close, volume FROM prices WHERE ticker=? ORDER BY date", (tk,))]
        if not bars or lp is None:
            return
        who = ", ".join(_callers(con, tk)) or "someone"
        # 1. Big move vs the last close before today
        prev = next((b for b in reversed(bars) if b["date"] < today and b["close"]), None)
        if prev:
            pct = (lp - prev["close"]) / prev["close"] * 100
            step = int(math.floor(abs(pct) / thr)) if thr > 0 else 0
            if step >= 1:
                key = f"alert:move:{tk}:{today}"
                done = int(db.get_meta(con, key, 0) or 0)
                if step > done:
                    word = "up" if pct > 0 else "down"
                    msg = f"{tk} is {word} {abs(pct):.1f}% today at {_fmt(lp)} (from {_fmt(prev['close'])}). Sent by {who}."
                    a = _add(con, tk, "move", msg, f"alert:move:{tk}:{today}:{step}")
                    db.set_meta(con, key, step)
                    if a:
                        new.append(a)
        # 2. Squeeze fired (once per ticker per day)
        if len(bars) >= 40:
            sig = ta.compute(bars, lp)
            if sig.get("ok") and sig["bb"]["fired"]:
                direction = "up" if (sig["bb"]["momo"] or 0) > 0 else "down"
                msg = f"{tk} squeeze just fired, momentum {direction}. Now {_fmt(lp)}. Sent by {who}."
                a = _add(con, tk, "squeeze", msg, f"alert:squeeze:{tk}:{bars[-1]['date']}")
                if a:
                    new.append(a)


def _check_hits(con, new):
    rows = con.execute("SELECT s.id, s.ticker, s.sender_name, s.target_price, j.reasoning FROM judgments j "
                       "JOIN submissions s ON s.id=j.submission_id WHERE j.verdict='hit' AND s.target_price IS NOT NULL AND s.hidden=0").fetchall()
    for r in rows:
        msg = f"{r['sender_name']} called it: {r['ticker']} reached the {_fmt(r['target_price'])} target."
        a = _add(con, r["ticker"], "hit", msg, f"alert:hit:{r['id']}")
        if a:
            new.append(a)


def send_imessage(chat_guid: str, text: str) -> bool:
    """Send through the Messages app on this Mac (the stocks@ account). Needs Automation permission once."""
    script = 'on run argv\n tell application "Messages"\n  set theChat to a reference to chat id (item 1 of argv)\n' \
             '  send (item 2 of argv) to theChat\n end tell\nend run'
    try:
        p = subprocess.run(["osascript", "-e", script, chat_guid, text], capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            log.warning("imessage send failed: %s", p.stderr.strip()[:300])
            return False
        return True
    except Exception as e:
        log.warning("imessage send failed: %s", e)
        return False
