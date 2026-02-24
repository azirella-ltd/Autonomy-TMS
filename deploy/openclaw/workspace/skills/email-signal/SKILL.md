# Email Signal Capture

Parse forwarded emails and extract supply chain signals for the ForecastAdjustmentTRM.

## When to Use
- Planner forwards a supplier notification email
- Customer PO change or cancellation email
- Industry newsletter with market-moving data
- Logistics carrier delay notification

## Process
1. Accept forwarded email text (subject + body)
2. Identify sender domain to classify source reliability
3. Extract signal: type, direction, magnitude, affected products/sites
4. Submit via signal-capture skill

## API Flow
```
POST /api/v1/signals/ingest
{
  "source": "email_forward",
  "signal_type": "<classified_type>",
  "direction": "up|down",
  "magnitude_hint": <number_or_null>,
  "site_id": "<site_key>",
  "signal_text": "<extracted_summary>",
  "signal_confidence": <0.0-1.0>,
  "channel": "openclaw_email"
}
```

## Source Reliability
- Known supplier domain → confidence += 0.2
- Known customer domain → confidence += 0.2
- Internal company domain → confidence += 0.1
- Unknown/newsletter → confidence base 0.3

## Signal Type Classification
- Force majeure, shutdown, strike → SUPPLY_DISRUPTION
- PO increase, new order, forecast raise → DEMAND_SURGE
- Price increase, tariff, surcharge → COST_CHANGE
- Recall, defect, non-conformance → QUALITY_ISSUE
- Delay, port congestion, weather → LEAD_TIME_CHANGE

## Output Format
Summarize the extracted signal before submission. Include:
- Original sender and subject
- Classified signal type and direction
- Confidence score with reasoning
- Affected products/sites if identifiable
