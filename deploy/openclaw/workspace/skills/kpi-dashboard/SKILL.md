# kpi-dashboard

## Description
Generate a KPI summary digest for the planner.

## Triggers
- "Dashboard"
- "KPI summary"
- "How are we doing?"
- "Status report"
- "Daily digest"

## Implementation
1. GET /api/v1/site-agent/status (all active agents)
2. GET /api/v1/inventory/levels?summary=true
3. GET /api/v1/supply-plan/latest/scorecard
4. Format digest:
   - Service Level: {otif}%
   - Inventory: ${total_value} ({dos} days of supply)
   - Open Exceptions: {count} ({critical} critical)
   - Agent Touchless Rate: {rate}%
   - Pending Human Decisions: {count}
   - Top Risk: {highest_severity_condition}
5. If any metric is in CRITICAL status, highlight it prominently
