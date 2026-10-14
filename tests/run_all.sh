#!/bin/zsh
# Runs every test suite, each in its own process (the app loads the legal data once at startup, so suites cannot share one).
cd "$(dirname "$0")/.."
export LEXBHARAT_ENV=dev
failed=0
for m in test_auth test_editor test_signup; do
  printf "%-14s " "$m"
  out=$(./.venv/bin/python -W ignore -m unittest tests.$m 2>&1)
  if [ $? -eq 0 ]; then echo "$(echo "$out" | grep -E '^Ran ') - OK"; else echo "FAILED"; echo "$out" | tail -25; failed=1; fi
done
exit $failed
