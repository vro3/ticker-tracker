"""Read new messages (with attachments) from the macOS Messages database."""
import os
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config

APPLE_EPOCH = 978307200  # 2001-01-01 in unix seconds
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".webp", ".gif", ".tiff"}
SETTLE_SECONDS = 90       # wait this long after a picture for a follow-up caption
CAPTION_WINDOW = 180      # a text within this many seconds of a picture is its caption
TICKER_IN_TEXT = re.compile(r"\$([A-Za-z]{1,5})\b")


def apple_to_datetime(value, tz: ZoneInfo) -> datetime:
    if value is None:
        return datetime.now(tz)
    if value > 10**12:          # nanoseconds (macOS 10.13+)
        secs = value / 1e9
    else:
        secs = float(value)
    return datetime.fromtimestamp(secs + APPLE_EPOCH, tz=timezone.utc).astimezone(tz)


def parse_attributed_body(blob) -> str:
    """Pull the plain string out of the typedstream blob Messages stores in attributedBody."""
    if not blob:
        return ""
    try:
        idx = blob.find(b"NSString")
        if idx == -1:
            return ""
        s = blob[idx + len(b"NSString") + 5:]
        if s[0] == 0x81:
            length = int.from_bytes(s[1:3], "little")
            s = s[3:]
        else:
            length = s[0]
            s = s[1:]
        return s[:length].decode("utf-8", errors="ignore")
    except Exception:
        return ""


def clean_text(text: str) -> str:
    return (text or "").replace("￼", "").strip()


def open_chat_db(path: str) -> sqlite3.Connection:
    uri = f"file:{path}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def fetch_rows(con, after_rowid: int):
    q = """
    SELECT m.ROWID AS rowid, m.date, m.text, m.attributedBody, m.is_from_me,
           m.cache_has_attachments, m.associated_message_type,
           h.id AS handle,
           c.display_name AS chat_name, c.chat_identifier
    FROM message m
    LEFT JOIN handle h ON h.ROWID = m.handle_id
    LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
    LEFT JOIN chat c ON c.ROWID = cmj.chat_id
    WHERE m.ROWID > ?
    ORDER BY m.ROWID
    """
    return con.execute(q, (after_rowid,)).fetchall()


def fetch_attachments(con, rowid: int):
    q = """
    SELECT a.filename, a.mime_type, a.uti
    FROM message_attachment_join maj
    JOIN attachment a ON a.ROWID = maj.attachment_id
    WHERE maj.message_id = ?
    """
    return con.execute(q, (rowid,)).fetchall()


def image_attachments(con, rowid: int):
    out = []
    for a in fetch_attachments(con, rowid):
        fn = a["filename"]
        if not fn:
            continue
        p = Path(os.path.expanduser(fn))
        mime = a["mime_type"] or ""
        if p.suffix.lower() in IMAGE_EXT or mime.startswith("image/"):
            out.append(p)
    return out


def stage_image(src: Path, dest_name: str) -> Path:
    """Copy an attachment into our screenshots folder as a web-friendly JPEG/PNG, max 1600px."""
    config.ensure_dirs()
    dest = config.SCREENSHOT_DIR / (dest_name + ".jpg")
    try:
        subprocess.run(
            ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "85",
             "-Z", "1600", str(src), "--out", str(dest)],
            check=True, capture_output=True, timeout=60,
        )
        return dest
    except Exception:
        dest = config.SCREENSHOT_DIR / (dest_name + src.suffix.lower())
        shutil.copy2(src, dest)
        return dest


class Message:
    def __init__(self, row, tz):
        self.rowid = row["rowid"]
        self.sent_at = apple_to_datetime(row["date"], tz)
        self.text = clean_text(row["text"]) or clean_text(parse_attributed_body(row["attributedBody"]))
        self.is_from_me = bool(row["is_from_me"])
        self.handle = row["handle"] or ("me" if self.is_from_me else "unknown")
        self.chat_name = row["chat_name"] or row["chat_identifier"] or ""
        self.reaction = bool(row["associated_message_type"])
        self.images = []
        self.caption = ""
        self.consumed = False
        self.skip = False


def collect_new(cfg: dict, after_rowid: int):
    """Return (messages_to_process, new_high_water_mark).

    Picture messages are held until SETTLE_SECONDS have passed so a follow-up text can be
    attached as the caption. Text-only messages that contain $TICKER are returned as
    submissions with no picture.
    """
    tz = ZoneInfo(cfg["timezone"])
    con = open_chat_db(cfg["chat_db"])
    try:
        rows = fetch_rows(con, after_rowid)
        msgs = []
        seen = set()
        for r in rows:
            if r["rowid"] in seen:      # a message can join several chats; keep the first
                continue
            seen.add(r["rowid"])
            m = Message(r, tz)
            m.skip = m.reaction or bool(cfg.get("chat_filter")) and cfg["chat_filter"].lower() not in m.chat_name.lower()
            if not m.skip:
                m.images = image_attachments(con, m.rowid)
            msgs.append(m)
    finally:
        con.close()

    now = datetime.now(tz)

    def settled(m):
        return bool(m.text) or (now - m.sent_at) >= timedelta(seconds=SETTLE_SECONDS)

    # Pass 1: attach captions to settled pictures (own text first, else nearest text from same sender).
    for i, m in enumerate(msgs):
        if m.images and settled(m):
            m.caption = m.text or _find_caption(msgs, i)

    # Pass 2: walk in order; stop at the first thing that still needs to wait.
    ready = []
    high_water = after_rowid
    for i, m in enumerate(msgs):
        if m.skip:
            pass
        elif m.images:
            if not settled(m):
                break
            ready.append(m)
        elif not m.consumed and TICKER_IN_TEXT.search(m.text):
            if _unsettled_image_follows(msgs, i, settled):
                break
            m.caption = m.text
            ready.append(m)
        high_water = m.rowid
    return ready, high_water


def _find_caption(msgs, i):
    me = msgs[i]
    best = None
    for j, other in enumerate(msgs):
        if j == i or other.skip or other.images or other.consumed or other.handle != me.handle:
            continue
        dt = abs((other.sent_at - me.sent_at).total_seconds())
        if dt <= CAPTION_WINDOW and other.text and (best is None or dt < best[0]):
            best = (dt, other)
    if best:
        best[1].consumed = True
        return best[1].text
    return ""


def _unsettled_image_follows(msgs, i, settled):
    me = msgs[i]
    for other in msgs[i + 1:]:
        if other.images and other.handle == me.handle and not settled(other):
            if (other.sent_at - me.sent_at).total_seconds() <= CAPTION_WINDOW:
                return True
    return False


def sender_name(cfg: dict, handle: str) -> str:
    people = cfg.get("people", {})
    if handle in people:
        return people[handle]
    digits = re.sub(r"\D", "", handle)
    for k, v in people.items():
        if digits and re.sub(r"\D", "", k) == digits:
            return v
    if handle == "me":
        return people.get("me", "Tracker")
    return handle
