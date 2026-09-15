#!/bin/bash
# =============================================================================
# RankBuilder — Coolify redeploy trigger + verify (run ON THE VPS)
# =============================================================================
# Triggered by GitHub Actions (deploy-container.yml) or manually. Calls the
# local Coolify API (localhost, so the token never leaves the box), polls the
# deployment to completion, then verifies the public health endpoint.
#
# Token: created 2026-09-14, stored root-only at /root/.coolify-agent-token.
#   (Sanctum stores a hash in the DB; the plaintext lives only in this file.)
#
# Usage (on VPS):
#   bash /root/scripts/rankbuilder-redeploy.sh
# =============================================================================
set -euo pipefail

TOKEN_FILE="/root/.coolify-agent-token"
API="http://localhost:8000/api/v1"
UUID="y3b4wzlu322g0xc7rwdshr6k"          # RankBuilder app (Coolify)
HEALTH_URL="https://rankbuilder.fortressblinds.co.za/health"

[ -r "$TOKEN_FILE" ] || { echo "ERROR: $TOKEN_FILE missing"; exit 1; }
TOKEN=$(cat "$TOKEN_FILE")

echo "=== Triggering deploy for $UUID ==="
# Coolify v4.3.19+: /deploy is a POST endpoint (GET returns
# "This endpoint has changed to a POST request").
RESP=$(curl -s --max-time 30 -X POST -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"uuid\":\"$UUID\"}" \
    "$API/deploy")
echo "$RESP"

DEP_UUID=$(echo "$RESP" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d['deployments'][0]['deployment_uuid'])" \
    2>/dev/null || true)
if [ -z "$DEP_UUID" ]; then
    echo "ERROR: no deployment_uuid in response"
    exit 1
fi
echo "=== deployment_uuid: $DEP_UUID ==="

STATUS=""
for i in $(seq 1 50); do
    STATUS=$(curl -s --max-time 15 -H "Authorization: Bearer $TOKEN" \
        "$API/deployments/$DEP_UUID" | python3 -c \
        "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || true)
    echo "[$i] status=$STATUS"
    case "$STATUS" in
        finished)  echo "=== DEPLOY FINISHED ==="; break ;;
        failed|cancelled) echo "ERROR: deploy $STATUS"; exit 1 ;;
    esac
    sleep 15
done

if [ "$STATUS" != "finished" ]; then
    echo "ERROR: timed out waiting for deploy"
    exit 1
fi

echo "=== Verifying public health endpoint ==="
for i in $(seq 1 12); do
    CODE=$(curl -s --max-time 10 -o /dev/null -w "%{http_code}" "$HEALTH_URL" || echo 000)
    echo "[$i] health=$CODE"
    [ "$CODE" = "200" ] && { echo "=== HEALTH OK ==="; exit 0; }
    sleep 10
done

echo "ERROR: health endpoint not 200 after deploy"
exit 1
