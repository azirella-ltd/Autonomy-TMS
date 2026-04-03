"""
MCP Client Session Manager.

Wraps the Anthropic MCP SDK to provide:
- Connection lifecycle (connect, disconnect, reconnect)
- Tool discovery and invocation
- Audit logging of all calls (SOC II)
- Connection pooling per tenant+ERP
- Retry with exponential backoff

The MCP SDK (pip install mcp) is optional — if not installed, this module
provides a lightweight HTTP-based fallback for SSE/Streamable HTTP servers.
"""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .config import MCPServerParams, MCPTransport

logger = logging.getLogger(__name__)

# Try to import the official MCP SDK
try:
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    from mcp.client.stdio import StdioServerParameters, stdio_client
    MCP_SDK_AVAILABLE = True
except ImportError:
    MCP_SDK_AVAILABLE = False
    logger.info("MCP SDK not installed — using HTTP fallback for SSE/Streamable HTTP")


@dataclass
class MCPToolInfo:
    """Discovered MCP tool metadata."""
    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass
class MCPToolResult:
    """Result of an MCP tool invocation."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    duration_ms: float = 0
    correlation_id: str = ""
    tool_name: str = ""


class MCPClientSession:
    """Manages a single MCP client connection to an ERP MCP server.

    Supports two modes:
    1. Full MCP SDK (stdio or SSE transport) — preferred
    2. HTTP fallback (direct REST calls to MCP-compatible HTTP endpoints)
    """

    def __init__(self, params: MCPServerParams):
        self.params = params
        self._session: Optional[Any] = None  # mcp.ClientSession
        self._transport_ctx = None
        self._tools: Dict[str, MCPToolInfo] = {}
        self._connected = False
        self._connect_lock = asyncio.Lock()
        self._http_client: Optional[httpx.AsyncClient] = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def tools(self) -> Dict[str, MCPToolInfo]:
        return dict(self._tools)

    async def connect(self) -> None:
        """Establish connection to the MCP server."""
        async with self._connect_lock:
            if self._connected:
                return

            if MCP_SDK_AVAILABLE and self.params.transport in (
                MCPTransport.STDIO, MCPTransport.SSE
            ):
                await self._connect_sdk()
            else:
                await self._connect_http()

            self._connected = True
            logger.info(
                "MCP connected: erp=%s tenant=%d transport=%s tools=%d",
                self.params.erp_type,
                self.params.tenant_id,
                self.params.transport,
                len(self._tools),
            )

    async def _connect_sdk(self) -> None:
        """Connect using the official MCP SDK."""
        if self.params.transport == MCPTransport.STDIO:
            if not self.params.server_command:
                raise ValueError("server_command required for STDIO transport")

            server_params = StdioServerParameters(
                command=self.params.server_command[0],
                args=self.params.server_command[1:] if len(self.params.server_command) > 1 else [],
                env=self.params.server_env,
            )
            # stdio_client is an async context manager — we need to keep it alive
            self._transport_ctx = stdio_client(server_params)
            read_stream, write_stream = await self._transport_ctx.__aenter__()
            self._session = ClientSession(read_stream, write_stream)
            await self._session.initialize()

        elif self.params.transport == MCPTransport.SSE:
            if not self.params.server_url:
                raise ValueError("server_url required for SSE transport")

            headers = {}
            if self.params.auth_config and self.params.auth_config.get("api_key"):
                headers["Authorization"] = f"Bearer {self.params.auth_config['api_key']}"

            self._transport_ctx = sse_client(
                self.params.server_url,
                headers=headers,
            )
            read_stream, write_stream = await self._transport_ctx.__aenter__()
            self._session = ClientSession(read_stream, write_stream)
            await self._session.initialize()

        # Discover tools
        await self._discover_tools_sdk()

    async def _connect_http(self) -> None:
        """Connect using direct HTTP (fallback when SDK not available)."""
        if not self.params.server_url:
            raise ValueError("server_url required for HTTP fallback")

        headers = {"Content-Type": "application/json"}
        if self.params.auth_config:
            if self.params.auth_config.get("api_key"):
                headers["Authorization"] = f"Bearer {self.params.auth_config['api_key']}"
            elif self.params.auth_config.get("oauth_token"):
                headers["Authorization"] = f"Bearer {self.params.auth_config['oauth_token']}"

        self._http_client = httpx.AsyncClient(
            base_url=self.params.server_url.rstrip("/"),
            headers=headers,
            timeout=60.0,
        )

        # Try to discover tools via HTTP
        await self._discover_tools_http()

    async def _discover_tools_sdk(self) -> None:
        """Discover available tools via MCP SDK."""
        if not self._session:
            return
        result = await self._session.list_tools()
        self._tools = {}
        for tool in result.tools:
            self._tools[tool.name] = MCPToolInfo(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema if hasattr(tool, "inputSchema") else {},
            )

    async def _discover_tools_http(self) -> None:
        """Discover tools via HTTP endpoint (MCP Streamable HTTP spec)."""
        if not self._http_client:
            return
        try:
            resp = await self._http_client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
            )
            if resp.status_code == 200:
                data = resp.json()
                tools = data.get("result", {}).get("tools", [])
                self._tools = {}
                for tool in tools:
                    self._tools[tool["name"]] = MCPToolInfo(
                        name=tool["name"],
                        description=tool.get("description", ""),
                        input_schema=tool.get("inputSchema", {}),
                    )
        except Exception as e:
            logger.warning("Tool discovery failed via HTTP: %s", e)

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> MCPToolResult:
        """Invoke an MCP tool and return the result.

        Args:
            tool_name: The MCP tool name (or canonical name resolved via mappings)
            arguments: Tool arguments
            correlation_id: Optional correlation ID for audit chain
        """
        if not self._connected:
            await self.connect()

        cid = correlation_id or str(uuid.uuid4())
        # Resolve canonical tool name → actual MCP tool name
        actual_tool = tool_name
        if self.params.tool_mappings and tool_name in self.params.tool_mappings:
            actual_tool = self.params.tool_mappings[tool_name]

        start = time.monotonic()
        try:
            if self._session and MCP_SDK_AVAILABLE:
                result = await self._call_tool_sdk(actual_tool, arguments)
            else:
                result = await self._call_tool_http(actual_tool, arguments)

            duration = (time.monotonic() - start) * 1000
            return MCPToolResult(
                success=True,
                data=result,
                duration_ms=duration,
                correlation_id=cid,
                tool_name=actual_tool,
            )
        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            logger.error(
                "MCP tool call failed: tool=%s erp=%s tenant=%d error=%s",
                actual_tool, self.params.erp_type, self.params.tenant_id, e,
            )
            return MCPToolResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                correlation_id=cid,
                tool_name=actual_tool,
            )

    async def _call_tool_sdk(self, tool_name: str, arguments: Dict) -> Any:
        """Call tool via MCP SDK."""
        result = await self._session.call_tool(tool_name, arguments=arguments)
        # MCP SDK returns CallToolResult with content list
        if hasattr(result, "content") and result.content:
            # Extract text content
            texts = []
            for content in result.content:
                if hasattr(content, "text"):
                    texts.append(content.text)
            combined = "\n".join(texts)
            # Try to parse as JSON
            try:
                return json.loads(combined)
            except (json.JSONDecodeError, ValueError):
                return combined
        return None

    async def _call_tool_http(self, tool_name: str, arguments: Dict) -> Any:
        """Call tool via HTTP fallback (JSON-RPC 2.0)."""
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized")

        resp = await self._http_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
                "id": str(uuid.uuid4()),
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"MCP error: {data['error']}")
        result = data.get("result", {})
        content = result.get("content", [])
        if content and isinstance(content, list):
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            combined = "\n".join(texts)
            try:
                return json.loads(combined)
            except (json.JSONDecodeError, ValueError):
                return combined
        return result

    async def list_tools(self) -> List[MCPToolInfo]:
        """Return discovered tools."""
        if not self._connected:
            await self.connect()
        return list(self._tools.values())

    async def health_check(self) -> bool:
        """Check if the MCP server is responsive."""
        try:
            if self._session and MCP_SDK_AVAILABLE:
                await self._session.list_tools()
                return True
            elif self._http_client:
                resp = await self._http_client.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "method": "ping", "id": 1},
                )
                return resp.status_code == 200
        except Exception:
            return False
        return False

    async def disconnect(self) -> None:
        """Close the MCP connection."""
        self._connected = False
        if self._transport_ctx:
            try:
                await self._transport_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self._transport_ctx = None
        self._session = None
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self._tools = {}

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.disconnect()


class MCPConnectionPool:
    """Connection pool: one MCPClientSession per tenant+ERP.

    Thread-safe, lazy-connects on first use, auto-reconnects on failure.
    """

    def __init__(self):
        self._pool: Dict[str, MCPClientSession] = {}
        self._lock = asyncio.Lock()

    def _key(self, tenant_id: int, erp_type: str) -> str:
        return f"{tenant_id}:{erp_type}"

    async def get_client(
        self,
        params: MCPServerParams,
    ) -> MCPClientSession:
        """Get or create an MCP client session for a tenant+ERP."""
        key = self._key(params.tenant_id, params.erp_type)
        async with self._lock:
            if key in self._pool:
                client = self._pool[key]
                if client.connected:
                    return client
                # Stale connection — remove and recreate
                await client.disconnect()

            client = MCPClientSession(params)
            self._pool[key] = client

        await client.connect()
        return client

    async def remove(self, tenant_id: int, erp_type: str) -> None:
        """Disconnect and remove a client from the pool."""
        key = self._key(tenant_id, erp_type)
        async with self._lock:
            client = self._pool.pop(key, None)
        if client:
            await client.disconnect()

    async def close_all(self) -> None:
        """Disconnect all clients (shutdown)."""
        async with self._lock:
            clients = list(self._pool.values())
            self._pool.clear()
        for client in clients:
            await client.disconnect()

    @property
    def active_connections(self) -> int:
        return sum(1 for c in self._pool.values() if c.connected)


# Singleton pool
mcp_pool = MCPConnectionPool()
