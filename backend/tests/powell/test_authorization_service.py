"""
Tests for AuthorizationService — production authorization protocol.

Covers: request submission, auto-resolution, counter-proposal, escalation,
SLA timeout, human resolution, query operations, and full workflows.
"""

import pytest
from datetime import datetime, timedelta

from app.models.authorization_models import (
    AuthorizationThread,
    AuthorizationRequestRecord,
    AuthorizationResponseRecord,
    AuthorizationDecision,
    AuthorizationPriority,
    ThreadStatus,
)
from app.services.authorization_service import AuthorizationService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def service():
    return AuthorizationService(db=None)


@pytest.fixture
def high_benefit_request():
    """Request with benefit well above threshold → should auto-authorize."""
    return {
        "requesting_agent": "SO_ATP",
        "target_agent": "LOGISTICS",
        "proposed_action": {"action_type": "expedite_order", "description": "Rush order #123"},
        "net_benefit": 100.0,
        "benefit_threshold": 10.0,  # 100 >> 10 * 2 = 20
        "priority": "HIGH",
        "site_key": "site_1",
        "justification": "Critical customer order at risk",
    }


@pytest.fixture
def low_benefit_request():
    """Request with benefit well below threshold → should auto-deny."""
    return {
        "requesting_agent": "INVENTORY",
        "target_agent": "LOGISTICS",
        "proposed_action": {"action_type": "cross_dc_transfer", "description": "Rebalance stock"},
        "net_benefit": 2.0,
        "benefit_threshold": 10.0,  # 2 < 10 * 0.5 = 5
        "priority": "LOW",
    }


@pytest.fixture
def borderline_request():
    """Request near threshold → requires human review (no auto-resolution)."""
    return {
        "requesting_agent": "PLANT",
        "target_agent": "FINANCE",
        "proposed_action": {"action_type": "authorize_overtime", "description": "Weekend shift"},
        "net_benefit": 12.0,
        "benefit_threshold": 10.0,  # 12 is between 5 and 20
        "priority": "MEDIUM",
    }


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TestModels:
    def test_thread_status_enum(self):
        assert len(ThreadStatus) == 7
        assert ThreadStatus.OPEN == "OPEN"
        assert ThreadStatus.ESCALATED == "ESCALATED"

    def test_decision_enum(self):
        assert len(AuthorizationDecision) == 5
        assert AuthorizationDecision.AUTHORIZE == "AUTHORIZE"

    def test_thread_to_dict(self):
        t = AuthorizationThread(
            thread_id="t1",
            requesting_agent="A",
            target_agent="B",
            status=ThreadStatus.OPEN,
        )
        d = t.to_dict()
        assert d["thread_id"] == "t1"
        assert d["status"] == "OPEN"


# ---------------------------------------------------------------------------
# Request Submission
# ---------------------------------------------------------------------------

class TestSubmitRequest:
    def test_creates_thread(self, service, borderline_request):
        thread = service.submit_request(**borderline_request)
        assert thread.thread_id is not None
        assert thread.requesting_agent == "PLANT"
        assert thread.target_agent == "FINANCE"
        assert thread.status == ThreadStatus.OPEN

    def test_sets_sla(self, service, borderline_request):
        thread = service.submit_request(**borderline_request)
        assert thread.sla_expires_at is not None
        assert thread.sla_expires_at > thread.created_at

    def test_creates_event(self, service, borderline_request):
        thread = service.submit_request(**borderline_request)
        assert len(thread.events) >= 1
        assert thread.events[0]["type"] == "request_submitted"


# ---------------------------------------------------------------------------
# Auto-Resolution
# ---------------------------------------------------------------------------

