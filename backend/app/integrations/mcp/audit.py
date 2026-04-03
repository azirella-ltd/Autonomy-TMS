"""
MCP Audit Logger — SOC II Compliance.

Every MCP tool call (inbound read or outbound write) is logged to
audit.mcp_call_log with:
- Tenant scope
- Direction (inbound/outbound)
- Tool name and arguments hash (no PII in arguments)
- Result summary
- Correlation ID for decision chain tracing
- Duration

Audit table lives in the 'audit' schema alongside pgaudit logs.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import Column, Integer, String, Text, DateTime, Float, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

logger = logging.getLogger(__name__)


class MCPCallLog(Base):
    """Audit log entry for an MCP tool call.

    Extension: SOC II audit trail for MCP operations.
    Lives in audit schema.
    """

    __tablename__ = "mcp_call_log"
    __table_args__ = {"schema": "audit"}

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    config_id = Column(Integer, nullable=True)
    erp_type = Column(String(20), nullable=False)

    # Call metadata
    direction = Column(String(10), nullable=False)  # "inbound" | "outbound"
    tool_name = Column(String(200), nullable=False)
    arguments_hash = Column(String(64), nullable=True)  # SHA-256 of arguments JSON
    arguments_summary = Column(Text, nullable=True)  # Human-readable summary (no PII)
    result_summary = Column(Text, nullable=True)  # Truncated result
    status = Column(String(20), nullable=False)  # "success" | "error" | "timeout"
    error_message = Column(Text, nullable=True)

    # Performance
    duration_ms = Column(Float, nullable=True)

    # Tracing
    correlation_id = Column(String(36), nullable=True, index=True)
    decision_id = Column(Integer, nullable=True)  # FK to powell decision if outbound

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=sql_text("NOW()"))


class MCPAuditLogger:
    """Logs MCP tool calls to audit.mcp_call_log."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_call(
        self,
        tenant_id: int,
        erp_type: str,
        direction: str,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Any,
        status: str,
        duration_ms: float,
        correlation_id: Optional[str] = None,
        config_id: Optional[int] = None,
        decision_id: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Log an MCP tool call to the audit table."""
        try:
            # Hash arguments (don't store raw — may contain credentials)
            args_json = json.dumps(arguments, sort_keys=True, default=str)
            args_hash = hashlib.sha256(args_json.encode()).hexdigest()

            # Summarize arguments (keys only, no values)
            args_summary = ", ".join(f"{k}=<{type(v).__name__}>" for k, v in arguments.items())

            # Summarize result (truncate)
            result_str = str(result)[:500] if result else None

            await self.db.execute(
                sql_text("""
                    INSERT INTO audit.mcp_call_log (
                        tenant_id, config_id, erp_type, direction, tool_name,
                        arguments_hash, arguments_summary, result_summary,
                        status, error_message, duration_ms,
                        correlation_id, decision_id
                    ) VALUES (
                        :tenant_id, :config_id, :erp_type, :direction, :tool_name,
                        :args_hash, :args_summary, :result_summary,
                        :status, :error_message, :duration_ms,
                        :correlation_id, :decision_id
                    )
                """),
                {
                    "tenant_id": tenant_id,
                    "config_id": config_id,
                    "erp_type": erp_type,
                    "direction": direction,
                    "tool_name": tool_name,
                    "args_hash": args_hash,
                    "args_summary": args_summary,
                    "result_summary": result_str,
                    "status": status,
                    "error_message": error_message,
                    "duration_ms": duration_ms,
                    "correlation_id": correlation_id,
                    "decision_id": decision_id,
                },
            )
            await self.db.flush()
        except Exception as e:
            # Audit logging must never break the main flow
            logger.error("Failed to log MCP call: %s", e)
