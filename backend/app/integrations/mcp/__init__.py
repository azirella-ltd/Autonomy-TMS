"""
MCP (Model Context Protocol) Integration Layer.

Provides bidirectional MCP client infrastructure for live ERP operations:
- INBOUND: Poll ERP MCP servers for changes (CDC via MCP)
- OUTBOUND: Write-back agent decisions (PO/MO/TO) governed by AIIO mode

Bulk initial extraction is NOT handled here — use per-ERP extractors for that.
"""
