"""
Executive Briefing Service — LLM-Synthesized Strategy Briefings

Collects metrics from existing platform services, synthesizes them through
Claude Sonnet (or vLLM fallback), and delivers executive briefings with
scored recommendations and interactive follow-up.

Architecture:
    BriefingDataCollector — gathers JSON "data pack" from 6 existing APIs
    ExecutiveBriefingService — orchestrates LLM synthesis, stores briefings
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.models.executive_briefing import (
    ExecutiveBriefing, BriefingFollowup, BriefingSchedule,
)
from app.services.skills.claude_client import ClaudeClient

logger = logging.getLogger(__name__)

# Path to the briefing system prompt
_PROMPT_PATH = Path(__file__).parent / "skills" / "executive_briefing" / "BRIEFING_PROMPT.md"

# Cache for loaded prompt (module-level, loaded once)
_prompt_cache: Optional[str] = None


def _load_prompt() -> str:
    """Load and cache the BRIEFING_PROMPT.md system prompt."""
    global _prompt_cache
    if _prompt_cache is None:
        _prompt_cache = _PROMPT_PATH.read_text(encoding="utf-8")
        logger.info("Loaded BRIEFING_PROMPT.md (%d chars)", len(_prompt_cache))
    return _prompt_cache


import re

def _parse_llm_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks and preamble."""
    # Try direct parse first
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Try extracting from ```json ... ``` blocks
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass

    # Try finding the outermost { ... } using brace matching
    start = text.find('{')
    if start >= 0:
        # Track the last valid closing brace at depth 0
        depth = 0
        last_close = -1
        in_string = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if escape:
                escape = False
                continue
            if c == '\\' and in_string:
                escape = True
                continue
            if c == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    last_close = i
                    break  # Found matching close

        if last_close > start:
            candidate = text[start:last_close + 1]
            try:
                return json.loads(candidate)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("JSON parse failed on extracted block (%d chars): %s", len(candidate), e)

    # Log first/last 200 chars for debugging
    logger.error(
        "Could not parse JSON from LLM response (%d chars). Start: %s ... End: %s",
        len(text), text[:200], text[-200:]
    )
    raise ValueError(f"Could not parse JSON from LLM response ({len(text)} chars)")


# ---------------------------------------------------------------------------
# Data Collector
# ---------------------------------------------------------------------------

