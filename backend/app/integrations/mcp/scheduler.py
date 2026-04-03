"""
MCP Scheduler Integration.

Bridges MCP live operations into the existing APScheduler infrastructure.
Registers per-tenant MCP polling jobs that:
1. Connect to ERP MCP server
2. Poll for changes since last sync
3. Route through Context Engine
4. Emit HiveSignals for TRM consumption

Also provides the write-back executor that processes TRM decisions
and sends them to ERP via MCP (governed by AIIO mode).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from .adapters.sap_s4 import SAPS4MCPAdapter, SAP_ENTITY_SETS
from .audit import MCPAuditLogger
from .client import MCPConnectionPool, MCPToolResult, mcp_pool
from .config import MCPServerConfig, MCPServerParams, get_mcp_config, list_mcp_configs
from .context_engine import ContextEngine
from .writeback_service import MCPWritebackService

logger = logging.getLogger(__name__)


def _resolve_adapter(erp_type: str, client):
    """Resolve the MCP adapter for an ERP type."""
    if erp_type == "sap_s4":
        return SAPS4MCPAdapter(client)
    elif erp_type == "odoo":
        from .adapters.odoo import OdooMCPAdapter
        return OdooMCPAdapter(client)
    elif erp_type == "d365":
        from .adapters.d365 import D365MCPAdapter
        return D365MCPAdapter(client)
    else:
        raise ValueError(f"No MCP adapter for ERP type: {erp_type}")


def _config_to_params(config: MCPServerConfig) -> MCPServerParams:
    """Convert DB config to runtime params."""
    return MCPServerParams(
        erp_type=config.erp_type,
        transport=config.transport,
        tenant_id=config.tenant_id,
        server_command=config.server_command,
        server_url=config.server_url,
        server_env=config.server_env,
        auth_config=None,  # TODO: decrypt auth_config_encrypted
        tool_mappings=config.tool_mappings,
        poll_interval_seconds=config.poll_interval_seconds,
    )


async def execute_mcp_poll(
    db: AsyncSession,
    tenant_id: int,
    config_id: int,
    erp_type: str,
    signal_buses: Optional[Dict] = None,
    ws_broadcast_fn=None,
) -> Dict[str, Any]:
    """Execute a single MCP CDC poll cycle.

    Called by APScheduler on the configured interval.

    Args:
        db: Async DB session
        tenant_id: Tenant scope
        config_id: Supply chain config ID
        erp_type: ERP type to poll
        signal_buses: Site HiveSignalBus instances
        ws_broadcast_fn: WebSocket broadcast function

    Returns:
        Summary of changes detected
    """
    # Load MCP config
    mcp_config = await get_mcp_config(db, tenant_id, erp_type)
    if not mcp_config:
        logger.debug("No MCP config for tenant=%d erp=%s", tenant_id, erp_type)
        return {"status": "no_config"}

    if not mcp_config.enabled:
        return {"status": "disabled"}

    params = _config_to_params(mcp_config)

    # Get last poll timestamp
    since = mcp_config.last_poll_at or datetime(2020, 1, 1, tzinfo=timezone.utc)

    try:
        # Connect to MCP server
        client = await mcp_pool.get_client(params)

        # Get adapter and poll for changes
        adapter = _resolve_adapter(erp_type, client)
        raw_changes = await adapter.poll_changes(since=since)

        if not raw_changes:
            # Update last_poll_at even if no changes
            await _update_last_poll(db, mcp_config.id)
            return {"status": "no_changes"}

        # Route through Context Engine
        context_engine = ContextEngine(
            db=db,
            signal_buses=signal_buses or {},
            ws_broadcast_fn=ws_broadcast_fn,
        )

        entity_specs = SAP_ENTITY_SETS if erp_type == "sap_s4" else {}
        summary = await context_engine.process_inbound(
            erp_type=erp_type,
            changes=raw_changes,
            config_id=config_id,
            tenant_id=tenant_id,
            entity_specs=entity_specs,
        )

        # Update last_poll_at
        await _update_last_poll(db, mcp_config.id)
        await db.commit()

        logger.info(
            "MCP poll complete: tenant=%d erp=%s entities=%d",
            tenant_id, erp_type, len(summary),
        )
        return {"status": "success", "summary": summary}

    except Exception as e:
        logger.error(
            "MCP poll failed: tenant=%d erp=%s error=%s",
            tenant_id, erp_type, e,
        )
        # Log to audit
        audit = MCPAuditLogger(db)
        await audit.log_call(
            tenant_id=tenant_id,
            erp_type=erp_type,
            direction="inbound",
            tool_name="mcp_poll",
            arguments={"since": since.isoformat()},
            result=None,
            status="error",
            duration_ms=0,
            error_message=str(e),
            config_id=config_id,
        )
        await db.commit()
        return {"status": "error", "error": str(e)}


async def execute_mcp_writeback(
    db: AsyncSession,
    tenant_id: int,
    config_id: int,
    erp_type: str,
    decision_id: int,
    decision_type: str,
    decision_data: Dict[str, Any],
    aiio_mode: str,
    ws_broadcast_fn=None,
) -> Dict[str, Any]:
    """Execute a write-back of a TRM decision to ERP via MCP.

    Called when a TRM decision is ACTIONED and the tenant has MCP configured.

    Returns:
        Result summary
    """
    mcp_config = await get_mcp_config(db, tenant_id, erp_type)
    if not mcp_config:
        return {"status": "no_config"}

    params = _config_to_params(mcp_config)

    try:
        client = await mcp_pool.get_client(params)
        writeback = MCPWritebackService(db, ws_broadcast_fn)

        result = await writeback.execute_decision(
            decision_id=decision_id,
            decision_type=decision_type,
            decision_data=decision_data,
            aiio_mode=aiio_mode,
            mcp_client=client,
            tenant_id=tenant_id,
            config_id=config_id,
        )

        await db.commit()

        return {
            "status": "success" if result.executed else "held",
            "executed": result.executed,
            "held_for_approval": result.held_for_approval,
            "erp_reference": result.erp_reference,
            "error": result.error,
        }

    except Exception as e:
        logger.error(
            "MCP write-back failed: tenant=%d decision=%d error=%s",
            tenant_id, decision_id, e,
        )
        return {"status": "error", "error": str(e)}


async def register_mcp_jobs(scheduler_service, db: AsyncSession) -> int:
    """Register MCP polling jobs for all tenants with MCP configs.

    Called at application startup to set up APScheduler jobs.

    Returns:
        Number of jobs registered
    """
    count = 0
    try:
        # Query all enabled MCP configs
        result = await db.execute(
            sql_text("""
                SELECT msc.id, msc.tenant_id, msc.erp_type, msc.poll_interval_seconds,
                       sc.id as config_id
                FROM mcp_server_config msc
                JOIN supply_chain_configs sc ON sc.tenant_id = msc.tenant_id AND sc.is_active = true
                WHERE msc.enabled = true
            """)
        )
        configs = result.fetchall()

        for row in configs:
            job_id = f"mcp_poll_{row.tenant_id}_{row.erp_type}"
            interval = row.poll_interval_seconds or 300

            scheduler_service.add_interval_job(
                func=_mcp_poll_wrapper,
                job_id=job_id,
                seconds=interval,
                kwargs={
                    "tenant_id": row.tenant_id,
                    "config_id": row.config_id,
                    "erp_type": row.erp_type,
                },
                replace_existing=True,
            )
            count += 1
            logger.info(
                "Registered MCP poll job: %s (every %ds)",
                job_id, interval,
            )

    except Exception as e:
        logger.warning("Could not register MCP jobs (table may not exist yet): %s", e)

    return count


async def _mcp_poll_wrapper(tenant_id: int, config_id: int, erp_type: str):
    """Wrapper for APScheduler — creates DB session and calls execute_mcp_poll."""
    from app.db.session import async_session_factory

    async with async_session_factory() as db:
        await execute_mcp_poll(
            db=db,
            tenant_id=tenant_id,
            config_id=config_id,
            erp_type=erp_type,
        )


async def _update_last_poll(db: AsyncSession, config_id: int) -> None:
    """Update last_poll_at on the MCP server config."""
    await db.execute(
        sql_text("""
            UPDATE mcp_server_config
            SET last_poll_at = NOW()
            WHERE id = :config_id
        """),
        {"config_id": config_id},
    )
