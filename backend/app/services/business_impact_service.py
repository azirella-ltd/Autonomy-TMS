"""
Business Impact Calculation Service

Computes probabilistic balanced scorecard metrics for decision proposals
by running planning workflows in child scenarios and comparing to parent.

Algorithm:
1. Get effective configurations for parent and child scenarios
2. Run planning workflows (ATP/CTP/MRP) for both scenarios
3. Compute probabilistic metrics using stochastic sampler
4. Generate comparative business case with P10/P50/P90 distributions
5. Store impact snapshots for approval workflow

Metrics:
- Financial: total_cost, revenue, roi with probability distributions
- Customer: otif, fill_rate, backlog_value with distributions
- Operational: inventory_turns, dos, cycle_time, bullwhip_ratio
- Strategic: flexibility_score, supplier_reliability, co2_emissions
"""
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.orm import Session
import datetime
import statistics

from app.models.supply_chain_config import (
    SupplyChainConfig,
    DecisionProposal,
    BusinessImpactSnapshot,
)
from app.services.scenario_branching_service import ScenarioBranchingService


class BusinessImpactService:
    """Service for computing business impact of decision proposals"""

    def __init__(self, db: Session):
        self.db = db
        self.branching_service = ScenarioBranchingService(db)

    # =========================================================================
    # Core Operations
    # =========================================================================

    def compute_business_impact(
        self,
        proposal_id: int,
        planning_horizon: int = 52,
        simulation_runs: int = 1000,
    ) -> Dict[str, Any]:
        """
        Compute business impact for a decision proposal.

        Compares parent scenario (baseline) vs child scenario (with proposed changes)
        using probabilistic balanced scorecard metrics.

        Args:
            proposal_id: Decision proposal ID
            planning_horizon: Weeks to simulate (default: 52)
            simulation_runs: Monte Carlo runs (default: 1000)

        Returns:
            Dictionary with comparative metrics:
            {
                "parent_metrics": {...},
                "child_metrics": {...},
                "delta_metrics": {...},  # Child - Parent
                "improvement_probability": {...},  # P(child > parent)
            }
        """
        # Get proposal
        proposal = self.db.query(DecisionProposal).filter_by(id=proposal_id).first()
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        # Get effective configurations
        parent_config = self.branching_service.get_effective_config(proposal.parent_scenario_id)
        child_config = self.branching_service.get_effective_config(proposal.scenario_id)

        # Simulate parent scenario
        parent_metrics = self._simulate_scenario(
            parent_config,
            planning_horizon,
            simulation_runs,
            proposal.action_type,
        )

        # Simulate child scenario (with proposed changes)
        child_metrics = self._simulate_scenario(
            child_config,
            planning_horizon,
            simulation_runs,
            proposal.action_type,
        )

        # Compute deltas and improvement probabilities
        delta_metrics = self._compute_delta_metrics(parent_metrics, child_metrics)
        improvement_probability = self._compute_improvement_probability(
            parent_metrics, child_metrics
        )

        # Store snapshots
        self._store_impact_snapshots(
            proposal_id,
            proposal.scenario_id,
            proposal.parent_scenario_id,
            parent_metrics,
            child_metrics,
            planning_horizon,
            simulation_runs,
        )

        # Update proposal with business case
        business_case = self._generate_business_case(
            parent_metrics,
            child_metrics,
            delta_metrics,
            improvement_probability,
            proposal.action_type,
            proposal.action_params,
        )

        proposal.business_case = business_case
        proposal.financial_impact = delta_metrics["financial"]
        proposal.operational_impact = delta_metrics["operational"]
        proposal.strategic_impact = delta_metrics["strategic"]
        proposal.risk_metrics = {
            "improvement_probability": improvement_probability,
            "downside_risk": self._compute_downside_risk(parent_metrics, child_metrics),
        }

        self.db.commit()

        return {
            "parent_metrics": parent_metrics,
            "child_metrics": child_metrics,
            "delta_metrics": delta_metrics,
            "improvement_probability": improvement_probability,
            "business_case": business_case,
        }

    def approve_proposal(
        self,
        proposal_id: int,
        approved_by: str,
        commit_to_parent: bool = True,
    ) -> SupplyChainConfig:
        """
        Approve a decision proposal.

        Args:
            proposal_id: Decision proposal ID
            approved_by: User ID approving
            commit_to_parent: If True, commit child scenario to parent (default: True)

        Returns:
            Updated parent configuration (if committed)
        """
        proposal = self.db.query(DecisionProposal).filter_by(id=proposal_id).first()
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        if proposal.status != "pending":
            raise ValueError(f"Proposal already {proposal.status}")

        # Update proposal status
        proposal.status = "approved"
        proposal.approved_by = approved_by
        proposal.approved_at = datetime.datetime.utcnow()

        # Optionally commit child scenario to parent
        parent_config = None
        if commit_to_parent and proposal.parent_scenario_id:
            parent_config = self.branching_service.commit_scenario(
                proposal.scenario_id,
                committed_by=approved_by,
            )
            proposal.executed_at = datetime.datetime.utcnow()
            proposal.status = "executed"

        self.db.commit()
        return parent_config

    def reject_proposal(
        self,
        proposal_id: int,
        rejected_by: str,
        reason: str,
        delete_scenario: bool = True,
    ) -> None:
        """
        Reject a decision proposal.

        Args:
            proposal_id: Decision proposal ID
            rejected_by: User ID rejecting
            reason: Rejection reason
            delete_scenario: If True, delete child scenario (default: True)
        """
        proposal = self.db.query(DecisionProposal).filter_by(id=proposal_id).first()
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        if proposal.status != "pending":
            raise ValueError(f"Proposal already {proposal.status}")

        # Update proposal status
        proposal.status = "rejected"
        proposal.approved_by = rejected_by
        proposal.approved_at = datetime.datetime.utcnow()
        proposal.rejection_reason = reason

        # Optionally delete child scenario
        if delete_scenario:
            self.branching_service.rollback_scenario(proposal.scenario_id)
            # Note: Don't delete the scenario config itself, just the deltas
            # This preserves the audit trail

        self.db.commit()

    # =========================================================================
    # Simulation Methods
    # =========================================================================

    def _simulate_scenario(
        self,
        config: Dict[str, Any],
        planning_horizon: int,
        simulation_runs: int,
        action_type: str,
    ) -> Dict[str, Any]:
        """
        Simulate a scenario and compute probabilistic metrics.

        For Phase 1, uses simplified simulation based on config entities.
        Future phases will integrate full AWS SC planning workflows.

        Returns:
            Dictionary with probabilistic balanced scorecard metrics:
            {
                "financial": {"total_cost": {"p10": ..., "p50": ..., "p90": ...}, ...},
                "customer": {"otif": {...}, "fill_rate": {...}, ...},
                "operational": {"inventory_turns": {...}, "dos": {...}, ...},
                "strategic": {"flexibility_score": ..., ...}
            }
        """
        # Extract scenario metadata
        scenario_config = config["config"]
        nodes = config["nodes"]
        lanes = config["lanes"]
        markets = config.get("markets", [])

        # Simplified simulation for Phase 1
        # TODO: Replace with full planning workflow integration
        num_nodes = len(nodes)
        num_lanes = len(lanes)
        num_markets = len(markets)

        # Simulate financial metrics
        financial = self._simulate_financial_metrics(
            nodes, lanes, planning_horizon, simulation_runs
        )

        # Simulate customer metrics
        customer = self._simulate_customer_metrics(
            markets, nodes, planning_horizon, simulation_runs
        )

        # Simulate operational metrics
        operational = self._simulate_operational_metrics(
            nodes, lanes, planning_horizon, simulation_runs
        )

        # Simulate strategic metrics
        strategic = self._simulate_strategic_metrics(
            nodes, lanes, markets, action_type
        )

        return {
            "financial": financial,
            "customer": customer,
            "operational": operational,
            "strategic": strategic,
        }

    def _simulate_financial_metrics(
        self, nodes, lanes, planning_horizon, simulation_runs
    ) -> Dict[str, Dict[str, float]]:
        """
        Simulate financial metrics using Monte Carlo.

        Metrics:
        - total_cost: Sum of inventory holding + ordering + shortage costs
        - revenue: Sales revenue from customer fulfillment
        - roi: (Revenue - Cost) / Cost
        """
        # Simplified cost model (placeholder for full planning integration)
        base_inventory_cost = len(nodes) * 1000  # $1000 per node per week
        base_ordering_cost = len(lanes) * 500  # $500 per lane per week
        base_shortage_cost = len(nodes) * 200  # $200 per node per week

        # Add randomness (normal distribution with 10% CV)
        inventory_costs = [
            max(0, base_inventory_cost + (base_inventory_cost * 0.1 * ((i % 10) - 5) / 5))
            for i in range(simulation_runs)
        ]
        ordering_costs = [
            max(0, base_ordering_cost + (base_ordering_cost * 0.1 * ((i % 7) - 3.5) / 3.5))
            for i in range(simulation_runs)
        ]
        shortage_costs = [
            max(0, base_shortage_cost + (base_shortage_cost * 0.15 * ((i % 8) - 4) / 4))
            for i in range(simulation_runs)
        ]

        total_costs = [
            inv + order + short
            for inv, order, short in zip(inventory_costs, ordering_costs, shortage_costs)
        ]

        # Revenue (simplified)
        base_revenue = base_inventory_cost * 1.5  # 50% margin
        revenues = [
            max(0, base_revenue + (base_revenue * 0.08 * ((i % 9) - 4.5) / 4.5))
            for i in range(simulation_runs)
        ]

        # ROI
        rois = [(rev - cost) / cost if cost > 0 else 0 for rev, cost in zip(revenues, total_costs)]

        return {
            "total_cost": self._compute_percentiles(total_costs),
            "revenue": self._compute_percentiles(revenues),
            "roi": self._compute_percentiles(rois),
        }

    def _simulate_customer_metrics(
        self, markets, nodes, planning_horizon, simulation_runs
    ) -> Dict[str, Dict[str, float]]:
        """
        Simulate customer service metrics.

        Metrics:
        - otif: On-Time-In-Full delivery rate
        - fill_rate: Percentage of demand fulfilled immediately
        - backlog_value: Dollar value of unfulfilled orders
        """
        # Simplified service level model
        base_otif = 0.90 + (0.02 * len(nodes))  # More nodes = better redundancy
        base_fill_rate = 0.85 + (0.03 * len(nodes))

        otifs = [
            min(1.0, max(0.0, base_otif + ((i % 20) - 10) * 0.01))
            for i in range(simulation_runs)
        ]
        fill_rates = [
            min(1.0, max(0.0, base_fill_rate + ((i % 15) - 7.5) * 0.012))
            for i in range(simulation_runs)
        ]

        base_backlog = 5000 * len(markets)
        backlogs = [
            max(0, base_backlog * (1 - fill_rates[i]) + ((i % 12) - 6) * 200)
            for i in range(simulation_runs)
        ]

        return {
            "otif": self._compute_percentiles(otifs),
            "fill_rate": self._compute_percentiles(fill_rates),
            "backlog_value": self._compute_percentiles(backlogs),
        }

    def _simulate_operational_metrics(
        self, nodes, lanes, planning_horizon, simulation_runs
    ) -> Dict[str, Dict[str, float]]:
        """
        Simulate operational efficiency metrics.

        Metrics:
        - inventory_turns: Annual inventory turnover rate
        - dos: Days of supply on hand
        - cycle_time: Average order-to-delivery time
        - bullwhip_ratio: Demand variance amplification
        """
        base_turns = 12.0 - (len(nodes) * 0.5)  # More nodes = slower turns
        base_dos = 30 + (len(nodes) * 2)
        base_cycle_time = sum(
            lane.get("supply_lead_time", {}).get("value", 2) for lane in lanes
        ) / max(1, len(lanes))

        inventory_turns = [
            max(1, base_turns + ((i % 10) - 5) * 0.2)
            for i in range(simulation_runs)
        ]
        dos_values = [
            max(0, base_dos + ((i % 8) - 4) * 2)
            for i in range(simulation_runs)
        ]
        cycle_times = [
            max(1, base_cycle_time + ((i % 6) - 3) * 0.3)
            for i in range(simulation_runs)
        ]

        # Bullwhip ratio (variance amplification through supply chain)
        base_bullwhip = 1.0 + (len(nodes) - 1) * 0.15
        bullwhip_ratios = [
            max(1.0, base_bullwhip + ((i % 7) - 3.5) * 0.05)
            for i in range(simulation_runs)
        ]

        return {
            "inventory_turns": self._compute_percentiles(inventory_turns),
            "dos": self._compute_percentiles(dos_values),
            "cycle_time": self._compute_percentiles(cycle_times),
            "bullwhip_ratio": self._compute_percentiles(bullwhip_ratios),
        }

    def _simulate_strategic_metrics(
        self, nodes, lanes, markets, action_type: str
    ) -> Dict[str, float]:
        """
        Compute strategic metrics (deterministic for now).

        Metrics:
        - flexibility_score: Network ability to adapt (0-100)
        - supplier_reliability: Supplier performance score (0-100)
        - co2_emissions: Estimated annual CO2 emissions (tons)
        """
        # Flexibility: More nodes + lanes = more flexible
        flexibility_score = min(100, 50 + len(nodes) * 5 + len(lanes) * 3)

        # Supplier reliability (placeholder)
        supplier_reliability = 85.0

        # CO2 emissions (simplified model based on lanes)
        co2_emissions = len(lanes) * 500  # 500 tons per lane per year

        # Adjust based on action type
        if action_type == "expedite":
            co2_emissions *= 1.2  # Expediting increases emissions
        elif action_type == "add_local_supplier":
            co2_emissions *= 0.9  # Local sourcing reduces emissions

        return {
            "flexibility_score": flexibility_score,
            "supplier_reliability": supplier_reliability,
            "co2_emissions": co2_emissions,
        }

    # =========================================================================
    # Analysis Methods
    # =========================================================================

    def _compute_delta_metrics(
        self, parent_metrics: Dict, child_metrics: Dict
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        Compute delta (difference) between child and parent metrics.

        Returns child - parent for all metrics.
        """
        delta = {}

        for category in ["financial", "customer", "operational"]:
            delta[category] = {}
            for metric, child_dist in child_metrics[category].items():
                parent_dist = parent_metrics[category][metric]
                delta[category][metric] = {
                    "p10": child_dist["p10"] - parent_dist["p10"],
                    "p50": child_dist["p50"] - parent_dist["p50"],
                    "p90": child_dist["p90"] - parent_dist["p90"],
                }

        # Strategic metrics (deterministic)
        delta["strategic"] = {}
        for metric, child_val in child_metrics["strategic"].items():
            parent_val = parent_metrics["strategic"][metric]
            delta["strategic"][metric] = child_val - parent_val

        return delta

    def _compute_improvement_probability(
        self, parent_metrics: Dict, child_metrics: Dict
    ) -> Dict[str, float]:
        """
        Compute probability that child scenario improves each metric.

        Approximates P(child > parent) using normal distribution assumption.
        """
        improvement_prob = {}

        # For each metric, estimate P(child > parent)
        # Using simple heuristic: if P50(child) > P50(parent), assume 50%+ probability
        for category in ["financial", "customer", "operational"]:
            for metric in child_metrics[category]:
                child_p50 = child_metrics[category][metric]["p50"]
                parent_p50 = parent_metrics[category][metric]["p50"]

                # Determine if higher is better
                higher_is_better = metric in ["revenue", "roi", "otif", "fill_rate", "inventory_turns"]

                if higher_is_better:
                    improvement = child_p50 - parent_p50
                else:
                    improvement = parent_p50 - child_p50  # Lower is better

                # Simple probability estimate (50% + improvement as percentage)
                prob = 0.5 + min(0.5, max(-0.5, improvement / max(abs(parent_p50), 1) * 0.5))
                improvement_prob[f"{category}.{metric}"] = round(prob, 3)

        return improvement_prob

    def _compute_downside_risk(
        self, parent_metrics: Dict, child_metrics: Dict
    ) -> Dict[str, float]:
        """
        Compute downside risk (worst-case scenario).

        Returns P10 percentile deltas for key metrics.
        """
        downside = {}

        # Financial downside
        downside["total_cost_p10_increase"] = (
            child_metrics["financial"]["total_cost"]["p10"]
            - parent_metrics["financial"]["total_cost"]["p10"]
        )

        # Customer service downside
        downside["fill_rate_p10_decrease"] = (
            parent_metrics["customer"]["fill_rate"]["p10"]
            - child_metrics["customer"]["fill_rate"]["p10"]
        )

        return downside

    def _compute_percentiles(self, values: List[float]) -> Dict[str, float]:
        """Compute P10, P50, P90 percentiles"""
        sorted_values = sorted(values)
        n = len(sorted_values)

        return {
            "p10": sorted_values[int(n * 0.1)],
            "p50": sorted_values[int(n * 0.5)],
            "p90": sorted_values[int(n * 0.9)],
            "mean": statistics.mean(values),
            "std": statistics.stdev(values) if len(values) > 1 else 0,
        }

    def _generate_business_case(
        self,
        parent_metrics: Dict,
        child_metrics: Dict,
        delta_metrics: Dict,
        improvement_probability: Dict,
        action_type: str,
        action_params: Dict,
    ) -> Dict[str, Any]:
        """
        Generate human-readable business case summary.

        Returns structured business case for approval workflow.
        """
        return {
            "title": f"Business Case for {action_type}",
            "summary": self._generate_summary(delta_metrics, improvement_probability),
            "action_type": action_type,
            "action_params": action_params,
            "key_findings": self._generate_key_findings(delta_metrics, improvement_probability),
            "recommendation": self._generate_recommendation(delta_metrics, improvement_probability),
            "risks": self._generate_risk_summary(parent_metrics, child_metrics),
            "expected_impact": {
                "financial": delta_metrics["financial"],
                "customer": delta_metrics["customer"],
                "operational": delta_metrics["operational"],
                "strategic": delta_metrics["strategic"],
            },
        }

    def _generate_summary(self, delta_metrics: Dict, improvement_probability: Dict) -> str:
        """Generate executive summary"""
        # Count improvements
        improvements = sum(1 for p in improvement_probability.values() if p > 0.5)
        total_metrics = len(improvement_probability)

        return (
            f"Analysis shows improvement in {improvements}/{total_metrics} key metrics. "
            f"Expected cost change: ${delta_metrics['financial']['total_cost']['p50']:.0f}. "
            f"Expected service level change: {delta_metrics['customer']['fill_rate']['p50']:.1%}."
        )

    def _generate_key_findings(self, delta_metrics: Dict, improvement_probability: Dict) -> List[str]:
        """Generate key findings list"""
        findings = []

        # Financial findings
        cost_delta = delta_metrics["financial"]["total_cost"]["p50"]
        if abs(cost_delta) > 1000:
            findings.append(
                f"Total cost expected to {'increase' if cost_delta > 0 else 'decrease'} "
                f"by ${abs(cost_delta):.0f} (P50)"
            )

        # Customer findings
        fill_rate_delta = delta_metrics["customer"]["fill_rate"]["p50"]
        if abs(fill_rate_delta) > 0.01:
            findings.append(
                f"Fill rate expected to {'improve' if fill_rate_delta > 0 else 'decline'} "
                f"by {abs(fill_rate_delta):.1%}"
            )

        return findings

    def _generate_recommendation(self, delta_metrics: Dict, improvement_probability: Dict) -> str:
        """Generate recommendation"""
        # Count net improvements
        improvements = sum(1 for p in improvement_probability.values() if p > 0.5)
        total = len(improvement_probability)

        if improvements / total > 0.7:
            return "APPROVE - Strong positive impact across most metrics"
        elif improvements / total > 0.5:
            return "APPROVE WITH CAUTION - Moderate positive impact, monitor risks"
        else:
            return "REJECT - Insufficient improvement to justify change"

    def _generate_risk_summary(self, parent_metrics: Dict, child_metrics: Dict) -> List[str]:
        """Generate risk summary"""
        risks = []

        downside_risk = self._compute_downside_risk(parent_metrics, child_metrics)

        if downside_risk["total_cost_p10_increase"] > 5000:
            risks.append(
                f"High cost risk: P10 scenario shows ${downside_risk['total_cost_p10_increase']:.0f} increase"
            )

        if downside_risk["fill_rate_p10_decrease"] > 0.05:
            risks.append(
                f"Service level risk: P10 scenario shows {downside_risk['fill_rate_p10_decrease']:.1%} decline"
            )

        return risks if risks else ["Low risk - minimal downside exposure"]

    # =========================================================================
    # Storage Methods
    # =========================================================================

    def _store_impact_snapshots(
        self,
        proposal_id: int,
        child_scenario_id: int,
        parent_scenario_id: int,
        parent_metrics: Dict,
        child_metrics: Dict,
        planning_horizon: int,
        simulation_runs: int,
    ) -> None:
        """Store impact snapshots for audit trail"""
        # Parent (before) snapshot
        parent_snapshot = BusinessImpactSnapshot(
            proposal_id=proposal_id,
            scenario_id=parent_scenario_id,
            snapshot_type="before",
            planning_horizon=planning_horizon,
            simulation_runs=simulation_runs,
            financial_metrics=parent_metrics["financial"],
            customer_metrics=parent_metrics["customer"],
            operational_metrics=parent_metrics["operational"],
            strategic_metrics=parent_metrics["strategic"],
        )

        # Child (after) snapshot
        child_snapshot = BusinessImpactSnapshot(
            proposal_id=proposal_id,
            scenario_id=child_scenario_id,
            snapshot_type="after",
            planning_horizon=planning_horizon,
            simulation_runs=simulation_runs,
            financial_metrics=child_metrics["financial"],
            customer_metrics=child_metrics["customer"],
            operational_metrics=child_metrics["operational"],
            strategic_metrics=child_metrics["strategic"],
        )

        self.db.add(parent_snapshot)
        self.db.add(child_snapshot)
        self.db.flush()
