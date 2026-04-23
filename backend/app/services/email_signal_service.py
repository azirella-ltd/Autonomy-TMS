"""
Email Signal Service — Ingest, Classify, and Route Email-Derived SC Signals

Pipeline:
  1. Receive raw email (from IMAP/Gmail connector or manual paste)
  2. PII scrub — strip names, emails, phones; extract sender domain
  3. Resolve domain → TradingPartner (company identification, GDPR-safe)
  4. LLM classification — extract signal type, direction, magnitude, urgency
  5. Scope resolution — fuzzy-match product/site references against tenant data
  6. Route to TRM — create ForecastAdjustmentState or equivalent for relevant TRMs
  7. Surface in Decision Stream as actionable alert

Emails are a SIGNAL SOURCE for existing TRMs (especially ForecastAdjustmentTRM),
not a new decision type. This follows the same pattern as directive_service.py.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_signal import (
    EmailSignal, EmailConnection, SIGNAL_TYPES, SIGNAL_TRM_ROUTING,
)

logger = logging.getLogger(__name__)


# ── LLM classification prompt ───────────────────────────────────────────────

_CLASSIFY_SYSTEM_PROMPT = """You are a supply chain email signal classifier for the Autonomy platform.

Your job: analyze a PII-scrubbed email from a trading partner (customer or supplier) and
extract a structured supply chain signal.

The email is from company "{partner_name}" ({partner_type}).
Available product families in this tenant: {product_families}
Available site/region names in this tenant: {site_names}

