"""
Slack Signal Service — Ingest, Classify, and Route Slack-Derived SC Signals

Pipeline:
  1. Receive Slack message (from webhook push or bot channel polling)
  2. LLM classification — extract signal type, direction, magnitude, urgency
  3. Scope resolution — fuzzy-match product/site references against tenant data
  4. Route to TRM — create decision states for relevant TRMs
  5. Surface in Decision Stream as actionable alert

Slack messages are a SIGNAL SOURCE for existing TRMs (especially ForecastAdjustmentTRM),
following the same pattern as email_signal_service.py.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.slack_signal import (
    SlackSignal, SlackConnection, SIGNAL_TYPES, SIGNAL_TRM_ROUTING,
)

logger = logging.getLogger(__name__)


# ── LLM classification prompt ───────────────────────────────────────────────

_CLASSIFY_SYSTEM_PROMPT = """You are a supply chain Slack message signal classifier for the Autonomy platform.

Your job: analyze a Slack message from a supply chain channel and extract a structured supply chain signal.

The message is from channel "{channel_name}" posted by "{sender_name}".
Available product families in this tenant: {product_families}
Available site/region names in this tenant: {site_names}

Analyze the message and return JSON with these fields:
{{
  "signal_type": one of {signal_types},
  "direction": "up" | "down" | "no_change" | null,
  "magnitude_pct": float or null (estimated % impact, e.g. 15.0 for "15% increase"),
  "confidence": float 0-1 (how clearly this is a supply chain signal vs general chatter),
  "urgency": "low" | "medium" | "high" | "critical",
  "summary": "1-2 sentence plain English summary of the supply chain signal",
  "product_refs": [list of product/family names mentioned, from tenant's product list] or [],
  "site_refs": [list of site/region names mentioned, from tenant's site list] or [],
  "time_horizon_weeks": integer or null (estimated duration of impact),
  "target_trm_types": [list from: forecast_adjustment, inventory_buffer, po_creation, to_execution, quality_disposition, mo_execution, maintenance_scheduling, order_tracking, atp_executor] or []
}}

Rules:
- "general_inquiry" is for messages that don't contain actionable SC intelligence
- Set confidence LOW (<0.4) for ambiguous messages or casual chatter; HIGH (>0.7) for clear signals
- Urgency reflects time sensitivity: disruption notification = critical, FYI = low
- Product/site refs should ONLY contain items from the provided tenant lists
- If no specific products or sites mentioned, leave the lists empty
- Return ONLY valid JSON, no markdown
"""


class SlackSignalService:
    """Ingest, classify, and route Slack-derived supply chain signals."""

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    # ── Connection management ─────────────────────────────────────────────

    async def create_connection(self, data: dict) -> SlackConnection:
        """Create a new Slack connection for this tenant."""
        conn = SlackConnection(
            tenant_id=self.tenant_id,
            name=data["name"],
            connection_type=data["connection_type"],
            webhook_url=data.get("webhook_url"),
            bot_token_encrypted=data.get("bot_token"),  # TODO: encrypt at rest
            channel_ids=data.get("channel_ids"),
            channel_names=data.get("channel_names"),
            allowed_signal_types=data.get("allowed_signal_types"),
            poll_interval_minutes=data.get("poll_interval_minutes", 5),
            auto_route_enabled=data.get("auto_route_enabled", True),
            min_confidence_to_route=data.get("min_confidence_to_route", 0.6),
        )
        self.db.add(conn)
        await self.db.flush()
        await self.db.refresh(conn)
        return conn

    async def get_connections(self) -> List[SlackConnection]:
        """List all Slack connections for this tenant."""
        result = await self.db.execute(
            select(SlackConnection)
            .where(SlackConnection.tenant_id == self.tenant_id)
            .order_by(SlackConnection.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_connection(self, conn_id: int, data: dict) -> SlackConnection:
        """Update an existing Slack connection."""
        conn = await self.db.get(SlackConnection, conn_id)
        if not conn or conn.tenant_id != self.tenant_id:
            raise ValueError(f"Connection {conn_id} not found for tenant {self.tenant_id}")

        for field, value in data.items():
            if field == "bot_token" and value is not None:
                conn.bot_token_encrypted = value  # TODO: encrypt at rest
            elif hasattr(conn, field) and field not in ("id", "tenant_id", "created_at"):
                setattr(conn, field, value)

        await self.db.flush()
        await self.db.refresh(conn)
        return conn

    async def delete_connection(self, conn_id: int) -> bool:
        """Delete a Slack connection."""
        conn = await self.db.get(SlackConnection, conn_id)
        if not conn or conn.tenant_id != self.tenant_id:
            return False
        await self.db.delete(conn)
        await self.db.flush()
        return True

    async def test_connection(self, conn_id: int) -> dict:
        """Test a Slack connection.

        For bot tokens: attempts conversations.list API call.
        For webhooks: validates URL format.

        Returns:
            {"ok": bool, "message": str, "channels": [...]}
        """
        conn = await self.db.get(SlackConnection, conn_id)
        if not conn or conn.tenant_id != self.tenant_id:
            return {"ok": False, "message": "Connection not found", "channels": []}

        if conn.connection_type == "bot":
            return await self._test_bot_connection(conn)
        elif conn.connection_type == "webhook":
            return self._test_webhook_connection(conn)
        else:
            return {"ok": False, "message": f"Unknown connection type: {conn.connection_type}", "channels": []}

    async def _test_bot_connection(self, conn: SlackConnection) -> dict:
        """Test a bot token by calling conversations.list."""
        token = conn.bot_token_encrypted  # TODO: decrypt
        if not token:
            return {"ok": False, "message": "No bot token configured", "channels": []}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://slack.com/api/conversations.list",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"types": "public_channel,private_channel", "limit": 100},
                )
                data = resp.json()

                if not data.get("ok"):
                    return {
                        "ok": False,
                        "message": f"Slack API error: {data.get('error', 'unknown')}",
                        "channels": [],
                    }

                channels = [
                    {"id": ch["id"], "name": ch.get("name", ""), "is_member": ch.get("is_member", False)}
                    for ch in data.get("channels", [])
                ]
                return {
                    "ok": True,
                    "message": f"Connected. Found {len(channels)} channels.",
                    "channels": channels,
                }
        except httpx.RequestError as e:
            return {"ok": False, "message": f"HTTP error: {e}", "channels": []}
        except Exception as e:
            return {"ok": False, "message": f"Connection test failed: {e}", "channels": []}

    def _test_webhook_connection(self, conn: SlackConnection) -> dict:
        """Validate webhook URL format."""
        url = conn.webhook_url or ""
        if not url:
            return {"ok": False, "message": "No webhook URL configured", "channels": []}

        # Slack webhook URLs follow a known pattern
        if url.startswith("https://hooks.slack.com/") or url.startswith("https://"):
            return {
                "ok": True,
                "message": "Webhook URL format is valid. Messages will be received when Slack posts to this endpoint.",
                "channels": [],
            }
        return {"ok": False, "message": "Invalid webhook URL format", "channels": []}

    # ── Message ingestion ─────────────────────────────────────────────────

    async def ingest_message(self, connection_id: int, message: dict) -> Optional[SlackSignal]:
        """Ingest a single Slack message and classify it.

        Args:
            connection_id: ID of the SlackConnection
            message: dict with keys:
                - channel_id (str): Slack channel ID
                - channel_name (str): Human-readable channel name
                - message_ts (str): Slack message timestamp
                - sender_name (str, optional): Display name of sender
                - text (str): Message content
                - thread_ts (str, optional): Parent thread timestamp

        Returns:
            SlackSignal if created, None if duplicate or filtered out.
        """
        conn = await self.db.get(SlackConnection, connection_id)
        if not conn or conn.tenant_id != self.tenant_id:
            logger.warning("Connection %d not found for tenant %d", connection_id, self.tenant_id)
            return None

        channel_id = message.get("channel_id", "")
        message_ts = message.get("message_ts", "")
        msg_text = message.get("text", "")

        if not msg_text or not msg_text.strip():
            return None

        # Check for duplicate (same channel + timestamp)
        existing = await self.db.execute(
            select(SlackSignal).where(
                and_(
                    SlackSignal.tenant_id == self.tenant_id,
                    SlackSignal.channel_id == channel_id,
                    SlackSignal.message_ts == message_ts,
                )
            )
        )
        if existing.scalar_one_or_none():
            logger.debug("Duplicate message ts=%s in channel=%s, skipping", message_ts, channel_id)
            return None

        # Resolve config_id from tenant's first active config
        config_id = await self._get_tenant_config_id()

        # Create signal record
        signal = SlackSignal(
            tenant_id=self.tenant_id,
            config_id=config_id,
            connection_id=connection_id,
            channel_id=channel_id,
            channel_name=message.get("channel_name", ""),
            message_ts=message_ts,
            sender_name=message.get("sender_name"),
            message_text=msg_text,
            thread_ts=message.get("thread_ts"),
            status="INGESTED",
            received_at=self._ts_to_datetime(message_ts),
        )
        self.db.add(signal)
        await self.db.flush()

        # Classify the signal
        signal = await self.classify_signal(signal)

        # Auto-route if confidence is high enough
        if signal.signal_confidence is not None:
            min_confidence = conn.min_confidence_to_route or 0.6
            if not conn.auto_route_enabled:
                min_confidence = 999  # Disable auto-routing

            target_trms = signal.target_trm_types or []
            if signal.signal_confidence >= min_confidence and target_trms:
                await self._route_signal(signal)

        # Check allowed_signal_types filter
        if conn.allowed_signal_types and signal.signal_type:
            if signal.signal_type not in conn.allowed_signal_types:
                signal.status = "DISMISSED"
                signal.dismiss_reason = "Signal type not in allowed list"

        await self.db.commit()

        logger.info(
            "Slack signal ingested: id=%d, type=%s, channel=%s, confidence=%.2f",
            signal.id, signal.signal_type, signal.channel_name or signal.channel_id,
            signal.signal_confidence or 0,
        )
        return signal

    async def classify_signal(self, signal: SlackSignal) -> SlackSignal:
        """Classify a Slack message using LLM (Haiku tier).

        Updates the signal with classification results (signal_type, direction,
        magnitude, urgency, summary, scope, TRM routing).
        """
        config_id = signal.config_id
        tenant_context = await self._get_tenant_context(config_id) if config_id else {"site_names": [], "product_families": []}

        system_prompt = _CLASSIFY_SYSTEM_PROMPT.format(
            channel_name=signal.channel_name or signal.channel_id,
            sender_name=signal.sender_name or "Unknown",
            product_families=json.dumps(tenant_context.get("product_families", [])),
            site_names=json.dumps(tenant_context.get("site_names", [])),
            signal_types=json.dumps(SIGNAL_TYPES),
        )

        user_prompt = signal.message_text

        try:
            from app.services.skills.claude_client import ClaudeClient
            client = ClaudeClient()
            response = await client.complete(
                system_prompt=system_prompt,
                user_message=user_prompt,
                model_tier="haiku",
            )
            classification = json.loads(response.get("content", "{}"))
        except Exception as e:
            logger.warning("LLM Slack classification failed, using heuristic: %s", e)
            classification = self._heuristic_classify(signal.message_text)

        # Apply classification results
        signal.signal_type = classification.get("signal_type", "general_inquiry")
        signal.signal_direction = classification.get("direction")
        signal.signal_magnitude_pct = classification.get("magnitude_pct")
        signal.signal_confidence = classification.get("confidence", 0.5)
        signal.signal_urgency = classification.get("urgency", "medium")
        signal.signal_summary = classification.get("summary")

        # Resolve product/site scope
        product_refs = classification.get("product_refs", [])
        site_refs = classification.get("site_refs", [])
        if config_id and (product_refs or site_refs):
            resolved_products, resolved_sites = await self._resolve_scope(
                product_refs, site_refs, config_id,
            )
            signal.resolved_product_ids = resolved_products if resolved_products else None
            signal.resolved_site_ids = resolved_sites if resolved_sites else None

        signal.time_horizon_weeks = classification.get("time_horizon_weeks")

        # Determine TRM routing
        target_trms = classification.get("target_trm_types") or SIGNAL_TRM_ROUTING.get(signal.signal_type, [])
        signal.target_trm_types = target_trms if target_trms else None

        signal.status = "CLASSIFIED"
        signal.classified_at = datetime.utcnow()

        return signal

    def _heuristic_classify(self, text_content: str) -> Dict[str, Any]:
        """Fallback classification when LLM is unavailable."""
        combined = text_content.lower()

        signal_type = "general_inquiry"
        direction = None
        urgency = "low"

        if any(w in combined for w in ["shortage", "disruption", "force majeure", "unable to supply", "allocation"]):
            signal_type = "supply_disruption"
            direction = "down"
            urgency = "critical"
        elif any(w in combined for w in ["delay", "lead time", "extended delivery", "pushed back"]):
            signal_type = "lead_time_change"
            direction = "up"
            urgency = "high"
        elif any(w in combined for w in ["price increase", "surcharge", "cost increase", "rate increase"]):
            signal_type = "price_change"
            direction = "up"
            urgency = "medium"
        elif any(w in combined for w in ["quality", "defect", "recall", "non-conformance", "reject"]):
            signal_type = "quality_issue"
            urgency = "high"
        elif any(w in combined for w in ["increase order", "additional volume", "more units", "rush order", "demand spike"]):
            signal_type = "demand_increase"
            direction = "up"
            urgency = "medium"
        elif any(w in combined for w in ["cancel", "reduce order", "fewer units", "postpone", "demand drop"]):
            signal_type = "demand_decrease"
            direction = "down"
            urgency = "medium"
        elif any(w in combined for w in ["new product", "launch", "introduction"]):
            signal_type = "new_product"
            urgency = "medium"
        elif any(w in combined for w in ["discontinue", "end of life", "eol", "phase out"]):
            signal_type = "discontinuation"
            direction = "down"
            urgency = "medium"
        elif any(w in combined for w in ["capacity", "shutdown", "maintenance window"]):
            signal_type = "capacity_change"
            direction = "down"
            urgency = "high"

        # Extract magnitude hint
        magnitude = None
        pct_match = re.search(r'(\d+(?:\.\d+)?)\s*%', combined)
        if pct_match:
            magnitude = float(pct_match.group(1))

        target_trms = SIGNAL_TRM_ROUTING.get(signal_type, [])

        return {
            "signal_type": signal_type,
            "direction": direction,
            "magnitude_pct": magnitude,
            "confidence": 0.4 if signal_type != "general_inquiry" else 0.2,
            "urgency": urgency,
            "summary": f"Slack message classified as {signal_type.replace('_', ' ')}",
            "product_refs": [],
            "site_refs": [],
            "time_horizon_weeks": None,
            "target_trm_types": target_trms,
        }

    async def _route_signal(self, signal: SlackSignal) -> None:
        """Route a classified signal to appropriate TRM(s).

        Creates ForecastAdjustmentState entries for demand signals,
        and surfaces as Decision Stream alerts for all signals.
        """
        signal.status = "ROUTED"
        signal.routed_at = datetime.utcnow()
        decision_ids = []

        trm_types = signal.target_trm_types or []
        products = signal.resolved_product_ids or []
        sites = signal.resolved_site_ids or []

        # SCP-fork ForecastAdjustmentTRM routing removed 2026-04-23.
        # TMS DemandSensingTRM is the transport-plane analog; Slack-signal
        # → DemandSensingTRM routing is item 1.13 scope.
        if "forecast_adjustment" in trm_types:
            logger.debug(
                "Slack signal %d targets forecast_adjustment — SCP-fork TRM retired; "
                "TMS DemandSensingTRM routing pending (item 1.13).",
                signal.id,
            )

        signal.routed_decision_ids = decision_ids if decision_ids else None
        logger.info(
            "Slack signal %d routed to %d TRMs, %d decisions created",
            signal.id, len(trm_types), len(decision_ids),
        )

    # ── Query methods ─────────────────────────────────────────────────────

    async def get_signals(
        self,
        config_id: Optional[int] = None,
        status: Optional[str] = None,
        signal_type: Optional[str] = None,
        channel_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[SlackSignal]:
        """Get Slack signals with optional filters."""
        conditions = [SlackSignal.tenant_id == self.tenant_id]
        if config_id:
            conditions.append(SlackSignal.config_id == config_id)
        if status:
            conditions.append(SlackSignal.status == status)
        if signal_type:
            conditions.append(SlackSignal.signal_type == signal_type)
        if channel_id:
            conditions.append(SlackSignal.channel_id == channel_id)

        stmt = (
            select(SlackSignal)
            .where(and_(*conditions))
            .order_by(SlackSignal.received_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def dismiss_signal(self, signal_id: int, user_id: Optional[int] = None, reason: Optional[str] = None) -> Optional[SlackSignal]:
        """Dismiss a signal (human determined it's not actionable)."""
        signal = await self.db.get(SlackSignal, signal_id)
        if not signal or signal.tenant_id != self.tenant_id:
            return None
        signal.status = "DISMISSED"
        signal.dismissed_by = user_id
        signal.dismiss_reason = reason
        await self.db.commit()
        return signal

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        """Get summary statistics for the Slack signals dashboard."""
        tid = self.tenant_id

        # Count by status
        status_result = await self.db.execute(
            text("""
                SELECT status, COUNT(*) FROM slack_signals
                WHERE tenant_id = :tid
                GROUP BY status
            """),
            {"tid": tid},
        )
        by_status = {r[0]: r[1] for r in status_result.fetchall()}

        # Count by signal type
        type_result = await self.db.execute(
            text("""
                SELECT signal_type, COUNT(*) FROM slack_signals
                WHERE tenant_id = :tid AND signal_type IS NOT NULL
                GROUP BY signal_type
                ORDER BY COUNT(*) DESC
            """),
            {"tid": tid},
        )
        by_type = {r[0]: r[1] for r in type_result.fetchall()}

        # Count by channel
        channel_result = await self.db.execute(
            text("""
                SELECT COALESCE(channel_name, channel_id), COUNT(*)
                FROM slack_signals
                WHERE tenant_id = :tid
                GROUP BY COALESCE(channel_name, channel_id)
                ORDER BY COUNT(*) DESC
                LIMIT 10
            """),
            {"tid": tid},
        )
        top_channels = [
            {"channel": r[0], "count": r[1]}
            for r in channel_result.fetchall()
        ]

        # Totals and averages
        avg_result = await self.db.execute(
            text("""
                SELECT AVG(signal_confidence), COUNT(*)
                FROM slack_signals
                WHERE tenant_id = :tid
            """),
            {"tid": tid},
        )
        avg_row = avg_result.fetchone()

        # Signals in last 24h
        recent_result = await self.db.execute(
            text("""
                SELECT COUNT(*) FROM slack_signals
                WHERE tenant_id = :tid AND created_at > NOW() - INTERVAL '24 hours'
            """),
            {"tid": tid},
        )
        recent_count = recent_result.scalar() or 0

        return {
            "total": avg_row[1] if avg_row else 0,
            "last_24h": recent_count,
            "avg_confidence": round(avg_row[0], 3) if avg_row and avg_row[0] else 0,
            "by_status": by_status,
            "by_type": by_type,
            "top_channels": top_channels,
        }

    # ── Channel polling (bot mode) ────────────────────────────────────────

    async def poll_channels(self, connection_id: int) -> dict:
        """Poll Slack channels for new messages (bot token mode).

        Uses conversations.history API with oldest=last_message_ts for dedup.

        Returns:
            {"messages_found": N, "signals_created": M}
        """
        conn = await self.db.get(SlackConnection, connection_id)
        if not conn or conn.tenant_id != self.tenant_id:
            return {"messages_found": 0, "signals_created": 0, "error": "Connection not found"}

        if conn.connection_type != "bot":
            return {"messages_found": 0, "signals_created": 0, "error": "Connection is not bot type"}

        token = conn.bot_token_encrypted  # TODO: decrypt
        if not token:
            return {"messages_found": 0, "signals_created": 0, "error": "No bot token configured"}

        channel_ids = conn.channel_ids or []
        if not channel_ids:
            return {"messages_found": 0, "signals_created": 0, "error": "No channels configured"}

        # Build channel_id -> channel_name map
        channel_name_map = {}
        if conn.channel_names and conn.channel_ids:
            for i, cid in enumerate(conn.channel_ids):
                if i < len(conn.channel_names):
                    channel_name_map[cid] = conn.channel_names[i]

        total_found = 0
        total_created = 0
        latest_ts = conn.last_message_ts

        async with httpx.AsyncClient(timeout=15.0) as client:
            for channel_id in channel_ids:
                try:
                    params = {
                        "channel": channel_id,
                        "limit": 100,
                    }
                    if conn.last_message_ts:
                        params["oldest"] = conn.last_message_ts

                    resp = await client.get(
                        "https://slack.com/api/conversations.history",
                        headers={"Authorization": f"Bearer {token}"},
                        params=params,
                    )
                    data = resp.json()

                    if not data.get("ok"):
                        logger.warning(
                            "Slack API error for channel %s: %s",
                            channel_id, data.get("error", "unknown"),
                        )
                        continue

                    messages = data.get("messages", [])
                    total_found += len(messages)

                    for msg in messages:
                        msg_ts = msg.get("ts", "")

                        # Skip bot messages and system messages
                        if msg.get("subtype") in ("bot_message", "channel_join", "channel_leave", "channel_topic"):
                            continue

                        msg_text = msg.get("text", "")
                        if not msg_text or not msg_text.strip():
                            continue

                        # Resolve sender display name (no PII — just Slack display name)
                        sender_name = msg.get("user_profile", {}).get("display_name") or msg.get("username")

                        signal = await self.ingest_message(
                            connection_id=connection_id,
                            message={
                                "channel_id": channel_id,
                                "channel_name": channel_name_map.get(channel_id, ""),
                                "message_ts": msg_ts,
                                "sender_name": sender_name,
                                "text": msg_text,
                                "thread_ts": msg.get("thread_ts"),
                            },
                        )
                        if signal:
                            total_created += 1

                        # Track latest timestamp for dedup
                        if not latest_ts or msg_ts > latest_ts:
                            latest_ts = msg_ts

                except httpx.RequestError as e:
                    logger.warning("HTTP error polling channel %s: %s", channel_id, e)
                except Exception as e:
                    logger.warning("Error polling channel %s: %s", channel_id, e)

        # Update poll state
        conn.last_poll_at = datetime.utcnow()
        if latest_ts:
            conn.last_message_ts = latest_ts
        await self.db.commit()

        return {"messages_found": total_found, "signals_created": total_created}

    # ── Internal helpers ──────────────────────────────────────────────────

    async def _get_tenant_config_id(self) -> Optional[int]:
        """Get the first active supply chain config for this tenant."""
        result = await self.db.execute(
            text("SELECT id FROM supply_chain_configs WHERE tenant_id = :tid AND is_active = true LIMIT 1"),
            {"tid": self.tenant_id},
        )
        row = result.fetchone()
        return row[0] if row else None

    async def _get_tenant_context(self, config_id: int) -> Dict[str, Any]:
        """Load product families and site names for classification context."""
        sites_result = await self.db.execute(
            text("SELECT name FROM site WHERE config_id = :c ORDER BY name"),
            {"c": config_id},
        )
        site_names = [r[0] for r in sites_result.fetchall()]

        products_result = await self.db.execute(
            text("""
                SELECT DISTINCT description FROM product_hierarchy_node
                WHERE config_id = :c AND level_name IN ('family', 'category')
                ORDER BY description
            """),
            {"c": config_id},
        )
        families = [r[0] for r in products_result.fetchall()]

        if not families:
            prod_result = await self.db.execute(
                text("SELECT DISTINCT product_name FROM product WHERE config_id = :c LIMIT 50"),
                {"c": config_id},
            )
            families = [r[0] for r in prod_result.fetchall()]

        return {"site_names": site_names, "product_families": families}

    async def _resolve_scope(
        self,
        product_refs: List[str],
        site_refs: List[str],
        config_id: int,
    ) -> Tuple[List[str], List[str]]:
        """Fuzzy-match product/site references against tenant data."""
        resolved_products = []
        resolved_sites = []

        if product_refs:
            try:
                result = await self.db.execute(
                    text("""
                        SELECT id FROM product
                        WHERE config_id = :c AND (
                            LOWER(product_name) = ANY(:refs)
                            OR LOWER(id) = ANY(:refs)
                        )
                    """),
                    {"c": config_id, "refs": [r.lower() for r in product_refs]},
                )
                resolved_products = [r[0] for r in result.fetchall()]
            except Exception:
                pass

        if site_refs:
            try:
                result = await self.db.execute(
                    text("""
                        SELECT site_key FROM site
                        WHERE config_id = :c AND (
                            LOWER(name) = ANY(:refs)
                            OR LOWER(site_key) = ANY(:refs)
                        )
                    """),
                    {"c": config_id, "refs": [r.lower() for r in site_refs]},
                )
                resolved_sites = [r[0] for r in result.fetchall()]
            except Exception:
                pass

        return resolved_products, resolved_sites

    @staticmethod
    def _ts_to_datetime(ts: str) -> datetime:
        """Convert Slack message timestamp to datetime.

        Slack timestamps are Unix epoch with microsecond decimal (e.g., "1710234567.123456").
        """
        try:
            epoch = float(ts)
            return datetime.utcfromtimestamp(epoch)
        except (ValueError, TypeError, OSError):
            return datetime.utcnow()
