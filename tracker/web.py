"""Tiny dashboard server: static page + JSON API. No framework needed."""
import json
import logging
import mimetypes
import threading
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import config, db, pipeline

log = logging.getLogger("tracker.web")
STATIC = Path(__file__).parent / "static"


def build_payload():
    con = db.connect()
    try:
        latest = {r["ticker"]: dict(r) for r in con.execute("SELECT * FROM latest")}
        judg = {r["submission_id"]: dict(r) for r in con.execute("SELECT * FROM judgments")}
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
        return {"generated_at": datetime.now(timezone.utc).isoformat(), "summary": summary,
                "people": sorted(people.values(), key=lambda p: -(p["avg_pct"] or -999)), "submissions": subs}
    finally:
        con.close()


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

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/data":
            return self._json(build_payload())
        if path.startswith("/screenshots/"):
            name = Path(path).name
            f = config.SCREENSHOT_DIR / name
            if f.exists() and f.is_file():
                return self._send(200, f.read_bytes(), mimetypes.guess_type(name)[0] or "image/jpeg")
            return self._json({"error": "not found"}, 404)
        f = STATIC / Path(path).name
        if path.count("/") == 1 and f.exists():
            return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        if path == "/api/refresh":
            n = pipeline.refresh_prices()
            return self._json({"ok": True, "tickers": n})
        if path == "/api/ingest":
            n = pipeline.ingest(config.load())
            return self._json({"ok": True, "new": n})
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] == ["api", "submissions"]:
            sub_id = int(parts[2])
            if "ticker" in body:
                ok = pipeline.correct_ticker(sub_id, body["ticker"])
                return self._json({"ok": ok})
            if body.get("delete"):
                with db.tx() as con:
                    con.execute("DELETE FROM submissions WHERE id=?", (sub_id,))
                    con.execute("DELETE FROM judgments WHERE submission_id=?", (sub_id,))
                return self._json({"ok": True})
        self._json({"error": "not found"}, 404)


def serve(port: int, block=True):
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    log.info("dashboard on http://localhost:%d", port)
    if block:
        srv.serve_forever()
    else:
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
    return srv