Analyze the email and return JSON with these fields:
{{
  "signal_type": one of {signal_types},
  "direction": "up" | "down" | "no_change" | null,
  "magnitude_pct": float or null (estimated % impact, e.g. 15.0 for "15% increase"),
  "confidence": float 0-1 (how clearly this is a supply chain signal vs general comms),
  "urgency": float 0-1 (how time-sensitive: 0=informational, 0.5=routine, 0.8=urgent, 1.0=critical),
  "summary": "1-2 sentence plain English summary of the supply chain signal",
  "product_refs": [list of product/family names mentioned, from tenant's product list] or [],
  "site_refs": [list of site/region names mentioned, from tenant's site list] or [],
  "time_horizon_weeks": integer or null (estimated duration of impact),
  "target_trm_types": [list from: forecast_adjustment, inventory_buffer, po_creation, to_execution, quality_disposition, mo_execution, maintenance_scheduling, order_tracking, atp_executor] or []
}}

Rules:
- "general_inquiry" is for emails that don't contain actionable SC intelligence
- Set confidence LOW (<0.4) for ambiguous emails; HIGH (>0.7) for clear demand/supply signals
- Urgency reflects time sensitivity: disruption notification = high, FYI = low
- Product/site refs should ONLY contain items from the provided tenant lists
- If no specific products or sites mentioned, leave the lists empty
- Return ONLY valid JSON, no markdown
"""


class EmailSignalService:
    """Ingest, classify, and route email-derived supply chain signals."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest_email(
        self,
        tenant_id: int,
        config_id: int,
        connection_id: Optional[int],
        email_uid: str,
        from_header: str,
        subject: str,
        body: str,
        received_at: datetime,
    ) -> EmailSignal:
        """Full pipeline: scrub → resolve partner → classify → persist → route.

        Args:
            from_header: Raw From: header (e.g., "John Smith <john@acme.com>").
                         Personal identity is extracted for domain resolution only
                         and is NEVER persisted.
        """
        from app.services.email_pii_scrubber import scrub_email, scrub_subject

        # 1. Check for duplicate
        existing = await self.db.execute(
            select(EmailSignal).where(
                and_(
                    EmailSignal.tenant_id == tenant_id,
                    EmailSignal.email_uid == email_uid,
                )
            )
        )
        if existing.scalar_one_or_none():
            logger.debug("Duplicate email_uid=%s, skipping", email_uid)
            return None

        # 2. PII scrub
        scrub_result = scrub_email(body, from_header)
        scrubbed_subject = scrub_subject(subject)

        # 3. Resolve domain → TradingPartner
        partner_info = await self._resolve_partner(
            scrub_result.sender_domain, tenant_id, config_id,
        )

        # 4. Check domain allowlist/blocklist
        if connection_id:
            conn = await self.db.get(EmailConnection, connection_id)
            if conn:
                if conn.domain_allowlist and scrub_result.sender_domain not in conn.domain_allowlist:
                    logger.debug("Domain %s not in allowlist, skipping", scrub_result.sender_domain)
                    return None
                if conn.domain_blocklist and scrub_result.sender_domain in conn.domain_blocklist:
                    logger.debug("Domain %s in blocklist, skipping", scrub_result.sender_domain)
                    return None

        # 5. Classify with LLM
        tenant_context = await self._get_tenant_context(config_id)
        classification = await self._classify_email(
            scrub_result.scrubbed_text,
            scrubbed_subject,
            partner_info.get("name", scrub_result.sender_domain),
            partner_info.get("type", "unknown"),
            tenant_context,
        )

        # 6. Resolve product/site scope
        resolved_products, resolved_sites = await self._resolve_scope(
            classification.get("product_refs", []),
            classification.get("site_refs", []),
            config_id,
        )

        # 7. Determine TRM routing
        signal_type = classification.get("signal_type", "general_inquiry")
        target_trms = classification.get("target_trm_types") or SIGNAL_TRM_ROUTING.get(signal_type, [])

        # 8. Persist
        signal = EmailSignal(
            tenant_id=tenant_id,
            config_id=config_id,
            connection_id=connection_id,
            email_uid=email_uid,
            received_at=received_at,
            subject_scrubbed=scrubbed_subject,
            body_scrubbed=scrub_result.scrubbed_text,
            sender_domain=scrub_result.sender_domain,
            resolved_partner_id=partner_info.get("id"),
            partner_type=partner_info.get("type"),
            partner_name=partner_info.get("name"),
            signal_type=signal_type,
            signal_direction=classification.get("direction"),
            signal_magnitude_pct=classification.get("magnitude_pct"),
            signal_confidence=classification.get("confidence", 0.5),
            signal_urgency=classification.get("urgency", 0.5),
            signal_summary=classification.get("summary", "Email signal"),
            resolved_product_ids=resolved_products if resolved_products else None,
            resolved_site_ids=resolved_sites if resolved_sites else None,
            time_horizon_weeks=classification.get("time_horizon_weeks"),
            target_trm_types=target_trms if target_trms else None,
            status="CLASSIFIED",
            classified_at=datetime.utcnow(),
        )
        self.db.add(signal)
        await self.db.flush()

        # 9. Auto-route if confidence is high enough
        confidence = classification.get("confidence", 0)
        min_confidence = 0.6
        if connection_id:
            conn = await self.db.get(EmailConnection, connection_id)
            if conn:
                min_confidence = conn.min_confidence_to_route
                if not conn.auto_route_enabled:
                    min_confidence = 999  # Disable auto-routing

        if confidence >= min_confidence and target_trms:
            await self._route_signal(signal)

        await self.db.commit()

        logger.info(
            "Email signal ingested: id=%d, type=%s, partner=%s, confidence=%.2f, urgency=%.2f",
            signal.id, signal.signal_type, signal.partner_name or signal.sender_domain,
            signal.signal_confidence, signal.signal_urgency,
        )
        return signal

    async def _resolve_partner(
        self, domain: str, tenant_id: int, config_id: int,
    ) -> Dict[str, Any]:
        """Resolve sender domain to a TradingPartner.

        Resolution strategy:
          1. Exact domain substring match against trading_partners.description
          2. Company name fuzzy match from domain (acme-corp.com → "ACME")
          3. Return domain as fallback name if no match
        """
        # Extract company hint from domain (strip TLD and common suffixes)
        domain_parts = domain.split(".")
        company_hint = domain_parts[0] if domain_parts else domain
        company_hint = company_hint.replace("-", " ").replace("_", " ")

        # Try matching against TradingPartner
        try:
            result = await self.db.execute(
                text("""
                    SELECT id, tpartner_type, description
                    FROM trading_partners
                    WHERE company_id IN (
                        SELECT id FROM company WHERE id IN (
                            SELECT company_id FROM site WHERE config_id = :config_id
                        )
                    )
                    AND (
                        LOWER(description) LIKE :domain_pattern
                        OR LOWER(description) LIKE :hint_pattern
                    )
                    LIMIT 1
                """),
                {
                    "config_id": config_id,
                    "domain_pattern": f"%{domain.split('.')[0].lower()}%",
                    "hint_pattern": f"%{company_hint.lower()}%",
                },
            )
            row = result.fetchone()
            if row:
                return {
                    "id": row[0],
                    "type": row[1],
                    "name": row[2],
                }
        except Exception as e:
            logger.debug("TradingPartner lookup failed: %s", e)

        return {
            "id": None,
            "type": "unknown",
            "name": company_hint.title(),
        }

    async def _classify_email(
        self,
        scrubbed_body: str,
        scrubbed_subject: str,
        partner_name: str,
        partner_type: str,
        tenant_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Classify email content using LLM (Haiku tier)."""
        system_prompt = _CLASSIFY_SYSTEM_PROMPT.format(
            partner_name=partner_name,
            partner_type=partner_type,
            product_families=json.dumps(tenant_context.get("product_families", [])),
            site_names=json.dumps(tenant_context.get("site_names", [])),
            signal_types=json.dumps(SIGNAL_TYPES),
        )

        user_prompt = f"Subject: {scrubbed_subject}\n\n{scrubbed_body}"

        try:
            from app.services.skills.claude_client import ClaudeClient
            client = ClaudeClient()
            response = await client.invoke(
                system=system_prompt,
                user_prompt=user_prompt,
                model_tier="haiku",
            )
            return json.loads(response)
        except Exception as e:
            logger.warning("LLM email classification failed, using heuristic: %s", e)
            return self._heuristic_classify(scrubbed_body, scrubbed_subject, partner_type)

    def _heuristic_classify(
        self, body: str, subject: str, partner_type: str,
    ) -> Dict[str, Any]:
        """Fallback classification when LLM is unavailable."""
        combined = (subject + " " + body).lower()

        # Signal type detection
        signal_type = "general_inquiry"
        direction = None
        urgency = 0.3

        if any(w in combined for w in ["shortage", "disruption", "force majeure", "unable to supply", "allocation"]):
            signal_type = "supply_disruption"
            direction = "down"
            urgency = 0.9
        elif any(w in combined for w in ["delay", "lead time", "extended delivery", "pushed back"]):
            signal_type = "lead_time_change"
            direction = "up"
            urgency = 0.7
        elif any(w in combined for w in ["price increase", "surcharge", "cost increase", "rate increase"]):
            signal_type = "price_change"
            direction = "up"
            urgency = 0.6
        elif any(w in combined for w in ["quality", "defect", "recall", "non-conformance", "reject"]):
            signal_type = "quality_issue"
            urgency = 0.8
        elif any(w in combined for w in ["increase order", "additional volume", "more units", "rush order"]):
            signal_type = "demand_increase"
            direction = "up"
            urgency = 0.6
        elif any(w in combined for w in ["cancel", "reduce order", "fewer units", "postpone"]):
            signal_type = "demand_decrease"
            direction = "down"
            urgency = 0.6
        elif any(w in combined for w in ["new product", "launch", "introduction"]):
            signal_type = "new_product"
            urgency = 0.5
        elif any(w in combined for w in ["discontinue", "end of life", "eol", "phase out"]):
            signal_type = "discontinuation"
            direction = "down"
            urgency = 0.6
        elif any(w in combined for w in ["capacity", "shutdown", "maintenance window"]):
            signal_type = "capacity_change"
            direction = "down"
            urgency = 0.7

        # Extract magnitude hint
        import re
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
            "summary": f"{'Supplier' if partner_type == 'vendor' else 'Customer'} email classified as {signal_type.replace('_', ' ')}",
            "product_refs": [],
            "site_refs": [],
            "time_horizon_weeks": None,
            "target_trm_types": target_trms,
        }

    async def _route_signal(self, signal: EmailSignal) -> None:
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
        # TMS DemandSensingTRM is the transport-plane analog
        # (adjusts ShippingForecast.forecast_loads, not SKU-level demand).
        # Email-signal → DemandSensingTRM routing is item 1.13 scope.
        if "forecast_adjustment" in trm_types:
            logger.debug(
                "Email signal %d targets forecast_adjustment — SCP-fork TRM retired; "
                "TMS DemandSensingTRM routing pending (item 1.13).",
                signal.id,
            )

        signal.routed_decision_ids = decision_ids if decision_ids else None
        logger.info(
            "Email signal %d routed to %d TRMs, %d decisions created",
            signal.id, len(trm_types), len(decision_ids),
        )

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

    # ── Query methods ────────────────────────────────────────────────────────

    async def get_signals(
        self,
        tenant_id: int,
        config_id: Optional[int] = None,
        status: Optional[str] = None,
        signal_type: Optional[str] = None,
        partner_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[EmailSignal]:
        """Get email signals with optional filters."""
        conditions = [EmailSignal.tenant_id == tenant_id]
        if config_id:
            conditions.append(EmailSignal.config_id == config_id)
        if status:
            conditions.append(EmailSignal.status == status)
        if signal_type:
            conditions.append(EmailSignal.signal_type == signal_type)
        if partner_type:
            conditions.append(EmailSignal.partner_type == partner_type)

        stmt = (
            select(EmailSignal)
            .where(and_(*conditions))
            .order_by(EmailSignal.received_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_dashboard_stats(self, tenant_id: int) -> Dict[str, Any]:
        """Get summary statistics for the email signals dashboard."""
        # Count by status
        status_result = await self.db.execute(
            text("""
                SELECT status, COUNT(*) FROM email_signals
                WHERE tenant_id = :tid
                GROUP BY status
            """),
            {"tid": tenant_id},
        )
        by_status = {r[0]: r[1] for r in status_result.fetchall()}

        # Count by signal type
        type_result = await self.db.execute(
            text("""
                SELECT signal_type, COUNT(*) FROM email_signals
                WHERE tenant_id = :tid
                GROUP BY signal_type
                ORDER BY COUNT(*) DESC
            """),
            {"tid": tenant_id},
        )
        by_type = {r[0]: r[1] for r in type_result.fetchall()}

        # Count by partner
        partner_result = await self.db.execute(
            text("""
                SELECT COALESCE(partner_name, sender_domain), partner_type, COUNT(*)
                FROM email_signals
                WHERE tenant_id = :tid
                GROUP BY COALESCE(partner_name, sender_domain), partner_type
                ORDER BY COUNT(*) DESC
                LIMIT 10
            """),
            {"tid": tenant_id},
        )
        top_partners = [
            {"name": r[0], "type": r[1], "count": r[2]}
            for r in partner_result.fetchall()
        ]

        # Average confidence and urgency
        avg_result = await self.db.execute(
            text("""
                SELECT AVG(signal_confidence), AVG(signal_urgency), COUNT(*)
                FROM email_signals
                WHERE tenant_id = :tid
            """),
            {"tid": tenant_id},
        )
        avg_row = avg_result.fetchone()

        # Signals in last 24h
        recent_result = await self.db.execute(
            text("""
                SELECT COUNT(*) FROM email_signals
                WHERE tenant_id = :tid AND ingested_at > NOW() - INTERVAL '24 hours'
            """),
            {"tid": tenant_id},
        )
        recent_count = recent_result.scalar() or 0

        return {
            "total": avg_row[2] if avg_row else 0,
            "last_24h": recent_count,
            "avg_confidence": round(avg_row[0], 3) if avg_row and avg_row[0] else 0,
            "avg_urgency": round(avg_row[1], 3) if avg_row and avg_row[1] else 0,
            "by_status": by_status,
            "by_type": by_type,
            "top_partners": top_partners,
        }

    async def dismiss_signal(
        self, signal_id: int, tenant_id: int, user_id: int, reason: str,
    ) -> Optional[EmailSignal]:
        """Dismiss a signal (human determined it's not actionable)."""
        signal = await self.db.get(EmailSignal, signal_id)
        if not signal or signal.tenant_id != tenant_id:
            return None
        signal.status = "DISMISSED"
        signal.dismissed_by = user_id
        signal.dismiss_reason = reason
        await self.db.commit()
        return signal
