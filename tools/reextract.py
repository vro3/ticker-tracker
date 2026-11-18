"""Re-read screenshots for submissions that failed extraction (status='error'), e.g. after the Claude login expired.

Usage: .venv/bin/python tools/reextract.py [--limit N]
Network and the model call happen outside any DB transaction; each row is updated in its own short write.
Version 1.0 · 2026-11-18
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tracker import config, db, judge, pipeline, prices, vision  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    cfg = config.load()
    with db.tx() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT id, screenshot, note FROM submissions WHERE status='error' AND hidden=0 ORDER BY id")]
    if a.limit:
        rows = rows[:a.limit]
    print(f"{len(rows)} to re-read", flush=True)
    fixed = still_bad = 0
    for i, r in enumerate(rows, 1):
        img = config.SCREENSHOT_DIR / r["screenshot"] if r["screenshot"] else None
        try:
            if img is not None and not img.is_file():
                raise FileNotFoundError(f"screenshot missing: {img.name}")
            data = vision.extract(cfg, img, r["note"] or "")
            if not isinstance(data, dict):
                raise ValueError("extractor did not return an object")
            ticker = pipeline._clean_ticker(data.get("ticker"))
            conf = pipeline._num(data.get("confidence"))
            status = "ok" if ticker and (conf or 0) >= 0.5 else "needs_review"
            err = None
            if status == "ok" and not prices.validate_ticker(ticker):
                status, err = "needs_review", f"Ticker {ticker} not found in market data"
            direction = pipeline._text(data.get("direction"), 10) or "unknown"
            if direction not in ("up", "down", "watch", "unknown"):
                direction = "unknown"
            with db.tx() as con:
                con.execute("""UPDATE submissions SET ticker=?, company=?, price_seen=?, currency=?, goal=?, direction=?,
                               target_price=?, horizon_days=?, confidence=?, extraction_json=?, status=?, error=? WHERE id=?""",
                            (ticker, pipeline._text(data.get("company"), 120), pipeline._num(data.get("price")),
                             pipeline._text(data.get("currency"), 8), pipeline._text(data.get("goal"), 500), direction,
                             pipeline._num(data.get("target_price")), pipeline._int(data.get("horizon_days")), conf,
                             json.dumps(data)[:4000], status, err, r["id"]))
            fixed += status == "ok"
            still_bad += status != "ok"
            print(f"[{i}/{len(rows)}] #{r['id']} -> {ticker} {status}", flush=True)
        except Exception as e:
            still_bad += 1
            with db.tx() as con:
                con.execute("UPDATE submissions SET error=? WHERE id=?", (str(e)[:500], r["id"]))
            print(f"[{i}/{len(rows)}] #{r['id']} still failing: {str(e)[:120]}", flush=True)
            if "log in" in str(e) or "authenticate" in str(e).lower():
                print("Claude login problem; stopping.", flush=True)
                break
        time.sleep(1)
    with db.tx() as con:
        prices.refresh(con)
        judge.judge_all(con)
    print(f"done: {fixed} read ok, {still_bad} need a look", flush=True)


if __name__ == "__main__":
    main()
