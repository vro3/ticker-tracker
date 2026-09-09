"""Intraday bars (5-minute, regular session) from Yahoo for Vince's setups: EMA8/VWMA26 on the 5m,
three-candle gaps on the 15m, and 1h/2h/4h continuity. Refreshed every few minutes during market hours.
Version 1.0 · 2026-09-08
"""
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from . import ta

log = logging.getLogger("tracker.intraday")
NY = ZoneInfo("America/New_York")
SESSION_OPEN_MIN = 9 * 60 + 30


def fetch_5m(tickers):
    """{ticker: [bar dicts with ts (ISO, New York), open, high, low, close, volume]} for the last 5 sessions."""
    import yfinance as yf
    out = {}
    if not tickers:
        return out
    try:
        df = yf.download(list(tickers), period="5d", interval="5m", group_by="ticker",
                         progress=False, threads=True, prepost=False)
    except Exception as e:
        log.warning("5m download failed: %s", e)
        return out
    multi = hasattr(df.columns, "levels")
    for tk in tickers:
        try:
            d = (df[tk] if multi else df).dropna(subset=["Close"])
            bars = []
            for ts, r in d.iterrows():
                t = ts.tz_convert(NY) if ts.tzinfo else ts.tz_localize("UTC").tz_convert(NY)
                bars.append({"ts": t.isoformat(), "open": float(r["Open"]), "high": float(r["High"]),
                             "low": float(r["Low"]), "close": float(r["Close"]),
                             "volume": float(r["Volume"]) if r["Volume"] == r["Volume"] else 0.0})
            out[tk] = bars
        except Exception as e:
            log.warning("5m %s: %s", tk, e)
    return out


def store(con, data):
    for tk, bars in data.items():
        con.execute("DELETE FROM intraday WHERE ticker=?", (tk,))
        con.executemany("INSERT OR REPLACE INTO intraday(ticker, ts, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
                        [(tk, b["ts"], b["open"], b["high"], b["low"], b["close"], b["volume"]) for b in bars])
    con.commit()


def load(con, ticker):
    return [dict(r) for r in con.execute(
        "SELECT ts, open, high, low, close, volume FROM intraday WHERE ticker=? ORDER BY ts", (ticker,))]


def refresh(con, tickers):
    data = fetch_5m(tickers)
    store(con, data)
    return len(data)


def _bucket(ts_iso, minutes):
    """Start of the aggregation bucket containing ts, anchored to the 9:30 session open (like thinkorswim)."""
    t = datetime.fromisoformat(ts_iso)
    mins = t.hour * 60 + t.minute - SESSION_OPEN_MIN
    if mins < 0:
        mins = 0
    start = SESSION_OPEN_MIN + (mins // minutes) * minutes
    return t.replace(hour=start // 60, minute=start % 60, second=0, microsecond=0)


def resample(bars5, minutes):
    out = []
    cur = None
    for b in bars5:
        key = _bucket(b["ts"], minutes)
        if cur is None or cur["_key"] != key:
            cur = {"_key": key, "ts": key.isoformat(), "open": b["open"], "high": b["high"], "low": b["low"],
                   "close": b["close"], "volume": b["volume"]}
            out.append(cur)
        else:
            cur["high"] = max(cur["high"], b["high"])
            cur["low"] = min(cur["low"], b["low"])
            cur["close"] = b["close"]
            cur["volume"] += b["volume"]
    for o in out:
        o.pop("_key", None)
    return out


def setups(bars5, price=None):
    """Everything Vince's charts show, from 5m bars."""
    if len(bars5) < 30:
        return {"ok": False, "why": f"only {len(bars5)} five-minute bars"}
    price = price or bars5[-1]["close"]
    m15 = resample(bars5, 15)
    h1, h2, h4 = resample(bars5, 60), resample(bars5, 120), resample(bars5, 240)
    last_day = bars5[-1]["ts"][:10]
    same_day = lambda bars: [b for b in bars if b["ts"][:10] == last_day]
    opens = {"1h": (same_day(h1) or [{}])[-1].get("open"), "2h": (same_day(h2) or [{}])[-1].get("open"),
             "4h": (same_day(h4) or [{}])[-1].get("open")}
    return {"ok": True, "as_of": bars5[-1]["ts"], "price": price,
            "m5": ta.ema_vwma_state(bars5),
            "m15_gaps": ta.gap_zones(m15),
            "ftfc": ta.ftfc(price, opens)}
