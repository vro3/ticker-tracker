"""Daily closes and latest prices via yfinance."""
import logging
from datetime import date, datetime, timedelta, timezone

log = logging.getLogger("tracker.prices")


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
            start = date.fromisoformat(first) - timedelta(days=7)
            if last:
                start = max(start, date.fromisoformat(last) - timedelta(days=3))
            rows = fetch_history(tk, start)
            con.executemany(
                "INSERT OR REPLACE INTO prices(ticker,date,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)", rows)
            price, name = fetch_latest(tk)
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
