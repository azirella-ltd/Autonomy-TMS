"""
Autonomy MCP Server — Supply Chain Intelligence as a Service.

Exposes Autonomy's unique capabilities via the Model Context Protocol,
allowing any MCP-compatible agent (Claude Code, Copilot, custom agents,
customer BI tools) to query and interact with the platform.

This is the SERVER side — Autonomy providing capabilities.
The CLIENT side (consuming ERP MCP servers) lives in integrations/mcp/.

Capabilities exposed:
  Phase 1 (read-only, low risk):
    - ask_decision_stream: Query recent agent decisions
    - get_atp_availability: Real-time ATP/CTP check
    - ask_why: Explain agent decision reasoning
    - get_network_status: DAG topology health
    - get_kpi_metrics: BSC metrics, service levels

  Phase 2 (write, AIIO-governed):
    - override_decision: Override an agent decision with reason
    - get_forecast: Conformal forecast (P10/P50/P90)
    - get_supply_plan: Current plan of record

  Phase 3 (compute-heavy):
    - simulate_scenario: What-if scenario evaluation
    - get_governance_status: Policy, override rates, touchless rate
"""
