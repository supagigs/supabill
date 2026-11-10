#!/usr/bin/env bash
# SupaBill — install onto an existing Frappe v16 bench (Mac or Linux).
#
#   ./install.sh --bench ~/frappe-bench --site staging.local [--source /path/to/supabill | --repo URL] [--branch main]
#
# Safe by design: refuses production-looking sites unless --i-know-this-is-production is given,
# backs the site up before installing, and never deletes anything.
set -euo pipefail

BENCH="" SITE="" SOURCE="" REPO="https://github.com/supagigs/supabill.git" BRANCH="main" ALLOW_PROD=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --bench) BENCH="$2"; shift 2 ;;
    --site) SITE="$2"; shift 2 ;;
    --source) SOURCE="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --i-know-this-is-production) ALLOW_PROD=1; shift ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1"; exit 2 ;;
  esac
done
[[ -n "$BENCH" && -n "$SITE" ]] || { echo "Usage: $0 --bench <path> --site <site> [--source <dir>|--repo <url>]"; exit 2; }
cd "$BENCH"
[[ -d "sites/$SITE" ]] || { echo "Site $SITE not found in $BENCH/sites"; exit 1; }
if [[ "$SITE" == *"erp.supagigs.cloud"* && $ALLOW_PROD -ne 1 ]]; then
  echo "Refusing to install on $SITE (production). Use a staging site first."; exit 1
fi

echo "==> Checking requirements"
NODE_MAJOR=$(node -v | sed 's/v\([0-9]*\).*/\1/')
[[ "$NODE_MAJOR" -ge 24 ]] || { echo "Node 24+ is required by Frappe v16 (found $(node -v))"; exit 1; }
bench version | grep -q "^frappe 16" || { echo "Frappe v16 is required"; bench version; exit 1; }
command -v soffice >/dev/null && echo "   LibreOffice found: PDFs will match the Word template exactly" \
  || echo "   LibreOffice not found: PDFs use the HTML layout (install libreoffice-writer for exact PDFs)"

echo "==> Backing up $SITE"
bench --site "$SITE" backup --with-files

if [[ -d apps/supabill ]]; then
  echo "SupaBill is already in this bench. Use update.sh instead."; exit 1
fi
echo "==> Getting the app"
if [[ -n "$SOURCE" ]]; then
  bench get-app "$SOURCE"
else
  bench get-app --branch "$BRANCH" "$REPO"
fi

echo "==> Installing on $SITE"
bench --site "$SITE" install-app supabill
bench build --app supabill
bench --site "$SITE" clear-cache

echo "==> Health check"
bench --site "$SITE" execute supabill.api.session.user_access --kwargs '{"user": "Administrator"}' | grep -q '"has_access": true' \
  && echo "   OK: SupaBill responds" || { echo "   Health check failed"; exit 1; }
cat <<MSG

Done. Next steps:
  1. Give people the SupaBill User or SupaBill Manager role.
  2. Open /supabill and fill in Settings, Wallets and Clients.
  3. Optional: connect Excel and AllRatesToday (see docs/admin-guide.md).
Rollback: bench --site $SITE uninstall-app supabill  (or restore the backup above).
MSG
