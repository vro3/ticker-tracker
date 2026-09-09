#!/bin/bash
# Runs every test module. Usage: tests/run_all.sh
cd "$(dirname "$0")/.." || exit 1
fail=0
for t in test_ta test_intraday test_alerts_web test_imessage; do
  out=$(.venv/bin/python -m tests.$t 2>&1); rc=$?
  echo "$out" | tail -1 | sed "s/^/$t: /"
  [ $rc -ne 0 ] && { fail=1; echo "$out" | grep -E "FAIL|Error" | head -5; }
done
exit $fail
