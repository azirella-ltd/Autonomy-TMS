"""
Edge Agent Management API

Endpoints for managing PicoClaw fleet, OpenClaw gateway, signal ingestion,
and security audit for edge agent integrations.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/edge-agents", tags=["Edge Agents"])

# ============================================================================
# Pydantic Models
# ============================================================================

class PicoClawInstance(BaseModel):
    site_key: str
    site_name: Optional[str] = None
    site_type: Optional[str] = None
    region: Optional[str] = None
    mode: str = "deterministic"
    status: str = "STALE"
    last_heartbeat: Optional[datetime] = None
    uptime_pct: Optional[float] = None
    memory_mb: Optional[float] = None
    inventory_ratio: Optional[float] = None
    service_level: Optional[float] = None
    demand_deviation: Optional[float] = None

class PicoClawRegister(BaseModel):
    site_key: str
    site_name: Optional[str] = None
    site_type: Optional[str] = None
    region: Optional[str] = None
    mode: str = "deterministic"
    alert_channel: Optional[str] = None
    heartbeat_interval_min: int = 30

class ServiceAccountCreate(BaseModel):
    name: str
    scope: str = "site"
    site_key: Optional[str] = None

class OpenClawConfig(BaseModel):
    provider: str = "vllm"
    model: str = "qwen3-8b"
    api_base: str = "http://localhost:8001/v1"
    api_key: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.1

class SignalApproval(BaseModel):
    magnitude_override: Optional[float] = None
    reason: Optional[str] = None

class SignalRejection(BaseModel):
    reason: str

class SourceReliabilityUpdate(BaseModel):
    weight: float = Field(ge=0.0, le=1.0)

class ChecklistUpdate(BaseModel):
    checked: bool


# ============================================================================
# PicoClaw Fleet Management
# ============================================================================

@router.get("/picoclaw/fleet/summary")
async def get_fleet_summary():
    """Get fleet-wide summary of PicoClaw instances."""
    # TODO: Query actual PicoClaw fleet status from database/service
    return {
        "total": 0,
        "healthy": 0,
        "warning": 0,
        "critical": 0,
        "stale": 0,
        "last_updated": datetime.utcnow().isoformat(),
    }


@router.get("/picoclaw/fleet/instances")
async def get_fleet_instances(
    status: Optional[str] = Query(None, description="Filter by status"),
    site_type: Optional[str] = Query(None, description="Filter by site type"),
    region: Optional[str] = Query(None, description="Filter by region"),
):
    """Get all PicoClaw instances with optional filters."""
    # TODO: Query database for registered PicoClaw instances
    return []


@router.get("/picoclaw/fleet/instances/{site_key}")
async def get_instance(site_key: str):
    """Get details for a specific PicoClaw instance."""
    # TODO: Look up instance by site_key
    raise HTTPException(status_code=404, detail=f"Instance {site_key} not found")


@router.post("/picoclaw/fleet/instances")
async def register_instance(data: PicoClawRegister):
    """Register a new PicoClaw instance."""
    # TODO: Create instance record in database
    return {
        "site_key": data.site_key,
        "status": "registered",
        "message": f"PicoClaw instance {data.site_key} registered successfully",
    }


@router.put("/picoclaw/fleet/instances/{site_key}")
async def update_instance(site_key: str, data: Dict[str, Any]):
    """Update PicoClaw instance configuration."""
    # TODO: Update instance configuration
    return {"site_key": site_key, "status": "updated"}


@router.delete("/picoclaw/fleet/instances/{site_key}")
async def remove_instance(site_key: str):
    """Remove a PicoClaw instance."""
    # TODO: Soft-delete instance
    return {"site_key": site_key, "status": "removed"}


@router.get("/picoclaw/fleet/instances/{site_key}/heartbeats")
async def get_heartbeats(
    site_key: str,
    limit: int = Query(24, ge=1, le=100),
):
    """Get heartbeat history for a PicoClaw instance."""
    # TODO: Query heartbeat log
    return []


@router.get("/picoclaw/fleet/instances/{site_key}/alerts")
async def get_site_alerts(
    site_key: str,
    limit: int = Query(20, ge=1, le=100),
):
    """Get CDC alerts for a specific site."""
    # TODO: Query alert log for site
    return []


@router.get("/picoclaw/fleet/alerts")
async def get_fleet_alerts(
    severity: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Get alerts across all PicoClaw instances."""
    # TODO: Query all fleet alerts
    return []


