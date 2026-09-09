"""Command line entry point: python -m tracker <command>."""
import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config, db, imessage, judge, pipeline, prices, web


def setup_logging():
    config.ensure_dirs()
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt,
                        handlers=[logging.StreamHandler(sys.stdout),
                                  RotatingFileHandler(config.LOG_PATH, maxBytes=5_000_000, backupCount=3)])


def cmd_run(args):
    cfg = config.load()
    try:
        web.serve(cfg["port"], block=False)
    except OSError as e:
        logging.getLogger("tracker").error("dashboard port %s unavailable (%s); running without it", cfg["port"], e)
    last_prices = 0
    last_quotes = 0
    last_intraday = 0
    log = logging.getLogger("tracker")
    log.info("running: poll every %ss, prices every %sm, quotes every %ss in market hours, home %s",
             cfg["poll_seconds"], cfg["price_refresh_minutes"], cfg.get("quote_refresh_seconds", 30), config.APP_HOME)
    while True:
        try:
            cfg = config.load()
        except Exception as e:
            log.error("config.json unreadable, keeping last good config: %s", e)
        try:
            pipeline.ingest(cfg)
            with db.tx() as con:
                db.set_meta(con, "last_poll", datetime.now().astimezone().isoformat())
        except Exception as e:
            log.error("ingest failed: %s", e)
            _note_error(e)
        if time.time() - last_prices > cfg["price_refresh_minutes"] * 60:
            try:
                pipeline.refresh_prices()
                with db.tx() as con:
                    db.set_meta(con, "last_price_refresh", datetime.now().isoformat())
            except Exception as e:
                log.error("price refresh failed: %s", e)
                _note_error(e)
            last_prices = last_quotes = time.time()
        elif prices.market_open_now() and time.time() - last_quotes >= cfg.get("quote_refresh_seconds", 30):
            try:
                pipeline.refresh_quotes()
                with db.tx() as con:
                    db.set_meta(con, "last_price_refresh", datetime.now().isoformat())
            except Exception as e:
                log.error("quote refresh failed: %s", e)
                _note_error(e)
            last_quotes = time.time()
        if (prices.market_open_now() or last_intraday == 0) and time.time() - last_intraday >= cfg.get("intraday_refresh_seconds", 300):
            try:
                pipeline.refresh_intraday()
            except Exception as e:
                log.error("intraday refresh failed: %s", e)
                _note_error(e)
            last_intraday = time.time()
        time.sleep(max(5, int(cfg.get("poll_seconds", 30))))


def _note_error(e):
    try:
        with db.tx() as con:
            db.set_meta(con, "last_error", f"{datetime.now().astimezone().isoformat()} {type(e).__name__}: {str(e)[:300]}")
    except Exception:
        pass


def cmd_ingest(args):
    n = pipeline.ingest(config.load())
    print(f"new submissions: {n}")


def cmd_prices(args):
    print(f"tickers refreshed: {pipeline.refresh_prices()}")


def cmd_judge(args):
    with db.tx() as con:
        print(f"judged: {judge.judge_all(con)}")


def cmd_serve(args):
    web.serve(config.load()["port"])


def cmd_add(args):
    """Manually add a screenshot (for testing, or for pictures that did not come through iMessage)."""
    cfg = config.load()
    tz = ZoneInfo(cfg["timezone"])
    sent_at = datetime.fromisoformat(args.when).replace(tzinfo=tz) if args.when else datetime.now(tz)
    image = Path(args.image).expanduser() if args.image else None
    with db.tx() as con:
        override = None
        if args.ticker:
            override = {"ticker": args.ticker, "price": args.price, "goal": args.note or None,
                        "direction": args.direction, "target_price": args.target, "horizon_days": args.horizon,
                        "confidence": 1.0}
        sid = pipeline.record_submission(con, cfg, sent_at=sent_at, sender_handle=args.sender, sender_name=args.sender,
                                         chat_name="manual", image=image, caption=args.note or "", override=override)
        prices.refresh(con)
        judge.judge_all(con)
        row = con.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
    print({k: row[k] for k in ("id", "ticker", "company", "price_seen", "goal", "direction", "target_price",
                               "horizon_days", "confidence", "status", "error")})


