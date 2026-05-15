"""SCP shim — canonical MCP governance-status tool in Core.

``register(mcp)`` now lives in
``azirella_integrations.mcp.tools.governance`` (lifted 2026-05-16 per
MIGRATION_REGISTER §3.74). **TMS-canonical** — the lifted version
exposes an optional ``config_id`` parameter (advisory; ownership-
verified via ``require_config``) and adds an ``echoed`` block with
input parameters + a ``config_id_enforced`` flag. SCP gains the
optional ``config_id`` argument transparently via this shim.
"""
from azirella_integrations.mcp.tools.governance import register  # noqa: F401


__all__ = ["register"]
