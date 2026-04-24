"""
agent_decisions dual-write helper for TMS TRMs.

PREPARE.3 write-path: every TMS TRM's `evaluate_and_log` call goes
through `record_trm_decision()` to land a single canonical row in
`core.agent_decisions`. This unblocks Decision Stream visibility,
Agent Performance dashboards, and override tracking — all of which
read from `agent_decisions` as the system of record.

Design notes:

- **AIIO doctrine — ACTIONED by default.** Agents Always Act; the
  human inspects selectively. Even HOLD / REJECT is an action the
  agent took. We always write with status=ACTIONED and let Decision
  Stream + OverrideClassifier re-classify downstream as needed.

- **Non-fatal on errors.** If the write fails (transient DB issue,
  mapper error, foreign-key collision during tests) we log at
  ERROR and continue — TRM evaluation must never fail because the
  audit-trail write failed. The caller gets `None` back.

- **Urgency bucketing.** Decision's `urgency` float is bucketed into
  the `DecisionUrgency` enum: ≥0.7 URGENT, ≥0.3 STANDARD, else LOW.

- **Context payload.** Full TRM scoring detail goes into
  `context_data` JSON so downstream analytics / debugging can
  reconstruct the decision without re-running the heuristic.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# TRM type → Core DecisionType enum value (uses the canonical mapping
# already in planning_cascade.py; keep these aligned)
_TRM_TO_DECISION_TYPE = {
    "capacity_promise": "CAPACITY_PROMISE",
    "shipment_tracking": "SHIPMENT_TRACKING",
    "demand_sensing": "DEMAND_SENSING",
    "capacity_buffer": "CAPACITY_BUFFER",
    "exception_management": "EXCEPTION_MANAGEMENT",
    "freight_procurement": "FREIGHT_PROCUREMENT",
    "broker_routing": "BROKER_ROUTING",
    "dock_scheduling": "DOCK_SCHEDULING",
    "load_build": "LOAD_BUILD",
    "intermodal_transfer": "INTERMODAL_TRANSFER",
    "equipment_reposition": "EQUIPMENT_REPOSITION",
}

# TRM service agent_version identifier — matches docs/TRM reference
_AGENT_TYPE = "tms_trm"


def _bucket_urgency(urgency_float: Optional[float]) -> str:
    """Bucket [0,1] urgency into URGENT / STANDARD / LOW."""
    from app.models.decision_tracking import DecisionUrgency
    u = float(urgency_float or 0.0)
    if u >= 0.7:
        return DecisionUrgency.URGENT
    if u >= 0.3:
        return DecisionUrgency.STANDARD
    return DecisionUrgency.LOW


def record_trm_decision(
    db: Session,
    *,
    tenant_id: int,
    trm_type: str,
    result: Dict[str, Any],
    item_code: str,
    item_name: Optional[str] = None,
    category: Optional[str] = None,
    impact_value: Optional[float] = None,
    impact_description: Optional[str] = None,
) -> Optional[int]:
    """Write one AgentDecision row per TRM evaluation.

    Args:
        db: sync SQLAlchemy session (commits on this session).
        tenant_id: tenant owning the trigger entity.
        trm_type: canonical key (e.g. "demand_sensing"). See
            `_TRM_TO_DECISION_TYPE` for the full set.
        result: the TRM service's `evaluate_and_log` / `evaluate_*`
            return dict. Must contain at least `action_name`,
            `reasoning`, `confidence`, `urgency`. All other fields
            flow into `context_data`.
        item_code: stable identifier for the trigger entity
            (e.g. f"load-{load_id}", f"target-{target_id}", etc.).
        item_name: human-readable name (load_number, shipment_number,
            lane label, etc.). Defaults to item_code.
        category: optional category/grouping label for analytics.
        impact_value / impact_description: business-impact metadata
            (cost delta, units, etc.). Propagated to `impact_*` columns
            on AgentDecision.

    Returns:
        The new AgentDecision.id on success, None on failure (failure
        is logged but never raised — TRM evaluation must not fail
        because the audit write failed).
    """
    try:
        from app.models.decision_tracking import (
            AgentDecision, DecisionType, DecisionStatus,
        )
    except Exception as e:  # pragma: no cover
        logger.error("AgentDecision import failed; skipping dual-write: %s", e)
        return None

    decision_type_name = _TRM_TO_DECISION_TYPE.get(trm_type)
    if not decision_type_name:
        logger.warning(
            "record_trm_decision: unknown trm_type %r; skipping dual-write",
            trm_type,
        )
        return None
    try:
        decision_type = DecisionType[decision_type_name]
    except KeyError:
        # Enum doesn't yet include this value (shouldn't happen post
        # 2026-04-15 backfill, but be defensive).
        logger.warning(
            "record_trm_decision: DecisionType.%s not in enum; skipping",
            decision_type_name,
        )
        return None

    action_name = str(result.get("action_name", "UNKNOWN"))
    reasoning = str(result.get("reasoning") or "")
    confidence = float(result.get("confidence") or 0.0)
    urgency_float = float(result.get("urgency") or 0.0)
    quantity = result.get("quantity") or result.get("proposed_quantity") \
        or result.get("proposed_buffer_loads") or result.get("proposed_forecast") \
        or result.get("hours_late")

    # Build a compact agent_recommendation string for the Decision Stream
    recommendation = action_name
    try:
        if quantity is not None and not isinstance(quantity, bool):
            quantity_float = float(quantity)
            if quantity_float != 0.0:
                recommendation = f"{action_name} ({quantity_float:+.2f})"
    except (TypeError, ValueError):
        pass

    # Strip transient objects from the scoring_detail before JSON-izing
    scoring_detail = result.get("scoring_detail") or {}
    context_payload: Dict[str, Any] = {
        "trm_type": trm_type,
        "action_name": action_name,
        "scoring_detail": scoring_detail,
    }
    for k, v in result.items():
        if k in {"reasoning", "confidence", "urgency", "scoring_detail"}:
            continue
        # Only primitive JSON-safe types go into context_data; skip the rest
        if isinstance(v, (str, int, float, bool)) or v is None:
            context_payload[k] = v

    try:
        row = AgentDecision(
            tenant_id=tenant_id,
            decision_type=decision_type,
            item_code=item_code[:50],
            item_name=(item_name or item_code)[:200],
            category=category[:100] if category else None,
            issue_summary=reasoning[:65000] or f"{action_name} — {trm_type}",
            impact_value=impact_value,
            impact_description=impact_description[:255] if impact_description else None,
            agent_recommendation=recommendation[:65000],
            agent_reasoning=reasoning[:65000] or None,
            agent_confidence=confidence,
            recommended_value=(
                float(quantity) if (
                    quantity is not None
                    and not isinstance(quantity, bool)
                    and isinstance(quantity, (int, float))
                ) else None
            ),
            status=DecisionStatus.ACTIONED,
            urgency=_bucket_urgency(urgency_float),
            agent_type=_AGENT_TYPE,
            agent_version=f"{trm_type}_v1",
            context_data=context_payload,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return int(row.id)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(
            "record_trm_decision: dual-write failed for %s (%s): %s",
            trm_type, item_code, e,
        )
        return None
    except Exception as e:  # pragma: no cover
        db.rollback()
        logger.error(
            "record_trm_decision: unexpected error for %s (%s): %s",
            trm_type, item_code, e,
        )
        return None
