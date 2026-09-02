#!/bin/bash
# =============================================================================
# RankBuilder CRM — Frontend Deploy Script (hardened)
# =============================================================================
# Builds the React frontend and deploys it to the nginx web root with CORRECT
# permissions, eliminating the blank-page bug where the assets/ dir lost its
# execute bit (nginx then 403s the JS bundle).
#
# Run ON THE VPS (as root) where the CRM runs.
#
# The bug this prevents: a plain `cp -r dist/*` can produce an assets/ dir with
# mode drw-r--r-- (no x). nginx workers run as an unprivileged user and need
# r-x on every directory to serve the hashed JS bundle; without the x bit the
# browser loads index.html (200) but the JS returns 403 -> blank white page.
#
# This script builds, copies, then EXPLICITLY re-applies safe perms:
#   dirs  = 755 (drwxr-xr-x)  -> r-x so nginx can traverse
#   files = 644 (-rw-r--r--)  -> readable
#   owner = www-data          -> matches nginx expectations
#
# Usage (on VPS):
#   /root/deploy-crm-frontend.sh
#
# Optional env overrides:
#   FRONTEND_DIR   (default /root/rankbuilder/crm/frontend)
#   WEB_ROOT       (default /var/www/crm-frontend)
#   RUN_BUILD      (1 = npm run build first; 0 = just copy the existing dist/)
# =============================================================================
set -euo pipefail

FRONTEND_DIR="${FRONTEND_DIR:-/root/rankbuilder/crm/frontend}"
WEB_ROOT="${WEB_ROOT:-/var/www/crm-frontend}"
RUN_BUILD="${RUN_BUILD:-1}"
APP_NAME="RankBuilder CRM frontend"

log()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
pass() { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
err()  { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; }

[ -d "$FRONTEND_DIR" ] || { err "Frontend dir not found: $FRONTEND_DIR"; exit 1; }

# ── 1. Build (if requested) ───────────────────────────────────────────────
if [ "$RUN_BUILD" = "1" ]; then
  log "Building $APP_NAME..."
  (
    cd "$FRONTEND_DIR"
    if [ ! -d node_modules ]; then
      log "Installing npm deps (first build)..."
      npm ci --silent || npm install --silent
    fi
    npm run build
  )
  pass "Build complete -> $FRONTEND_DIR/dist"
fi

[ -d "$FRONTEND_DIR/dist" ] || { err "No dist/ found (build failed or RUN_BUILD=0 with no prior build)"; exit 1; }

# ── 2. Copy to web root (preserve, then fix perms) ────────────────────────
log "Deploying to $WEB_ROOT ..."
mkdir -p "$WEB_ROOT"

# Staging copy: rsync if available (cleaner), else cp -r. Use --delete to keep
# the web root in sync with the built output (removes stale hashed assets).
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --checksum "$FRONTEND_DIR/dist/" "$WEB_ROOT/" 2>/dev/null \
    || rsync -a --delete "$FRONTEND_DIR/dist/" "$WEB_ROOT/"
else
  # Fallback: copy into a temp dir so we never leave a half-copied web root.
  TMP_ROOT="${WEB_ROOT}.tmp.$$"
  rm -rf "$TMP_ROOT"
  mkdir -p "$TMP_ROOT"
  cp -r "$FRONTEND_DIR/dist/." "$TMP_ROOT/"
  rm -rf "$WEB_ROOT"
  mv "$TMP_ROOT" "$WEB_ROOT"
fi

# Also sync the help markdown (served at /help/agent|admin by nginx location).
for f in help-agent.md help-admin.md; do
  if [ -f "$FRONTEND_DIR/$f" ]; then
    cp "$FRONTEND_DIR/$f" "$WEB_ROOT/" 2>/dev/null || true
  fi
done

# ── 3. HARDEN: explicit safe permissions (THE KEY FIX) ────────────────────
log "Setting correct permissions on $WEB_ROOT ..."
find "$WEB_ROOT" -type d -exec chmod 755 {} \;
find "$WEB_ROOT" -type f -exec chmod 644 {} \;
chown -R www-data:www-data "$WEB_ROOT"
# Ensure the web root itself is traversable
chmod 755 "$WEB_ROOT"

pass "Permissions: dirs=755 (drwxr-xr-x), files=644 (-rw-r--r--), owner=www-data"

# ── 4. Verify ──────────────────────────────────────────────────────────────
log "Verifying served assets over HTTPS..."
DOMAIN="dashboard.fortressblinds.co.za"
# Pick the JS bundle referenced by the freshly deployed index.html
JS=$(grep -oE '/assets/[^"]+\.js' "$WEB_ROOT/index.html" | head -1)
if [ -n "$JS" ]; then
  CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "https://${DOMAIN}${JS}" 2>/dev/null || echo "000")
  echo "  $JS -> HTTP $CODE"
  if [ "$CODE" = "200" ]; then
    pass "JS bundle serves correctly (was the 403 blank-page bug)."
  else
    err "JS bundle returned HTTP $CODE — check nginx + permissions."
    exit 1
  fi
else
  err "No JS bundle reference found in index.html"
  exit 1
fi

log "$APP_NAME deployed + hardened ✅"
