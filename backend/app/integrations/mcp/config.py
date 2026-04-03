"""
MCP Server Configuration.

Per-tenant, per-ERP configuration for connecting to external MCP servers.
Configurations are stored in the DB (mcp_server_config table) and loaded
at scheduler execution time.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.base import Base

logger = logging.getLogger(__name__)


class MCPTransport(str, Enum):
    """Transport mechanism for MCP server communication."""
    STDIO = "stdio"    # Local subprocess (npx, python -m)
    SSE = "sse"        # Server-Sent Events over HTTP
    STREAMABLE_HTTP = "streamable_http"  # HTTP with streaming (MCP 2025+)


class ERPType(str, Enum):
    """Supported ERP types for MCP integration."""
    SAP_S4 = "sap_s4"
    SAP_B1 = "sap_b1"
    D365 = "d365"
    ODOO = "odoo"
    INFOR = "infor"
    NETSUITE = "netsuite"


class MCPServerConfig(Base):
    """Persistent MCP server configuration per tenant+ERP.

    Extension: Platform-specific model for MCP server connectivity.
    Not part of the AWS SC data model.
    """

    __tablename__ = "mcp_server_config"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    erp_type = Column(String(20), nullable=False)  # ERPType value

    # Transport
    transport = Column(String(30), nullable=False, default="sse")

    # STDIO transport: command to launch MCP server subprocess
    # e.g. ["npx", "-y", "sap-odata-mcp-server"] or ["python", "-m", "mcp_server_odoo"]
    server_command = Column(JSON, nullable=True)

    # SSE / Streamable HTTP transport: server URL
    # e.g. "http://mcp-sap-server:3000/sse"
    server_url = Column(String(500), nullable=True)

    # Authentication (encrypted at rest — column-level encryption)
    # Structure varies by ERP:
    #   SAP: {ashost, sysnr, client, user, password, odata_base_url, ...}
    #   Odoo: {url, database, api_key}
    #   D365: {tenant_id_azure, client_id, client_secret, environment}
    auth_config_encrypted = Column(Text, nullable=True)

    # Environment variables to pass to STDIO server subprocess
    # e.g. {"SAP_BASE_URL": "https://...", "SAP_CLIENT": "100"}
    server_env = Column(JSON, nullable=True)

    # Tool name mappings: canonical name → actual MCP tool name
    # e.g. {"get_materials": "sap_odata_query_A_Product"}
    # If null, adapter defaults are used
    tool_mappings = Column(JSON, nullable=True)

    # Polling configuration
    poll_interval_seconds = Column(Integer, nullable=False, default=300)  # 5 min
    enabled = Column(Boolean, nullable=False, default=True)

    # Status
    is_validated = Column(Boolean, nullable=False, default=False)
    last_validated_at = Column(DateTime, nullable=True)
    last_poll_at = Column(DateTime, nullable=True)
    validation_message = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)


@dataclass
class MCPServerParams:
    """Runtime-resolved MCP server parameters (not persisted).

    Built from MCPServerConfig DB row + decrypted auth.
    """
    erp_type: str
    transport: str
    tenant_id: int
    server_command: Optional[List[str]] = None
    server_url: Optional[str] = None
    server_env: Optional[Dict[str, str]] = None
    auth_config: Optional[Dict[str, Any]] = None
    tool_mappings: Optional[Dict[str, str]] = None
    poll_interval_seconds: int = 300


async def get_mcp_config(
    db: AsyncSession,
    tenant_id: int,
    erp_type: str,
) -> Optional[MCPServerConfig]:
    """Load MCP server config for a tenant + ERP type."""
    result = await db.execute(
        select(MCPServerConfig).where(
            MCPServerConfig.tenant_id == tenant_id,
            MCPServerConfig.erp_type == erp_type,
            MCPServerConfig.enabled.is_(True),
        )
    )
    return result.scalars().first()


async def list_mcp_configs(
    db: AsyncSession,
    tenant_id: int,
) -> List[MCPServerConfig]:
    """List all MCP server configs for a tenant."""
    result = await db.execute(
        select(MCPServerConfig).where(
            MCPServerConfig.tenant_id == tenant_id,
        ).order_by(MCPServerConfig.erp_type)
    )
    return list(result.scalars().all())
