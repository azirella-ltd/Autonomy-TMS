"""
Governance Sweeper Jobs — Auto-apply and Escalation for INSPECT Decisions

Two APScheduler jobs:
  1. Auto-Apply Sweeper (every 5 min): Execute or expire INSPECT decisions
     past their hold_until deadline.
  2. Escalation Checker (every 30 min): Flag stale INSPECT decisions that
     have been pending longer than escalate_after_minutes.
  3. Directive Expiry (hourly): Expire GuardrailDirectives past effective_until.

Follows the APScheduler pattern from relearning_jobs.py.
"""

import logging
from datetime import datetime

from sqlalchemy import and_
from apscheduler.triggers.cron import CronTrigger

from app.db.session import SessionLocal
from app.models.agent_action import AgentAction, ActionMode, ExecutionResult
from app.models.decision_governance import DecisionGovernancePolicy, GuardrailDirective

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job registration
# ---------------------------------------------------------------------------

def register_governance_jobs(scheduler_service: 'SyncSchedulerService') -> None:
    """Register governance sweeper jobs with the scheduler."""
    scheduler = scheduler_service._scheduler

    scheduler.add_job(
        func=_run_auto_apply_sweeper,
        trigger=CronTrigger(minute="*/5"),  # Every 5 minutes
        id="governance_auto_apply_sweeper",
        name="Governance: Auto-apply expired INSPECT decisions",
        replace_existing=True,
        misfire_grace_time=300,
    )
    logger.info("Registered governance auto-apply sweeper (every 5 min)")

    scheduler.add_job(
        func=_run_escalation_checker,
        trigger=CronTrigger(minute="*/30"),  # Every 30 minutes
        id="governance_escalation_checker",
        name="Governance: Escalate stale INSPECT decisions",
        replace_existing=True,
        misfire_grace_time=1800,
    )
    logger.info("Registered governance escalation checker (every 30 min)")

    scheduler.add_job(
        func=_run_directive_expiry,
        trigger=CronTrigger(minute=50),  # Hourly at :50
        id="governance_directive_expiry",
        name="Governance: Expire past-due guardrail directives",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info("Registered governance directive expiry (hourly at :50)")


# ---------------------------------------------------------------------------
# Job implementations
# ---------------------------------------------------------------------------

def _run_auto_apply_sweeper():
    """
    Auto-apply or expire INSPECT decisions past their hold_until deadline.

    For each expired decision:
      - If policy.auto_apply_on_expiry = True → execution_result = SUCCESS
      - If policy.auto_apply_on_expiry = False → execution_result = FAILED
    """
    db = SessionLocal()
    try:
        now = datetime.utcnow()

        expired = db.query(AgentAction).filter(
            AgentAction.action_mode == ActionMode.INSPECT,
            AgentAction.execution_result == ExecutionResult.PENDING,
            AgentAction.hold_until != None,
            AgentAction.hold_until < now,
        ).all()

        if not expired:
            return

        auto_applied = 0
        expired_count = 0

        for action in expired:
            # Look up the policy to check auto_apply_on_expiry
            policy = None
            if action.governance_policy_id:
                policy = db.query(DecisionGovernancePolicy).filter_by(
                    id=action.governance_policy_id,
                ).first()

            auto_apply = policy.auto_apply_on_expiry if policy else True

            if auto_apply:
                action.execution_result = ExecutionResult.SUCCESS
                action.resolution_reason = "Auto-applied: review window expired"
                auto_applied += 1
            else:
                action.execution_result = ExecutionResult.FAILED
                action.resolution_reason = "Expired: review window elapsed without response"
                expired_count += 1

        db.commit()
        logger.info(
            "Governance sweeper: auto-applied=%d expired=%d",
            auto_applied, expired_count,
        )

    except Exception as e:
        logger.error("Governance auto-apply sweeper failed: %s", e)
        db.rollback()
    finally:
        db.close()


def _run_escalation_checker():
    """
    Flag INSPECT decisions that have been pending too long without response.

    Looks up the policy's escalate_after_minutes and sets escalated_at
    on decisions that exceed the threshold.
    """
    db = SessionLocal()
    try:
        now = datetime.utcnow()

        # Get all pending INSPECT decisions that haven't been escalated yet
        pending = db.query(AgentAction).filter(
            AgentAction.action_mode == ActionMode.INSPECT,
            AgentAction.execution_result == ExecutionResult.PENDING,
            AgentAction.escalated_at == None,
        ).all()

        if not pending:
            return

        escalated = 0
        for action in pending:
            # Determine escalation threshold
            escalate_minutes = 480  # Default 8 hours
            if action.governance_policy_id:
                policy = db.query(DecisionGovernancePolicy).filter_by(
                    id=action.governance_policy_id,
                ).first()
                if policy:
                    escalate_minutes = policy.escalate_after_minutes

            # Check if past escalation threshold
            if action.created_at:
                age_minutes = (now - action.created_at).total_seconds() / 60.0
                if age_minutes >= escalate_minutes:
                    action.escalated_at = now
                    escalated += 1

        if escalated > 0:
            db.commit()
            logger.info("Governance escalation: flagged %d decisions", escalated)

    except Exception as e:
        logger.error("Governance escalation checker failed: %s", e)
        db.rollback()
    finally:
        db.close()


def _run_directive_expiry():
    """
    Expire GuardrailDirectives past their effective_until date.

    Only affects APPLIED directives (PENDING ones don't have effective_until
    enforced until they're applied).
    """
    db = SessionLocal()
    try:
        now = datetime.utcnow()

        expired = db.query(GuardrailDirective).filter(
            GuardrailDirective.status == "APPLIED",
            GuardrailDirective.effective_until != None,
            GuardrailDirective.effective_until < now,
        ).all()

        if not expired:
            return

        for directive in expired:
            directive.status = "EXPIRED"

        db.commit()
        logger.info("Governance directive expiry: expired %d directives", len(expired))

    except Exception as e:
        logger.error("Governance directive expiry failed: %s", e)
        db.rollback()
    finally:
        db.close()
