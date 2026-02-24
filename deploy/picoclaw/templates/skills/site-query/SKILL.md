# site-query

## Description
Answer human questions about this site's current state. This is the ONLY
time the LLM is invoked in enterprise (deterministic) mode.

## Triggers
- "Why is {site} low/high/critical?"
- "What happened at {site}?"
- "Status of {site}"
- Any human message via chat gateway

## Implementation
1. GET /api/v1/site-agent/cdc/status/{site_key} (current state)
2. GET /api/v1/site-agent/cdc/triggers/{site_key}?limit=10 (recent triggers)
3. GET /api/v1/inventory/levels?site_key={site_key} (inventory snapshot)
4. Pass all context to LLM for natural language explanation
5. Reply via gateway with explanation and recommended actions