@router.post("/picoclaw/fleet/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    """Acknowledge a CDC alert."""
    # TODO: Mark alert as acknowledged
    return {"alert_id": alert_id, "acknowledged": True}


@router.post("/picoclaw/fleet/instances/{site_key}/digest")
async def force_send_digest(site_key: str):
    """Force send buffered warning digest for a site."""
    # TODO: Trigger digest send
    return {"site_key": site_key, "digest_sent": True}


# ---- Service Accounts ----

@router.get("/picoclaw/service-accounts")
async def get_service_accounts():
    """Get all PicoClaw service accounts."""
    # TODO: Query service accounts
    return []


@router.post("/picoclaw/service-accounts")
async def create_service_account(data: ServiceAccountCreate):
    """Create a new service account for PicoClaw authentication."""
    # TODO: Generate JWT service account
    return {
        "id": "sa-new",
        "name": data.name,
        "scope": data.scope,
        "token_masked": "****...****",
        "status": "active",
        "created_at": datetime.utcnow().isoformat(),
    }


@router.post("/picoclaw/service-accounts/{account_id}/rotate")
async def rotate_service_account_token(account_id: str):
    """Rotate a service account token."""
    # TODO: Generate new token, revoke old
    return {"account_id": account_id, "rotated": True}


@router.delete("/picoclaw/service-accounts/{account_id}")
async def revoke_service_account(account_id: str):
    """Revoke a service account."""
    # TODO: Mark account as revoked
    return {"account_id": account_id, "revoked": True}


# ============================================================================
# OpenClaw Gateway Management
# ============================================================================

@router.get("/openclaw/gateway/status")
async def get_gateway_status():
    """Get OpenClaw gateway status."""
    # TODO: Check actual gateway status via health endpoint
    return {
        "gateway_running": False,
        "version": "Unknown",
        "meets_min_version": False,
        "channels_connected": 0,
        "skills_active": 0,
        "queries_today": 0,
        "avg_response_ms": 0,
        "active_sessions": 0,
        "signals_captured_today": 0,
        "gateway_binding": "127.0.0.1:3100",
        "auth_configured": False,
        "workspace_path": "/opt/openclaw/workspace",
        "soul_configured": False,
    }


@router.get("/openclaw/gateway/config")
async def get_gateway_config():
    """Get OpenClaw gateway configuration."""
    # TODO: Read configuration from database/file
    return {
        "provider": "vllm",
        "model": "qwen3-8b",
        "api_base": "http://localhost:8001/v1",
        "gateway_port": 3100,
        "gateway_binding": "127.0.0.1",
    }


@router.put("/openclaw/gateway/config")
async def update_gateway_config(data: Dict[str, Any]):
    """Update OpenClaw gateway configuration."""
    # TODO: Persist configuration
    return {"status": "updated", "config": data}


@router.post("/openclaw/gateway/test")
async def test_gateway():
    """Test OpenClaw gateway connectivity."""
    # TODO: Ping gateway health endpoint
    return {"success": False, "message": "Gateway not running"}


# ---- Skills ----

@router.get("/openclaw/skills")
async def get_skills():
    """Get installed OpenClaw skills."""
    return [
        {"id": "supply-plan-query", "name": "Supply Plan Query", "enabled": True, "category": "planning", "description": "Query supply plan data (product, demand, inventory, OTIF)"},
        {"id": "atp-check", "name": "ATP Check", "enabled": True, "category": "execution", "description": "Check Available-to-Promise for orders"},
        {"id": "override-decision", "name": "Override Decision", "enabled": True, "category": "governance", "description": "Capture planner overrides with reasoning"},
        {"id": "ask-why", "name": "Ask Why", "enabled": True, "category": "explainability", "description": "Explain agent decisions with evidence citations"},
        {"id": "kpi-dashboard", "name": "KPI Dashboard", "enabled": True, "category": "monitoring", "description": "Service level, inventory, exceptions summary"},
        {"id": "signal-capture", "name": "Signal Capture", "enabled": True, "category": "signals", "description": "Extract demand/disruption signals from messages"},
        {"id": "voice-signal", "name": "Voice Signal", "enabled": False, "category": "signals", "description": "Transcribe and classify voice notes via Whisper"},
        {"id": "email-signal", "name": "Email Signal", "enabled": False, "category": "signals", "description": "Parse emails for supply chain signals"},
    ]


@router.put("/openclaw/skills/{skill_id}")
async def toggle_skill(skill_id: str, data: Dict[str, Any]):
    """Enable or disable a skill."""
    # TODO: Update skill state
    return {"skill_id": skill_id, "enabled": data.get("enabled", True)}


@router.post("/openclaw/skills/{skill_id}/test")
async def test_skill(skill_id: str, data: Dict[str, Any]):
    """Test a skill with sample input."""
    # TODO: Execute skill in sandbox
    return {
        "skill_id": skill_id,
        "success": True,
        "response": f"Skill {skill_id} test executed successfully",
        "duration_ms": 150,
    }


# ---- Channels ----

@router.get("/openclaw/channels")
async def get_channels():
    """Get configured channels."""
    return [
        {"id": "slack", "name": "Slack", "type": "slack", "status": "disconnected", "configured": False},
        {"id": "teams", "name": "Microsoft Teams", "type": "teams", "status": "disconnected", "configured": False},
        {"id": "whatsapp", "name": "WhatsApp", "type": "whatsapp", "status": "disconnected", "configured": False,
         "warning": "Uses Baileys (unofficial). Review ToS compliance."},
        {"id": "telegram", "name": "Telegram", "type": "telegram", "status": "disconnected", "configured": False},
        {"id": "email", "name": "Email (IMAP)", "type": "email", "status": "disconnected", "configured": False},
    ]


@router.put("/openclaw/channels/{channel_id}")
async def update_channel(channel_id: str, data: Dict[str, Any]):
    """Update channel configuration."""
    # TODO: Persist channel config
    return {"channel_id": channel_id, "status": "updated"}


@router.post("/openclaw/channels/{channel_id}/test")
async def test_channel(channel_id: str):
    """Test channel connectivity."""
    # TODO: Verify channel connection
    return {"channel_id": channel_id, "success": False, "message": "Channel not configured"}


# ---- Sessions ----

@router.get("/openclaw/sessions")
async def get_session_log(
    limit: int = Query(50, ge=1, le=200),
):
    """Get OpenClaw session activity log."""
    # TODO: Query session log
    return []


# ---- LLM ----

@router.get("/openclaw/llm/status")
async def get_llm_status():
    """Get LLM service status."""
    # TODO: Check vLLM/external LLM health
    return {
        "running": False,
        "model": None,
        "vram_used_gb": None,
        "avg_latency_ms": None,
        "config": {
            "provider": "vllm",
            "model": "qwen3-8b",
            "api_base": "http://localhost:8001/v1",
        },
    }


@router.put("/openclaw/llm/config")
async def update_llm_config(data: OpenClawConfig):
    """Update LLM configuration."""
    # TODO: Persist LLM config, restart service if needed
    return {"status": "updated", "config": data.model_dump()}


# ============================================================================
# Signal Ingestion
# ============================================================================

signal_router = APIRouter(prefix="/signals", tags=["Signal Ingestion"])


@signal_router.get("/dashboard")
async def get_signal_dashboard(
    period: str = Query("today", description="Time period: today, week, month"),
):
    """Get signal ingestion dashboard summary."""
    return {
        "signals_today": 0,
        "auto_applied": 0,
        "pending_review": 0,
        "rejected": 0,
        "correlated_groups": 0,
        "signals_this_hour": 0,
        "duplicates_filtered": 0,
        "injection_attempts": 0,
        "rate_limited": 0,
        "type_breakdown": [
            {"type": "DEMAND_INCREASE", "count": 0},
            {"type": "DEMAND_DECREASE", "count": 0},
            {"type": "DISRUPTION", "count": 0},
            {"type": "PRICE_CHANGE", "count": 0},
            {"type": "LEAD_TIME_CHANGE", "count": 0},
            {"type": "QUALITY_ALERT", "count": 0},
            {"type": "NEW_OPPORTUNITY", "count": 0},
            {"type": "COMPETITOR_ACTION", "count": 0},
        ],
        "source_breakdown": [
            {"source": "slack", "count": 0, "reliability": 0.7},
            {"source": "email", "count": 0, "reliability": 0.5},
            {"source": "teams", "count": 0, "reliability": 0.7},
            {"source": "voice", "count": 0, "reliability": 0.4},
            {"source": "weather", "count": 0, "reliability": 0.7},
            {"source": "news", "count": 0, "reliability": 0.6},
        ],
    }


@signal_router.get("")
async def get_signals(
    source: Optional[str] = Query(None),
    signal_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Get recent signals with optional filters."""
    # TODO: Query signal ingestion table
    return []


@signal_router.get("/pending")
async def get_pending_signals(
    source: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
):
    """Get signals pending human review (confidence 0.3-0.8)."""
    # TODO: Query signals with pending status
    return []


@signal_router.post("/{signal_id}/approve")
async def approve_signal(signal_id: str, data: SignalApproval = None):
    """Approve a pending signal and apply forecast adjustment."""
    # TODO: Apply signal, create forecast adjustment
    return {"signal_id": signal_id, "status": "approved", "adjustment_applied": True}


@signal_router.post("/{signal_id}/reject")
async def reject_signal(signal_id: str, data: SignalRejection):
    """Reject a pending signal."""
    # TODO: Mark signal as rejected with reason
    return {"signal_id": signal_id, "status": "rejected", "reason": data.reason}


@signal_router.get("/{signal_id}")
async def get_signal_details(signal_id: str):
    """Get detailed signal information with confidence breakdown."""
    # TODO: Look up signal details
    raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")


@signal_router.get("/correlations")
async def get_correlations(
    limit: int = Query(20, ge=1, le=50),
):
    """Get active multi-signal correlation groups."""
    # TODO: Query correlation engine
    return []


@signal_router.get("/adjustments")
async def get_adjustment_history(
    limit: int = Query(50, ge=1, le=200),
):
    """Get forecast adjustment history from signals."""
    # TODO: Query adjustment log
    return []


@signal_router.post("/adjustments/{adjustment_id}/revert")
async def revert_adjustment(adjustment_id: str):
    """Revert a previously applied forecast adjustment."""
    # TODO: Revert the adjustment and log
    return {"adjustment_id": adjustment_id, "reverted": True}


@signal_router.get("/channel-sources")
async def get_channel_sources():
    """Get channel-to-signal source mapping configuration."""
    return [
        {"channel": "slack_demand", "signal_source": "sales_input", "reliability": 0.7},
        {"channel": "slack_customer", "signal_source": "customer_feedback", "reliability": 0.7},
        {"channel": "teams", "signal_source": "sales_input", "reliability": 0.7},
        {"channel": "whatsapp", "signal_source": "sales_input", "reliability": 0.6},
        {"channel": "telegram", "signal_source": "customer_feedback", "reliability": 0.6},
        {"channel": "email_customer", "signal_source": "customer_feedback", "reliability": 0.5},
        {"channel": "email_market", "signal_source": "market_intelligence", "reliability": 0.8},
        {"channel": "voice", "signal_source": "voice", "reliability": 0.4},
        {"channel": "weather_api", "signal_source": "weather", "reliability": 0.7},
        {"channel": "economic_api", "signal_source": "economic_indicator", "reliability": 0.8},
        {"channel": "news_rss", "signal_source": "news", "reliability": 0.6},
    ]


@signal_router.put("/channel-sources/{channel_id}")
async def update_channel_source(channel_id: str, data: Dict[str, Any]):
    """Update channel-to-source mapping."""
    # TODO: Persist mapping
    return {"channel_id": channel_id, "status": "updated"}


@signal_router.get("/rate-limits")
async def get_rate_limits():
    """Get rate limiting status and configuration."""
    return {
        "per_source_limit": 100,
        "global_limit": 500,
        "current_hour_total": 0,
        "per_source_current": {},
        "deduplication_window_hours": 1,
    }


@signal_router.get("/source-reliability")
async def get_source_reliability():
    """Get source reliability configuration and learned weights."""
    return [
        {"source": "email", "default_weight": 0.5, "learned_weight": None, "signals_count": 0, "accuracy": None},
        {"source": "slack", "default_weight": 0.7, "learned_weight": None, "signals_count": 0, "accuracy": None},
        {"source": "teams", "default_weight": 0.7, "learned_weight": None, "signals_count": 0, "accuracy": None},
        {"source": "whatsapp", "default_weight": 0.6, "learned_weight": None, "signals_count": 0, "accuracy": None},
        {"source": "telegram", "default_weight": 0.6, "learned_weight": None, "signals_count": 0, "accuracy": None},
        {"source": "voice", "default_weight": 0.4, "learned_weight": None, "signals_count": 0, "accuracy": None},
        {"source": "market_intelligence", "default_weight": 0.8, "learned_weight": None, "signals_count": 0, "accuracy": None},
        {"source": "news", "default_weight": 0.6, "learned_weight": None, "signals_count": 0, "accuracy": None},
        {"source": "weather", "default_weight": 0.7, "learned_weight": None, "signals_count": 0, "accuracy": None},
        {"source": "economic_indicator", "default_weight": 0.8, "learned_weight": None, "signals_count": 0, "accuracy": None},
        {"source": "customer_feedback", "default_weight": 0.6, "learned_weight": None, "signals_count": 0, "accuracy": None},
        {"source": "sales_input", "default_weight": 0.7, "learned_weight": None, "signals_count": 0, "accuracy": None},
    ]


@signal_router.put("/source-reliability/{source}")
async def update_source_reliability(source: str, data: SourceReliabilityUpdate):
    """Update source reliability weight."""
    # TODO: Persist to database
    return {"source": source, "weight": data.weight, "status": "updated"}


# ============================================================================
# Security & Audit
# ============================================================================

@router.get("/security/audit")
async def get_audit_summary():
    """Get security audit summary for all edge agents."""
    return {
        "openclaw_secure": False,
        "openclaw_cve_count": 7,
        "openclaw_version_ok": False,
        "picoclaw_secure": False,
        "picoclaw_readonly": False,
        "checklist_complete": False,
        "checklist_passed": 0,
        "checklist_total": 30,
        "injection_attempts": 0,
        "credentials_in_env": False,
        "sanitization_enabled": False,
        "whatsapp_pilot_only": True,
    }


@router.get("/security/cves")
async def get_cve_status():
    """Get CVE status for installed versions."""
    return [
        {"id": "CVE-2026-25253", "severity": "CRITICAL", "cvss": 8.8, "component": "OpenClaw",
         "desc": "RCE via crafted gatewayUrl in skills", "fixed_in": "v2026.2.15", "status": "unknown"},
        {"id": "CVE-2026-26325", "severity": "HIGH", "cvss": 7.5, "component": "OpenClaw",
         "desc": "Authentication bypass via expired token reuse", "fixed_in": "v2026.2.10", "status": "unknown"},
        {"id": "CVE-2026-25474", "severity": "HIGH", "cvss": 7.1, "component": "OpenClaw",
         "desc": "Telegram webhook forgery (missing webhookSecret)", "fixed_in": "v2026.2.8", "status": "unknown"},
        {"id": "CVE-2026-26324", "severity": "MEDIUM", "cvss": 6.5, "component": "OpenClaw",
         "desc": "SSRF via skill proxy endpoint", "fixed_in": "v2026.2.12", "status": "unknown"},
        {"id": "CVE-2026-27003", "severity": "MEDIUM", "cvss": 5.3, "component": "OpenClaw",
         "desc": "Telegram token exposure in error logs", "fixed_in": "v2026.2.14", "status": "unknown"},
        {"id": "CVE-2026-27004", "severity": "MEDIUM", "cvss": 5.0, "component": "OpenClaw",
         "desc": "Session isolation bypass via sessions_send", "fixed_in": "v2026.2.15", "status": "unknown"},
        {"id": "GHSA-r5fq", "severity": "HIGH", "cvss": 7.2, "component": "OpenClaw",
         "desc": "Path traversal in workspace file access", "fixed_in": "v2026.1.28", "status": "unknown"},
    ]


@router.get("/security/checklist")
async def get_checklist():
    """Get pre-deployment security checklist status."""
    return {
        "sections": [
            {
                "name": "Infrastructure",
                "items": [
                    {"id": "infra-1", "label": "OpenClaw version >= v2026.2.15", "checked": False},
                    {"id": "infra-2", "label": "Gateway bound to 127.0.0.1 (loopback only)", "checked": False},
                    {"id": "infra-3", "label": "Reverse proxy configured (nginx/caddy)", "checked": False},
                    {"id": "infra-4", "label": "Container runs as non-root with --cap-drop ALL", "checked": False},
                    {"id": "infra-5", "label": "PicoClaw containers are read-only (--read-only)", "checked": False},
                    {"id": "infra-6", "label": "SecureClaw audit passed (OpenClaw)", "checked": False},
                ],
            },
            {
                "name": "Credentials",
                "items": [
                    {"id": "cred-1", "label": "All credentials stored in environment variables", "checked": False},
                    {"id": "cred-2", "label": "Bot tokens in env vars (not config files)", "checked": False},
                    {"id": "cred-3", "label": "Gateway auth token rotated (not default)", "checked": False},
                    {"id": "cred-4", "label": "Per-site JWT scoping for PicoClaw accounts", "checked": False},
                    {"id": "cred-5", "label": "Service account tokens have expiry dates", "checked": False},
                ],
            },
            {
                "name": "Channel Security",
                "items": [
                    {"id": "chan-1", "label": "Telegram webhookSecret configured", "checked": False},
                    {"id": "chan-2", "label": "Slack bot scoped to required channels only", "checked": False},
                    {"id": "chan-3", "label": "Email sender validation enabled", "checked": False},
                    {"id": "chan-4", "label": "DM pairing mode enabled (no group auth bypass)", "checked": False},
                    {"id": "chan-5", "label": "WhatsApp pilot-only flag set (if using Baileys)", "checked": False},
                ],
            },
            {
                "name": "Signal Ingestion",
                "items": [
                    {"id": "sig-1", "label": "Rate limiting enabled (100/hour/source)", "checked": False},
                    {"id": "sig-2", "label": "Deduplication window active (1h)", "checked": False},
                    {"id": "sig-3", "label": "Input sanitization (control char stripping)", "checked": False},
                    {"id": "sig-4", "label": "Confidence gating thresholds configured", "checked": False},
                    {"id": "sig-5", "label": "Adjustment magnitude caps enabled (±50%)", "checked": False},
                    {"id": "sig-6", "label": "Prompt injection pattern detection active", "checked": False},
                ],
            },
            {
                "name": "Monitoring",
                "items": [
                    {"id": "mon-1", "label": "Access logs forwarded to SIEM", "checked": False},
                    {"id": "mon-2", "label": "Failed authentication alerting configured", "checked": False},
                    {"id": "mon-3", "label": "Anomalous signal pattern detection active", "checked": False},
                ],
            },
            {
                "name": "Skills",
                "items": [
                    {"id": "skill-1", "label": "No ClawHub marketplace skills installed", "checked": False},
                    {"id": "skill-2", "label": "npm audit clean for skill dependencies", "checked": False},
                    {"id": "skill-3", "label": "package-lock.json checked into version control", "checked": False},
                ],
            },
        ],
    }


@router.put("/security/checklist/{item_id}")
async def update_checklist_item(item_id: str, data: ChecklistUpdate):
    """Update a checklist item status."""
    # TODO: Persist checklist state
    return {"item_id": item_id, "checked": data.checked}


@router.get("/security/integration-health")
async def get_integration_health():
    """Get health status of all integrated services."""
    return {
        "services": [
            {"name": "Autonomy REST API", "status": "healthy", "latency": 12, "last_check": datetime.utcnow().isoformat()},
            {"name": "OpenClaw Gateway", "status": "unknown", "latency": None, "last_check": None},
            {"name": "PicoClaw Fleet", "status": "unknown", "latency": None, "last_check": None},
            {"name": "vLLM Service", "status": "unknown", "latency": None, "last_check": None},
            {"name": "PostgreSQL Database", "status": "healthy", "latency": 3, "last_check": datetime.utcnow().isoformat()},
            {"name": "Signal Ingestion Pipeline", "status": "unknown", "latency": None, "last_check": None},
        ],
        "recent_errors": [],
    }


@router.get("/security/activity-log")
async def get_activity_log(
    component: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Get unified activity log for edge agents."""
    # TODO: Query activity log
    return []


@router.get("/security/injection-stats")
async def get_injection_stats():
    """Get prompt injection detection statistics."""
    return {
        "total_blocked": 0,
        "this_week": 0,
        "by_type": {
            "role_assumption": 0,
            "code_injection": 0,
            "escape_sequence": 0,
        },
    }
