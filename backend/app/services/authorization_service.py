"""
Authorization Service — Production-grade service for Agentic Authorization Protocol.

Replaces the in-memory demo in authorization_protocol.py with a service that
supports both DB-backed persistence and in-memory operation (for testing).

Key features:
- Net benefit threshold auto-resolution
- SLA tracking with auto-escalation
- Counter-proposal workflow
- Human escalation with pre-digested options
- Audit trail via events

Auto-resolution thresholds:
- net_benefit > 2× threshold → auto-AUTHORIZE
- net_benefit < 0.5× threshold → auto-DENY
- 0.5× to 2× → requires human review

Architecture reference: AGENTIC_AUTHORIZATION_PROTOCOL.md
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from app.models.authorization_models import (
    AuthorizationThread,
    AuthorizationRequestRecord,
    AuthorizationResponseRecord,
    AuthorizationDecision,
    AuthorizationPriority,
    ThreadStatus,
)
from app.services.authorization_protocol import AgentRole, ActionCategory

logger = logging.getLogger(__name__)

# SLA durations by priority
SLA_DURATIONS: Dict[str, timedelta] = {
    "CRITICAL": timedelta(minutes=15),
    "HIGH": timedelta(hours=1),
    "MEDIUM": timedelta(hours=4),
    "LOW": timedelta(hours=24),
    "ROUTINE": timedelta(hours=48),
}


class AuthorizationService:
    """Production authorization service with auto-resolution and SLA tracking.

    Supports both DB-backed and in-memory operation.

    Args:
        db: Optional SQLAlchemy session. When None, uses in-memory store.
    """

    def __init__(self, db=None):
        self.db = db
        # In-memory store (used when db is None)
        self._threads: Dict[str, AuthorizationThread] = {}
        self._requests: Dict[str, AuthorizationRequestRecord] = {}
        self._responses: List[AuthorizationResponseRecord] = []

    # ------------------------------------------------------------------
    # Submit & Evaluate
    # ------------------------------------------------------------------

    def submit_request(
        self,
        requesting_agent: str,
        target_agent: str,
        proposed_action: Dict[str, Any],
        balanced_scorecard: Optional[Dict[str, Any]] = None,
        net_benefit: float = 0.0,
        benefit_threshold: float = 0.0,
        justification: Optional[str] = None,
        evidence: Optional[Dict[str, Any]] = None,
        priority: str = "MEDIUM",
        site_key: Optional[str] = None,
        scenario_id: Optional[int] = None,
    ) -> AuthorizationThread:
        """Submit a new authorization request.

        Creates a thread and request record, then attempts auto-resolution.

        Args:
            requesting_agent: Agent role making the request.
            target_agent: Agent role being asked.
            proposed_action: Action details dict.
            balanced_scorecard: Optional BSC for the proposed action.
            net_benefit: Net benefit score from BSC.
            benefit_threshold: Threshold for auto-resolution.
            justification: Text justification.
            evidence: Supporting evidence dict.
            priority: Priority level string.
            site_key: Optional site identifier.
            scenario_id: Optional planning scenario ID.

        Returns:
            The created AuthorizationThread.
        """
        thread_id = str(uuid.uuid4())[:16]
        request_id = str(uuid.uuid4())[:16]

        priority_enum = AuthorizationPriority(priority)
        sla_duration = SLA_DURATIONS.get(priority, timedelta(hours=4))

        # Create thread
        thread = AuthorizationThread(
            thread_id=thread_id,
            requesting_agent=requesting_agent,
            target_agent=target_agent,
            site_key=site_key,
            status=ThreadStatus.OPEN,
            priority=priority_enum,
            created_at=datetime.utcnow(),
            sla_expires_at=datetime.utcnow() + sla_duration,
            net_benefit=net_benefit,
            benefit_threshold=benefit_threshold,
            events=[{
                "type": "request_submitted",
                "timestamp": datetime.utcnow().isoformat(),
                "agent": requesting_agent,
            }],
        )

        # Create request record
        request = AuthorizationRequestRecord(
            request_id=request_id,
            thread_id=thread_id,
            proposed_action=proposed_action,
            balanced_scorecard=balanced_scorecard,
            net_benefit=net_benefit,
            benefit_threshold=benefit_threshold,
            justification=justification,
            evidence=evidence,
            priority=priority_enum,
            scenario_id=scenario_id,
            created_at=datetime.utcnow(),
        )

        self._persist_thread(thread)
        self._persist_request(request)

        # Attempt auto-resolution
        auto_decision = self._evaluate_auto_resolve(net_benefit, benefit_threshold)
        if auto_decision is not None:
            self._auto_resolve(thread, auto_decision)

        return thread

    def evaluate_request(self, thread_id: str) -> Optional[AuthorizationDecision]:
        """Re-evaluate a thread for auto-resolution.

        Args:
            thread_id: Thread to evaluate.

        Returns:
            AuthorizationDecision if auto-resolved, None otherwise.
        """
        thread = self._get_thread(thread_id)
        if thread is None or thread.is_resolved:
            return None

        decision = self._evaluate_auto_resolve(
            thread.net_benefit or 0, thread.benefit_threshold or 0,
        )
        if decision is not None:
            self._auto_resolve(thread, decision)
        return decision

    # ------------------------------------------------------------------
    # Responses
    # ------------------------------------------------------------------

    def respond(
        self,
        thread_id: str,
        decision: str,
        reason: Optional[str] = None,
        responding_agent: Optional[str] = None,
        counter_proposal: Optional[Dict[str, Any]] = None,
        counter_scenario_id: Optional[int] = None,
        contention_details: Optional[Dict[str, Any]] = None,
    ) -> AuthorizationResponseRecord:
        """Add a response to a thread.

        Args:
            thread_id: Thread to respond to.
            decision: Decision string (AUTHORIZE, DENY, COUNTER_OFFER, ESCALATE).
            reason: Explanation text.
            responding_agent: Agent making the response.
            counter_proposal: Optional counter-proposal dict.
            counter_scenario_id: Optional scenario ID for counter.
            contention_details: Optional resource conflict details.

        Returns:
            The created AuthorizationResponseRecord.

        Raises:
            ValueError: If thread not found or already resolved.
        """
        thread = self._get_thread(thread_id)
        if thread is None:
            raise ValueError(f"Thread {thread_id} not found")
        if thread.is_resolved:
            raise ValueError(f"Thread {thread_id} already resolved")

        decision_enum = AuthorizationDecision(decision)
        response_id = str(uuid.uuid4())[:16]

        response = AuthorizationResponseRecord(
            response_id=response_id,
            thread_id=thread_id,
            decision=decision_enum,
            reason=reason,
            responding_agent=responding_agent,
            counter_proposal=counter_proposal,
            counter_scenario_id=counter_scenario_id,
            contention_details=contention_details,
            responded_at=datetime.utcnow(),
        )

        self._persist_response(response)

        # Update thread status based on decision
        if decision_enum == AuthorizationDecision.AUTHORIZE:
            self._resolve_thread(thread, decision_enum, "agent")
        elif decision_enum == AuthorizationDecision.DENY:
            self._resolve_thread(thread, decision_enum, "agent")
        elif decision_enum == AuthorizationDecision.COUNTER_OFFER:
            thread.status = ThreadStatus.COUNTER_OFFERED
            self._add_event(thread, "counter_offered", responding_agent)
            self._save_thread(thread)
        elif decision_enum == AuthorizationDecision.ESCALATE:
            thread.status = ThreadStatus.ESCALATED
            self._add_event(thread, "escalated", responding_agent)
            self._save_thread(thread)

        return response

    def counter_propose(
        self,
        thread_id: str,
        counter_scenario_id: Optional[int] = None,
        counter_proposal: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
    ) -> AuthorizationResponseRecord:
        """Submit a counter-proposal for a thread.

        Args:
            thread_id: Thread ID.
            counter_scenario_id: Optional alternative scenario.
            counter_proposal: Counter-proposal details.
            reason: Explanation.

        Returns:
            AuthorizationResponseRecord with COUNTER_OFFER decision.
        """
        thread = self._get_thread(thread_id)
        if thread is None:
            raise ValueError(f"Thread {thread_id} not found")

        return self.respond(
            thread_id=thread_id,
            decision="COUNTER_OFFER",
            reason=reason,
            responding_agent=thread.target_agent,
            counter_proposal=counter_proposal,
            counter_scenario_id=counter_scenario_id,
        )

    def escalate(
        self,
        thread_id: str,
        escalated_to: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> AuthorizationThread:
        """Escalate a thread for human review.

        Args:
            thread_id: Thread to escalate.
            escalated_to: Target for escalation (e.g., "human_planner").
            reason: Reason for escalation.

        Returns:
            Updated AuthorizationThread.

        Raises:
            ValueError: If thread not found.
        """
        thread = self._get_thread(thread_id)
        if thread is None:
            raise ValueError(f"Thread {thread_id} not found")

        self.respond(
            thread_id=thread_id,
            decision="ESCALATE",
            reason=reason or "Escalated for human review",
            responding_agent=thread.target_agent,
        )

        return thread

    def resolve(
        self,
        thread_id: str,
        decision: str,
        reason: Optional[str] = None,
        resolved_by: Optional[str] = None,
    ) -> AuthorizationThread:
        """Manually resolve a thread (typically by human).

        Args:
            thread_id: Thread to resolve.
            decision: Final decision (AUTHORIZE or DENY).
            reason: Resolution reason.
            resolved_by: Who resolved (human identifier).

        Returns:
            Updated AuthorizationThread.

        Raises:
            ValueError: If thread not found.
        """
        thread = self._get_thread(thread_id)
        if thread is None:
            raise ValueError(f"Thread {thread_id} not found")

        decision_enum = AuthorizationDecision(decision)
        source = "human" if resolved_by else "agent"

        # Create resolution response record (before resolving, to avoid
        # is_resolved guard in respond())
        if reason:
            response_id = str(uuid.uuid4())[:16]
            response = AuthorizationResponseRecord(
                response_id=response_id,
                thread_id=thread_id,
                decision=decision_enum,
                reason=reason,
                responding_agent=resolved_by or "system",
                responded_at=datetime.utcnow(),
            )
            self._persist_response(response)

        self._resolve_thread(thread, decision_enum, source)
        return thread

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_pending(self, site_key: Optional[str] = None) -> List[AuthorizationThread]:
        """Get all pending (unresolved) threads.

        Args:
            site_key: Optional filter by site.

        Returns:
            List of pending AuthorizationThread objects.
        """
        threads = self._all_threads()
        pending = [t for t in threads if not t.is_resolved]
        if site_key:
            pending = [t for t in pending if t.site_key == site_key]
        return pending

    def get_thread(self, thread_id: str) -> Optional[AuthorizationThread]:
        """Get a thread by ID."""
        return self._get_thread(thread_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get aggregated authorization statistics."""
        threads = self._all_threads()
        resolved = [t for t in threads if t.is_resolved]
        active = [t for t in threads if not t.is_resolved]

        decisions = {}
        for t in resolved:
            d = t.final_decision.value if t.final_decision else "UNKNOWN"
            decisions[d] = decisions.get(d, 0) + 1

        auto_resolved = sum(1 for t in resolved if t.resolution_source == "auto")
        escalated = sum(1 for t in threads if t.status == ThreadStatus.ESCALATED)

        return {
            "active_threads": len(active),
            "resolved_threads": len(resolved),
            "auto_resolved": auto_resolved,
            "escalated": escalated,
            "decisions_by_type": decisions,
            "total": len(threads),
        }

    # ------------------------------------------------------------------
    # SLA Enforcement
    # ------------------------------------------------------------------

    def check_sla_timeouts(self) -> List[AuthorizationThread]:
        """Check all open threads for SLA expiry and auto-escalate.

        Returns:
            List of threads that were escalated due to timeout.
        """
        expired = []
        for thread in self._all_threads():
            if thread.is_expired and not thread.is_resolved:
                thread.status = ThreadStatus.ESCALATED
                self._add_event(thread, "sla_timeout", "system")
                self._save_thread(thread)
                expired.append(thread)
                logger.warning(
                    f"Authorization thread {thread.thread_id} expired SLA, "
                    f"escalating ({thread.requesting_agent} → {thread.target_agent})"
                )
        return expired

    # ------------------------------------------------------------------
    # Auto-resolution logic
    # ------------------------------------------------------------------

    def _evaluate_auto_resolve(
        self,
        net_benefit: float,
        benefit_threshold: float,
        margin_high: float = 2.0,
        margin_low: float = 0.5,
    ) -> Optional[AuthorizationDecision]:
        """Determine if a request can be auto-resolved.

        - net_benefit > threshold * margin_high → auto-AUTHORIZE
        - net_benefit < threshold * margin_low → auto-DENY
        - else → None (human review)
        """
        if benefit_threshold <= 0:
            return None

        if net_benefit > benefit_threshold * margin_high:
            return AuthorizationDecision.AUTHORIZE
        elif net_benefit < benefit_threshold * margin_low:
            return AuthorizationDecision.DENY
        return None

    def _auto_resolve(self, thread: AuthorizationThread, decision: AuthorizationDecision):
        """Auto-resolve a thread."""
        self._resolve_thread(thread, decision, "auto")
        logger.info(
            f"Auto-resolved thread {thread.thread_id}: {decision.value} "
            f"(benefit={thread.net_benefit}, threshold={thread.benefit_threshold})"
        )

    def _resolve_thread(
        self,
        thread: AuthorizationThread,
        decision: AuthorizationDecision,
        source: str,
    ):
        """Mark a thread as resolved."""
        if decision == AuthorizationDecision.AUTHORIZE:
            thread.status = ThreadStatus.ACCEPTED
        elif decision == AuthorizationDecision.DENY:
            thread.status = ThreadStatus.DENIED
        else:
            thread.status = ThreadStatus.RESOLVED

        thread.final_decision = decision
        thread.resolution_source = source
        thread.resolved_at = datetime.utcnow()
        self._add_event(thread, f"resolved_{decision.value.lower()}", source)
        self._save_thread(thread)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_event(self, thread: AuthorizationThread, event_type: str, agent: str):
        if thread.events is None:
            thread.events = []
        thread.events.append({
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "agent": agent,
        })

    # ------------------------------------------------------------------
    # Persistence (in-memory or DB)
    # ------------------------------------------------------------------

    def _persist_thread(self, thread: AuthorizationThread):
        if self.db is not None:
            self.db.add(thread)
            self.db.flush()
        else:
            self._threads[thread.thread_id] = thread

    def _save_thread(self, thread: AuthorizationThread):
        if self.db is not None:
            self.db.add(thread)
            self.db.flush()
        else:
            self._threads[thread.thread_id] = thread

    def _persist_request(self, request: AuthorizationRequestRecord):
        if self.db is not None:
            self.db.add(request)
            self.db.flush()
        else:
            self._requests[request.request_id] = request

    def _persist_response(self, response: AuthorizationResponseRecord):
        if self.db is not None:
            self.db.add(response)
            self.db.flush()
        else:
            self._responses.append(response)

    def _get_thread(self, thread_id: str) -> Optional[AuthorizationThread]:
        if self.db is not None:
            return (
                self.db.query(AuthorizationThread)
                .filter(AuthorizationThread.thread_id == thread_id)
                .first()
            )
        return self._threads.get(thread_id)

    def _all_threads(self) -> List[AuthorizationThread]:
        if self.db is not None:
            return self.db.query(AuthorizationThread).all()
        return list(self._threads.values())

    # ------------------------------------------------------------------
    # Agent Authorization with Authority Boundaries
    # ------------------------------------------------------------------

    def create_agent_authorization_request(
        self,
        agent_role: str,
        action_type: str,
        site_key: str,
        proposed_action: Optional[Dict[str, Any]] = None,
        net_benefit: float = 0.0,
        benefit_threshold: float = 0.0,
        justification: Optional[str] = None,
        evidence: Optional[Dict[str, Any]] = None,
        priority: str = "MEDIUM",
    ) -> Dict[str, Any]:
        """Create an authorization request using authority boundaries.

        Looks up the agent's authority boundary, classifies the action,
        and either auto-authorizes (UNILATERAL), routes to the correct
        target (REQUIRES_AUTHORIZATION), or rejects (FORBIDDEN).

        Returns:
            Dict with 'category', 'decision', and optionally 'thread'.
        """
        from app.services.powell.authority_boundaries import (
            check_action_category,
            get_required_target,
        )

        try:
            role = AgentRole(agent_role)
        except ValueError:
            return {"category": "unknown_role", "decision": "DENY", "reason": f"Unknown role: {agent_role}"}

        category = check_action_category(role, action_type)

        if category == ActionCategory.UNILATERAL:
            logger.info(f"UNILATERAL: {agent_role}/{action_type} at {site_key}")
            return {
                "category": "unilateral",
                "decision": "AUTHORIZE",
                "reason": "Action is within agent's unilateral authority",
            }

        if category == ActionCategory.FORBIDDEN:
            logger.warning(f"FORBIDDEN: {agent_role}/{action_type} at {site_key}")
            return {
                "category": "forbidden",
                "decision": "DENY",
                "reason": "Action is forbidden for this agent role",
            }

        # REQUIRES_AUTHORIZATION — route to target agent
        target = get_required_target(role, action_type)
        target_agent = target.target_agent.value if target else "unknown"
        sla_minutes = target.sla_minutes if target else 240

        # Auto-approve if no contention and flag is set
        if target and target.auto_approve_if_no_contention and net_benefit > benefit_threshold:
            logger.info(
                f"AUTO-APPROVE (no contention): {agent_role}/{action_type} → {target_agent}"
            )
            return {
                "category": "requires_authorization",
                "decision": "AUTHORIZE",
                "reason": f"Auto-approved (no contention, net_benefit={net_benefit:.2f})",
                "target_agent": target_agent,
            }

        # Create thread via submit_request
        thread = self.submit_request(
            requesting_agent=agent_role,
            target_agent=target_agent,
            proposed_action=proposed_action or {"action_type": action_type},
            net_benefit=net_benefit,
            benefit_threshold=benefit_threshold,
            justification=justification,
            evidence=evidence,
            priority=priority,
            site_key=site_key,
        )

        decision = None
        if thread.final_decision:
            decision = thread.final_decision.value

        return {
            "category": "requires_authorization",
            "decision": decision,
            "thread_id": thread.thread_id,
            "target_agent": target_agent,
            "sla_minutes": sla_minutes,
            "status": thread.status.value if thread.status else None,
        }

    def escalate_to_human(
        self,
        thread_id: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Escalate a thread for human review and format for OpenClaw.

        Returns:
            Formatted escalation dict from EscalationFormatter.
        """
        thread = self._get_thread(thread_id)
        if thread is None:
            raise ValueError(f"Thread {thread_id} not found")

        # Mark as escalated
        self.escalate(thread_id, reason=reason)

        # Format for human delivery
        try:
            from app.services.escalation_formatter import EscalationFormatter
            from app.services.hive_what_if_engine import HiveWhatIfEngine

            engine = HiveWhatIfEngine(
                site_key=getattr(thread, "site_key", "default") or "default"
            )
            formatter = EscalationFormatter(what_if_engine=engine)
            return formatter.format_escalation(thread)
        except Exception as e:
            logger.warning(f"Escalation formatting failed: {e}")
            return {
                "type": "authorization_escalation",
                "thread_id": thread_id,
                "summary": f"Authorization requires human review: {reason or 'No details'}",
                "escalation_reason": reason or "Escalated for human review",
            }
