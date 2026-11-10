#!/usr/bin/env bash
# Runs every SupaBill browser test against a site. Needs demo data and the ui.* users:
#   bench --site <site> execute supabill.supabill.tests.demo_data.load
#   bench --site <site> execute supabill.supabill.tests.demo_data.ui_users
# Usage: SB_BASE=http://site.local:8002 ./run_all.sh <screenshot-dir>
set -u
OUT="${1:-./shots}"; mkdir -p "$OUT"; cd "$(dirname "$0")"
fail=0
for t in smoke invoice setup register edf wallet_import invoice_import; do
  echo "== $t"; node "$t.cjs" "$OUT" || fail=1
done
exit $fail
