"""Tiny dashboard server: static page + JSON API. No framework needed."""
import json
import logging
import mimetypes
import re
import threading
import time
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import config, db, intraday, pipeline, ta

log = logging.getLogger("tracker.web")
STATIC = Path(__file__).parent / "static"
TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")
MAX_BODY = 64_000
_PAYLOAD = {"at": 0.0, "data": None}
_PAYLOAD_LOCK = threading.Lock()
_WORK_LOCK = threading.Lock()          # one expensive job (refresh/ingest/correct) at a time
PAYLOAD_TTL = 20                       # seconds; the page polls every 30


def health(con=None):
    """Freshness of every moving part, for /api/health and the dashboard footer."""
    own = con is None
    if own:
        con = db.connect()
    try:
        now = datetime.now(timezone.utc)

        def age(iso):
            if not iso:
                return None
            try:
                t = datetime.fromisoformat(iso)
                if t.tzinfo is None:
                    t = t.astimezone()
                return round((now - t.astimezone(timezone.utc)).total_seconds())
            except Exception:
                return None
        last_poll = db.get_meta(con, "last_poll")
        last_prices = db.get_meta(con, "last_price_refresh")
        last_intraday = con.execute("SELECT MAX(ts) AS t FROM intraday").fetchone()["t"]
        counts = {"submissions": con.execute("SELECT COUNT(*) AS n FROM submissions").fetchone()["n"],
                  "tickers": con.execute("SELECT COUNT(DISTINCT ticker) AS n FROM submissions WHERE ticker IS NOT NULL").fetchone()["n"],
                  "price_rows": con.execute("SELECT COUNT(*) AS n FROM prices").fetchone()["n"],
                  "alerts": con.execute("SELECT COUNT(*) AS n FROM alerts").fetchone()["n"]}
        poll_age = age(last_poll)
        ok = poll_age is not None and poll_age < 600
        return {"ok": ok, "last_poll": last_poll, "poll_age_s": poll_age, "last_price_refresh": last_prices,
                "price_age_s": age(last_prices), "last_intraday_bar": last_intraday, "last_error": db.get_meta(con, "last_error"),
                "counts": counts, "server_time": now.isoformat()}
    finally:
        if own:
            con.close()


