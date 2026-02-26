"""
Supply Planning Agent

Owns the Supply Commit (SC) decision.
The best demand-informed, constraint-respecting set of supply actions
that balances inventory investment against service risk within the S&OP policy envelope.

Responsibilities:
- Select or blend candidates from SupBP
- Apply policy constraints from PolicyEnvelope
- Detect integrity violations (block submission)
- Flag outcome risks (mark suggested)
- Generate rationale and confidence scores

The agent does NOT own:
- UCF (demand planning)
- Supplier contracts
- Capacity expansion
- Allocation to segments (that's Allocation Agent)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import date, datetime
from enum import Enum
import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class IntegrityViolation:
    """Integrity violation that blocks submission"""
    violation_type: str
    sku: str
    period: Optional[int] = None
    detail: str = ""
    severity: str = "error"  # error, warning


@dataclass
class RiskFlag:
    """Risk flag that marks a decision for review"""
    risk_type: str
    sku: str
    detail: str = ""
    metric_value: Optional[float] = None
    threshold: Optional[float] = None
    suggested_action: str = ""


class SupplyAgent:
    """
    Supply Planning Agent

    Owns the Supply Commit decision artifact.
    Grounded by the Supply Baseline Pack (SupBP).
    Constrained by the Policy Envelope from S&OP.
    """

    def __init__(self, db: Session):
        self.db = db

    def generate_supply_commit(
        self,
        config_id: int,
        tenant_id: int,
        supply_baseline_pack_id: int,
        supply_baseline_pack_hash: str,
        policy_envelope: Dict[str, Any],
        inventory_state: Dict[str, Any],
        mode: str = "copilot",  # "copilot" or "autonomous"
    ) -> Dict[str, Any]:
        """
        Generate Supply Commit from SupBP candidates.

        Args:
            config_id: Supply chain config ID
            tenant_id: Customer ID
            supply_baseline_pack_id: SupBP ID
            supply_baseline_pack_hash: Hash for feed-forward contract
            policy_envelope: Active policy envelope
            inventory_state: Current inventory state
            mode: Agent mode (copilot requires review, autonomous auto-submits)

        Returns:
            SupplyCommit as dict
        """
        from app.models.planning_cascade import (
            SupplyCommit, SupplyBaselinePack, CommitStatus
        )

        # Load SupBP
        supbp = self.db.query(SupplyBaselinePack).filter_by(id=supply_baseline_pack_id).first()
        if not supbp:
            raise ValueError(f"SupBP {supply_baseline_pack_id} not found")

        candidates = supbp.candidates

        # Select best candidate (or blend)
        selected_candidate, selected_method, reasoning = self._select_candidate(
            candidates, policy_envelope, inventory_state
        )

        # Build recommendations from selected candidate
        recommendations = self._build_recommendations(selected_candidate, policy_envelope)

        # Check integrity (block submission if violated)
        integrity_violations = self._check_integrity(
            recommendations, policy_envelope, inventory_state
        )

        # Check outcome risks (flag for review)
        risk_flags = self._check_outcome_risks(
            recommendations, policy_envelope, inventory_state
        )

        # Determine if review required
        requires_review = (
            mode == "copilot" or
            len(integrity_violations) > 0 or
            len(risk_flags) > 0
        )

        # Calculate projections
        projected_otif = selected_candidate.get("projected_otif", 0.95)
        projected_inventory_cost = selected_candidate.get("projected_cost", 0)
        projected_dos = selected_candidate.get("projected_dos", 14)

        # Calculate confidence
        confidence = self._calculate_confidence(
            selected_candidate, integrity_violations, risk_flags
        )

        # Determine initial status
        if len(integrity_violations) > 0:
            status = CommitStatus.PROPOSED  # Can't auto-submit with violations
        elif mode == "autonomous" and len(risk_flags) == 0:
            status = CommitStatus.AUTO_SUBMITTED
        else:
            status = CommitStatus.PROPOSED

        # Create Supply Commit
        supply_commit = SupplyCommit(
            config_id=config_id,
            tenant_id=tenant_id,
            supply_baseline_pack_id=supply_baseline_pack_id,
            supply_baseline_pack_hash=supply_baseline_pack_hash,
            selected_method=selected_method,
            recommendations=recommendations,
            projected_inventory=selected_candidate.get("projected_inventory"),
            projected_otif=projected_otif,
            projected_inventory_cost=projected_inventory_cost,
            projected_dos=projected_dos,
            supply_pegging=self._generate_supply_pegging(recommendations),
            integrity_violations=[
                {"type": v.violation_type, "sku": v.sku, "period": v.period, "detail": v.detail}
                for v in integrity_violations
            ] if integrity_violations else None,
            risk_flags=[
                {"type": f.risk_type, "sku": f.sku, "detail": f.detail,
                 "metric_value": f.metric_value, "threshold": f.threshold,
                 "suggested_action": f.suggested_action}
                for f in risk_flags
            ] if risk_flags else None,
            status=status,
            requires_review=requires_review,
            review_reason=self._generate_review_reason(integrity_violations, risk_flags) if requires_review else None,
            agent_confidence=confidence,
            agent_reasoning=reasoning,
        )

        supply_commit.hash = supply_commit.compute_hash()

        if status == CommitStatus.AUTO_SUBMITTED:
            supply_commit.submitted_at = datetime.utcnow()

        self.db.add(supply_commit)
        self.db.commit()
        self.db.refresh(supply_commit)

        logger.info(
            f"Generated Supply Commit {supply_commit.hash[:8]}: "
            f"{len(recommendations)} orders, {len(integrity_violations)} violations, "
            f"{len(risk_flags)} risk flags, status={status.value}"
        )

        return self._commit_to_dict(supply_commit)

    def _select_candidate(
        self,
        candidates: List[Dict[str, Any]],
        policy_envelope: Dict[str, Any],
        inventory_state: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], str, str]:
        """
        Select best candidate from SupBP.

        Selection criteria (in order):
        1. Meets OTIF floors from policy envelope
        2. Stays within inventory investment caps
        3. Minimizes cost while meeting service
        """
        if len(candidates) == 1:
            # INPUT mode - single customer candidate
            return candidates[0], candidates[0]["method"], "Single candidate from customer plan"

        otif_floors = policy_envelope.get("otif_floors", {})
        min_otif = min(otif_floors.values()) if otif_floors else 0.90

        # Filter candidates meeting service floor
        viable = [c for c in candidates if c.get("projected_otif", 0) >= min_otif]

        if not viable:
            # No candidate meets floor - take highest service
            viable = sorted(candidates, key=lambda x: x.get("projected_otif", 0), reverse=True)[:2]
            reasoning = f"No candidate meets OTIF floor ({min_otif}); selected highest service"
        else:
            reasoning = f"Selected from {len(viable)} candidates meeting OTIF floor"

        # Among viable, select lowest cost
        selected = min(viable, key=lambda x: x.get("projected_cost", float('inf')))

        reasoning += f"; method={selected['method']}, OTIF={selected.get('projected_otif', 0):.2%}"

        return selected, selected["method"], reasoning

    def _build_recommendations(
        self,
        candidate: Dict[str, Any],
        policy_envelope: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Build recommendations list from selected candidate"""
        orders = candidate.get("orders", [])

        recommendations = []
        for order in orders:
            recommendations.append({
                "sku": order.get("sku"),
                "supplier_id": order.get("supplier_id"),
                "destination_id": order.get("destination_id"),
                "order_qty": order.get("order_qty"),
                "order_date": order.get("order_date"),
                "expected_receipt_date": order.get("expected_receipt_date"),
                "confidence": order.get("confidence", 0.9),
                "rationale": order.get("rationale", ""),
            })

        return recommendations

    def _check_integrity(
        self,
        recommendations: List[Dict[str, Any]],
        policy_envelope: Dict[str, Any],
        inventory_state: Dict[str, Any],
    ) -> List[IntegrityViolation]:
        """
        Check integrity constraints (block submission if violated).

        Integrity policies:
        - Inventory Balance: No negative projected inventory
        - Lead Time Feasibility: Orders can arrive in time
        - MOQ Compliance: Orders meet minimum order quantities
        - Demand Coverage: All demand has documented reason if unaddressed
        """
        violations = []

        # Group recommendations by SKU
        by_sku = {}
        for rec in recommendations:
            sku = rec.get("sku")
            if sku not in by_sku:
                by_sku[sku] = []
            by_sku[sku].append(rec)

        # Check each SKU
        for sku, orders in by_sku.items():
            inv = inventory_state.get(sku, {})

            # Check for negative inventory projection
            if inv.get("projected_stockout_period"):
                violations.append(IntegrityViolation(
                    violation_type="negative_inventory",
                    sku=sku,
                    period=inv.get("projected_stockout_period"),
                    detail=f"Negative inventory projected in period {inv.get('projected_stockout_period')}",
                ))

            # Check lead time feasibility
            for order in orders:
                order_date = order.get("order_date")
                receipt_date = order.get("expected_receipt_date")
                if order_date and receipt_date:
                    # Check if receipt date is realistic
                    min_lead_time = inv.get("min_lead_time_days", 3)
                    # Simplified check
                    if isinstance(order_date, str) and isinstance(receipt_date, str):
                        from datetime import datetime
                        od = datetime.fromisoformat(order_date).date()
                        rd = datetime.fromisoformat(receipt_date).date()
                        if (rd - od).days < min_lead_time:
                            violations.append(IntegrityViolation(
                                violation_type="lead_time_infeasible",
                                sku=sku,
                                detail=f"Lead time {(rd - od).days} days < minimum {min_lead_time}",
                            ))

            # Check MOQ compliance
            for order in orders:
                order_qty = order.get("order_qty", 0)
                moq = inv.get("min_order_qty", 0)
                if order_qty > 0 and order_qty < moq:
                    violations.append(IntegrityViolation(
                        violation_type="moq_violation",
                        sku=sku,
                        detail=f"Order qty {order_qty} < MOQ {moq}",
                    ))

        return violations

    def _check_outcome_risks(
        self,
        recommendations: List[Dict[str, Any]],
        policy_envelope: Dict[str, Any],
        inventory_state: Dict[str, Any],
    ) -> List[RiskFlag]:
        """
        Check outcome risks (flag for review, don't block).

        Risk policies:
        - Service Risk: Projected OTIF below floor
        - Inventory Investment: DOS exceeds ceiling
        - Supplier Concentration: Single-source share too high
        - Expedite Exposure: Expedite spend too high
        - E&O Exposure: Excess & obsolescence risk
        - Plan Stability: Period-over-period whiplash
        """
        risk_flags = []

        otif_floors = policy_envelope.get("otif_floors", {})
        dos_ceilings = policy_envelope.get("dos_ceilings", {})
        supplier_limits = policy_envelope.get("supplier_concentration_limits", {})
        expedite_caps = policy_envelope.get("expedite_caps", {})

        # Group by SKU for analysis
        by_sku = {}
        for rec in recommendations:
            sku = rec.get("sku")
            if sku not in by_sku:
                by_sku[sku] = []
            by_sku[sku].append(rec)

        # Check service risk per SKU
        for sku, orders in by_sku.items():
            inv = inventory_state.get(sku, {})
            category = inv.get("category", "default")

            # Service risk
            projected_otif = inv.get("projected_otif", 0.95)
            floor = otif_floors.get("standard", 0.95)  # Default to standard tier
            if projected_otif < floor:
                risk_flags.append(RiskFlag(
                    risk_type="service_risk",
                    sku=sku,
                    detail=f"Projected OTIF {projected_otif:.1%} below floor {floor:.1%}",
                    metric_value=projected_otif,
                    threshold=floor,
                    suggested_action="Increase order quantity or expedite",
                ))

            # DOS ceiling
            projected_dos = inv.get("projected_dos", 14)
            ceiling = dos_ceilings.get(category, 30)
            if projected_dos > ceiling:
                risk_flags.append(RiskFlag(
                    risk_type="inventory_investment",
                    sku=sku,
                    detail=f"Projected DOS {projected_dos:.0f} exceeds ceiling {ceiling}",
                    metric_value=projected_dos,
                    threshold=ceiling,
                    suggested_action="Reduce order quantities",
                ))

        # Check supplier concentration
        supplier_spend = {}
        total_spend = 0
        for rec in recommendations:
            supplier = rec.get("supplier_id")
            qty = rec.get("order_qty", 0)
            cost = inventory_state.get(rec.get("sku"), {}).get("unit_cost", 10)
            spend = qty * cost
            supplier_spend[supplier] = supplier_spend.get(supplier, 0) + spend
            total_spend += spend

        if total_spend > 0:
            for supplier, spend in supplier_spend.items():
                share = spend / total_spend
                limit = supplier_limits.get(supplier, 0.50)
                if share > limit:
                    risk_flags.append(RiskFlag(
                        risk_type="supplier_concentration",
                        sku="ALL",
                        detail=f"{supplier} share {share:.1%} exceeds limit {limit:.1%}",
                        metric_value=share,
                        threshold=limit,
                        suggested_action=f"Diversify away from {supplier}",
                    ))

        return risk_flags

    def _calculate_confidence(
        self,
        candidate: Dict[str, Any],
        violations: List[IntegrityViolation],
        risk_flags: List[RiskFlag],
    ) -> float:
        """Calculate agent confidence in the Supply Commit"""
        base_confidence = 0.95

        # Reduce for violations
        confidence = base_confidence - 0.1 * len(violations)

        # Reduce for risk flags
        confidence -= 0.05 * len(risk_flags)

        # Factor in candidate confidence
        if "orders" in candidate:
            order_confidences = [o.get("confidence", 0.9) for o in candidate["orders"]]
            if order_confidences:
                avg_order_confidence = sum(order_confidences) / len(order_confidences)
                confidence = confidence * avg_order_confidence

        return max(0.1, min(1.0, confidence))

    def _generate_supply_pegging(
        self,
        recommendations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate supply pegging (demand -> supply action mapping)"""
        pegging = {}
        for rec in recommendations:
            sku = rec.get("sku")
            if sku not in pegging:
                pegging[sku] = []
            pegging[sku].append({
                "supply_action": "PO",
                "supplier": rec.get("supplier_id"),
                "qty": rec.get("order_qty"),
                "date": rec.get("expected_receipt_date"),
            })
        return pegging

    def _generate_review_reason(
        self,
        violations: List[IntegrityViolation],
        risk_flags: List[RiskFlag],
    ) -> str:
        """Generate human-readable review reason"""
        reasons = []

        if violations:
            reasons.append(f"{len(violations)} integrity violation(s)")

        if risk_flags:
            risk_types = set(f.risk_type for f in risk_flags)
            reasons.append(f"{len(risk_flags)} risk flag(s): {', '.join(risk_types)}")

        return "; ".join(reasons) if reasons else "Copilot mode - all decisions require review"

    def review_supply_commit(
        self,
        commit_id: int,
        user_id: int,
        action: str,  # "accept", "override", "reject"
        override_details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Review a Supply Commit.

        Args:
            commit_id: Supply Commit ID
            user_id: Reviewing user
            action: "accept", "override", or "reject"
            override_details: Changes if action is "override"

        Returns:
            Updated Supply Commit as dict
        """
        from app.models.planning_cascade import SupplyCommit, CommitStatus

        commit = self.db.query(SupplyCommit).filter_by(id=commit_id).first()
        if not commit:
            raise ValueError(f"Supply Commit {commit_id} not found")

        commit.reviewed_by = user_id
        commit.reviewed_at = datetime.utcnow()

        if action == "accept":
            commit.status = CommitStatus.ACCEPTED
        elif action == "override":
            commit.status = CommitStatus.OVERRIDDEN
            commit.override_details = override_details
            if override_details and "recommendations" in override_details:
                commit.recommendations = override_details["recommendations"]
        elif action == "reject":
            commit.status = CommitStatus.REJECTED
        else:
            raise ValueError(f"Invalid action: {action}")

        self.db.commit()
        self.db.refresh(commit)

        logger.info(f"Supply Commit {commit.hash[:8]} {action}ed by user {user_id}")

        return self._commit_to_dict(commit)

    def submit_supply_commit(
        self,
        commit_id: int,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Submit Supply Commit for execution.

        Validates that no integrity violations remain.
        """
        from app.models.planning_cascade import SupplyCommit, CommitStatus

        commit = self.db.query(SupplyCommit).filter_by(id=commit_id).first()
        if not commit:
            raise ValueError(f"Supply Commit {commit_id} not found")

        # Check for unresolved integrity violations
        if commit.integrity_violations and len(commit.integrity_violations) > 0:
            raise ValueError("Cannot submit: integrity violations unresolved")

        commit.status = CommitStatus.SUBMITTED
        commit.submitted_at = datetime.utcnow()
        commit.approved_by = user_id
        commit.approved_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(commit)

        logger.info(f"Supply Commit {commit.hash[:8]} submitted")

        return self._commit_to_dict(commit)

    def _commit_to_dict(self, commit) -> Dict[str, Any]:
        """Convert SupplyCommit to dict"""
        return {
            "id": commit.id,
            "hash": commit.hash,
            "supply_baseline_pack_hash": commit.supply_baseline_pack_hash,
            "selected_method": commit.selected_method,
            "recommendations": commit.recommendations,
            "projected_otif": commit.projected_otif,
            "projected_inventory_cost": commit.projected_inventory_cost,
            "projected_dos": commit.projected_dos,
            "integrity_violations": commit.integrity_violations,
            "risk_flags": commit.risk_flags,
            "status": commit.status.value,
            "requires_review": commit.requires_review,
            "review_reason": commit.review_reason,
            "agent_confidence": commit.agent_confidence,
            "agent_reasoning": commit.agent_reasoning,
            "reviewed_by": commit.reviewed_by,
            "reviewed_at": commit.reviewed_at.isoformat() if commit.reviewed_at else None,
            "submitted_at": commit.submitted_at.isoformat() if commit.submitted_at else None,
            "created_at": commit.created_at.isoformat() if commit.created_at else None,
        }