class TestAutoResolution:
    def test_high_benefit_auto_authorizes(self, service, high_benefit_request):
        thread = service.submit_request(**high_benefit_request)
        assert thread.status == ThreadStatus.ACCEPTED
        assert thread.final_decision == AuthorizationDecision.AUTHORIZE
        assert thread.resolution_source == "auto"

    def test_low_benefit_auto_denies(self, service, low_benefit_request):
        thread = service.submit_request(**low_benefit_request)
        assert thread.status == ThreadStatus.DENIED
        assert thread.final_decision == AuthorizationDecision.DENY
        assert thread.resolution_source == "auto"

    def test_borderline_stays_open(self, service, borderline_request):
        thread = service.submit_request(**borderline_request)
        assert thread.status == ThreadStatus.OPEN
        assert thread.final_decision is None

    def test_zero_threshold_no_auto(self, service):
        thread = service.submit_request(
            requesting_agent="A",
            target_agent="B",
            proposed_action={"action_type": "test"},
            net_benefit=50,
            benefit_threshold=0,
        )
        assert thread.status == ThreadStatus.OPEN


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class TestResponses:
    def test_authorize_resolves_thread(self, service, borderline_request):
        thread = service.submit_request(**borderline_request)
        response = service.respond(
            thread.thread_id, "AUTHORIZE", reason="Approved", responding_agent="FINANCE",
        )
        assert response.decision == AuthorizationDecision.AUTHORIZE
        assert thread.status == ThreadStatus.ACCEPTED
        assert thread.is_resolved

    def test_deny_resolves_thread(self, service, borderline_request):
        thread = service.submit_request(**borderline_request)
        service.respond(thread.thread_id, "DENY", reason="Insufficient budget")
        assert thread.status == ThreadStatus.DENIED
        assert thread.is_resolved

    def test_respond_to_nonexistent(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.respond("bad_id", "AUTHORIZE")

    def test_respond_to_resolved(self, service, high_benefit_request):
        thread = service.submit_request(**high_benefit_request)
        # Already auto-resolved
        with pytest.raises(ValueError, match="already resolved"):
            service.respond(thread.thread_id, "DENY")


# ---------------------------------------------------------------------------
# Counter-Proposal
# ---------------------------------------------------------------------------

class TestCounterProposal:
    def test_counter_propose(self, service, borderline_request):
        thread = service.submit_request(**borderline_request)
        response = service.counter_propose(
            thread.thread_id,
            counter_proposal={"action_type": "partial_overtime", "hours": 4},
            reason="Approve half shift only",
        )
        assert response.decision == AuthorizationDecision.COUNTER_OFFER
        assert thread.status == ThreadStatus.COUNTER_OFFERED

    def test_counter_propose_nonexistent(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.counter_propose("bad_id")


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------

class TestEscalation:
    def test_escalate_thread(self, service, borderline_request):
        thread = service.submit_request(**borderline_request)
        service.escalate(thread.thread_id, escalated_to="human_planner")
        assert thread.status == ThreadStatus.ESCALATED

    def test_escalate_nonexistent(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.escalate("bad_id")


# ---------------------------------------------------------------------------
# Human Resolution
# ---------------------------------------------------------------------------

class TestHumanResolution:
    def test_resolve_by_human(self, service, borderline_request):
        thread = service.submit_request(**borderline_request)
        service.resolve(
            thread.thread_id,
            decision="AUTHORIZE",
            reason="Approved after review",
            resolved_by="jane.doe",
        )
        assert thread.status == ThreadStatus.ACCEPTED
        assert thread.resolution_source == "human"
        assert thread.final_decision == AuthorizationDecision.AUTHORIZE

    def test_resolve_nonexistent(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.resolve("bad_id", "AUTHORIZE")


# ---------------------------------------------------------------------------
# SLA Timeout
# ---------------------------------------------------------------------------

class TestSLATimeout:
    def test_expired_thread_detected(self, service, borderline_request):
        thread = service.submit_request(**borderline_request)
        # Force expiry
        thread.sla_expires_at = datetime.utcnow() - timedelta(minutes=1)
        service._save_thread(thread)

        expired = service.check_sla_timeouts()
        assert len(expired) == 1
        assert expired[0].thread_id == thread.thread_id
        assert thread.status == ThreadStatus.ESCALATED

    def test_non_expired_not_escalated(self, service, borderline_request):
        thread = service.submit_request(**borderline_request)
        # SLA is in the future
        expired = service.check_sla_timeouts()
        assert len(expired) == 0
        assert thread.status == ThreadStatus.OPEN


# ---------------------------------------------------------------------------
# Query Operations
# ---------------------------------------------------------------------------

class TestQueryOperations:
    def test_get_pending(self, service, borderline_request, high_benefit_request):
        service.submit_request(**borderline_request)  # stays open
        service.submit_request(**high_benefit_request)  # auto-resolved
        pending = service.get_pending()
        assert len(pending) == 1

    def test_get_pending_by_site(self, service):
        service.submit_request(
            requesting_agent="A", target_agent="B",
            proposed_action={"action_type": "test"},
            site_key="site_1",
        )
        service.submit_request(
            requesting_agent="C", target_agent="D",
            proposed_action={"action_type": "test"},
            site_key="site_2",
        )
        pending_1 = service.get_pending(site_key="site_1")
        assert len(pending_1) == 1

    def test_get_thread(self, service, borderline_request):
        thread = service.submit_request(**borderline_request)
        found = service.get_thread(thread.thread_id)
        assert found is not None
        assert found.thread_id == thread.thread_id

    def test_get_stats(self, service, borderline_request, high_benefit_request, low_benefit_request):
        service.submit_request(**borderline_request)
        service.submit_request(**high_benefit_request)
        service.submit_request(**low_benefit_request)
        stats = service.get_stats()
        assert stats["total"] == 3
        assert stats["active_threads"] == 1
        assert stats["resolved_threads"] == 2
        assert stats["auto_resolved"] == 2


# ---------------------------------------------------------------------------
# Full Workflow
# ---------------------------------------------------------------------------

class TestFullWorkflow:
    def test_submit_counter_resolve(self, service):
        """Submit → counter-propose → accept counter → resolve."""
        thread = service.submit_request(
            requesting_agent="PLANT",
            target_agent="FINANCE",
            proposed_action={"action_type": "overtime", "hours": 8},
            net_benefit=12,
            benefit_threshold=10,
            priority="MEDIUM",
        )
        assert thread.status == ThreadStatus.OPEN

        # Finance counter-proposes
        service.counter_propose(
            thread.thread_id,
            counter_proposal={"action_type": "partial_overtime", "hours": 4},
            reason="Budget constraint",
        )
        assert thread.status == ThreadStatus.COUNTER_OFFERED

        # Human resolves
        service.resolve(
            thread.thread_id,
            decision="AUTHORIZE",
            reason="Approved partial overtime",
            resolved_by="manager",
        )
        assert thread.status == ThreadStatus.ACCEPTED
        assert thread.resolution_source == "human"

    def test_submit_escalate_resolve(self, service):
        """Submit → escalate → human resolve."""
        thread = service.submit_request(
            requesting_agent="SO_ATP",
            target_agent="LOGISTICS",
            proposed_action={"action_type": "expedite"},
            net_benefit=15,
            benefit_threshold=10,
        )

        service.escalate(thread.thread_id, reason="Need VP approval")
        assert thread.status == ThreadStatus.ESCALATED

        service.resolve(thread.thread_id, "DENY", reason="Not justified", resolved_by="vp")
        assert thread.status == ThreadStatus.DENIED
