# override-decision

## Description
Override an agent recommendation with human reasoning. Feeds into RLHF training loop.

## Triggers
- "Override {decision_id}. Reason: {reason}"
- "Reject recommendation for {order_id} because {reason}"
- "I disagree with {decision}. {reason}"
- "Change the decision to {action} because {reason}"

## Implementation
1. Parse decision_id and reason from message
2. POST /api/v1/site-agent/decisions/{decision_id}/override
   Body: {
     "accepted": false,
     "reason": "{reason}",
     "human_feedback": "{full_message}"
   }
3. Confirm: "Override recorded for {decision_id}. Your reasoning will be
   used to improve future agent decisions."
4. If decision_id not found, search recent decisions:
   GET /api/v1/site-agent/decisions?limit=20
   Ask the planner to clarify which decision they mean.
