# atp-check

## Description
Check Available-to-Promise for an order.

## Triggers
- "Can we promise {qty} of {product} at {site} by {date}?"
- "ATP check for order {order_id}"
- "What can we ship?"
- "Check availability for {product}"

## Implementation
1. POST /api/v1/site-agent/atp/check
   Body: {
     "order_id": "{order_id}",
     "product_id": "{product}",
     "site_key": "{site}",
     "requested_qty": {qty},
     "priority": {priority}
   }
2. Return: promised_qty, promise_date, source (deterministic vs trm_adjusted), confidence
3. If shortage, explain:
   "Only {available} of {requested} available. TRM suggests: {explanation}"
4. If TRM adjusted the result, show both deterministic and TRM recommendations
