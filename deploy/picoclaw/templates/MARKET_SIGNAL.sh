#!/bin/bash
# MARKET_SIGNAL.sh — Deterministic market data signal capture (NO LLM)
# Runs daily via PicoClaw cron. Fetches external data feeds and submits
# structured signals to the Autonomy Signal Ingestion API.

set -euo pipefail

SITE_KEY="${PICOCLAW_SITE_KEY}"
API_BASE="${PICOCLAW_API_BASE}"
AUTH_TOKEN="${PICOCLAW_AUTH_TOKEN}"

# --- Weather (if API key configured) ---
if [ -n "${WEATHER_API_KEY:-}" ] && [ -n "${WEATHER_LOCATION:-}" ]; then
  WEATHER=$(curl -sf "https://api.openweathermap.org/data/2.5/forecast?q=${WEATHER_LOCATION}&appid=${WEATHER_API_KEY}&units=metric" 2>/dev/null || echo "{}")

  # Check for severe weather in next 48h
  SEVERE=$(echo "$WEATHER" | jq '[.list[]? | select(.weather[]?.id < 700 and .weather[]?.id >= 200)] | length' 2>/dev/null || echo "0")

  if [ "$SEVERE" -gt 0 ]; then
    curl -sf -X POST -H "Authorization: Bearer ${AUTH_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "{\"source\":\"weather\",\"signal_type\":\"SUPPLY_DISRUPTION\",\"direction\":\"down\",\"magnitude_hint\":null,\"site_id\":\"${SITE_KEY}\",\"signal_text\":\"Severe weather alert: ${SEVERE} events forecast in next 48h for ${WEATHER_LOCATION}\",\"signal_confidence\":0.6,\"channel\":\"picoclaw_market\"}" \
      "${API_BASE}/api/v1/signals/ingest" > /dev/null 2>&1 || true
  fi
fi

# --- Commodity price index (if configured) ---
if [ -n "${COMMODITY_API_URL:-}" ]; then
  PRICE_DATA=$(curl -sf "${COMMODITY_API_URL}" 2>/dev/null || echo "{}")
  PRICE_CHANGE=$(echo "$PRICE_DATA" | jq -r '.change_pct // 0' 2>/dev/null || echo "0")

  # Signal if price moved more than 5%
  if [ "$(echo "$PRICE_CHANGE > 5 || $PRICE_CHANGE < -5" | bc -l 2>/dev/null || echo 0)" = "1" ]; then
    DIRECTION="up"
    [ "$(echo "$PRICE_CHANGE < 0" | bc -l 2>/dev/null || echo 0)" = "1" ] && DIRECTION="down"

    curl -sf -X POST -H "Authorization: Bearer ${AUTH_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "{\"source\":\"economic_indicator\",\"signal_type\":\"COST_CHANGE\",\"direction\":\"${DIRECTION}\",\"magnitude_hint\":${PRICE_CHANGE},\"site_id\":\"${SITE_KEY}\",\"signal_text\":\"Commodity price change: ${PRICE_CHANGE}%\",\"signal_confidence\":0.7,\"channel\":\"picoclaw_market\"}" \
      "${API_BASE}/api/v1/signals/ingest" > /dev/null 2>&1 || true
  fi
fi
