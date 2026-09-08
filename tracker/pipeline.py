"""Glue: new iMessages -> screenshot staging -> Claude extraction -> database -> prices -> verdicts."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import config, db, imessage, judge, prices, vision

log = logging.getLogger("tracker")


def record_submission(con, cfg, *, sent_at, sender_handle, sender_name, chat_name, image: Path | None,
                      caption: str, msg_rowid=None, override: dict | None = None):
    """override lets a human supply ticker/price directly and skip the vision step."""
    sent_date = sent_at.date().isoformat()
    stamp = sent_at.strftime("%Y%m%d-%H%M%S")
    staged = imessage.stage_image(image, f"{stamp}-{sender_name}".replace(" ", "_")) if image else None
    row = {
        "msg_rowid": msg_rowid, "sent_at": sent_at.isoformat(), "sent_date": sent_date,
        "sender_handle": sender_handle, "sender_name": sender_name, "chat_name": chat_name,
        "screenshot": staged.name if staged else None, "note": caption or None,
        "status": "ok", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        data = override if override else vision.extract(cfg, staged, caption)
        row.update({
            "ticker": (data.get("ticker") or "").upper().strip() or None,
            "company": data.get("company"), "price_seen": data.get("price"), "currency": data.get("currency"),
            "goal": data.get("goal"), "direction": data.get("direction") or "unknown",
            "target_price": data.get("target_price"), "horizon_days": data.get("horizon_days"),
            "confidence": data.get("confidence"), "extraction_json": json.dumps(data),
        })
        if not row["ticker"] or (row["confidence"] or 0) < 0.5:
            row["status"] = "needs_review"
        elif not prices.validate_ticker(row["ticker"]):
            row["status"] = "needs_review"
            row["error"] = f"Ticker {row['ticker']} not found in market data"
    except Exception as e:
        log.exception("extraction failed")
        row["status"] = "error"
        row["error"] = str(e)[:500]
    cols = ", ".join(row.keys())
    marks = ", ".join("?" for _ in row)
    cur = con.execute(f"INSERT INTO submissions({cols}) VALUES ({marks})", list(row.values()))
    con.commit()
    log.info("submission #%d %s %s %s [%s]", cur.lastrowid, sender_name, row.get("ticker"), row.get("price_seen"), row["status"])
    return cur.lastrowid


def ingest(cfg):
    """Look for new messages and record them. Returns number of new submissions."""
    with db.tx() as con:
        after = int(db.get_meta(con, "last_msg_rowid", 0))
        if after == 0:
            after = _initial_high_water(cfg)
            db.set_meta(con, "last_msg_rowid", after)
            log.info("first run: ignoring messages before rowid %d", after)
            return 0
        ready, high = imessage.collect_new(cfg, after)
        n = 0
        for m in ready:
            if con.execute("SELECT 1 FROM seen_messages WHERE msg_rowid=?", (m.rowid,)).fetchone():
                continue
            con.execute("INSERT INTO seen_messages(msg_rowid, seen_at) VALUES (?,?)",
                        (m.rowid, datetime.now(timezone.utc).isoformat()))
            name = imessage.sender_name(cfg, m.handle)
            image = m.images[0] if m.images else None
            record_submission(con, cfg, sent_at=m.sent_at, sender_handle=m.handle, sender_name=name,
                              chat_name=m.chat_name, image=image, caption=m.caption, msg_rowid=m.rowid)
            n += 1
        if high > after:
            db.set_meta(con, "last_msg_rowid", high)
        if n:
            prices.refresh(con)
            judge.judge_all(con)
    return n


def _initial_high_water(cfg) -> int:
    con = imessage.open_chat_db(cfg["chat_db"])
    try:
        return int(con.execute("SELECT COALESCE(MAX(ROWID),0) FROM message").fetchone()[0])
    finally:
        con.close()


def refresh_prices():
    with db.tx() as con:
        n = prices.refresh(con)
        judge.judge_all(con)
    return n


def correct_ticker(sub_id: int, ticker: str):
    ticker = ticker.upper().strip()
    with db.tx() as con:
        ok = prices.validate_ticker(ticker)
        con.execute("UPDATE submissions SET ticker=?, status=?, error=NULL WHERE id=?",
                    (ticker, "ok" if ok else "needs_review", sub_id))
        prices.refresh(con, [ticker])
        judge.judge_all(con)
        return ok
