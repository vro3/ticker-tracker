# Overnight build plan · 2026-09-08 (Vince asleep, full autonomy; do not enable group texting; commit+push when green)

## Phase 1 — Features
- [ ] Card grade (green/yellow/red) from tested rules: liquidity, oversold (close<lower BB & RSI14<=30, RSI2<10), down>=7% day, above/below 200 EMA
- [ ] Speculative flag: price < $5 or avg dollar volume < $2M/day
- [ ] Vince scripts: RSI2 reversal (rsi2<10 & close>EMA34 / >90 & <EMA34), buy vs sell volume split + relvol spike, pivot confirmation ladder (5-bar pivot low confirmed by close > pivot bar high; stop=pivot low; add=+0.75 stdev; target)
- [ ] Squeeze bars-since-fire label
## Phase 2 — Reliability
- [ ] Rotating log file; /api/health; doctor checks cloudflared + claude auth + intraday freshness
- [ ] Guard: intraday/quotes with empty ticker list; yfinance exceptions never kill loop; DB busy timeouts
- [ ] Hourly self-check: if last successful poll > 10 min, log ERROR (visible in dashboard health)
- [ ] launchd: ThrottleInterval, both agents KeepAlive verified
## Phase 3 — Tests
- [ ] tests/test_ta.py synthetic bars: ema, rsi, zones, gaps, strat, ftfc, grade
- [ ] tests/test_intraday.py resample buckets
- [ ] tests/test_alerts.py dedupe
- [ ] tests/test_web.py payload builds with temp DB
- [ ] run all + existing test_imessage
## Phase 4 — Audit
- [ ] code-reviewer agent pass; fix findings; rerun tests; browser check public URL; commit; push
## Progress log
- 22:25 Phase 1 done: grade/speculative/rsi2/volume split/pivot ladder wired to payload + cards
- 22:25 Phase 2 done: rotating log, /api/health, heartbeat meta last_poll/last_error, doctor extended
- 22:30 Phase 3: 4 test modules, all pass (tests/run_all.sh)
- 22:30 Phase 4 started: code-reviewer audit running
- 22:27 Phase 4 audit #1: 10 findings, all fixed (POST hardening, payload cache, XSS escape, lock-free network, NaN guards, TTM SMA, gap ordering, port guard, alert per-ticker guard + meta prune). Tests green. Abuse probes return 400/403/413/404 as intended.
- 22:45 Audit #2: 6 findings fixed (LAN/CSRF fail-open, 2 more XSS spots + ingest ticker validation, ingest tx restructure, db init-once, None guards, JS null guards). New tests/test_web_security.py (10 tests). All 5 suites green. Committed.
- 23:05 Audit #4: caption rowid claimed + high-water below caption; vision output coerced (no poison messages); backfill flag only with rows; CLI Read scoped to screenshots dir + tools disallowed; tests for store no-wipe, sent-by-id, coercion, backfill flag. E2E vision re-verified with scoped tools. All suites green.
- 23:20 Audit #5: soft delete + restore cmd, retry cap (3), alerts delivered after tx, intraday fetch outside tx, install.sh mkdir. All suites green. Final commit pushed. DONE.
