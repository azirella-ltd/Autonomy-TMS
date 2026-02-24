#!/bin/bash
# DIGEST.sh — Compile buffered warnings into digest (NO LLM)
# Runs every 4 hours via PicoClaw cron.

set -euo pipefail

DIGEST_FILE="${PICOCLAW_WORKSPACE:-/root/.picoclaw/workspace}/digest_buffer.log"
GATEWAY_CHANNEL="${PICOCLAW_ALERT_CHANNEL}"
SITE_KEY="${PICOCLAW_SITE_KEY}"

# Exit if no warnings buffered
if [ ! -s "$DIGEST_FILE" ]; then
  exit 0
fi

WARNING_COUNT=$(wc -l < "$DIGEST_FILE")
DIGEST_BODY=$(cat "$DIGEST_FILE")

picoclaw gateway send "${GATEWAY_CHANNEL}" \
  "${SITE_KEY} Digest -- ${WARNING_COUNT} warnings in last 4h:
${DIGEST_BODY}"

# Clear buffer after sending
> "$DIGEST_FILE"
