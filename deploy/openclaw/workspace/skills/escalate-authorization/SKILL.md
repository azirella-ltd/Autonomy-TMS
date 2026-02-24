# escalate-authorization

## Description
Format an authorization request for human review when agents cannot
resolve autonomously. Presents ranked options with Balanced Scorecard impact.

## Triggers
- Agent timeout (>5 min without response)
- Agent confidence < threshold
- Action net_benefit near zero (ambiguous trade-off)
- Policy requires human approval (e.g., PO > $50K)
- System notification: "Authorization escalated for {thread_id}"

## Implementation
1. GET /api/v1/authorization/threads/{thread_id}
   Retrieve full context: requesting agent, target agent, proposed action,
   balanced scorecard, net benefit, SLA deadline.

2. Format ranked options with Balanced Scorecard impact:
   - Option 1: Approve as-is
     Financial: {cost_impact}, Customer: {otif_impact}, Operational: {turns_impact}
     Net benefit: ${net_benefit}
   - Option 2: Counter-propose with modified parameters
     Financial: {alt_cost}, Customer: {alt_otif}, Operational: {alt_turns}
     Net benefit: ${alt_benefit}
   - Option 3: Reject (maintain status quo)
     Financial: $0 change, Customer: {risk_of_no_action}

3. Show why agents could not resolve:
   - Timeout: "Agent {target} did not respond within {sla} minutes"
   - Low confidence: "Agent confidence {score} below threshold {threshold}"
   - Ambiguous: "Net benefit ${benefit} is near decision threshold ${threshold}"

4. Wait for planner response.

5. POST /api/v1/authorization/threads/{thread_id}/resolve
   Body: {
     "decision": "{approve|reject|counter_propose}",
     "reasoning": "{planner_reasoning}",
     "resolved_by": "human_planner"
   }

6. Confirm: "Decision recorded. Your reasoning will improve future
   agent authorization decisions."