class BriefingDataCollector:
    """
    Assembles a JSON data pack from existing platform services.

    Each data source is wrapped in try/except so partial failures produce
    a data pack with some sections populated and others marked unavailable.
    """

    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    def collect(self) -> dict:
        """Gather metrics from all sources into a structured data pack."""
        data_pack = {
            "collected_at": datetime.utcnow().isoformat(),
            "tenant_id": self.tenant_id,
            "executive_dashboard": self._collect_executive_dashboard(),
            "balanced_scorecard": self._collect_balanced_scorecard(),
            "condition_alerts": self._collect_condition_alerts(),
            "cdc_triggers": self._collect_cdc_triggers(),
            "override_effectiveness": self._collect_override_effectiveness(),
            "recent_signals": self._collect_recent_signals(),
        }
        return data_pack

    def _safe_rollback(self):
        """Rollback session after failed query to reset aborted transaction."""
        try:
            self.db.rollback()
        except Exception:
            pass

    def _collect_executive_dashboard(self) -> dict:
        """KPIs, ROI, trends, S&OP worklist from AgentPerformanceService."""
        try:
            from app.services.agent_performance_service import AgentPerformanceService
            service = AgentPerformanceService(self.db)
            data = service.get_executive_dashboard_data(self.tenant_id)
            # Truncate trends to last 6 months
            if "trends" in data and isinstance(data["trends"], list):
                data["trends"] = data["trends"][-6:]
            # Truncate worklist to top 5
            if "sop_worklist_preview" in data and isinstance(data["sop_worklist_preview"], list):
                data["sop_worklist_preview"] = data["sop_worklist_preview"][:5]
            return {"available": True, "data": data}
        except Exception as e:
            self._safe_rollback()
            logger.warning("Failed to collect executive dashboard: %s", e)
            return {"available": False, "error": str(e)}

    def _collect_balanced_scorecard(self) -> dict:
        """4-tier Gartner BSC from HierarchicalMetricsService."""
        try:
            from app.services.hierarchical_metrics_service import HierarchicalMetricsService
            service = HierarchicalMetricsService()
            data = service.get_dashboard_metrics(self.tenant_id)
            # Keep only tier summaries, not full drill-down data
            tiers = data.get("tiers", {})
            return {"available": True, "data": {"tiers": tiers}}
        except Exception as e:
            self._safe_rollback()
            logger.warning("Failed to collect balanced scorecard: %s", e)
            return {"available": False, "error": str(e)}

    def _collect_condition_alerts(self) -> dict:
        """Active CRITICAL/WARNING alerts from last 7 days."""
        try:
            from app.models.condition_alert import ConditionAlert
            cutoff = datetime.utcnow() - timedelta(days=7)
            result = self.db.execute(
                select(ConditionAlert).where(
                    ConditionAlert.tenant_id == self.tenant_id,
                    ConditionAlert.severity.in_(["critical", "warning", "emergency"]),
                    ConditionAlert.created_at >= cutoff,
                ).order_by(desc(ConditionAlert.created_at)).limit(20)
            )
            # Handle both sync and async result patterns
            try:
                alerts = result.scalars().all()
            except Exception:
                alerts = []
            return {
                "available": True,
                "data": {
                    "count": len(alerts),
                    "alerts": [
                        {
                            "id": a.id,
                            "condition_type": a.condition_type.value if hasattr(a.condition_type, 'value') else str(a.condition_type),
                            "severity": a.severity.value if hasattr(a.severity, 'value') else str(a.severity),
                            "site_key": getattr(a, 'site_key', None),
                            "product_id": getattr(a, 'product_id', None),
                            "message": getattr(a, 'message', None),
                            "created_at": a.created_at.isoformat() if a.created_at else None,
                            "resolved": getattr(a, 'resolved', False),
                        }
                        for a in alerts
                    ],
                },
            }
        except Exception as e:
            self._safe_rollback()
            logger.warning("Failed to collect condition alerts: %s", e)
            return {"available": False, "error": str(e)}

    def _collect_cdc_triggers(self) -> dict:
        """Recent CDC triggers from powell_cdc_trigger_log."""
        try:
            from sqlalchemy import text
            cutoff = datetime.utcnow() - timedelta(days=7)
            result = self.db.execute(
                text("""
                    SELECT id, site_key, severity, reasons, action_taken, created_at
                    FROM powell_cdc_trigger_log
                    WHERE created_at >= :cutoff
                    ORDER BY created_at DESC
                    LIMIT 10
                """),
                {"cutoff": cutoff},
            )
            try:
                rows = result.fetchall()
            except Exception:
                rows = []
            triggers = [
                {
                    "id": r[0],
                    "site_key": r[1],
                    "severity": r[2],
                    "reasons": r[3],
                    "action_taken": r[4],
                    "created_at": r[5].isoformat() if r[5] else None,
                }
                for r in rows
            ]
            return {"available": True, "data": {"count": len(triggers), "triggers": triggers}}
        except Exception as e:
            self._safe_rollback()
            logger.warning("Failed to collect CDC triggers: %s", e)
            return {"available": False, "error": str(e)}

    def _collect_override_effectiveness(self) -> dict:
        """Override quality metrics from performance_metrics table."""
        try:
            from sqlalchemy import text
            result = self.db.execute(
                text("""
                    SELECT category, decision_type,
                           SUM(override_count) as total_overrides,
                           AVG(override_rate) as avg_override_rate,
                           AVG(agent_score) as avg_agent_score,
                           AVG(planner_score) as avg_planner_score
                    FROM performance_metrics
                    WHERE tenant_id = :tenant_id
                    GROUP BY category, decision_type
                    ORDER BY total_overrides DESC
                    LIMIT 20
                """),
                {"tenant_id": self.tenant_id},
            )
            try:
                rows = result.fetchall()
            except Exception:
                rows = []
            summary = [
                {
                    "category": r[0],
                    "decision_type": r[1],
                    "total_overrides": r[2],
                    "avg_override_rate": round(float(r[3]), 3) if r[3] else 0,
                    "avg_agent_score": round(float(r[4]), 1) if r[4] else 0,
                    "avg_planner_score": round(float(r[5]), 1) if r[5] else 0,
                }
                for r in rows
            ]
            return {"available": True, "data": summary}
        except Exception as e:
            self._safe_rollback()
            logger.warning("Failed to collect override effectiveness: %s", e)
            return {"available": False, "error": str(e)}

    def _collect_recent_signals(self) -> dict:
        """Recent external signals from signal_ingestion table."""
        try:
            from sqlalchemy import text
            cutoff = datetime.utcnow() - timedelta(days=7)
            result = self.db.execute(
                text("""
                    SELECT signal_type, status, COUNT(*) as cnt
                    FROM signal_ingestion
                    WHERE created_at >= :cutoff
                    GROUP BY signal_type, status
                    ORDER BY cnt DESC
                    LIMIT 30
                """),
                {"cutoff": cutoff},
            )
            try:
                rows = result.fetchall()
            except Exception:
                rows = []
            signals = [
                {"signal_type": r[0], "status": r[1], "count": r[2]}
                for r in rows
            ]
            return {"available": True, "data": {"signals": signals, "total": sum(s["count"] for s in signals)}}
        except Exception as e:
            self._safe_rollback()
            logger.warning("Failed to collect recent signals: %s", e)
            return {"available": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Main Service
# ---------------------------------------------------------------------------

class ExecutiveBriefingService:
    """
    Orchestrates LLM synthesis for executive briefings.

    Uses ClaudeClient (dual Claude/vLLM backend) to generate briefings
    from collected data packs, with optional Knowledge Base context.
    """

    def __init__(self, db: Session):
        self.db = db
        self._client = ClaudeClient()

    async def generate_briefing(
        self,
        tenant_id: int,
        briefing_type: str = "adhoc",
        requested_by: Optional[int] = None,
    ) -> dict:
        """
        Full briefing pipeline: create record → collect → synthesize → store.

        Returns the briefing dict on success, or a dict with status=failed on error.
        Use this for scheduler jobs that create their own records.
        For API endpoints that pre-create the record, use run_generation() instead.
        """
        briefing = ExecutiveBriefing(
            tenant_id=tenant_id,
            requested_by=requested_by,
            briefing_type=briefing_type,
            status="pending",
        )
        self.db.add(briefing)
        self.db.flush()
        return await self.run_generation(briefing)

    async def run_generation(self, briefing: ExecutiveBriefing) -> dict:
        """
        Run generation pipeline on an existing briefing record.

        Collects data, calls LLM, updates the briefing record in place.
        """
        briefing_id = briefing.id
        tenant_id = briefing.tenant_id
        logger.info("Starting generation for briefing %d, tenant %d", briefing_id, tenant_id)

        # 1. Collect data pack (may trigger rollbacks internally)
        try:
            collector = BriefingDataCollector(self.db, tenant_id)
            data_pack = collector.collect()
        except Exception as e:
            logger.error("Briefing %d data collection failed: %s", briefing_id, e)
            data_pack = {"error": str(e), "collected_at": datetime.utcnow().isoformat()}

        # Ensure clean session after collection (rollback any poisoned transaction)
        try:
            self.db.rollback()
        except Exception:
            pass

        # Re-fetch briefing from clean session state
        briefing = self.db.query(ExecutiveBriefing).filter(
            ExecutiveBriefing.id == briefing_id
        ).first()
        if not briefing:
            logger.error("Briefing %d disappeared from DB", briefing_id)
            return {"error": "Briefing not found"}

        # Update with data pack
        briefing.data_pack = data_pack
        briefing.status = "generating"
        self.db.commit()

        # 2. Load KB context (optional, best-effort — no DB needed)
        kb_context = ""
        try:
            kb_context = await self._load_kb_context(tenant_id)
        except Exception as e:
            logger.debug("KB context unavailable (non-fatal): %s", e)
            # Rollback if KB query poisoned the session
            try:
                self.db.rollback()
            except Exception:
                pass

        # 3. Load system prompt
        system_prompt = _load_prompt()
        if kb_context:
            system_prompt = system_prompt + "\n\n" + kb_context

        # 4. Build user message
        user_message = json.dumps(data_pack, default=str)

        # 5. Call LLM (pure network call, no DB)
        updates = {}
        start_time = time.monotonic()
        try:
            response = await self._client.complete(
                system_prompt=system_prompt,
                user_message=user_message,
                model_tier="sonnet",
                temperature=0.3,
                max_tokens=4096,
            )
            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            # 6. Parse response into local dict (no DB writes yet)
            result = _parse_llm_json(response["content"])

            updates = {
                "title": result.get("title", "Executive Briefing"),
                "executive_summary": result.get("executive_summary", ""),
                "narrative": json.dumps(result.get("narrative", {})),
                "recommendations": result.get("recommendations", []),
                "model_used": response["model"],
                "tokens_used": response["tokens_used"],
                "generation_time_ms": elapsed_ms,
                "kb_context_used": kb_context[:2000] if kb_context else None,
                "status": "completed",
                "completed_at": datetime.utcnow(),
            }
            logger.info(
                "Briefing %d completed: model=%s, tokens=%d, time=%dms",
                briefing_id, response["model"], response["tokens_used"], elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            updates = {
                "status": "failed",
                "error_message": f"LLM synthesis failed: {e}",
                "generation_time_ms": elapsed_ms,
                "completed_at": datetime.utcnow(),
            }
            logger.error("Briefing %d LLM synthesis failed: %s", briefing_id, e)

        # 7. Write results to DB with clean session
        try:
            self.db.rollback()
        except Exception:
            pass
        briefing = self.db.query(ExecutiveBriefing).filter(
            ExecutiveBriefing.id == briefing_id
        ).first()
        if briefing:
            for k, v in updates.items():
                setattr(briefing, k, v)
            self.db.commit()
            self.db.refresh(briefing)
            return briefing.to_dict()

        logger.error("Briefing %d disappeared from DB after LLM call", briefing_id)
        return {"error": "Briefing not found after generation"}

    async def ask_followup(
        self,
        briefing_id: int,
        tenant_id: int,
        question: str,
        asked_by: Optional[int] = None,
    ) -> dict:
        """
        Answer a follow-up question in the context of an existing briefing.
        """
        # Load parent briefing
        result = self.db.execute(
            select(ExecutiveBriefing).where(
                ExecutiveBriefing.id == briefing_id,
                ExecutiveBriefing.tenant_id == tenant_id,
            )
        )
        briefing = result.scalars().first()
        if not briefing:
            raise ValueError(f"Briefing {briefing_id} not found for tenant {tenant_id}")

        # Load existing followups for conversation context
        result = self.db.execute(
            select(BriefingFollowup).where(
                BriefingFollowup.briefing_id == briefing_id,
            ).order_by(BriefingFollowup.created_at)
        )
        existing_followups = result.scalars().all()

        # Build system prompt
        system_prompt = (
            "You are a senior strategy advisor. You previously generated an "
            "executive briefing. The user is asking a follow-up question.\n\n"
            "Use the data pack and your previous analysis to answer concisely. "
            "Cite specific metrics. Respond in natural language (not JSON).\n\n"
            "## Previous Briefing\n"
            f"Executive Summary: {briefing.executive_summary or 'N/A'}\n"
        )
        if briefing.narrative:
            try:
                narrative = json.loads(briefing.narrative) if isinstance(briefing.narrative, str) else briefing.narrative
                for section, content in narrative.items():
                    system_prompt += f"\n### {section}\n{content}\n"
            except (json.JSONDecodeError, TypeError):
                system_prompt += f"\nNarrative: {briefing.narrative}\n"

        # Add conversation history
        if existing_followups:
            system_prompt += "\n## Previous Q&A\n"
            for fu in existing_followups:
                system_prompt += f"\nQ: {fu.question}\nA: {fu.answer}\n"

        # Build user message with data context + question
        user_message = f"Data Pack Summary:\n{json.dumps(briefing.data_pack, default=str)[:3000]}\n\nQuestion: {question}"

        # Call LLM
        try:
            response = await self._client.complete(
                system_prompt=system_prompt,
                user_message=user_message,
                model_tier="sonnet",
                temperature=0.3,
                max_tokens=2048,
            )
            answer = response["content"]
        except Exception as e:
            answer = f"I apologize, but I'm unable to answer right now due to a technical issue: {e}"
            response = {"model": "error", "tokens_used": 0}

        # Store followup
        followup = BriefingFollowup(
            briefing_id=briefing_id,
            asked_by=asked_by,
            question=question,
            answer=answer,
            model_used=response.get("model", "unknown"),
            tokens_used=response.get("tokens_used", 0),
        )
        self.db.add(followup)
        self.db.commit()
        self.db.refresh(followup)
        return followup.to_dict()

    def get_latest(self, tenant_id: int) -> Optional[dict]:
        """Get the most recent completed briefing for a tenant."""
        result = self.db.execute(
            select(ExecutiveBriefing).where(
                ExecutiveBriefing.tenant_id == tenant_id,
                ExecutiveBriefing.status == "completed",
            ).order_by(desc(ExecutiveBriefing.created_at)).limit(1)
        )
        briefing = result.scalars().first()
        return briefing.to_dict() if briefing else None

    def get_briefing(self, briefing_id: int, tenant_id: int) -> Optional[dict]:
        """Get a specific briefing by ID (with tenant isolation)."""
        result = self.db.execute(
            select(ExecutiveBriefing).where(
                ExecutiveBriefing.id == briefing_id,
                ExecutiveBriefing.tenant_id == tenant_id,
            )
        )
        briefing = result.scalars().first()
        return briefing.to_dict() if briefing else None

    def list_briefings(
        self,
        tenant_id: int,
        limit: int = 20,
        offset: int = 0,
        briefing_type: Optional[str] = None,
    ) -> list[dict]:
        """List briefings for a tenant with pagination."""
        query = select(ExecutiveBriefing).where(
            ExecutiveBriefing.tenant_id == tenant_id,
        )
        if briefing_type:
            query = query.where(ExecutiveBriefing.briefing_type == briefing_type)
        query = query.order_by(desc(ExecutiveBriefing.created_at)).offset(offset).limit(limit)

        result = self.db.execute(query)
        briefings = result.scalars().all()
        # Return summary (without full data_pack/narrative for list view)
        return [
            {
                "id": b.id,
                "briefing_type": b.briefing_type.value if isinstance(b.briefing_type, BriefingType) else b.briefing_type,
                "status": b.status.value if isinstance(b.status, BriefingStatus) else b.status,
                "title": b.title,
                "executive_summary": b.executive_summary,
                "model_used": b.model_used,
                "tokens_used": b.tokens_used,
                "generation_time_ms": b.generation_time_ms,
                "created_at": b.created_at.isoformat() if b.created_at else None,
                "completed_at": b.completed_at.isoformat() if b.completed_at else None,
                "followup_count": len(b.followups) if b.followups else 0,
            }
            for b in briefings
        ]

    def get_schedule(self, tenant_id: int) -> dict:
        """Get schedule config for a tenant, or return defaults."""
        result = self.db.execute(
            select(BriefingSchedule).where(
                BriefingSchedule.tenant_id == tenant_id,
            )
        )
        schedule = result.scalars().first()
        if schedule:
            return schedule.to_dict()
        return {
            "id": None,
            "tenant_id": tenant_id,
            "enabled": False,
            "briefing_type": "weekly",
            "cron_day_of_week": "mon",
            "cron_hour": 6,
            "cron_minute": 0,
            "created_at": None,
            "updated_at": None,
        }

    def update_schedule(self, tenant_id: int, config: dict) -> dict:
        """Upsert schedule config for a tenant."""
        result = self.db.execute(
            select(BriefingSchedule).where(
                BriefingSchedule.tenant_id == tenant_id,
            )
        )
        schedule = result.scalars().first()

        if schedule is None:
            schedule = BriefingSchedule(tenant_id=tenant_id)
            self.db.add(schedule)

        schedule.enabled = config.get("enabled", True)
        schedule.briefing_type = config.get("briefing_type", "weekly")
        schedule.cron_day_of_week = config.get("cron_day_of_week", "mon")
        schedule.cron_hour = config.get("cron_hour", 6)
        schedule.cron_minute = config.get("cron_minute", 0)

        self.db.commit()
        self.db.refresh(schedule)
        return schedule.to_dict()

    async def _load_kb_context(self, tenant_id: int) -> str:
        """Load strategic context from Knowledge Base (best-effort)."""
        try:
            from app.services.knowledge_base_service import KnowledgeBaseService
            kb_service = KnowledgeBaseService(self.db, tenant_id)
            context = await kb_service.search_for_context(
                "company strategy supply chain priorities objectives risks competitive",
                top_k=5,
                max_tokens=4000,
            )
            return context or ""
        except Exception as e:
            logger.debug("KB context retrieval failed (non-fatal): %s", e)
            return ""

    async def close(self):
        """Clean up LLM client."""
        await self._client.close()