def build_payload():
    con = db.connect()
    try:
        latest = {r["ticker"]: dict(r) for r in con.execute("SELECT * FROM latest")}
        judg = {r["submission_id"]: dict(r) for r in con.execute("SELECT * FROM judgments")}
        ta_cache = {}

        def signals(tk):
            if tk not in ta_cache:
                bars = [dict(b) for b in con.execute(
                    "SELECT date, open, high, low, close, volume FROM prices WHERE ticker=? ORDER BY date", (tk,))]
                try:
                    ta_cache[tk] = ta.compute(bars, latest.get(tk, {}).get("price"))
                except Exception as e:
                    log.warning("ta %s failed: %s", tk, e)
                    ta_cache[tk] = {"ok": False, "why": str(e)[:100]}
            return ta_cache[tk]
        setup_cache = {}

        def setups(tk):
            if tk not in setup_cache:
                try:
                    bars = [dict(b) for b in con.execute(
                        "SELECT date, open, high, low, close, volume FROM prices WHERE ticker=? ORDER BY date", (tk,))]
                    price = latest.get(tk, {}).get("price") or (bars[-1]["close"] if bars else None)
                    daily = None
                    if len(bars) >= 30 and price:
                        daily = {"ema_vwma": ta.ema_vwma_state(bars), "gaps": ta.gap_zones(bars),
                                 "ftfc": ta.ftfc(price, ta.period_opens_daily(bars, price))}
                    intra = intraday.setups(intraday.load(con, tk), price)
                    setup_cache[tk] = {"daily": daily, "intraday": intra,
                                       "grade": ta.grade(bars, price, signals(tk)) if bars else None,
                                       "rsi2": ta.rsi2_reversal(bars) if bars else None,
                                       "volume": ta.volume_split(bars) if bars else None,
                                       "ladder": ta.pivot_ladder(bars) if bars else None}
                except Exception as e:
                    log.warning("setups %s failed: %s", tk, e)
                    setup_cache[tk] = None
            return setup_cache[tk]
        subs = []
        for r in con.execute("SELECT * FROM submissions ORDER BY sent_at DESC"):
            s = dict(r)
            s.pop("extraction_json", None)
            tk = s["ticker"]
            lp = latest.get(tk, {}).get("price") if tk else None
            base = s["price_seen"]
            series = []
            if tk:
                series = [dict(x) for x in con.execute(
                    "SELECT date, close FROM prices WHERE ticker=? AND date>=? ORDER BY date", (tk, s["sent_date"]))]
                if base is None and series:
                    base = series[0]["close"]
            s["base_price"] = base
            s["latest_price"] = lp
            s["latest_as_of"] = latest.get(tk, {}).get("as_of") if tk else None
            s["company"] = s["company"] or (latest.get(tk, {}).get("name") if tk else None)
            s["pct"] = ((lp - base) / base * 100) if (lp and base) else None
            s["days"] = (date.today() - date.fromisoformat(s["sent_date"])).days
            s["series"] = series
            j = judg.get(s["id"], {})
            s["ta"] = signals(tk) if tk else None
            s["setups"] = setups(tk) if tk else None
            s["verdict"] = j.get("verdict", "pending" if tk else None)
            s["reasoning"] = j.get("reasoning")
            subs.append(s)
        people = {}
        for s in subs:
            p = people.setdefault(s["sender_name"], {"name": s["sender_name"], "count": 0, "pcts": [],
                                                      "hit": 0, "miss": 0, "pending": 0, "no_call": 0})
            p["count"] += 1
            if s["pct"] is not None:
                p["pcts"].append(s["pct"])
            if s["verdict"] in p:
                p[s["verdict"]] += 1
        for p in people.values():
            p["avg_pct"] = sum(p["pcts"]) / len(p["pcts"]) if p["pcts"] else None
            p["best"] = max(p["pcts"]) if p["pcts"] else None
            del p["pcts"]
        pcts = [s["pct"] for s in subs if s["pct"] is not None]
        summary = {
            "count": len(subs),
            "tickers": len({s["ticker"] for s in subs if s["ticker"]}),
            "avg_pct": sum(pcts) / len(pcts) if pcts else None,
            "hits": sum(1 for s in subs if s["verdict"] == "hit"),
            "misses": sum(1 for s in subs if s["verdict"] == "miss"),
            "needs_review": sum(1 for s in subs if s["status"] != "ok"),
            "last_price_refresh": db.get_meta(con, "last_price_refresh"),
        }
        alerts_recent = [dict(r) for r in con.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 12")]
        summary["health"] = health(con)
        return {"generated_at": datetime.now(timezone.utc).isoformat(), "summary": summary, "alerts": alerts_recent,
                "people": sorted(people.values(), key=lambda p: -(p["avg_pct"] or -999)), "submissions": subs}
    finally:
        con.close()


def cached_payload():
    """Share one payload between all pollers for PAYLOAD_TTL seconds; invalidated by any write."""
    with _PAYLOAD_LOCK:
        if _PAYLOAD["data"] is not None and time.time() - _PAYLOAD["at"] < PAYLOAD_TTL:
            return _PAYLOAD["data"]
        data = build_payload()
        _PAYLOAD["data"], _PAYLOAD["at"] = data, time.time()
        return data


def invalidate_payload():
    with _PAYLOAD_LOCK:
        _PAYLOAD["at"] = 0.0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.debug(fmt, *args)

    def _send(self, code, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode())

    def _remote(self) -> bool:
        """True when the request came through the Cloudflare tunnel (or any proxy), not from this Mac."""
        return bool(self.headers.get("Cf-Connecting-Ip") or self.headers.get("X-Forwarded-For"))

    def do_GET(self):
        try:
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/api/health":
                h = health()
                return self._json(h, 200 if h["ok"] else 503)
            if path == "/api/data":
                return self._json(cached_payload())
            if path.startswith("/screenshots/"):
                name = Path(path).name
                f = (config.SCREENSHOT_DIR / name).resolve()
                if f.parent == config.SCREENSHOT_DIR.resolve() and f.is_file():
                    return self._send(200, f.read_bytes(), mimetypes.guess_type(name)[0] or "image/jpeg")
                return self._json({"error": "not found"}, 404)
            f = (STATIC / Path(path).name).resolve()
            if path.count("/") == 1 and f.parent == STATIC.resolve() and f.is_file():
                return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
            self._json({"error": "not found"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            log.exception("GET %s failed: %s", self.path, e)
            try:
                self._json({"error": "server error"}, 500)
            except Exception:
                pass

    def do_POST(self):
        try:
            path = urlparse(self.path).path
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._json({"error": "bad length"}, 400)
            if length < 0 or length > MAX_BODY:
                return self._json({"error": "body too large"}, 413)
            try:
                body = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except ValueError:
                return self._json({"error": "bad json"}, 400)
            if not isinstance(body, dict):
                return self._json({"error": "bad json"}, 400)
            if path in ("/api/refresh", "/api/ingest"):
                if self._remote():
                    return self._json({"error": "local only"}, 403)
                if not _WORK_LOCK.acquire(blocking=False):
                    return self._json({"error": "busy"}, 429)
                try:
                    if path == "/api/refresh":
                        n = pipeline.refresh_prices()
                        invalidate_payload()
                        return self._json({"ok": True, "tickers": n})
                    n = pipeline.ingest(config.load())
                    invalidate_payload()
                    return self._json({"ok": True, "new": n})
                finally:
                    _WORK_LOCK.release()
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[:2] == ["api", "submissions"] and parts[2].isdigit():
                sub_id = int(parts[2])
                if "ticker" in body:
                    ticker = str(body["ticker"]).upper().strip()
                    if not TICKER_RE.match(ticker):
                        return self._json({"ok": False, "error": "ticker must be 1-10 letters/digits"}, 400)
                    if not _WORK_LOCK.acquire(blocking=False):
                        return self._json({"error": "busy"}, 429)
                    try:
                        ok = pipeline.correct_ticker(sub_id, ticker)
                    finally:
                        _WORK_LOCK.release()
                    invalidate_payload()
                    return self._json({"ok": ok})
                if body.get("delete") is True:
                    with db.tx() as con:
                        con.execute("DELETE FROM submissions WHERE id=?", (sub_id,))
                        con.execute("DELETE FROM judgments WHERE submission_id=?", (sub_id,))
                    invalidate_payload()
                    return self._json({"ok": True})
            self._json({"error": "not found"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            log.exception("POST %s failed: %s", self.path, e)
            try:
                self._json({"error": "server error"}, 500)
            except Exception:
                pass


def serve(port: int, block=True):
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    log.info("dashboard on http://localhost:%d", port)
    if block:
        srv.serve_forever()
    else:
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
    return srv
