# Paused · 2026-11-18

Ticker Tracker is switched off. Nothing runs on the Mac mini and stocks.drummingdj.com no longer points anywhere.

## What was removed
- The tracker background service (`./uninstall.sh`)
- The Cloudflare tunnel service and the `stocks-tracker` tunnel itself
- `~/.cloudflared/config.yml` was renamed to `config.yml.stocks-tracker.bak` (it pointed at the deleted tunnel)
- Still to tidy if wanted: the `stocks` DNS record under drummingdj.com in the Cloudflare dashboard

## What was kept
- All data in `~/TickerTracker` (tracker.db, screenshots, config.json with the people map)
- Vince's thinkScript export in `~/thinkscripts` (private, not in this repo)
- This repo, including research in docs/planning

## Where it stood
- Records through Oct 22: 51 distinct ideas, 12 up, 38 down, typical result about -12%. Details in the chat summary and in the dashboard data.
- Known data problems: crypto and futures symbols (BTC, ETH, ES, SI, CL, MES) resolve to unrelated stocks on Yahoo; a few misread prices. Fix matching before trusting averages.
- 103 cards from Oct 26 to Nov 18 failed to read because the Claude login had expired. `tools/reextract.py` re-reads them.
- Last bug fixed: threaded yfinance downloads leaked file handles until the 256 limit (commit 34a273d).

## To bring it back
```bash
cd ~/ticker-tracker && git pull && ./install.sh
```
Then: Full Disk Access for the Python path it prints, `claude auth login`, and recreate a tunnel if the public URL is wanted (`cloudflared tunnel create`, `route dns`, `service install`, then add `tunnel run` to the launch agent as before). Re-read the failed cards with:
```bash
.venv/bin/python tools/reextract.py
```
