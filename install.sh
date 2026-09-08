#!/bin/bash
# Installs Ticker Tracker on this Mac as an always-on background service.
# Safe to run again; it just refreshes everything.
set -euo pipefail
cd "$(dirname "$0")"
PROJECT="$(pwd)"
LABEL=com.vr.tickertracker
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

echo "→ Python"
if ! command -v python3 >/dev/null; then
  echo "python3 not found. Install Xcode command line tools: xcode-select --install"; exit 1
fi
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
PYTHON="$(cd .venv/bin && pwd -P)/python"
REAL_PYTHON="$(.venv/bin/python -c 'import sys; print(sys._base_executable)')"

echo "→ Home folder and config"
mkdir -p "$HOME/TickerTracker"
.venv/bin/python -c 'from tracker import config; config.ensure_dirs(); print("   ", config.CONFIG_PATH)'

echo "→ Background service"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
sed -e "s|__PYTHON__|$PYTHON|g" -e "s|__PROJECT__|$PROJECT|g" -e "s|__HOME__|$HOME|g" \
  launchd/$LABEL.plist.template > "$PLIST"
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

cat <<MSG

Installed. Two one-time steps remain:

1. Full Disk Access (so it can read Messages):
   System Settings → Privacy & Security → Full Disk Access → (+) → press Cmd-Shift-G and paste:
      $REAL_PYTHON
   Turn it on, then run:  launchctl kickstart -k gui/$(id -u)/$LABEL

2. Screenshot reading (pick one):
   a. Run \`claude\` once in Terminal and log in (uses the Claude subscription), or
   b. Put an API key in $HOME/TickerTracker/config.json under "anthropic_api_key".

Check everything:   .venv/bin/python -m tracker doctor
Dashboard:          http://$(scutil --get LocalHostName 2>/dev/null || hostname).local:8787   (or http://localhost:8787 here)
Logs:               $HOME/TickerTracker/tracker.log
MSG
