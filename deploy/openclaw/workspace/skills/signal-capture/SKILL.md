# signal-capture

## Description
Capture supply chain signals from planner messages and route to
ForecastAdjustmentTRM for evaluation. Extracts structured signal
data from natural language input across any channel.

## Triggers
- "ACME just announced a 30% expansion"
- "Heard from sales that Q2 demand is going to spike"
- "Supplier Alpha delayed shipment by 2 weeks"
- "Weather forecast: hurricane approaching Gulf Coast"
- "Customer called - they want to double their order"
- Any message containing: forecast, demand, supply, delay, shortage,
  surplus, promotion, disruption, competitor, price change

## Implementation
1. CLASSIFY the message using LLM:
   - source: infer from channel + sender role
   - signal_type: DEMAND_INCREASE, SUPPLY_DISRUPTION, LEAD_TIME_CHANGE, etc.
   - direction: up, down, no_change
   - magnitude_hint: percentage if mentioned, null otherwise
   - product_id: specific product if mentioned
   - site_id: specific site if mentioned
   - time_horizon: timeframe if mentioned

2. VALIDATE extracted fields:
   - product_id must exist: GET /api/v1/products?search={product_name}
   - site_id must exist: GET /api/v1/supply-chain-configs/{id}/sites?search={site_name}
   - If ambiguous, ask sender for clarification

3. SUBMIT to Signal Ingestion API:
   POST /api/v1/signals/ingest
   {
     "source": "{channel_type}",
     "signal_type": "{classified_type}",
     "direction": "{up|down|no_change}",
     "magnitude_hint": {pct_or_null},
     "product_id": "{resolved_id}",
     "site_id": "{resolved_id}",
     "signal_text": "{original_message}",
     "signal_confidence": {0.0-1.0},
     "sender_role": "{planner|sales|customer|external}",
     "channel": "{slack|teams|whatsapp|telegram|email}"
   }

4. Report result:
   - If auto-applied (confidence >= 0.8): "Signal captured and auto-applied.
     Forecast adjusted {direction} by {magnitude}%."
   - If pending review (0.3-0.8): "Signal captured, pending human review.
     Estimated confidence: {confidence}."
   - If rejected (< 0.3): "Signal logged but below confidence threshold.
     Please provide more specific details."
