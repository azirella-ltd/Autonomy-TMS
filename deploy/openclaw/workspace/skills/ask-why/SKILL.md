# ask-why

## Description
Get agent reasoning for a specific decision with full context-aware explanation.

## Triggers
- "Why did you recommend {action}?"
- "Explain decision {decision_id}"
- "Ask why for {order_id}"
- "Why is the agent suggesting {action}?"

## Implementation
1. GET /api/v1/planning-cascade/trm-decision/{decision_id}/ask-why?level=NORMAL
2. Response contains ContextAwareExplanation with:
   - authority: agent classification (UNILATERAL/REQUIRES_AUTH/ADVISORY)
   - guardrails: CDC threshold status (WITHIN/APPROACHING/EXCEEDED) per metric
   - attribution: top-5 feature importances from gradient saliency
   - counterfactuals: nearest threshold boundaries that would change the outcome
   - summary + explanation at requested verbosity
3. Format natural language explanation:
   - "The deterministic engine found {shortage} units shortage for {product} at {site}."
   - "The TRM model (confidence: {confidence}) suggested {action}."
   - "Top driver: {top_feature} ({importance}%). {guardrail_summary}."
   - "Impact: {fill_rate}% fill rate, estimated cost ${cost}."
4. Fallback: GET /api/v1/site-agent/decisions/{decision_id} for legacy format
