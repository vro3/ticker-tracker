"""Builds a small fake chat.db with the real table shapes and checks the reader logic.
Run: .venv/bin/python -m tests.test_imessage
"""
import os
import sqlite3
import tempfile
import time
from pathlib import Path

from tracker import imessage

APPLE = 978307200


def ns(unix_secs):
    return int((unix_secs - APPLE) * 1e9)


def build(path: Path, now: float):
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT);
    CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, chat_identifier TEXT, display_name TEXT);
    CREATE TABLE message (ROWID INTEGER PRIMARY KEY, guid TEXT, text TEXT, attributedBody BLOB, handle_id INTEGER,
        date INTEGER, is_from_me INTEGER DEFAULT 0, cache_has_attachments INTEGER DEFAULT 0, associated_message_type INTEGER DEFAULT 0);
    CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);
    CREATE TABLE attachment (ROWID INTEGER PRIMARY KEY, filename TEXT, mime_type TEXT, uti TEXT);
    CREATE TABLE message_attachment_join (message_id INTEGER, attachment_id INTEGER);
    """)
    con.execute("INSERT INTO handle VALUES (1, '+16155550100'), (2, 'dana@icloud.com')")
    con.execute("INSERT INTO chat VALUES (1, 'chat123', 'Stocks')")
    img = Path(tempfile.gettempdir()) / "tt_fake.png"
    img.write_bytes(Path("tests/fixtures/nvda_sample.png").read_bytes())
    con.execute("INSERT INTO attachment VALUES (1, ?, 'image/png', 'public.png')", (str(img),))
    # attributedBody-only text (the way modern macOS stores it)
    body = b"streamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84\x12NSAttributedString\x00\x84\x84\x08NSObject\x00\x85\x92\x84\x84\x84\x08NSString\x01\x94\x84\x01+" + bytes([21]) + b"buying more at 187.42\x86"
    rows = [
        # old message, before high-water mark
        (1, None, "old stuff", 1, ns(now - 86400), 0, 0),
        # Vince: picture 10 min ago (no text) then a caption 20 s later
        (2, None, None, 1, ns(now - 600), 0, 1),
        (3, "think this hits 200 by Friday", None, 1, ns(now - 580), 0, 0),
        # Dana: text-only idea with $TICKER
        (4, "$AAPL looks tired, expecting a pullback", None, 2, ns(now - 400), 0, 0),
        # Dana: attributedBody caption first, then picture 15 s later, still settled (5 min ago)
        (5, None, body, 2, ns(now - 315), 0, 0),
        (6, None, None, 2, ns(now - 300), 0, 1),
        # Vince: picture 30 s ago, no caption yet -> must wait
        (7, None, None, 1, ns(now - 30), 0, 1),
        # a reaction (tapback) should be ignored
        (8, "Loved an image", None, 2, ns(now - 20), 0, 0),
    ]
    for r in rows:
        con.execute("INSERT INTO message(ROWID,text,attributedBody,handle_id,date,is_from_me,cache_has_attachments) VALUES (?,?,?,?,?,?,?)", r)
        con.execute("INSERT INTO chat_message_join VALUES (1, ?)", (r[0],))
    con.execute("UPDATE message SET associated_message_type=2000 WHERE ROWID=8")
    for mid in (2, 6, 7):
        con.execute("INSERT INTO message_attachment_join VALUES (?, 1)", (mid,))
    con.commit(); con.close()


def main():
    now = time.time()
    tmp = Path(tempfile.mkdtemp()) / "chat.db"
    build(tmp, now)
    cfg = {"timezone": "America/Chicago", "chat_db": str(tmp), "chat_filter": "stocks",
           "people": {"+1 (615) 555-0100": "Vince", "dana@icloud.com": "Dana"}}
    assert imessage.parse_attributed_body(open(tmp, "rb").read()[:0]) == ""
    ready, high = imessage.collect_new(cfg, after_rowid=1)
    got = [(m.rowid, imessage.sender_name(cfg, m.handle), bool(m.images), m.caption) for m in ready]
    for g in got:
        print(g)
    print("high water:", high)
    assert got == [
        (2, "Vince", True, "think this hits 200 by Friday"),
        (4, "Dana", False, "$AAPL looks tired, expecting a pullback"),
        (6, "Dana", True, "buying more at 187.42"),
    ], got
    assert high == 6, high  # stops before the unsettled picture (7)
    # once settled, message 7 is returned with no caption
    ready2, high2 = imessage.collect_new({**cfg, "chat_db": str(tmp)}, after_rowid=6)
    assert [m.rowid for m in ready2] == [] and high2 == 6, (ready2, high2)
    imessage.SETTLE_SECONDS = 0
    ready3, high3 = imessage.collect_new(cfg, after_rowid=6)
    assert [(m.rowid, m.caption) for m in ready3] == [(7, "")], ready3
    assert high3 == 8
    print("ALL PASS")


if __name__ == "__main__":
    main()
