#!/bin/bash
# HEARTBEAT.sh — Deterministic CDC monitor (NO LLM)
# Runs every 30 minutes via PicoClaw cron.
#
# At enterprise scale (50+ sites), this script handles 100% of heartbeats
# without any LLM invocation. LLM is reserved for human questions only.

set -euo pipefail

SITE_KEY="${PICOCLAW_SITE_KEY}"
API_BASE="${PICOCLAW_API_BASE}"
AUTH_TOKEN="${PICOCLAW_AUTH_TOKEN}"
GATEWAY_CHANNEL="${PICOCLAW_ALERT_CHANNEL}"
LOG_DIR="${PICOCLAW_WORKSPACE:-/root/.picoclaw/workspace}"

# Step 1: Query CDC status from Autonomy API
CDC_RESPONSE=$(curl -sf -H "Authorization: Bearer ${AUTH_TOKEN}" \
  "${API_BASE}/api/v1/site-agent/cdc/status/${SITE_KEY}" 2>/dev/null)

if [ $? -ne 0 ] || [ -z "$CDC_RESPONSE" ]; then
  picoclaw gateway send "${GATEWAY_CHANNEL}" \
    "CDC check failed for ${SITE_KEY} -- API unreachable"
  echo "$(date -Iseconds) ERROR API_UNREACHABLE" >> "${LOG_DIR}/heartbeat.log"
  exit 1
fi

# Step 2: Extract metrics (jq -- no LLM needed)
SEVERITY=$(echo "$CDC_RESPONSE" | jq -r '.severity // "NORMAL"')
INV_RATIO=$(echo "$CDC_RESPONSE" | jq -r '.inventory_ratio // 1.0')
SERVICE_LEVEL=$(echo "$CDC_RESPONSE" | jq -r '.service_level // 1.0')
TRIGGERED=$(echo "$CDC_RESPONSE" | jq -r '.triggered_conditions // "[]"')

# Step 3: Route by severity (deterministic if/else)
case "$SEVERITY" in
  "CRITICAL")
    picoclaw gateway send "${GATEWAY_CHANNEL}" \
      "CRITICAL -- ${SITE_KEY}: Inv ratio=${INV_RATIO}, SL=${SERVICE_LEVEL}. Conditions: ${TRIGGERED}"
    # POST alert back to Autonomy for tracking
    curl -sf -X POST -H "Authorization: Bearer ${AUTH_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "{\"site_key\":\"${SITE_KEY}\",\"severity\":\"CRITICAL\",\"source\":\"picoclaw\",\"conditions\":${TRIGGERED}}" \
      "${API_BASE}/api/v1/edge-agents/picoclaw/fleet/instances/${SITE_KEY}/heartbeat" \
      > /dev/null 2>&1 || true
    echo "$(date -Iseconds) CRITICAL inv=${INV_RATIO} sl=${SERVICE_LEVEL}" >> "${LOG_DIR}/heartbeat.log"
    ;;
  "WARNING")
    # Buffer warning for next digest
    echo "$(date -Iseconds) WARNING ${SITE_KEY} inv=${INV_RATIO} sl=${SERVICE_LEVEL}" \
      >> "${LOG_DIR}/digest_buffer.log"
    echo "$(date -Iseconds) WARNING inv=${INV_RATIO} sl=${SERVICE_LEVEL}" >> "${LOG_DIR}/heartbeat.log"
    ;;
  *)
    # Normal -- log timestamp only
    echo "$(date -Iseconds) OK" >> "${LOG_DIR}/heartbeat.log"
    ;;
esac

# Keep last 48 entries (24 hours at 30-min intervals)
if [ -f "${LOG_DIR}/heartbeat.log" ]; then
  tail -48 "${LOG_DIR}/heartbeat.log" > "${LOG_DIR}/heartbeat.log.tmp" \
    && mv "${LOG_DIR}/heartbeat.log.tmp" "${LOG_DIR}/heartbeat.log"
fi
