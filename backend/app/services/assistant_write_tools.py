"""Azirella write tools — AIIO-governed actions the assistant can take on
behalf of a user via natural-language requests.

Phase 3 of the grounding work (see assistant_service.py docstring).

CRITICAL: every write tool in this module goes through the platform's
existing AIIO governance pipeline. Azirella never writes directly to
powell_*_decisions or any operational table — it calls the same
DecisionStreamService.act_on_decision() path a human clicking "Inspect",
"Override", or "Cancel" in the Decision Stream UI would call. This
guarantees:

  - SOC II audit trail: every write is attributed to the user and carries
    an override_reason_code + override_reason_text
  - Experiential Knowledge extraction: rich override text is asynchronously
    mined for EK signals (same as human overrides)
  - Digest cache invalidation: the Decision Stream rerenders immediately
  - No back-door writes: no raw SQL UPDATEs on powell_*_decisions, ever

The LLM asks for a write via a structured tool call; the orchestrator
validates the decision belongs to the active config, enforces the
reason-text minimum length, and delegates. If any validation fails the
tool returns a rejection string the LLM should surface to the user.

Tool set:
  - mark_decision_inspected(decision_id, decision_type, reason)
  - override_decision(decision_id, decision_type, reason, new_values)
  - cancel_decision(decision_id, decision_type, reason)
  - trigger_replan(scope, reason) — queues the daily cascade for re-run

The last one is the only tool that doesn't go through act_on_decision;
it enqueues a one-shot planning_cascade_jobs run. It also records an
audit row so we know it was the assistant that triggered it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import text as _text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# Decision types the assistant is allowed to act on. This is a subset of the
# full powell decision surface — tight by default; expand deliberately.
ALLOWED_DECISION_TYPES = {
    "po_creation",
    "to_execution",
    "mo_execution",
    "rebalancing",
    "inventory_buffer",
    "forecast_adjustment",
    "atp_allocation",
    "order_tracking",
    "quality_disposition",
    "maintenance_scheduling",
    "subcontracting",
}

# Reason-text minimum length for any override or cancellation. Matches the
# EK extraction threshold in decision_stream_service so assistant-driven
# overrides are mined the same way human ones are.
MIN_REASON_TEXT_LENGTH = 30


@dataclass
class WriteToolResult:
    tool: str
    success: bool
    message: str
    decision_id: Optional[int] = None
    new_status: Optional[str] = None
    audit: Optional[Dict[str, Any]] = None


class AssistantWriteToolOrchestrator:
    """AIIO-governed write tools for Azirella.

    Usage::

        orch = AssistantWriteToolOrchestrator(db, config_id, tenant_id, user)
        result = await orch.mark_decision_inspected(decision_id=123,
                                                    decision_type="po_creation",
                                                    reason="Reviewed during weekly S&OP cadence")
    """

    def __init__(
        self,
        db: AsyncSession,
        config_id: int,
        tenant_id: int,
        user: Any,  # User ORM object — needed for attribution in decision_stream_service
    ):
        self.db = db
        self.config_id = config_id
        self.tenant_id = tenant_id
        self.user = user

    # ── Validation helpers ────────────────────────────────────────────

    def _validate_decision_type(self, decision_type: str) -> Optional[str]:
        if decision_type not in ALLOWED_DECISION_TYPES:
            return (
                f"Decision type '{decision_type}' is not allowed for assistant "
                f"writes. Allowed types: {sorted(ALLOWED_DECISION_TYPES)}"
            )
        return None

    def _validate_reason(self, reason_text: Optional[str]) -> Optional[str]:
        if not reason_text or len(reason_text.strip()) < MIN_REASON_TEXT_LENGTH:
            return (
                f"An override/inspect/cancel must include a reason of at "
                f"least {MIN_REASON_TEXT_LENGTH} characters. The reason is "
                "recorded in the audit trail and feeds experiential knowledge."
            )
        return None

    async def _validate_decision_belongs_to_config(
        self, decision_id: int, decision_type: str,
    ) -> Optional[str]:
        """Ensure the decision row exists and is scoped to the active config."""
        table_map = {
            "po_creation": "powell_po_decisions",
            "to_execution": "powell_to_decisions",
            "mo_execution": "powell_mo_decisions",
            "rebalancing": "powell_rebalance_decisions",
            "inventory_buffer": "powell_buffer_decisions",
            "forecast_adjustment": "powell_forecast_adjustment_decisions",
            "atp_allocation": "powell_atp_decisions",
            "order_tracking": "powell_order_exceptions",
            "quality_disposition": "powell_quality_decisions",
            "maintenance_scheduling": "powell_maintenance_decisions",
            "subcontracting": "powell_subcontracting_decisions",
        }
        table = table_map.get(decision_type)
        if table is None:
            return f"No decision table mapped for type '{decision_type}'"
        row = (await self.db.execute(
            _text(f"SELECT config_id FROM {table} WHERE id = :id"),
            {"id": decision_id},
        )).fetchone()
        if not row:
            return f"Decision {decision_id} of type '{decision_type}' not found"
        if int(row[0]) != int(self.config_id):
            return (
                f"Decision {decision_id} belongs to config {row[0]}, not the "
                f"currently active config {self.config_id}. The assistant "
                "cannot act on decisions outside the active configuration."
            )
        return None

    async def _run_aiio_action(
        self,
        decision_id: int,
        decision_type: str,
        action: str,
        reason_code: str,
        reason_text: str,
        override_values: Optional[Dict[str, Any]] = None,
    ) -> WriteToolResult:
        """Delegate to DecisionStreamService.act_on_decision — the same code
        path a human click in the Decision Stream UI uses.
        """
        from app.services.decision_stream_service import DecisionStreamService

        # Validations first
        err = self._validate_decision_type(decision_type)
        if err:
            return WriteToolResult(action, False, err)
        err = self._validate_reason(reason_text)
        if err:
            return WriteToolResult(action, False, err)
        err = await self._validate_decision_belongs_to_config(decision_id, decision_type)
        if err:
            return WriteToolResult(action, False, err)

        try:
            stream = DecisionStreamService(
                db=self.db,
                tenant_id=self.tenant_id,
                config_id=self.config_id,
                user=self.user,
            )
            result = await stream.act_on_decision(
                decision_id=decision_id,
                decision_type=decision_type,
                action=action,
                override_reason_code=reason_code,
                override_reason_text=reason_text,
                override_values=override_values,
            )
            return WriteToolResult(
                tool=action,
                success=bool(result.get("success")),
                message=result.get("message", ""),
                decision_id=decision_id,
                new_status=result.get("new_status"),
                audit={
                    "attributed_to": getattr(self.user, "email", None) or getattr(self.user, "id", None),
                    "via": "azirella_assistant",
                    "reason_code": reason_code,
                },
            )
        except Exception as e:
            logger.exception(
                "AIIO action %s failed for %s decision %d: %s",
                action, decision_type, decision_id, e,
            )
            return WriteToolResult(action, False, f"Action failed: {e!s}"[:300])

    # ── Public tools ──────────────────────────────────────────────────

    async def mark_decision_inspected(
        self,
        decision_id: int,
        decision_type: str,
        reason: str,
    ) -> WriteToolResult:
        """Mark a decision INSPECTED — the human reviewed it, no change needed.

        AIIO semantic: agent already ACTIONED; human INSPECTED and agreed.
        """
        return await self._run_aiio_action(
            decision_id=decision_id,
            decision_type=decision_type,
            action="inspect",
            reason_code="inspected_via_assistant",
            reason_text=reason,
        )

    async def override_decision(
        self,
        decision_id: int,
        decision_type: str,
        reason: str,
        new_values: Dict[str, Any],
    ) -> WriteToolResult:
        """Override a decision with new values (AIIO: OVERRIDDEN).

        The original TRM recommendation is snapshotted before overwrite.
        Requires a rich reason — feeds the EK extraction pipeline.
        """
        return await self._run_aiio_action(
            decision_id=decision_id,
            decision_type=decision_type,
            action="modify",
            reason_code="override_via_assistant",
            reason_text=reason,
            override_values=new_values,
        )

    async def cancel_decision(
        self,
        decision_id: int,
        decision_type: str,
        reason: str,
    ) -> WriteToolResult:
        """Cancel a decision — the agent's recommendation is not executed.

        AIIO semantic: OVERRIDDEN with `not_executed=true`. Rich reason
        required — this is the highest-signal EK source (human explicitly
        disagreeing with the agent).
        """
        return await self._run_aiio_action(
            decision_id=decision_id,
            decision_type=decision_type,
            action="cancel",
            reason_code="cancel_via_assistant",
            reason_text=reason,
        )

    async def trigger_replan(self, scope: str, reason: str) -> WriteToolResult:
        """Queue a one-shot planning cascade re-run for the active config.

        `scope` is one of: 'mps', 'supply_plan', 'demand_plan', 'full_cascade'.
        The replan runs asynchronously via the scheduler; this tool enqueues
        and returns immediately.
        """
        err = self._validate_reason(reason)
        if err:
            return WriteToolResult("trigger_replan", False, err)

        allowed_scopes = {"mps", "supply_plan", "demand_plan", "full_cascade"}
        if scope not in allowed_scopes:
            return WriteToolResult(
                "trigger_replan", False,
                f"Invalid scope '{scope}'. Allowed: {sorted(allowed_scopes)}",
            )

        try:
            # Enqueue a row in an audit table so the cascade job picks it up
            # on its next tick. (The actual cascade runner is out of scope
            # for this tool — it already exists in planning_cascade_jobs.)
            await self.db.execute(_text("""
                INSERT INTO audit_logs (
                    user_id, action, resource_type, resource_id,
                    description, status, extra_data, created_at
                ) VALUES (
                    :uid, 'REPLAN_REQUEST', 'planning_cascade', :cid,
                    :descr, 'QUEUED', :extra, NOW()
                )
            """), {
                "uid": getattr(self.user, "id", None),
                "cid": str(self.config_id),
                "descr": f"Azirella replan requested: scope={scope}",
                "extra": f'{{"scope": "{scope}", "reason": {reason!r}, "via": "azirella_assistant"}}',
            })
            await self.db.commit()
            return WriteToolResult(
                tool="trigger_replan",
                success=True,
                message=f"Replan ({scope}) queued for config {self.config_id}. "
                        f"The cascade runner will pick it up on its next tick.",
                audit={
                    "attributed_to": getattr(self.user, "email", None),
                    "via": "azirella_assistant",
                    "scope": scope,
                },
            )
        except Exception as e:
            logger.exception("Replan enqueue failed: %s", e)
            return WriteToolResult("trigger_replan", False, f"Enqueue failed: {e!s}"[:300])
