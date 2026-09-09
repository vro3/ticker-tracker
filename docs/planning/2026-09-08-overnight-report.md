# Overnight build report · Sept 8-9, 2026
Written for Vince to read in the morning. Live site: https://stocks.drummingdj.com

## What changed while you slept
1. Card grade. Every card now carries Setup / Watch / Avoid with the reasons under it, built only from the rules that tested well (oversold + liquidity + trend filter). A dashed "speculative" tag marks anything under $5 or thinly traded, because the baseline in that group tested negative.
2. Your own scripts on the cards: RSI(2) reversal vs the 34 EMA, buy-versus-sell volume split with spike flag, and the pivot-confirmation ladder (entry, stop, add, target, active/stopped).
3. Reliability: health footer on the page and /api/health; rotating log; heartbeat and last-error tracking; doctor now checks the Claude login, the service, and the tunnel; the service survives a taken port; messages that fail to record are retried instead of lost; intraday data is never wiped by an empty fetch; alerts survive a bad ticker.
4. Security: the public page can no longer trigger expensive work (refresh/ingest are local-only), request bodies are capped, tickers are validated on both the manual and the screenshot path, every server value is escaped in the page, cross-site posts are refused, and the Claude CLI can only read files inside the screenshots folder with shell/web/write tools disabled.
5. Tests: 5 suites, 40+ tests, including HTTP-level security tests and failure-path tests. Run them any time with tests/run_all.sh.
6. Five independent audit passes, 35+ findings, all fixed and re-tested. Everything committed and pushed to GitHub.
7. The ✕ on a card now hides instead of deleting. `python -m tracker restore` lists hidden cards and brings one back. A message that fails to record three times is skipped instead of blocking the queue forever.

## Not done on purpose
- Texting alerts into the group is still OFF. It is one config flag away (alert_imessage: true). Posting into your group chat is your call.
- No login gate, as you asked. Anyone with the URL can view, hide a card, or fix a ticker. Hiding is reversible, so the worst a stranger can do is tidy up.

## What to glance at
- The dashboard footer should say "Tracker healthy". If it says stalled, run: cd ~/ticker-tracker && .venv/bin/python -m tracker doctor
- Research and numbers: docs/planning/backtest.md, backtest-combos.md, strategy-evidence.md, thinkscript-gap-report.md
