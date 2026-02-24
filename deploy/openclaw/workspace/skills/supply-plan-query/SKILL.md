# supply-plan-query

## Description
Query the current supply plan for a product-site combination.

## Triggers
- "Show me the supply plan for {product} at {site}"
- "What's the plan for {product}?"
- "Supply plan status"
- "What are we ordering for {product}?"

## Implementation
1. Authenticate: POST /api/v1/auth/login (use cached JWT)
2. Query: GET /api/v1/supply-plan?product={product}&site={site}
3. Format response with:
   - Demand: gross requirements by period
   - On-hand: current inventory level
   - Safety stock: target level and policy type
   - Planned orders: PO/TO/MO with timing and quantity
   - OTIF forecast: expected service level
4. If no results, suggest checking config_id or product name spelling
5. If multiple matches, list options and ask the planner to clarify
