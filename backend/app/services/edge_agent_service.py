"""
Edge Agent Service — Business logic for PicoClaw/OpenClaw/Signal management.

Provides CRUD operations and business logic for:
- PicoClaw fleet management (instances, heartbeats, alerts, service accounts)
- OpenClaw gateway configuration (channels, skills, sessions, LLM config)
- Security checklist and audit logging
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update, delete, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.edge_agents import (
    EdgePicoClawInstance,
    EdgePicoClawHeartbeat,
    EdgePicoClawAlert,
    EdgeServiceAccount,
    EdgeOpenClawConfig,
    EdgeOpenClawChannel,
    EdgeOpenClawSkill,
    EdgeOpenClawSession,
    EdgeSourceReliability,
    EdgeSecurityChecklist,
    EdgeActivityLog,
)

import logging

logger = logging.getLogger(__name__)


# Default skills to seed on first access
DEFAULT_SKILLS = [
    {"skill_id": "supply-plan-query", "name": "Supply Plan Query", "category": "planning",
     "description": "Query supply plan data (product, demand, inventory, OTIF)"},
    {"skill_id": "atp-check", "name": "ATP Check", "category": "execution",
     "description": "Check Available-to-Promise for orders"},
    {"skill_id": "override-decision", "name": "Override Decision", "category": "governance",
     "description": "Capture planner overrides with reasoning"},
    {"skill_id": "ask-why", "name": "Ask Why", "category": "explainability",
     "description": "Explain agent decisions with evidence citations"},
    {"skill_id": "kpi-dashboard", "name": "KPI Dashboard", "category": "monitoring",
     "description": "Service level, inventory, exceptions summary"},
    {"skill_id": "signal-capture", "name": "Signal Capture", "category": "signals",
     "description": "Extract demand/disruption signals from messages"},
    {"skill_id": "voice-signal", "name": "Voice Signal", "category": "signals",
     "description": "Transcribe and classify voice notes via Whisper", "enabled": False},
    {"skill_id": "email-signal", "name": "Email Signal", "category": "signals",
     "description": "Parse emails for supply chain signals", "enabled": False},
]

# Default channels
DEFAULT_CHANNELS = [
    {"channel_id": "slack", "name": "Slack", "channel_type": "slack"},
    {"channel_id": "teams", "name": "Microsoft Teams", "channel_type": "teams"},
    {"channel_id": "whatsapp", "name": "WhatsApp", "channel_type": "whatsapp",
     "warning": "Uses Baileys (unofficial). Review ToS compliance."},
    {"channel_id": "telegram", "name": "Telegram", "channel_type": "telegram"},
    {"channel_id": "email", "name": "Email (IMAP)", "channel_type": "email"},
]

# Default source reliability
DEFAULT_SOURCES = [
    {"source": "email", "default_weight": 0.5},
    {"source": "slack", "default_weight": 0.7},
    {"source": "teams", "default_weight": 0.7},
    {"source": "whatsapp", "default_weight": 0.6},
    {"source": "telegram", "default_weight": 0.6},
    {"source": "voice", "default_weight": 0.4},
    {"source": "market_intelligence", "default_weight": 0.8},
    {"source": "news", "default_weight": 0.6},
    {"source": "weather", "default_weight": 0.7},
    {"source": "economic_indicator", "default_weight": 0.8},
    {"source": "customer_feedback", "default_weight": 0.6},
    {"source": "sales_input", "default_weight": 0.7},
]

# Default security checklist items
SECURITY_CHECKLIST = [
    ("Infrastructure", [
        ("infra-1", "OpenClaw version >= v2026.2.15"),
        ("infra-2", "Gateway bound to 127.0.0.1 (loopback only)"),
        ("infra-3", "Reverse proxy configured (nginx/caddy)"),
        ("infra-4", "Container runs as non-root with --cap-drop ALL"),
        ("infra-5", "PicoClaw containers are read-only (--read-only)"),
        ("infra-6", "SecureClaw audit passed (OpenClaw)"),
    ]),
    ("Credentials", [
        ("cred-1", "All credentials stored in environment variables"),
        ("cred-2", "Bot tokens in env vars (not config files)"),
        ("cred-3", "Gateway auth token rotated (not default)"),
        ("cred-4", "Per-site JWT scoping for PicoClaw accounts"),
        ("cred-5", "Service account tokens have expiry dates"),
    ]),
    ("Channel Security", [
        ("chan-1", "Telegram webhookSecret configured"),
        ("chan-2", "Slack bot scoped to required channels only"),
        ("chan-3", "Email sender validation enabled"),
        ("chan-4", "DM pairing mode enabled (no group auth bypass)"),
        ("chan-5", "WhatsApp pilot-only flag set (if using Baileys)"),
    ]),
    ("Signal Ingestion", [
        ("sig-1", "Rate limiting enabled (100/hour/source)"),
        ("sig-2", "Deduplication window active (1h)"),
        ("sig-3", "Input sanitization (control char stripping)"),
        ("sig-4", "Confidence gating thresholds configured"),
        ("sig-5", "Adjustment magnitude caps enabled (±50%)"),
        ("sig-6", "Prompt injection pattern detection active"),
    ]),
    ("Monitoring", [
        ("mon-1", "Access logs forwarded to SIEM"),
        ("mon-2", "Failed authentication alerting configured"),
        ("mon-3", "Anomalous signal pattern detection active"),
    ]),
    ("Skills", [
        ("skill-1", "No ClawHub marketplace skills installed"),
        ("skill-2", "npm audit clean for skill dependencies"),
        ("skill-3", "package-lock.json checked into version control"),
    ]),
]


class EdgeAgentService:
    """Service layer for edge agent management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # -----------------------------------------------------------------------
    # PicoClaw Fleet
    # -----------------------------------------------------------------------

    async def get_fleet_summary(self) -> Dict[str, Any]:
        """Get fleet-wide status counts."""
        result = await self.db.execute(
            select(
                EdgePicoClawInstance.status,
                func.count(EdgePicoClawInstance.id),
            )
            .where(EdgePicoClawInstance.is_active == True)
            .group_by(EdgePicoClawInstance.status)
        )
        counts = {row[0]: row[1] for row in result.all()}
        total = sum(counts.values())
        return {
            "total": total,
            "healthy": counts.get("OK", 0),
            "warning": counts.get("WARNING", 0),
            "critical": counts.get("CRITICAL", 0),
            "stale": counts.get("STALE", 0),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    async def get_fleet_instances(
        self,
        status: Optional[str] = None,
        site_type: Optional[str] = None,
        region: Optional[str] = None,
    ) -> List[Dict]:
        """Get PicoClaw instances with optional filters."""
        q = select(EdgePicoClawInstance).where(EdgePicoClawInstance.is_active == True)
        if status:
            q = q.where(EdgePicoClawInstance.status == status)
        if site_type:
            q = q.where(EdgePicoClawInstance.site_type == site_type)
        if region:
            q = q.where(EdgePicoClawInstance.region == region)
        q = q.order_by(EdgePicoClawInstance.site_key)
        result = await self.db.execute(q)
        return [r.to_dict() for r in result.scalars().all()]

    async def get_instance(self, site_key: str) -> Optional[Dict]:
        """Get a single PicoClaw instance."""
        result = await self.db.execute(
            select(EdgePicoClawInstance).where(EdgePicoClawInstance.site_key == site_key)
        )
        inst = result.scalar_one_or_none()
        return inst.to_dict() if inst else None

    async def register_instance(self, data: Dict[str, Any]) -> Dict:
        """Register a new PicoClaw instance."""
        inst = EdgePicoClawInstance(
            site_key=data["site_key"],
            site_name=data.get("site_name"),
            site_type=data.get("site_type"),
            region=data.get("region"),
            mode=data.get("mode", "deterministic"),
            alert_channel=data.get("alert_channel"),
            heartbeat_interval_min=data.get("heartbeat_interval_min", 30),
            status="STALE",
        )
        self.db.add(inst)
        await self.db.flush()
        await self._log_activity("picoclaw", f"Registered instance {data['site_key']}", site_key=data["site_key"])
        return inst.to_dict()

    async def update_instance(self, site_key: str, data: Dict[str, Any]) -> Optional[Dict]:
        """Update PicoClaw instance configuration."""
        result = await self.db.execute(
            select(EdgePicoClawInstance).where(EdgePicoClawInstance.site_key == site_key)
        )
        inst = result.scalar_one_or_none()
        if not inst:
            return None
        for key in ("site_name", "site_type", "region", "mode", "alert_channel",
                     "heartbeat_interval_min", "digest_interval_min"):
            if key in data:
                setattr(inst, key, data[key])
        await self.db.flush()
        return inst.to_dict()

    async def remove_instance(self, site_key: str) -> bool:
        """Soft-delete a PicoClaw instance."""
        result = await self.db.execute(
            select(EdgePicoClawInstance).where(EdgePicoClawInstance.site_key == site_key)
        )
        inst = result.scalar_one_or_none()
        if not inst:
            return False
        inst.is_active = False
        inst.status = "STALE"
        await self.db.flush()
        await self._log_activity("picoclaw", f"Removed instance {site_key}", site_key=site_key)
        return True

    async def record_heartbeat(self, site_key: str, data: Dict[str, Any]) -> Optional[Dict]:
        """Record a heartbeat and update instance status."""
        result = await self.db.execute(
            select(EdgePicoClawInstance).where(EdgePicoClawInstance.site_key == site_key)
        )
        inst = result.scalar_one_or_none()
        if not inst:
            return None

        # Create heartbeat record
        hb = EdgePicoClawHeartbeat(
            site_key=site_key,
            memory_mb=data.get("memory_mb"),
            cpu_pct=data.get("cpu_pct"),
            uptime_seconds=data.get("uptime_seconds"),
            conditions=data.get("conditions"),
        )
        self.db.add(hb)

        # Update instance status from conditions
        inst.last_heartbeat = datetime.now(timezone.utc)
        inst.memory_mb = data.get("memory_mb")
        conditions = data.get("conditions", {})
        worst_status = "OK"
        for cond_name, cond_data in conditions.items():
            cond_status = cond_data.get("status", "OK")
            if cond_status == "CRITICAL":
                worst_status = "CRITICAL"
            elif cond_status == "WARNING" and worst_status != "CRITICAL":
                worst_status = "WARNING"
            # Update CDC metric snapshots
            if cond_name == "inventory_ratio":
                inst.inventory_ratio = cond_data.get("value")
            elif cond_name == "service_level":
                inst.service_level = cond_data.get("value")
            elif cond_name == "demand_deviation":
                inst.demand_deviation = cond_data.get("value")

        inst.status = worst_status
        await self.db.flush()
        return hb.to_dict()

    async def get_heartbeats(self, site_key: str, limit: int = 24) -> List[Dict]:
        """Get heartbeat history for an instance."""
        result = await self.db.execute(
            select(EdgePicoClawHeartbeat)
            .where(EdgePicoClawHeartbeat.site_key == site_key)
            .order_by(desc(EdgePicoClawHeartbeat.received_at))
            .limit(limit)
        )
        return [h.to_dict() for h in result.scalars().all()]

    async def get_fleet_alerts(
        self,
        severity: Optional[str] = None,
        site_key: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Get CDC alerts across fleet."""
        q = select(EdgePicoClawAlert).order_by(desc(EdgePicoClawAlert.created_at)).limit(limit)
        if severity:
            q = q.where(EdgePicoClawAlert.severity == severity)
        if site_key:
            q = q.where(EdgePicoClawAlert.site_key == site_key)
        result = await self.db.execute(q)
        return [a.to_dict() for a in result.scalars().all()]

    async def acknowledge_alert(self, alert_id: str, user: str = "admin") -> bool:
        """Acknowledge a CDC alert."""
        result = await self.db.execute(
            select(EdgePicoClawAlert).where(EdgePicoClawAlert.alert_id == alert_id)
        )
        alert = result.scalar_one_or_none()
        if not alert:
            return False
        alert.acknowledged = True
        alert.acknowledged_by = user
        alert.acknowledged_at = datetime.now(timezone.utc)
        await self.db.flush()
        return True

    # -----------------------------------------------------------------------
    # Service Accounts
    # -----------------------------------------------------------------------

    async def get_service_accounts(self) -> List[Dict]:
        """Get all active service accounts."""
        result = await self.db.execute(
            select(EdgeServiceAccount)
            .where(EdgeServiceAccount.status == "active")
            .order_by(EdgeServiceAccount.created_at)
        )
        return [sa.to_dict() for sa in result.scalars().all()]

    async def create_service_account(self, data: Dict[str, Any]) -> Dict:
        """Create a new service account with a generated token."""
        token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        token_masked = token[:8] + "****" + token[-4:]

        sa = EdgeServiceAccount(
            name=data["name"],
            scope=data.get("scope", "site"),
            site_key=data.get("site_key"),
            token_hash=token_hash,
            token_masked=token_masked,
            expires_at=datetime.now(timezone.utc) + timedelta(days=90),
        )
        self.db.add(sa)
        await self.db.flush()
        await self._log_activity("picoclaw", f"Created service account: {data['name']}")

        result = sa.to_dict()
        result["token"] = token  # Only returned on creation
        return result

    async def rotate_service_account_token(self, account_id: int) -> Optional[Dict]:
        """Rotate a service account token."""
        result = await self.db.execute(
            select(EdgeServiceAccount).where(EdgeServiceAccount.id == account_id)
        )
        sa = result.scalar_one_or_none()
        if not sa or sa.status != "active":
            return None

        token = secrets.token_urlsafe(48)
        sa.token_hash = hashlib.sha256(token.encode()).hexdigest()
        sa.token_masked = token[:8] + "****" + token[-4:]
        sa.expires_at = datetime.now(timezone.utc) + timedelta(days=90)
        await self.db.flush()
        await self._log_activity("picoclaw", f"Rotated token for account: {sa.name}")

        result_dict = sa.to_dict()
        result_dict["token"] = token
        return result_dict

    async def revoke_service_account(self, account_id: int) -> bool:
        """Revoke a service account."""
        result = await self.db.execute(
            select(EdgeServiceAccount).where(EdgeServiceAccount.id == account_id)
        )
        sa = result.scalar_one_or_none()
        if not sa:
            return False
        sa.status = "revoked"
        sa.revoked_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self._log_activity("picoclaw", f"Revoked service account: {sa.name}")
        return True

    # -----------------------------------------------------------------------
    # OpenClaw Gateway
    # -----------------------------------------------------------------------

    async def get_gateway_config(self) -> Dict:
        """Get or create default OpenClaw config."""
        result = await self.db.execute(select(EdgeOpenClawConfig).limit(1))
        config = result.scalar_one_or_none()
        if not config:
            config = EdgeOpenClawConfig()
            self.db.add(config)
            await self.db.flush()
        return config.to_dict()

    async def update_gateway_config(self, data: Dict[str, Any]) -> Dict:
        """Update OpenClaw gateway configuration."""
        result = await self.db.execute(select(EdgeOpenClawConfig).limit(1))
        config = result.scalar_one_or_none()
        if not config:
            config = EdgeOpenClawConfig()
            self.db.add(config)

        for key in ("provider", "model", "api_base", "max_tokens", "temperature",
                     "gateway_port", "gateway_binding", "workspace_path"):
            if key in data:
                setattr(config, key, data[key])
        await self.db.flush()
        await self._log_activity("openclaw", "Updated gateway config")
        return config.to_dict()

    async def get_skills(self) -> List[Dict]:
        """Get all skills, seeding defaults if empty."""
        result = await self.db.execute(
            select(EdgeOpenClawSkill).order_by(EdgeOpenClawSkill.skill_id)
        )
        skills = result.scalars().all()
        if not skills:
            # Seed defaults
            for s in DEFAULT_SKILLS:
                skill = EdgeOpenClawSkill(
                    skill_id=s["skill_id"],
                    name=s["name"],
                    category=s["category"],
                    description=s["description"],
                    enabled=s.get("enabled", True),
                )
                self.db.add(skill)
            await self.db.flush()
            result = await self.db.execute(
                select(EdgeOpenClawSkill).order_by(EdgeOpenClawSkill.skill_id)
            )
            skills = result.scalars().all()
        return [s.to_dict() for s in skills]

    async def toggle_skill(self, skill_id: str, enabled: bool) -> Optional[Dict]:
        """Enable or disable a skill."""
        result = await self.db.execute(
            select(EdgeOpenClawSkill).where(EdgeOpenClawSkill.skill_id == skill_id)
        )
        skill = result.scalar_one_or_none()
        if not skill:
            return None
        skill.enabled = enabled
        await self.db.flush()
        await self._log_activity("openclaw", f"{'Enabled' if enabled else 'Disabled'} skill: {skill_id}")
        return skill.to_dict()

    async def get_channels(self) -> List[Dict]:
        """Get all channels, seeding defaults if empty."""
        result = await self.db.execute(
            select(EdgeOpenClawChannel).order_by(EdgeOpenClawChannel.channel_id)
        )
        channels = result.scalars().all()
        if not channels:
            for c in DEFAULT_CHANNELS:
                chan = EdgeOpenClawChannel(
                    channel_id=c["channel_id"],
                    name=c["name"],
                    channel_type=c["channel_type"],
                    warning=c.get("warning"),
                )
                self.db.add(chan)
            await self.db.flush()
            result = await self.db.execute(
                select(EdgeOpenClawChannel).order_by(EdgeOpenClawChannel.channel_id)
            )
            channels = result.scalars().all()
        return [c.to_dict() for c in channels]

    async def update_channel(self, channel_id: str, data: Dict[str, Any]) -> Optional[Dict]:
        """Update channel configuration."""
        result = await self.db.execute(
            select(EdgeOpenClawChannel).where(EdgeOpenClawChannel.channel_id == channel_id)
        )
        chan = result.scalar_one_or_none()
        if not chan:
            return None
        if "config" in data:
            chan.config = data["config"]
        if "configured" in data:
            chan.configured = data["configured"]
        await self.db.flush()
        await self._log_activity("openclaw", f"Updated channel config: {channel_id}")
        return chan.to_dict()

    async def get_sessions(self, limit: int = 50) -> List[Dict]:
        """Get OpenClaw session activity log."""
        result = await self.db.execute(
            select(EdgeOpenClawSession)
            .order_by(desc(EdgeOpenClawSession.created_at))
            .limit(limit)
        )
        return [s.to_dict() for s in result.scalars().all()]

    # -----------------------------------------------------------------------
    # Source Reliability
    # -----------------------------------------------------------------------

    async def get_source_reliability(self) -> List[Dict]:
        """Get all source reliability configs, seeding defaults if empty."""
        result = await self.db.execute(
            select(EdgeSourceReliability).order_by(EdgeSourceReliability.source)
        )
        sources = result.scalars().all()
        if not sources:
            for s in DEFAULT_SOURCES:
                src = EdgeSourceReliability(source=s["source"], default_weight=s["default_weight"])
                self.db.add(src)
            await self.db.flush()
            result = await self.db.execute(
                select(EdgeSourceReliability).order_by(EdgeSourceReliability.source)
            )
            sources = result.scalars().all()
        return [s.to_dict() for s in sources]

    async def update_source_reliability(self, source: str, weight: float) -> Optional[Dict]:
        """Update source reliability manual weight."""
        result = await self.db.execute(
            select(EdgeSourceReliability).where(EdgeSourceReliability.source == source)
        )
        src = result.scalar_one_or_none()
        if not src:
            return None
        src.manual_weight = weight
        await self.db.flush()
        return src.to_dict()

    async def get_effective_source_weight(self, source: str) -> float:
        """Get the effective weight for a source (for signal ingestion)."""
        result = await self.db.execute(
            select(EdgeSourceReliability).where(EdgeSourceReliability.source == source)
        )
        src = result.scalar_one_or_none()
        if not src:
            return 0.5  # Unknown source default
        return src.effective_weight

    # -----------------------------------------------------------------------
    # Security Checklist
    # -----------------------------------------------------------------------

    async def get_checklist(self) -> Dict:
        """Get security checklist, seeding defaults if empty."""
        result = await self.db.execute(
            select(EdgeSecurityChecklist).order_by(EdgeSecurityChecklist.id)
        )
        items = result.scalars().all()
        if not items:
            for section_name, section_items in SECURITY_CHECKLIST:
                for item_id, label in section_items:
                    item = EdgeSecurityChecklist(
                        item_id=item_id, section=section_name, label=label
                    )
                    self.db.add(item)
            await self.db.flush()
            result = await self.db.execute(
                select(EdgeSecurityChecklist).order_by(EdgeSecurityChecklist.id)
            )
            items = result.scalars().all()

        # Group by section
        sections: Dict[str, List[Dict]] = {}
        for item in items:
            section = item.section
            if section not in sections:
                sections[section] = []
            sections[section].append(item.to_dict())

        return {
            "sections": [
                {"name": name, "items": items_list}
                for name, items_list in sections.items()
            ]
        }

    async def update_checklist_item(self, item_id: str, checked: bool, user: str = "admin") -> Optional[Dict]:
        """Update a checklist item."""
        result = await self.db.execute(
            select(EdgeSecurityChecklist).where(EdgeSecurityChecklist.item_id == item_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            return None
        item.checked = checked
        item.checked_by = user if checked else None
        item.checked_at = datetime.now(timezone.utc) if checked else None
        await self.db.flush()
        return item.to_dict()

    # -----------------------------------------------------------------------
    # Activity Log
    # -----------------------------------------------------------------------

    async def get_activity_log(
        self, component: Optional[str] = None, limit: int = 50
    ) -> List[Dict]:
        """Get unified activity log."""
        q = select(EdgeActivityLog).order_by(desc(EdgeActivityLog.created_at)).limit(limit)
        if component:
            q = q.where(EdgeActivityLog.component == component)
        result = await self.db.execute(q)
        return [a.to_dict() for a in result.scalars().all()]

    async def _log_activity(
        self,
        component: str,
        action: str,
        details: Optional[Dict] = None,
        site_key: Optional[str] = None,
        severity: str = "info",
    ) -> None:
        """Record an activity log entry."""
        entry = EdgeActivityLog(
            component=component,
            action=action,
            details=details,
            site_key=site_key,
            severity=severity,
        )
        self.db.add(entry)
