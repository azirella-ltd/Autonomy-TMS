"""
Allocation Planning Agent

Owns the Allocation Commit (AC) decision.
The best constraint-respecting distribution of constrained supply
across demand segments and time buckets.

Responsibilities:
- Apply policy bundle to produce allocations
- Explain allocations through pegging
- Detect unsafe auto-submissions
- Generate entitlement caps and priority ordering

The agent does NOT own:
- Segmentation definitions
- Customer tiering
- Demand shaping
- Supply creation (that's Supply Agent)
- Order-level promising (that's Execution)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import date, datetime
from enum import Enum
import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class AllocationCandidate:
    """A candidate allocation plan"""
    method: str
    allocations: List[Dict[str, Any]]
    unallocated: List[Dict[str, Any]]
    fair_share_deviation: float = 0.0
    service_floor_compliance: float = 1.0
    priority_inversions: int = 0


@dataclass
class AllocationIntegrityViolation:
    """Integrity violation for allocation"""
    violation_type: str
    segment: str
    sku: Optional[str] = None
    detail: str = ""


@dataclass
class AllocationRiskFlag:
    """Risk flag for allocation"""
    risk_type: str
    segment: str
    detail: str = ""
    metric_value: Optional[float] = None
    threshold: Optional[float] = None


class AllocationAgent:
    """
    Allocation Planning Agent

    Owns the Allocation Commit decision artifact.
    Grounded by the Solver Baseline Pack (SBP).
    Constrained by Policy Envelope + Supply Commit.
    """

    def __init__(self, db: Session):
        self.db = db

    def generate_allocation_commit(
        self,
        config_id: int,
        tenant_id: int,
        supply_commit_id: int,
        supply_commit_hash: str,
        policy_envelope: Dict[str, Any],
        demand_by_segment: Dict[str, Dict[str, float]],  # segment -> {sku: qty}
        mode: str = "copilot",
    ) -> Dict[str, Any]:
        """
        Generate Allocation Commit from Supply Commit and demand.

        Args:
            config_id: Supply chain config ID
            tenant_id: Customer ID
            supply_commit_id: Supply Commit ID (grounding)
            supply_commit_hash: Hash for feed-forward
            policy_envelope: Active policy envelope
            demand_by_segment: Demand by customer segment
            mode: Agent mode (copilot or autonomous)

        Returns:
            AllocationCommit as dict
        """
        from app.models.planning_cascade import (
            AllocationCommit, SolverBaselinePack, SupplyCommit, CommitStatus
        )

        # Load Supply Commit
        supply_commit = self.db.query(SupplyCommit).filter_by(id=supply_commit_id).first()
        if not supply_commit:
            raise ValueError(f"Supply Commit {supply_commit_id} not found")

        # Calculate available supply from Supply Commit
        available_supply = self._calculate_available_supply(supply_commit)

        # Generate SBP candidates
        sbp_candidates = self._generate_sbp_candidates(
            available_supply, demand_by_segment, policy_envelope
        )

        # Create SBP record
        sbp = SolverBaselinePack(
            config_id=config_id,
            tenant_id=tenant_id,
            supply_commit_id=supply_commit_id,
            supply_commit_hash=supply_commit_hash,
            candidates=[self._candidate_to_dict(c) for c in sbp_candidates],
            binding_constraints=self._extract_binding_constraints(sbp_candidates),
            marginal_values=self._calculate_marginal_values(sbp_candidates, demand_by_segment),
        )
        sbp.hash = sbp.compute_hash()

        self.db.add(sbp)
        self.db.flush()

        # Select best candidate
        selected, selected_method, reasoning = self._select_candidate(
            sbp_candidates, policy_envelope
        )

        # Build allocations
        allocations = self._build_allocations(selected, policy_envelope)

        # Check integrity
        integrity_violations = self._check_integrity(
            allocations, available_supply, demand_by_segment
        )

        # Check risks
        risk_flags = self._check_outcome_risks(
            allocations, policy_envelope, demand_by_segment
        )

        # Determine status
        requires_review = (
            mode == "copilot" or
            len(integrity_violations) > 0 or
            len(risk_flags) > 0
        )

        if len(integrity_violations) > 0:
            status = CommitStatus.PROPOSED
        elif mode == "autonomous" and len(risk_flags) == 0:
            status = CommitStatus.AUTO_SUBMITTED
        else:
            status = CommitStatus.PROPOSED

        # Calculate confidence
        confidence = self._calculate_confidence(selected, integrity_violations, risk_flags)

        # Create Allocation Commit
        allocation_commit = AllocationCommit(
            config_id=config_id,
            tenant_id=tenant_id,
            supply_commit_id=supply_commit_id,
            supply_commit_hash=supply_commit_hash,
            solver_baseline_pack_id=sbp.id,
            solver_baseline_pack_hash=sbp.hash,
            selected_method=selected_method,
            allocations=allocations,
            unallocated=selected.unallocated,
            pegging_summary=self._generate_pegging_summary(allocations, available_supply),
            integrity_violations=[
                {"type": v.violation_type, "segment": v.segment, "sku": v.sku, "detail": v.detail}
                for v in integrity_violations
            ] if integrity_violations else None,
            risk_flags=[
                {"type": f.risk_type, "segment": f.segment, "detail": f.detail,
                 "metric_value": f.metric_value, "threshold": f.threshold}
                for f in risk_flags
            ] if risk_flags else None,
            status=status,
            requires_review=requires_review,
            review_reason=self._generate_review_reason(integrity_violations, risk_flags) if requires_review else None,
            agent_confidence=confidence,
            agent_reasoning=reasoning,
        )

        allocation_commit.hash = allocation_commit.compute_hash()

        if status == CommitStatus.AUTO_SUBMITTED:
            allocation_commit.submitted_at = datetime.utcnow()

        self.db.add(allocation_commit)
        self.db.commit()
        self.db.refresh(allocation_commit)

        logger.info(
            f"Generated Allocation Commit {allocation_commit.hash[:8]}: "
            f"{len(allocations)} allocations, status={status.value}"
        )

        return self._commit_to_dict(allocation_commit)

    def _calculate_available_supply(
        self,
        supply_commit
    ) -> Dict[str, float]:
        """Calculate available supply from Supply Commit recommendations"""
        available = {}

        for rec in supply_commit.recommendations or []:
            sku = rec.get("sku")
            qty = rec.get("order_qty", 0)
            available[sku] = available.get(sku, 0) + qty

        return available

    def _generate_sbp_candidates(
        self,
        available_supply: Dict[str, float],
        demand_by_segment: Dict[str, Dict[str, float]],
        policy_envelope: Dict[str, Any],
    ) -> List[AllocationCandidate]:
        """Generate allocation candidates with different methods"""
        candidates = []

        # 1. Fair Share
        candidates.append(self._generate_fair_share(
            available_supply, demand_by_segment
        ))

        # 2. Priority-based
        candidates.append(self._generate_priority_based(
            available_supply, demand_by_segment, policy_envelope
        ))

        # 3. LP Optimal (simplified)
        candidates.append(self._generate_lp_allocation(
            available_supply, demand_by_segment, policy_envelope
        ))

        return candidates

    def _generate_fair_share(
        self,
        available_supply: Dict[str, float],
        demand_by_segment: Dict[str, Dict[str, float]],
    ) -> AllocationCandidate:
        """Generate fair-share allocation (proportional to demand)"""
        allocations = []
        unallocated = []

        for sku, available in available_supply.items():
            total_demand = sum(
                seg_demand.get(sku, 0)
                for seg_demand in demand_by_segment.values()
            )

            if total_demand <= 0:
                continue

            fill_rate = min(1.0, available / total_demand)

            for segment, seg_demand in demand_by_segment.items():
                demand = seg_demand.get(sku, 0)
                if demand > 0:
                    allocation_qty = demand * fill_rate
                    allocations.append({
                        "sku": sku,
                        "segment": segment,
                        "entitlement_qty": allocation_qty,
                        "priority": self._get_segment_priority(segment),
                        "demand": demand,
                        "fill_rate": fill_rate,
                    })

                    if allocation_qty < demand:
                        unallocated.append({
                            "sku": sku,
                            "segment": segment,
                            "qty": demand - allocation_qty,
                        })

        return AllocationCandidate(
            method="FAIR_SHARE_V1",
            allocations=allocations,
            unallocated=unallocated,
            fair_share_deviation=0.0,  # By definition
            service_floor_compliance=self._calculate_service_compliance(allocations, demand_by_segment),
        )

    def _generate_priority_based(
        self,
        available_supply: Dict[str, float],
        demand_by_segment: Dict[str, Dict[str, float]],
        policy_envelope: Dict[str, Any],
    ) -> AllocationCandidate:
        """Generate priority-based allocation (serve highest priority first)"""
        allocations = []
        unallocated = []
        priority_inversions = 0

        allocation_reserves = policy_envelope.get("allocation_reserves", {})

        # Sort segments by priority
        segments_by_priority = sorted(
            demand_by_segment.keys(),
            key=lambda s: self._get_segment_priority(s)
        )

        for sku, available in available_supply.items():
            remaining = available

            for segment in segments_by_priority:
                demand = demand_by_segment[segment].get(sku, 0)
                if demand <= 0:
                    continue

                # Apply reserves
                reserve_pct = allocation_reserves.get(segment, 0)
                reserved_for_higher = sum(
                    demand_by_segment[s].get(sku, 0) * allocation_reserves.get(s, 0)
                    for s in segments_by_priority
                    if self._get_segment_priority(s) < self._get_segment_priority(segment)
                )

                allocatable = max(0, remaining - reserved_for_higher)
                allocation_qty = min(demand, allocatable)

                allocations.append({
                    "sku": sku,
                    "segment": segment,
                    "entitlement_qty": allocation_qty,
                    "priority": self._get_segment_priority(segment),
                    "demand": demand,
                    "fill_rate": allocation_qty / demand if demand > 0 else 1.0,
                })

                remaining -= allocation_qty

                if allocation_qty < demand:
                    unallocated.append({
                        "sku": sku,
                        "segment": segment,
                        "qty": demand - allocation_qty,
                    })

        return AllocationCandidate(
            method="PRIORITY_V1",
            allocations=allocations,
            unallocated=unallocated,
            fair_share_deviation=self._calculate_fair_share_deviation(allocations),
            service_floor_compliance=self._calculate_service_compliance(allocations, demand_by_segment),
            priority_inversions=priority_inversions,
        )

    def _generate_lp_allocation(
        self,
        available_supply: Dict[str, float],
        demand_by_segment: Dict[str, Dict[str, float]],
        policy_envelope: Dict[str, Any],
    ) -> AllocationCandidate:
        """
        Generate LP-optimal allocation.

        Simplified: In production, would use scipy.optimize or Gurobi.
        Here we use a heuristic that balances priorities with fairness.
        """
        allocations = []
        unallocated = []

        otif_floors = policy_envelope.get("otif_floors", {})

        for sku, available in available_supply.items():
            total_demand = sum(
                seg_demand.get(sku, 0)
                for seg_demand in demand_by_segment.values()
            )

            if total_demand <= 0:
                continue

            # Weight by priority and floor
            weights = {}
            for segment in demand_by_segment:
                priority = self._get_segment_priority(segment)
                floor = otif_floors.get(segment, 0.90)
                weights[segment] = (1 / priority) * floor  # Higher priority, higher floor = higher weight

            total_weight = sum(weights.values())

            remaining = available
            for segment in sorted(demand_by_segment.keys(),
                                  key=lambda s: weights.get(s, 0),
                                  reverse=True):
                demand = demand_by_segment[segment].get(sku, 0)
                if demand <= 0:
                    continue

                # Allocate proportional to weight with priority bias
                weight_share = weights.get(segment, 0) / total_weight if total_weight > 0 else 0.25
                target_allocation = min(demand, available * weight_share * 1.2)  # 20% priority bonus
                allocation_qty = min(target_allocation, remaining, demand)

                allocations.append({
                    "sku": sku,
                    "segment": segment,
                    "entitlement_qty": allocation_qty,
                    "priority": self._get_segment_priority(segment),
                    "demand": demand,
                    "fill_rate": allocation_qty / demand if demand > 0 else 1.0,
                })

                remaining -= allocation_qty

                if allocation_qty < demand:
                    unallocated.append({
                        "sku": sku,
                        "segment": segment,
                        "qty": demand - allocation_qty,
                    })

        return AllocationCandidate(
            method="LP_OPTIMAL_V1",
            allocations=allocations,
            unallocated=unallocated,
            fair_share_deviation=self._calculate_fair_share_deviation(allocations),
            service_floor_compliance=self._calculate_service_compliance(allocations, demand_by_segment),
        )

    def _select_candidate(
        self,
        candidates: List[AllocationCandidate],
        policy_envelope: Dict[str, Any],
    ) -> Tuple[AllocationCandidate, str, str]:
        """Select best allocation candidate"""
        # Score candidates
        scores = []
        for c in candidates:
            score = (
                c.service_floor_compliance * 0.5 +
                (1 - c.fair_share_deviation) * 0.3 +
                (1 - c.priority_inversions / 10) * 0.2
            )
            scores.append((score, c))

        scores.sort(key=lambda x: x[0], reverse=True)
        best = scores[0][1]

        reasoning = (
            f"Selected {best.method}: "
            f"service compliance={best.service_floor_compliance:.2%}, "
            f"fair-share deviation={best.fair_share_deviation:.2%}"
        )

        return best, best.method, reasoning

    def _build_allocations(
        self,
        candidate: AllocationCandidate,
        policy_envelope: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Build allocation list from selected candidate"""
        return candidate.allocations

    def _check_integrity(
        self,
        allocations: List[Dict[str, Any]],
        available_supply: Dict[str, float],
        demand_by_segment: Dict[str, Dict[str, float]],
    ) -> List[AllocationIntegrityViolation]:
        """Check integrity constraints"""
        violations = []

        # Supply conservation: allocated <= available
        allocated_by_sku = {}
        for alloc in allocations:
            sku = alloc.get("sku")
            qty = alloc.get("entitlement_qty", 0)
            allocated_by_sku[sku] = allocated_by_sku.get(sku, 0) + qty

        for sku, allocated in allocated_by_sku.items():
            available = available_supply.get(sku, 0)
            if allocated > available * 1.001:  # Small tolerance
                violations.append(AllocationIntegrityViolation(
                    violation_type="supply_conservation",
                    segment="ALL",
                    sku=sku,
                    detail=f"Allocated {allocated:.0f} > available {available:.0f}",
                ))

        return violations

    def _check_outcome_risks(
        self,
        allocations: List[Dict[str, Any]],
        policy_envelope: Dict[str, Any],
        demand_by_segment: Dict[str, Dict[str, float]],
    ) -> List[AllocationRiskFlag]:
        """Check outcome risks"""
        risk_flags = []

        otif_floors = policy_envelope.get("otif_floors", {})

        # Service floor compliance by segment
        fill_by_segment = {}
        demand_by_seg = {}

        for alloc in allocations:
            segment = alloc.get("segment")
            qty = alloc.get("entitlement_qty", 0)
            demand = alloc.get("demand", 0)

            fill_by_segment[segment] = fill_by_segment.get(segment, 0) + qty
            demand_by_seg[segment] = demand_by_seg.get(segment, 0) + demand

        for segment, filled in fill_by_segment.items():
            demand = demand_by_seg.get(segment, 0)
            fill_rate = filled / demand if demand > 0 else 1.0
            floor = otif_floors.get(segment, 0.90)

            if fill_rate < floor:
                risk_flags.append(AllocationRiskFlag(
                    risk_type="service_floor_breach",
                    segment=segment,
                    detail=f"Fill rate {fill_rate:.1%} below floor {floor:.1%}",
                    metric_value=fill_rate,
                    threshold=floor,
                ))

        # Fair-share deviation check
        deviation = self._calculate_fair_share_deviation(allocations)
        if deviation > 0.15:  # 15% threshold
            risk_flags.append(AllocationRiskFlag(
                risk_type="fair_share_deviation",
                segment="ALL",
                detail=f"Fair-share deviation {deviation:.1%} exceeds threshold",
                metric_value=deviation,
                threshold=0.15,
            ))

        return risk_flags

    def _get_segment_priority(self, segment: str) -> int:
        """Get priority for a segment (lower = higher priority)"""
        priorities = {
            "strategic": 1,
            "standard": 2,
            "transactional": 3,
        }
        return priorities.get(segment.lower(), 3)

    def _calculate_fair_share_deviation(
        self,
        allocations: List[Dict[str, Any]]
    ) -> float:
        """Calculate deviation from fair-share allocation"""
        if not allocations:
            return 0.0

        # Group by SKU and calculate variance in fill rates
        fill_rates_by_sku = {}
        for alloc in allocations:
            sku = alloc.get("sku")
            fill_rate = alloc.get("fill_rate", 1.0)
            if sku not in fill_rates_by_sku:
                fill_rates_by_sku[sku] = []
            fill_rates_by_sku[sku].append(fill_rate)

        deviations = []
        for sku, rates in fill_rates_by_sku.items():
            if len(rates) > 1:
                mean_rate = sum(rates) / len(rates)
                variance = sum((r - mean_rate) ** 2 for r in rates) / len(rates)
                deviations.append(variance ** 0.5)

        return sum(deviations) / len(deviations) if deviations else 0.0

    def _calculate_service_compliance(
        self,
        allocations: List[Dict[str, Any]],
        demand_by_segment: Dict[str, Dict[str, float]],
    ) -> float:
        """Calculate service floor compliance rate"""
        if not allocations:
            return 1.0

        compliant = 0
        total = 0

        for alloc in allocations:
            total += 1
            fill_rate = alloc.get("fill_rate", 1.0)
            if fill_rate >= 0.90:  # Default floor
                compliant += 1

        return compliant / total if total > 0 else 1.0

    def _calculate_confidence(
        self,
        candidate: AllocationCandidate,
        violations: List[AllocationIntegrityViolation],
        risk_flags: List[AllocationRiskFlag],
    ) -> float:
        """Calculate agent confidence"""
        confidence = 0.90

        confidence -= 0.15 * len(violations)
        confidence -= 0.05 * len(risk_flags)

        confidence *= candidate.service_floor_compliance

        return max(0.1, min(1.0, confidence))

    def _generate_pegging_summary(
        self,
        allocations: List[Dict[str, Any]],
        available_supply: Dict[str, float],
    ) -> Dict[str, Any]:
        """Generate pegging summary"""
        return {
            "supply_pools": available_supply,
            "allocation_count": len(allocations),
            "segments_served": list(set(a.get("segment") for a in allocations)),
        }

    def _generate_review_reason(
        self,
        violations: List[AllocationIntegrityViolation],
        risk_flags: List[AllocationRiskFlag],
    ) -> str:
        """Generate review reason"""
        reasons = []
        if violations:
            reasons.append(f"{len(violations)} integrity violation(s)")
        if risk_flags:
            reasons.append(f"{len(risk_flags)} risk flag(s)")
        return "; ".join(reasons) if reasons else "Copilot mode"

    def _extract_binding_constraints(
        self,
        candidates: List[AllocationCandidate]
    ) -> List[Dict[str, Any]]:
        """Extract binding constraints from candidates"""
        # Simplified - in production would come from LP solver
        return [{"type": "supply_capacity", "binding": True}]

    def _calculate_marginal_values(
        self,
        candidates: List[AllocationCandidate],
        demand_by_segment: Dict[str, Dict[str, float]],
    ) -> Dict[str, Any]:
        """Calculate marginal values (shadow prices)"""
        # Simplified - in production would come from LP solver
        return {
            "supply_shadow_price": 1.0,
            "marginal_short_penalty": 10.0,
        }

    def _candidate_to_dict(self, candidate: AllocationCandidate) -> Dict[str, Any]:
        """Convert candidate to dict"""
        return {
            "method": candidate.method,
            "allocations": candidate.allocations,
            "unallocated": candidate.unallocated,
            "fair_share_deviation": candidate.fair_share_deviation,
            "service_floor_compliance": candidate.service_floor_compliance,
            "priority_inversions": candidate.priority_inversions,
        }

    def _commit_to_dict(self, commit) -> Dict[str, Any]:
        """Convert AllocationCommit to dict"""
        return {
            "id": commit.id,
            "hash": commit.hash,
            "supply_commit_hash": commit.supply_commit_hash,
            "solver_baseline_pack_hash": commit.solver_baseline_pack_hash,
            "selected_method": commit.selected_method,
            "allocations": commit.allocations,
            "unallocated": commit.unallocated,
            "integrity_violations": commit.integrity_violations,
            "risk_flags": commit.risk_flags,
            "status": commit.status.value,
            "requires_review": commit.requires_review,
            "review_reason": commit.review_reason,
            "agent_confidence": commit.agent_confidence,
            "agent_reasoning": commit.agent_reasoning,
            "created_at": commit.created_at.isoformat() if commit.created_at else None,
        }

    def review_allocation_commit(
        self,
        commit_id: int,
        user_id: int,
        action: str,
        override_details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Review an Allocation Commit"""
        from app.models.planning_cascade import AllocationCommit, CommitStatus

        commit = self.db.query(AllocationCommit).filter_by(id=commit_id).first()
        if not commit:
            raise ValueError(f"Allocation Commit {commit_id} not found")

        commit.reviewed_by = user_id
        commit.reviewed_at = datetime.utcnow()

        if action == "accept":
            commit.status = CommitStatus.ACCEPTED
        elif action == "override":
            commit.status = CommitStatus.OVERRIDDEN
            commit.override_details = override_details
            if override_details and "allocations" in override_details:
                commit.allocations = override_details["allocations"]
        elif action == "reject":
            commit.status = CommitStatus.REJECTED
        else:
            raise ValueError(f"Invalid action: {action}")

        self.db.commit()
        self.db.refresh(commit)

        return self._commit_to_dict(commit)

    def submit_allocation_commit(
        self,
        commit_id: int,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Submit Allocation Commit for execution"""
        from app.models.planning_cascade import AllocationCommit, CommitStatus

        commit = self.db.query(AllocationCommit).filter_by(id=commit_id).first()
        if not commit:
            raise ValueError(f"Allocation Commit {commit_id} not found")

        if commit.integrity_violations and len(commit.integrity_violations) > 0:
            raise ValueError("Cannot submit: integrity violations unresolved")

        commit.status = CommitStatus.SUBMITTED
        commit.submitted_at = datetime.utcnow()
        commit.approved_by = user_id
        commit.approved_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(commit)

        return self._commit_to_dict(commit)