def cmd_doctor(args):
    cfg = config.load()
    print(f"home:        {config.APP_HOME}")
    print(f"config:      {config.CONFIG_PATH}")
    print(f"chat.db:     {cfg['chat_db']}")
    try:
        con = imessage.open_chat_db(cfg["chat_db"])
        n = con.execute("SELECT COUNT(*) FROM message").fetchone()[0]
        chats = con.execute("SELECT display_name, chat_identifier FROM chat ORDER BY ROWID DESC LIMIT 5").fetchall()
        con.close()
        print(f"messages:    OK, {n} messages readable")
        for c in chats:
            print(f"  chat: {c['display_name'] or ''} ({c['chat_identifier']})")
    except Exception as e:
        print(f"messages:    FAIL: {e}")
        print("  -> Grant Full Disk Access to the python binary printed by install.sh, then rerun.")
    key = config.api_key(cfg)
    backend = cfg["vision_backend"]
    if backend == "auto":
        backend = "api" if key else "cli"
    print(f"vision:      {backend}" + ("" if backend == "api" else " (Claude Code CLI; run `claude` once to log in)"))
    try:
        ok = prices.validate_ticker("AAPL")
        print(f"market data: {'OK' if ok else 'FAIL'} (AAPL lookup)")
    except Exception as e:
        print(f"market data: FAIL: {e}")
    import shutil, subprocess, urllib.request
    claude = shutil.which("claude") or str(Path.home() / ".local/bin/claude")
    if backend == "cli":
        try:
            st = subprocess.run([claude, "auth", "status"], capture_output=True, text=True, timeout=20).stdout
            print(f"claude cli:  {'logged in' if '\"loggedIn\": true' in st else 'NOT logged in (run: claude auth login)'} ({claude})")
        except Exception as e:
            print(f"claude cli:  FAIL: {e}")
    try:
        with urllib.request.urlopen(f"http://localhost:{cfg['port']}/api/health", timeout=5) as r:
            import json as _j
            h = _j.loads(r.read())
            print(f"service:     {'OK' if h['ok'] else 'STALE'}; last poll {h['poll_age_s']}s ago; last error: {h['last_error'] or 'none'}")
    except Exception as e:
        print(f"service:     not answering on port {cfg['port']} ({e}); start it: launchctl kickstart -k gui/$(id -u)/com.vr.tickertracker")
    tun = shutil.which("cloudflared")
    print(f"tunnel:      {'cloudflared installed' if tun else 'cloudflared not installed'}" +
          (f"; service {'running' if subprocess.run(['pgrep', '-f', 'cloudflared tunnel run'], capture_output=True).returncode == 0 else 'NOT running'}" if tun else ""))
    print(f"dashboard:   http://localhost:{cfg['port']}")


def main():
    setup_logging()
    p = argparse.ArgumentParser(prog="tracker")
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("run", help="poll iMessage, refresh prices, serve dashboard (what launchd runs)").set_defaults(f=cmd_run)
    sp.add_parser("ingest", help="check for new messages once").set_defaults(f=cmd_ingest)
    sp.add_parser("prices", help="refresh prices once").set_defaults(f=cmd_prices)
    sp.add_parser("judge", help="re-score all calls").set_defaults(f=cmd_judge)
    sp.add_parser("serve", help="dashboard only").set_defaults(f=cmd_serve)
    sp.add_parser("doctor", help="check permissions and connectivity").set_defaults(f=cmd_doctor)
    a = sp.add_parser("add", help="add a screenshot by hand")
    a.add_argument("--image")
    a.add_argument("--sender", default="Manual")
    a.add_argument("--note", default="")
    a.add_argument("--when", help="ISO local time, e.g. 2026-08-16T09:30")
    a.add_argument("--ticker", help="skip the screenshot reading step and use this ticker")
    a.add_argument("--price", type=float, help="price seen (with --ticker)")
    a.add_argument("--direction", default="unknown", choices=["up", "down", "watch", "unknown"])
    a.add_argument("--target", type=float)
    a.add_argument("--horizon", type=int, help="days")
    a.set_defaults(f=cmd_add)
    args = p.parse_args()
    args.f(args)


if __name__ == "__main__":
    main()
