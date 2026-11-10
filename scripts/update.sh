#!/usr/bin/env bash
# SupaBill — update an existing install to the latest code (Mac or Linux).
#
#   ./update.sh --bench ~/frappe-bench --site staging.local [--ref v1.0.0] [--source /path/to/new/supabill]
#
# Stops if apps/supabill has local changes, backs the site up, updates, migrates, builds and checks health.
set -euo pipefail

BENCH="" SITE="" REF="" SOURCE="" ALLOW_PROD=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --bench) BENCH="$2"; shift 2 ;;
    --site) SITE="$2"; shift 2 ;;
    --ref) REF="$2"; shift 2 ;;
    --source) SOURCE="$2"; shift 2 ;;
    --i-know-this-is-production) ALLOW_PROD=1; shift ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1"; exit 2 ;;
  esac
done
[[ -n "$BENCH" && -n "$SITE" ]] || { echo "Usage: $0 --bench <path> --site <site> [--ref <tag>]"; exit 2; }
cd "$BENCH"
[[ -d apps/supabill/.git ]] || { echo "SupaBill is not installed in $BENCH (run install.sh)"; exit 1; }
if [[ "$SITE" == *"erp.supagigs.cloud"* && $ALLOW_PROD -ne 1 ]]; then
  echo "Refusing to update $SITE (production) without --i-know-this-is-production"; exit 1
fi

APP=apps/supabill
if [[ -n "$(git -C "$APP" status --porcelain --untracked-files=no)" ]]; then
  echo "apps/supabill has local changes. Commit or stash them first:"; git -C "$APP" status --short; exit 1
fi
OLD=$(git -C "$APP" rev-parse --short HEAD)
echo "==> Current version: $OLD"

echo "==> Backing up $SITE"
bench --site "$SITE" backup --with-files

echo "==> Fetching new code"
if [[ -n "$SOURCE" ]]; then
  git -C "$APP" fetch "$SOURCE" "${REF:-HEAD}"
  git -C "$APP" merge --ff-only FETCH_HEAD
else
  git -C "$APP" fetch --tags origin
  if [[ -n "$REF" ]]; then git -C "$APP" checkout --quiet "$REF"; else git -C "$APP" merge --ff-only "@{u}"; fi
fi
NEW=$(git -C "$APP" rev-parse --short HEAD)
echo "   $OLD -> $NEW"

echo "==> Installing Python requirements, migrating, building"
./env/bin/pip install -q -e "$APP"
bench --site "$SITE" migrate
bench build --app supabill
bench --site "$SITE" clear-cache

echo "==> Health check"
bench --site "$SITE" execute supabill.api.session.user_access --kwargs '{"user": "Administrator"}' | grep -q '"has_access": true' \
  && echo "   OK" || { echo "   Health check failed — roll back with: git -C $APP checkout $OLD && bench --site $SITE migrate, or restore the backup"; exit 1; }
echo "Updated to $NEW. Rollback: git -C $APP checkout $OLD && bench --site $SITE migrate && bench build --app supabill"
