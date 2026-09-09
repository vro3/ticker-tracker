# Ticker Tracker

Text a stock screenshot to the group. This watches the group from a Mac that stays on,
reads the ticker and price out of the picture, keeps your note as the "goal", pulls daily
closes from that day forward, and shows everything on one page: who sent what, what they
said would happen, and whether it did.

## How it works

1. A dedicated Apple ID is signed into Messages on the always-on Mac and added to the group text.
2. Every 30 seconds this reads new messages from that Mac's Messages database.
3. Each screenshot goes to Claude, which returns ticker, price shown, and a plain-English
   reading of the caption (direction, target price, time frame).
4. Daily closes and the latest price come from Yahoo Finance via `yfinance`, refreshed
   every 15 minutes, for every ticker ever sent, forever.
5. Calls are scored automatically: a target price counts as hit when the stock trades
   through it; "up"/"down" with no target is scored at the stated horizon, or 30 days.
6. The dashboard is a single page served on port 8787.

Text-only messages that contain `$TICKER` are tracked too, using that day's close as the
starting price.

Each card also shows daily-bar signals: nearest supply and demand zones (fresh / tested, broken zones
are dropped), 8/21 EMA state and days since the cross, position against the 200 EMA, Bollinger %B and
TTM squeeze, RSI(14), and an ATR stop. Alerts for big daily moves, squeezes firing, and targets hit
appear at the top of the page and can optionally be texted to the group. Details in
`docs/planning/ta-signals.md`.

## Install on the Mac mini

```bash
git clone https://github.com/vro3/ticker-tracker.git ~/ticker-tracker
cd ~/ticker-tracker
./install.sh
```

Then do the two one-time steps the installer prints:

- **Full Disk Access** for the Python binary it names (System Settings → Privacy & Security).
- **Screenshot reading**: run `claude` once in Terminal and log in, or put an API key in
  `~/TickerTracker/config.json`.

Check it: `.venv/bin/python -m tracker doctor`

## Config

`~/TickerTracker/config.json`

| key | meaning |
|---|---|
| `people` | map of phone numbers / emails to names, e.g. `{"+16155551234": "Vince"}` |
| `chat_filter` | only watch chats whose name contains this (optional) |
| `timezone` | default `America/Chicago` |
| `port` | dashboard port, default 8787 |
| `vision_backend` | `auto`, `api`, or `cli` |
| `anthropic_api_key` | only needed for `api` |
| `quote_refresh_seconds` | how often to pull near-real-time quotes during market hours, default 30 |
| `alert_move_pct` | a move of this many percent from yesterday's close (and each multiple) raises an alert, default 7 |
| `alert_imessage` | `true` to text alerts to the group from the Messages app on this Mac, default `false` |
| `alert_chat_guid` | the group's `guid` from chat.db, e.g. `any;+;7a12...` (needed for texting) |

Changes take effect on the next poll, no restart needed (except `port`).

## Day to day

- Dashboard: `http://<mini-name>.local:8787` from any device on the same network.
- If a screenshot could not be read confidently, the card turns yellow with a box to type
  the ticker. Nothing is lost.
- Add something by hand: `.venv/bin/python -m tracker add --image pic.png --sender Vince --note "..."`
- Logs: `~/TickerTracker/tracker.log`
- Restart: `launchctl kickstart -k gui/$(id -u)/com.vr.tickertracker`
- Remove: `./uninstall.sh`

## Data

Everything lives in `~/TickerTracker/`: `tracker.db` (SQLite), `screenshots/`, `config.json`.
Back that folder up and you have everything.

## Tests

```bash
.venv/bin/python -m tests.test_imessage
```
