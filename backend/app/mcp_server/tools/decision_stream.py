"""SCP shim — canonical MCP decision-stream tool in Core.

``register(mcp)`` now lives in
``azirella_integrations.mcp.tools.decision_stream`` (lifted 2026-05-16
per MIGRATION_REGISTER §3.74). **TMS-canonical** — the lift fixed a
latent bug on the SCP side where ``DecisionStreamService(db)`` was
called without the required ``tenant_id`` positional argument (the
service constructor needs it). The TMS version also adds
``_session_internal`` cross-plane safety annotations that mark the
freeform conversational response as not-for-parsing by structured
cross-plane callers.

Routing through the shim transparently fixes SCP's broken
DecisionStreamService instantiation.
"""
from azirella_integrations.mcp.tools.decision_stream import register  # noqa: F401


__all__ = ["register"]
