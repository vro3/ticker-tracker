"""Decide whether a submission's stated call played out. Deterministic, no API cost."""
from datetime import date, datetime, timedelta, timezone

DEFAULT_HORIZON = 30  # days to wait before scoring a call that named no time frame


def series_for(con, ticker: str, since: str):
    return con.execute("SELECT date, high, low, close FROM prices WHERE ticker=? AND date>=? ORDER BY date",
                       (ticker, since)).fetchall()


def base_price(con, sub) -> float | None:
    """Price we treat as the 'bought that day' price: what the screenshot showed, else that day's close."""
    if sub["price_seen"]:
        return float(sub["price_seen"])
    row = con.execute("SELECT close FROM prices WHERE ticker=? AND date<=? ORDER BY date DESC LIMIT 1",
                      (sub["ticker"], sub["sent_date"])).fetchone()
    return float(row["close"]) if row else None


def judge_one(con, sub, latest_price):
    base = base_price(con, sub)
    rows = series_for(con, sub["ticker"], sub["sent_date"])
    direction = sub["direction"] or "unknown"
    target = sub["target_price"]
    horizon = sub["horizon_days"]
    sent = date.fromisoformat(sub["sent_date"])
    today = date.today()
    days = (today - sent).days
    hi = max((r["high"] for r in rows if r["high"]), default=None)
    lo = min((r["low"] for r in rows if r["low"]), default=None)
    now = latest_price if latest_price is not None else (rows[-1]["close"] if rows else None)

    if direction in ("watch", "unknown") and not target:
        return "no_call", "No prediction was made, just watching."
    if base is None or now is None:
        return "pending", "Waiting for price data."

    pct = (now - base) / base * 100
    if target:
        if direction != "down" and hi is not None and hi >= target:
            return "hit", f"Reached target {target:g} (high {hi:g}) after being sent at {base:g}."
        if direction == "down" and lo is not None and lo <= target:
            return "hit", f"Fell to target {target:g} (low {lo:g}) after being sent at {base:g}."
        if horizon and days > horizon:
            return "miss", f"Target {target:g} not reached within {horizon} days. Now {now:g} ({pct:+.1f}%)."
        return "pending", f"Target {target:g}; now {now:g} ({pct:+.1f}%), day {days}."

    window = horizon or DEFAULT_HORIZON
    if days < window:
        return "pending", f"Called {direction}; now {pct:+.1f}% on day {days} of {window}."
    end_row = next((r for r in reversed(rows) if date.fromisoformat(r["date"]) <= sent + timedelta(days=window)), None)
    end_price = end_row["close"] if end_row else now
    end_pct = (end_price - base) / base * 100
    ok = end_pct > 0 if direction == "up" else end_pct < 0
    return ("hit" if ok else "miss"), f"Called {direction}; moved {end_pct:+.1f}% over {window} days."


def judge_all(con):
    latest = {r["ticker"]: r["price"] for r in con.execute("SELECT ticker, price FROM latest")}
    subs = con.execute("SELECT * FROM submissions WHERE ticker IS NOT NULL AND status='ok'").fetchall()
    now = datetime.now(timezone.utc).isoformat()
    for sub in subs:
        verdict, why = judge_one(con, sub, latest.get(sub["ticker"]))
        con.execute("INSERT OR REPLACE INTO judgments(submission_id, verdict, reasoning, as_of_price, judged_at) "
                    "VALUES (?,?,?,?,?)", (sub["id"], verdict, why, latest.get(sub["ticker"]), now))
    con.commit()
    return len(subs)
