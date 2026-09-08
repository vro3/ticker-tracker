#!/bin/bash
LABEL=com.vr.tickertracker
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Service removed. Data is still in $HOME/TickerTracker (delete it yourself if you want)."
