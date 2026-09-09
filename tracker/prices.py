"""Daily closes and latest prices via yfinance."""
import logging
from datetime import date, datetime, timedelta, timezone

log = logging.getLogger("tracker.prices")
HISTORY_DAYS = 420  # enough daily bars for a 200-day EMA and a year of supply/demand zones


def _yf():
    import yfinance as yf
    return yf


def fetch_history(ticker: str, start: date):
    yf = _yf()
    t = yf.Ticker(ticker)
    df = t.history(start=start.isoformat(), interval="1d", auto_adjust=False)
    rows = []
    for idx, r in df.iterrows():
        d = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
        rows.append((ticker, d, float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"]),
                     float(r["Volume"]) if r["Volume"] == r["Volume"] else None))
    return rows


def fetch_latest(ticker: str):
    yf = _yf()
    t = yf.Ticker(ticker)
    price, name = None, None
    try:
        fi = t.fast_info
        price = float(fi["last_price"]) if fi and fi["last_price"] else None
    except Exception:
        price = None
    try:
        name = t.info.get("shortName") or t.info.get("longName")
    except Exception:
        name = None
    if price is None:
        df = t.history(period="5d", interval="1d")
        if len(df):
            price = float(df["Close"].iloc[-1])
    return price, name


def market_open_now() -> bool:
    """True during US extended hours (4:00-20:00 New York, weekdays)."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/New_York"))
    return now.weekday() < 5 and 4 <= now.hour < 20


def fetch_quotes(tickers):
    """One batched request for the last 1-minute bar of every ticker, pre/post market included.
    Returns {ticker: (price, as_of_iso)}. Falls back to fast_info per ticker if a bar is missing."""
    yf = _yf()
    out = {}
    if not tickers:
        return out
    try:
        df = yf.download(list(tickers), period="1d", interval="1m", group_by="ticker",
                         progress=False, threads=True, prepost=True)
        multi = hasattr(df.columns, "levels")
        for tk in tickers:
            try:
                closes = (df[tk]["Close"] if multi else df["Close"]).dropna()
                if len(closes):
                    ts = closes.index[-1]
                    if ts.tzinfo is None:
                        ts = ts.tz_localize("America/New_York")
                    out[tk] = (float(closes.iloc[-1]), ts.tz_convert(timezone.utc).isoformat())
            except Exception:
                pass
    except Exception as e:
        log.warning("quotes: batch download failed: %s", e)
    for tk in tickers:
        if tk in out:
            continue
        try:
            fi = yf.Ticker(tk).fast_info
            if fi and fi["last_price"]:
                out[tk] = (float(fi["last_price"]), datetime.now(timezone.utc).isoformat())
        except Exception as e:
            log.warning("quotes: %s fast_info failed: %s", tk, e)
    return out


def refresh_quotes(con):
    """Cheap latest-price update for every tracked ticker; daily history untouched."""
    tickers = [r["ticker"] for r in con.execute(
        "SELECT DISTINCT ticker FROM submissions WHERE ticker IS NOT NULL AND status != 'error'")]
    quotes = fetch_quotes(tickers)
    for tk, (price, as_of) in quotes.items():
        con.execute("""INSERT INTO latest(ticker,price,as_of,name) VALUES (?,?,?,NULL)
                       ON CONFLICT(ticker) DO UPDATE SET price=excluded.price, as_of=excluded.as_of""",
                    (tk, price, as_of))
    con.commit()
    return len(quotes)


def refresh(con, tickers=None):
    """Fill in daily closes since each ticker's earliest submission and update latest prices."""
    if tickers is None:
        tickers = [r["ticker"] for r in con.execute(
            "SELECT DISTINCT ticker FROM submissions WHERE ticker IS NOT NULL AND status != 'error'")]
    updated = 0
    for tk in tickers:
        try:
            first = con.execute("SELECT MIN(sent_date) AS d FROM submissions WHERE ticker=?", (tk,)).fetchone()["d"]
            last = con.execute("SELECT MAX(date) AS d FROM prices WHERE ticker=?", (tk,)).fetchone()["d"]
            if first is None:
                continue
            start = date.fromisoformat(first) - timedelta(days=HISTORY_DAYS)
            have = con.execute("SELECT COUNT(*) AS n FROM prices WHERE ticker=?", (tk,)).fetchone()["n"]
            if last and have >= 200:
                start = max(start, date.fromisoformat(last) - timedelta(days=3))
            rows = fetch_history(tk, start)
            price, name = fetch_latest(tk)       # all network done before touching the DB
            con.executemany(
                "INSERT OR REPLACE INTO prices(ticker,date,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)", rows)
            if price is not None:
                con.execute("INSERT OR REPLACE INTO latest(ticker,price,as_of,name) VALUES (?,?,?,?)",
                            (tk, price, datetime.now(timezone.utc).isoformat(), name))
            con.commit()
            updated += 1
            log.info("prices: %s %d rows, latest %s", tk, len(rows), price)
        except Exception as e:
            log.warning("prices: %s failed: %s", tk, e)
    return updated


def validate_ticker(ticker: str) -> bool:
    try:
        df = _yf().Ticker(ticker).history(period="5d", interval="1d")
        return len(df) > 0
    except Exception:
        return False
