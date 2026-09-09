import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_messages (
    msg_rowid INTEGER PRIMARY KEY,
    seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_rowid INTEGER UNIQUE,
    sent_at TEXT NOT NULL,            -- ISO 8601 with offset, local time zone
    sent_date TEXT NOT NULL,          -- YYYY-MM-DD local
    sender_handle TEXT NOT NULL,
    sender_name TEXT NOT NULL,
    chat_name TEXT,
    screenshot TEXT,                  -- file name inside screenshots/
    ticker TEXT,
    company TEXT,
    price_seen REAL,                  -- price visible in the screenshot
    currency TEXT,
    note TEXT,                        -- what they typed with the picture
    goal TEXT,                        -- plain-English restatement of their goal
    direction TEXT,                   -- up / down / watch / unknown
    target_price REAL,
    horizon_days INTEGER,
    confidence REAL,
    status TEXT NOT NULL DEFAULT 'ok', -- ok / needs_review / error
    extraction_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prices (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,               -- YYYY-MM-DD (exchange local)
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (ticker, date)
);
CREATE TABLE IF NOT EXISTS latest (
    ticker TEXT PRIMARY KEY,
    price REAL,
    as_of TEXT,
    name TEXT
);
CREATE TABLE IF NOT EXISTS judgments (
    submission_id INTEGER PRIMARY KEY,
    verdict TEXT,                     -- hit / miss / pending / no_call
    reasoning TEXT,
    as_of_price REAL,
    judged_at TEXT
);
CREATE TABLE IF NOT EXISTS intraday (
    ticker TEXT NOT NULL,
    ts TEXT NOT NULL,                 -- 5-minute bar start, New York time
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (ticker, ts)
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT,
    kind TEXT,                        -- move / squeeze / hit
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    sent INTEGER NOT NULL DEFAULT 0   -- 1 once texted to the group
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


_initialized = set()   # DB paths whose schema/WAL setup already ran in this process


def connect() -> sqlite3.Connection:
    config.ensure_dirs()
    con = sqlite3.connect(config.DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    key = str(config.DB_PATH)
    if key not in _initialized:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)
        cols = {r["name"] for r in con.execute("PRAGMA table_info(submissions)")}
        if "hidden" not in cols:               # soft delete: the dashboard ✕ hides, never destroys
            con.execute("ALTER TABLE submissions ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")
            con.commit()
        _initialized.add(key)
    return con


@contextmanager
def tx():
    con = connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()


def set_meta(con, key, value):
    con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, str(value)))


def get_meta(con, key, default=None):
    row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default
