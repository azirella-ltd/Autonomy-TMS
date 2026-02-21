"""
Agent Context Explainer — Context-Aware Explanations for All Agent Types

Orchestrates explanation generation that references each agent's:
- Authority boundaries (unilateral / requires-authorization / advisory)
- Active guardrails (CDC thresholds, TRM confidence, agent mode)
- Policy parameters (theta from CFA optimization)
- Conformal prediction intervals (calibrated uncertainty)
- Feature attribution (model-derived: attention weights, gradient saliency)
- Counterfactuals (what would trigger different behavior)

Two delivery modes:
- Inline (<1ms): Template string attached to every decision
- On-demand (Ask Why API): Rich JSON with full context, optionally LLM-enhanced
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import logging

from app.models.explainability import ExplainabilityLevel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FeatureAttribution:
    """Model-derived feature importance for a decision."""
    method: str                                    # gat_attention | gradient_saliency | temporal_attention
    features: Dict[str, float] = field(default_factory=dict)           # feature → importance (0-1)
    neighbor_attention: Dict[str, float] = field(default_factory=dict) # neighbor_site → weight (GNN)
    temporal_attention: Dict[str, float] = field(default_factory=dict) # "t-1" → weight (tGNN)
    refinement_deltas: List[Dict] = field(default_factory=list)        # TRM recursive step changes

    def top_features(self, n: int = 5) -> List[Tuple[str, float]]:
        return sorted(self.features.items(), key=lambda x: abs(x[1]), reverse=True)[:n]

    def top_neighbors(self, n: int = 5) -> List[Tuple[str, float]]:
        return sorted(self.neighbor_attention.items(), key=lambda x: x[1], reverse=True)[:n]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuthorityContext:
    """Agent's authority classification for a specific decision."""
    agent_type: str                         # trm_atp, trm_po, gnn_sop, etc.
    authority_level: str                    # OPERATOR / SUPERVISOR / MANAGER / EXECUTIVE
    decision_classification: str            # UNILATERAL / REQUIRES_AUTHORIZATION / ADVISORY
    override_threshold_pct: float           # 0.20 / 0.40 / 0.60 / 1.00
    authority_statement: str                # Human-readable authority explanation
    approval_required: Optional[str] = None # "MANAGER" if escalation needed
    approval_reason: Optional[str] = None   # Why escalation was triggered

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GuardrailStatus:
    """Status of a single guardrail relative to its threshold."""
    name: str                               # demand_deviation, trm_confidence, etc.
    threshold: float
    actual: float
    status: str                             # WITHIN / APPROACHING / EXCEEDED
    margin: float                           # How close to threshold (0-1, 0=at threshold)
    action_if_exceeded: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ContextAwareExplanation:
    """Unified explanation output combining model attribution with agent context."""
    # Core
    summary: str                            # 1-sentence (always populated)
    explanation: str                        # Full text at requested verbosity
    confidence: float

    # Agent context
    authority: AuthorityContext = None
    guardrails: List[GuardrailStatus] = field(default_factory=list)
    policy_parameters: Dict[str, Any] = field(default_factory=dict)

    # Model attribution
    attribution: Optional[FeatureAttribution] = None

    # Conformal prediction
    prediction_interval: Optional[Dict[str, Any]] = None

    # Counterfactual
    counterfactuals: List[str] = field(default_factory=list)

    # Alternatives considered
    alternatives: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            'summary': self.summary,
            'explanation': self.explanation,
            'confidence': self.confidence,
            'authority': self.authority.to_dict() if self.authority else None,
            'guardrails': [g.to_dict() for g in self.guardrails],
            'policy_parameters': self.policy_parameters,
            'attribution': self.attribution.to_dict() if self.attribution else None,
            'prediction_interval': self.prediction_interval,
            'counterfactuals': self.counterfactuals,
            'alternatives': self.alternatives,
        }
        return result


# ---------------------------------------------------------------------------
# Agent Type Definitions
# ---------------------------------------------------------------------------

class AgentType(str, Enum):
    # Original 4 TRMs
    TRM_ATP = "trm_atp"
    TRM_PO = "trm_po"
    TRM_REBALANCE = "trm_rebalance"
    TRM_ORDER_TRACKING = "trm_order_tracking"
    # Extended TRMs (6 new)
    TRM_MO_EXECUTION = "trm_mo_execution"
    TRM_TO_EXECUTION = "trm_to_execution"
    TRM_QUALITY = "trm_quality"
    TRM_MAINTENANCE = "trm_maintenance"
    TRM_SUBCONTRACTING = "trm_subcontracting"
    TRM_FORECAST_ADJUSTMENT = "trm_forecast_adjustment"
    TRM_SAFETY_STOCK = "trm_safety_stock"
    # GNN models
    GNN_SOP = "gnn_sop"
    GNN_EXECUTION = "gnn_execution"


# Authority boundaries per agent type (from Agentic Authorization Protocol)
AGENT_AUTHORITY_MAP = {
    AgentType.TRM_ATP: {
        'default_level': 'OPERATOR',
        'unilateral': [
            'Reallocate within priority tier',
            'Partial fill within policy',
            'Defer non-critical orders',
            'Run CTP feasibility checks',
        ],
        'requires_auth': {
            'Logistics': ['Expedite shipment'],
            'Inventory': ['Cross-DC transfer'],
            'Supply': ['Rush purchase order'],
        },
        'forbidden': ['Override priority allocation from higher tier', 'Create new supply'],
    },
    AgentType.TRM_PO: {
        'default_level': 'OPERATOR',
        'unilateral': [
            'Create standard PO within cost threshold',
            'Select supplier from approved list',
            'Adjust PO timing within lead time window',
        ],
        'requires_auth': {
            'Procurement': ['Onboard new supplier', 'Contract deviation'],
            'Logistics': ['Freight mode change'],
            'S&OP': ['Policy exception'],
        },
        'forbidden': ['Exceed budget without approval', 'Single-source above concentration limit'],
    },
    AgentType.TRM_REBALANCE: {
        'default_level': 'OPERATOR',
        'unilateral': [
            'Intra-region transfers within policy',
            'Cycle count triggers',
            'Location assignment within warehouse',
        ],
        'requires_auth': {
            'Logistics': ['Cross-region transfer', 'Emergency transfer'],
            'S&OP': ['Safety stock exception'],
            'Supply': ['Expedite replenishment'],
        },
        'forbidden': ['Override allocation reserves', 'Transfer below safety stock'],
    },
    AgentType.TRM_ORDER_TRACKING: {
        'default_level': 'OPERATOR',
        'unilateral': [
            'Flag exceptions',
            'Recommend actions',
            'Trigger inspection',
        ],
        'requires_auth': {
            'Supervisor': ['Expedite order', 'Cancel and reorder'],
            'Quality': ['Release hold', 'Disposition'],
            'Supply': ['Return to vendor'],
        },
        'forbidden': ['Auto-cancel orders above threshold', 'Write off inventory'],
    },
    AgentType.TRM_MO_EXECUTION: {
        'default_level': 'OPERATOR',
        'unilateral': [
            'Schedule production within plan',
            'Sequence within changeover rules',
            'Batch size within MOQ/max',
        ],
        'requires_auth': {
            'Supply': ['Rush insertion into schedule'],
            'Quality': ['Release hold for production'],
            'Maintenance': ['Schedule around downtime'],
        },
        'forbidden': ['Override quality holds', 'Exceed capacity without approval'],
    },
    AgentType.TRM_TO_EXECUTION: {
        'default_level': 'OPERATOR',
        'unilateral': [
            'Release planned transfers on schedule',
            'Consolidate shipments within window',
            'Select carrier from approved list',
        ],
        'requires_auth': {
            'Logistics': ['Mode change', 'Cross-border routing'],
            'Inventory': ['Source below safety stock'],
            'Finance': ['Expedite premium above threshold'],
        },
        'forbidden': ['Cancel planned transfers without MRP approval'],
    },
    AgentType.TRM_QUALITY: {
        'default_level': 'SUPERVISOR',
        'unilateral': [
            'Place inspection hold',
            'Trigger inspection',
            'Accept within specification',
            'Disposition per standard SOP',
        ],
        'requires_auth': {
            'Plant': ['Return for rework (capacity impact)'],
            'Supply': ['Return to vendor'],
            'Finance': ['Write off / scrap above threshold'],
        },
        'forbidden': ['Release critical defects without sign-off'],
    },
    AgentType.TRM_MAINTENANCE: {
        'default_level': 'OPERATOR',
        'unilateral': [
            'Schedule preventive within window',
            'Adjust frequency within policy',
            'Assign maintenance crew',
        ],
        'requires_auth': {
            'Plant': ['Production shutdown for maintenance'],
            'Finance': ['CapEx above threshold'],
            'Procurement': ['Spare parts above budget'],
        },
        'forbidden': ['Defer safety-critical maintenance', 'Override lockout/tagout'],
    },
    AgentType.TRM_SUBCONTRACTING: {
        'default_level': 'OPERATOR',
        'unilateral': [
            'Route to approved subcontractors',
            'Split internal/external within policy',
        ],
        'requires_auth': {
            'Procurement': ['New subcontractor qualification'],
            'Quality': ['First-article inspection waiver'],
            'Finance': ['Cost premium above threshold'],
        },
        'forbidden': ['Single-source above concentration limit', 'IP-sensitive items without approval'],
    },
    AgentType.TRM_FORECAST_ADJUSTMENT: {
        'default_level': 'OPERATOR',
        'unilateral': [
            'Adjust forecast within statistical band',
            'Flag demand anomalies',
            'Incorporate POS signals',
        ],
        'requires_auth': {
            'S&OP': ['Override beyond statistical band'],
            'Channel': ['Volume commitment changes'],
            'Finance': ['Revenue forecast revision'],
        },
        'forbidden': ['Override consensus forecast without S&OP approval'],
    },
    AgentType.TRM_SAFETY_STOCK: {
        'default_level': 'OPERATOR',
        'unilateral': [
            'Compute safety stock per policy type',
            'Apply hierarchical overrides',
            'Adjust within configured bounds',
        ],
        'requires_auth': {
            'S&OP': ['Policy type change', 'Service level target change'],
            'Finance': ['Working capital impact above threshold'],
        },
        'forbidden': ['Zero safety stock without S&OP approval'],
    },
    AgentType.GNN_SOP: {
        'default_level': 'ADVISORY',
        'unilateral': [
            'Compute risk scores',
            'Generate structural embeddings',
            'Recommend safety stock multipliers',
        ],
        'requires_auth': {
            'S&OP': ['Policy parameter changes'],
            'Executive': ['Guardrail changes'],
        },
        'forbidden': ['Direct execution of any kind'],
    },
    AgentType.GNN_EXECUTION: {
        'default_level': 'ADVISORY',
        'unilateral': [
            'Generate priority allocations',
            'Compute demand forecasts',
            'Detect exception probabilities',
        ],
        'requires_auth': {
            'S&OP': ['Override allocation priorities'],
        },
        'forbidden': ['Direct execution — allocations consumed by TRMs only'],
    },
}

# Override threshold by authority level
AUTHORITY_OVERRIDE_THRESHOLDS = {
    'OPERATOR': 0.20,
    'SUPERVISOR': 0.40,
    'MANAGER': 0.60,
    'EXECUTIVE': 1.00,
    'ADVISORY': 0.0,
}

# Approval thresholds by decision category (from planning_decision.py)
APPROVAL_THRESHOLDS = {
    'demand_forecast': {
        'manager': {'delta_percent': 10},
        'director': {'delta_percent': 25},
        'vp': {'delta_percent': 50},
    },
    'supply_plan': {
        'manager': {'cost_delta': 10000},
        'director': {'cost_delta': 50000},
        'vp': {'cost_delta': 100000},
    },
    'safety_stock': {
        'manager': {'delta_percent': 20},
        'director': {'delta_percent': 50},
    },
    'sourcing': {
        'manager': {'cost_delta': 25000},
        'director': {'cost_delta': 100000},
        'vp': {'cost_delta': 500000},
    },
}

# CDC threshold defaults (from cdc_monitor.py CDCConfig)
CDC_THRESHOLDS = {
    'demand_deviation': {'value': 0.15, 'action': 'FULL_CFA', 'severity': 'HIGH'},
    'inventory_ratio_low': {'value': 0.70, 'action': 'ALLOCATION_ONLY', 'severity': 'MEDIUM'},
    'inventory_ratio_high': {'value': 1.50, 'action': 'ALLOCATION_ONLY', 'severity': 'LOW'},
    'service_level_drop': {'value': 0.05, 'action': 'FULL_CFA', 'severity': 'CRITICAL'},
    'lead_time_increase': {'value': 0.30, 'action': 'PARAM_ADJUSTMENT', 'severity': 'MEDIUM'},
    'backlog_growth_days': {'value': 2, 'action': 'ALLOCATION_ONLY', 'severity': 'LOW'},
    'supplier_reliability_drop': {'value': 0.15, 'action': 'FULL_CFA', 'severity': 'HIGH'},
}


# ---------------------------------------------------------------------------
# Authority Context Resolver
# ---------------------------------------------------------------------------

class AuthorityContextResolver:
    """Resolves authority boundaries for a given agent type and decision."""

    @staticmethod
    def resolve(
        agent_type: AgentType,
        decision_category: Optional[str] = None,
        decision_value: Optional[float] = None,
        delta_percent: Optional[float] = None,
    ) -> AuthorityContext:
        authority_def = AGENT_AUTHORITY_MAP.get(agent_type, {})
        level = authority_def.get('default_level', 'OPERATOR')
        override_pct = AUTHORITY_OVERRIDE_THRESHOLDS.get(level, 0.0)

        # Determine classification
        classification = 'UNILATERAL'
        approval_required = None
        approval_reason = None

        # Check if decision value exceeds approval thresholds
        if decision_category and decision_category in APPROVAL_THRESHOLDS:
            thresholds = APPROVAL_THRESHOLDS[decision_category]
            for approval_level in ['vp', 'director', 'manager']:
                level_thresholds = thresholds.get(approval_level, {})
                if 'cost_delta' in level_thresholds and decision_value is not None:
                    if abs(decision_value) > level_thresholds['cost_delta']:
                        classification = 'REQUIRES_AUTHORIZATION'
                        approval_required = approval_level.upper()
                        approval_reason = (
                            f"Cost delta ${abs(decision_value):,.0f} exceeds "
                            f"${level_thresholds['cost_delta']:,.0f} threshold"
                        )
                        break
                if 'delta_percent' in level_thresholds and delta_percent is not None:
                    if abs(delta_percent) > level_thresholds['delta_percent']:
                        classification = 'REQUIRES_AUTHORIZATION'
                        approval_required = approval_level.upper()
                        approval_reason = (
                            f"Change of {abs(delta_percent):.1f}% exceeds "
                            f"{level_thresholds['delta_percent']}% threshold"
                        )
                        break

        # GNN models are always advisory
        if level == 'ADVISORY':
            classification = 'ADVISORY'

        # Build authority statement
        unilateral_actions = authority_def.get('unilateral', [])
        auth_actions = authority_def.get('requires_auth', {})

        if classification == 'UNILATERAL':
            statement = (
                f"This decision is within my unilateral authority as {agent_type.value}. "
                f"Permitted actions: {', '.join(unilateral_actions[:2])}."
            )
        elif classification == 'ADVISORY':
            statement = (
                f"This is an advisory recommendation from {agent_type.value}. "
                f"No direct execution authority — outputs consumed by downstream agents."
            )
        else:
            auth_from = []
            for owner, actions in auth_actions.items():
                auth_from.append(f"{owner} ({', '.join(actions[:1])})")
            statement = (
                f"This decision requires {approval_required} approval. "
                f"{approval_reason}. "
                f"Authorization needed from: {'; '.join(auth_from[:2])}."
            )

        return AuthorityContext(
            agent_type=agent_type.value,
            authority_level=level,
            decision_classification=classification,
            override_threshold_pct=override_pct,
            authority_statement=statement,
            approval_required=approval_required,
            approval_reason=approval_reason,
        )


# ---------------------------------------------------------------------------
# Guardrail Status Reporter
# ---------------------------------------------------------------------------

class GuardrailStatusReporter:
    """Reports active guardrail status for a decision context."""

    @staticmethod
    def classify_status(actual: float, threshold: float, invert: bool = False) -> Tuple[str, float]:
        """
        Classify guardrail status.

        Args:
            actual: Current metric value
            threshold: Threshold value
            invert: If True, exceeding means going BELOW threshold (e.g., inventory_ratio_low)
        """
        if invert:
            ratio = actual / threshold if threshold != 0 else 1.0
            margin = ratio - 1.0  # Positive = above threshold (WITHIN)
        else:
            ratio = actual / threshold if threshold != 0 else 0.0
            margin = 1.0 - ratio  # Positive = below threshold (WITHIN)

        if margin < 0:
            return 'EXCEEDED', abs(margin)
        elif margin < 0.20:
            return 'APPROACHING', margin
        else:
            return 'WITHIN', margin

    @staticmethod
    def report(
        metrics: Optional[Dict[str, float]] = None,
        trm_confidence: Optional[float] = None,
        trm_confidence_threshold: float = 0.7,
        agent_mode: str = 'copilot',
        cdc_config: Optional[Dict[str, float]] = None,
    ) -> List[GuardrailStatus]:
        """
        Report all active guardrails and their current status.

        Args:
            metrics: Current site metrics (demand_deviation, inventory_ratio, etc.)
            trm_confidence: Current TRM model confidence (0-1)
            trm_confidence_threshold: Minimum confidence to apply TRM
            agent_mode: 'copilot' or 'autonomous'
            cdc_config: Override CDC thresholds (default from CDC_THRESHOLDS)
        """
        guardrails = []
        thresholds = cdc_config or {k: v['value'] for k, v in CDC_THRESHOLDS.items()}
        metrics = metrics or {}

        # CDC threshold checks
        if 'demand_deviation' in metrics:
            t = thresholds.get('demand_deviation', 0.15)
            status, margin = GuardrailStatusReporter.classify_status(
                abs(metrics['demand_deviation']), t
            )
            guardrails.append(GuardrailStatus(
                name='demand_deviation',
                threshold=t,
                actual=abs(metrics['demand_deviation']),
                status=status,
                margin=margin,
                action_if_exceeded=CDC_THRESHOLDS['demand_deviation']['action'],
            ))

        if 'inventory_ratio' in metrics:
            ratio = metrics['inventory_ratio']
            t_low = thresholds.get('inventory_ratio_low', 0.70)
            t_high = thresholds.get('inventory_ratio_high', 1.50)

            if ratio < t_low:
                margin = (ratio - t_low) / t_low  # Negative
                guardrails.append(GuardrailStatus(
                    name='inventory_ratio_low',
                    threshold=t_low,
                    actual=ratio,
                    status='EXCEEDED',
                    margin=abs(margin),
                    action_if_exceeded=CDC_THRESHOLDS['inventory_ratio_low']['action'],
                ))
            elif ratio > t_high:
                margin = (ratio - t_high) / t_high
                guardrails.append(GuardrailStatus(
                    name='inventory_ratio_high',
                    threshold=t_high,
                    actual=ratio,
                    status='EXCEEDED',
                    margin=margin,
                    action_if_exceeded=CDC_THRESHOLDS['inventory_ratio_high']['action'],
                ))
            else:
                # Within range — report distance to nearest boundary
                dist_low = (ratio - t_low) / (t_high - t_low)
                dist_high = (t_high - ratio) / (t_high - t_low)
                nearest = min(dist_low, dist_high)
                status = 'APPROACHING' if nearest < 0.20 else 'WITHIN'
                guardrails.append(GuardrailStatus(
                    name='inventory_ratio',
                    threshold=t_low,
                    actual=ratio,
                    status=status,
                    margin=nearest,
                ))

        if 'service_level_gap' in metrics:
            t = thresholds.get('service_level_drop', 0.05)
            gap = metrics['service_level_gap']  # target - actual (positive = below target)
            status, margin = GuardrailStatusReporter.classify_status(gap, t)
            guardrails.append(GuardrailStatus(
                name='service_level_drop',
                threshold=t,
                actual=gap,
                status=status,
                margin=margin,
                action_if_exceeded=CDC_THRESHOLDS['service_level_drop']['action'],
            ))

        if 'lead_time_increase' in metrics:
            t = thresholds.get('lead_time_increase', 0.30)
            status, margin = GuardrailStatusReporter.classify_status(
                metrics['lead_time_increase'], t
            )
            guardrails.append(GuardrailStatus(
                name='lead_time_increase',
                threshold=t,
                actual=metrics['lead_time_increase'],
                status=status,
                margin=margin,
                action_if_exceeded=CDC_THRESHOLDS['lead_time_increase']['action'],
            ))

        if 'supplier_reliability_drop' in metrics:
            t = thresholds.get('supplier_reliability_drop', 0.15)
            status, margin = GuardrailStatusReporter.classify_status(
                metrics['supplier_reliability_drop'], t
            )
            guardrails.append(GuardrailStatus(
                name='supplier_reliability_drop',
                threshold=t,
                actual=metrics['supplier_reliability_drop'],
                status=status,
                margin=margin,
                action_if_exceeded=CDC_THRESHOLDS['supplier_reliability_drop']['action'],
            ))

        # TRM confidence guardrail
        if trm_confidence is not None:
            conf_margin = (trm_confidence - trm_confidence_threshold) / trm_confidence_threshold
            if trm_confidence < trm_confidence_threshold:
                status = 'EXCEEDED'
            elif conf_margin < 0.20:
                status = 'APPROACHING'
            else:
                status = 'WITHIN'
            guardrails.append(GuardrailStatus(
                name='trm_confidence',
                threshold=trm_confidence_threshold,
                actual=trm_confidence,
                status=status,
                margin=abs(conf_margin),
                action_if_exceeded='Deterministic fallback',
            ))

        # Agent mode guardrail
        guardrails.append(GuardrailStatus(
            name='agent_mode',
            threshold=0,
            actual=0,
            status=agent_mode.upper(),
            margin=1.0,
            action_if_exceeded=f'Operating in {agent_mode} mode',
        ))

        return guardrails


# ---------------------------------------------------------------------------
# Policy Parameter Resolver
# ---------------------------------------------------------------------------

class PolicyParameterResolver:
    """Resolves active policy parameters (theta) for explanation context."""

    @staticmethod
    def resolve(
        policy_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Format policy parameters for explanation context.

        Args:
            policy_params: Active policy parameters from powell_policy_parameters table
        """
        if not policy_params:
            return {'status': 'No active policy parameters'}

        return {
            'parameters': policy_params.get('parameters', {}),
            'optimization_method': policy_params.get('optimization_method', 'unknown'),
            'optimization_objective': policy_params.get('optimization_objective', 'unknown'),
            'valid_from': str(policy_params.get('valid_from', '')),
            'valid_to': str(policy_params.get('valid_to', '')),
            'confidence_interval': [
                policy_params.get('confidence_interval_lower'),
                policy_params.get('confidence_interval_upper'),
            ],
        }


# ---------------------------------------------------------------------------
# Conformal Context Formatter
# ---------------------------------------------------------------------------

class ConformalContextFormatter:
    """Formats conformal prediction intervals with calibration quality."""

    @staticmethod
    def format(
        prediction: Optional[float] = None,
        interval_lower: Optional[float] = None,
        interval_upper: Optional[float] = None,
        coverage: Optional[float] = None,
        target_coverage: float = 0.80,
        empirical_coverage: Optional[float] = None,
        nonconformity_score: Optional[float] = None,
        drift_detected: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if prediction is None:
            return None

        # Assess calibration quality
        if empirical_coverage is not None:
            coverage_gap = abs(empirical_coverage - target_coverage)
            if coverage_gap < 0.05:
                calibration_quality = 'GOOD'
            elif coverage_gap < 0.15:
                calibration_quality = 'DEGRADED'
            else:
                calibration_quality = 'POOR'
        else:
            calibration_quality = 'INSUFFICIENT_DATA'

        if drift_detected:
            calibration_quality = 'DEGRADED (drift detected)'

        return {
            'estimate': prediction,
            'lower': interval_lower,
            'upper': interval_upper,
            'coverage': coverage or target_coverage,
            'empirical_coverage': empirical_coverage,
            'calibration_quality': calibration_quality,
            'nonconformity_score': nonconformity_score,
            'drift_detected': drift_detected,
        }


# ---------------------------------------------------------------------------
# Counterfactual Generator
# ---------------------------------------------------------------------------

class CounterfactualGenerator:
    """Generates lightweight counterfactuals by identifying nearest threshold boundaries."""

    @staticmethod
    def generate(
        guardrails: List[GuardrailStatus],
        authority: AuthorityContext,
        decision_context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        counterfactuals = []
        context = decision_context or {}

        # Threshold proximity counterfactuals from guardrails
        for g in guardrails:
            if g.name == 'agent_mode':
                continue
            if g.status == 'APPROACHING':
                counterfactuals.append(
                    f"If {g.name} moved from {g.actual:.2f} past threshold {g.threshold:.2f}, "
                    f"action '{g.action_if_exceeded}' would be triggered."
                )
            elif g.status == 'EXCEEDED':
                counterfactuals.append(
                    f"Guardrail {g.name} is exceeded ({g.actual:.2f} vs threshold {g.threshold:.2f}). "
                    f"Action '{g.action_if_exceeded}' has been triggered."
                )

        # Authority escalation counterfactual
        if authority.decision_classification == 'UNILATERAL':
            # Find next escalation boundary
            if 'cost_delta' in context:
                for level in ['manager', 'director', 'vp']:
                    cat = context.get('decision_category', 'supply_plan')
                    if cat in APPROVAL_THRESHOLDS:
                        level_t = APPROVAL_THRESHOLDS[cat].get(level, {})
                        if 'cost_delta' in level_t:
                            threshold = level_t['cost_delta']
                            if abs(context['cost_delta']) < threshold:
                                counterfactuals.append(
                                    f"If cost exceeded ${threshold:,.0f} "
                                    f"(currently ${abs(context['cost_delta']):,.0f}), "
                                    f"{level.upper()} approval would be required."
                                )
                                break

        # Confidence counterfactual
        if 'trm_confidence' in context:
            conf = context['trm_confidence']
            threshold = context.get('trm_confidence_threshold', 0.7)
            if conf >= threshold:
                counterfactuals.append(
                    f"If model confidence dropped below {threshold:.0%} "
                    f"(currently {conf:.0%}), deterministic fallback would be used."
                )

        return counterfactuals[:3]  # Max 3 counterfactuals


# ---------------------------------------------------------------------------
# Main Service
# ---------------------------------------------------------------------------

class AgentContextExplainer:
    """
    Central orchestrator for context-aware decision explanations.

    Usage:
        explainer = AgentContextExplainer(agent_type=AgentType.TRM_PO)
        explanation = explainer.generate_inline_explanation(
            decision_summary="Order 500 units from Supplier-A",
            confidence=0.85,
            metrics={'demand_deviation': 0.12, 'inventory_ratio': 0.85},
            trm_confidence=0.85,
            agent_mode='copilot',
            policy_params={...},
            decision_category='supply_plan',
            decision_value=7500,
        )
    """

    def __init__(self, agent_type: AgentType):
        self.agent_type = agent_type
        self._authority_resolver = AuthorityContextResolver()
        self._guardrail_reporter = GuardrailStatusReporter()
        self._policy_resolver = PolicyParameterResolver()
        self._conformal_formatter = ConformalContextFormatter()
        self._counterfactual_gen = CounterfactualGenerator()

    def resolve_authority(
        self,
        decision_category: Optional[str] = None,
        decision_value: Optional[float] = None,
        delta_percent: Optional[float] = None,
    ) -> AuthorityContext:
        return self._authority_resolver.resolve(
            agent_type=self.agent_type,
            decision_category=decision_category,
            decision_value=decision_value,
            delta_percent=delta_percent,
        )

    def report_guardrails(
        self,
        metrics: Optional[Dict[str, float]] = None,
        trm_confidence: Optional[float] = None,
        trm_confidence_threshold: float = 0.7,
        agent_mode: str = 'copilot',
    ) -> List[GuardrailStatus]:
        return self._guardrail_reporter.report(
            metrics=metrics,
            trm_confidence=trm_confidence,
            trm_confidence_threshold=trm_confidence_threshold,
            agent_mode=agent_mode,
        )

    def generate_inline_explanation(
        self,
        decision_summary: str,
        confidence: float,
        level: ExplainabilityLevel = ExplainabilityLevel.NORMAL,
        # Context inputs
        metrics: Optional[Dict[str, float]] = None,
        trm_confidence: Optional[float] = None,
        trm_confidence_threshold: float = 0.7,
        agent_mode: str = 'copilot',
        policy_params: Optional[Dict[str, Any]] = None,
        decision_category: Optional[str] = None,
        decision_value: Optional[float] = None,
        delta_percent: Optional[float] = None,
        attribution: Optional[FeatureAttribution] = None,
        # Conformal
        prediction: Optional[float] = None,
        interval_lower: Optional[float] = None,
        interval_upper: Optional[float] = None,
        coverage: Optional[float] = None,
        empirical_coverage: Optional[float] = None,
        nonconformity_score: Optional[float] = None,
        drift_detected: bool = False,
    ) -> ContextAwareExplanation:
        """
        Generate a context-aware explanation. Template-based for real-time use.

        Returns ContextAwareExplanation with all context assembled.
        """
        # Resolve all context
        authority = self.resolve_authority(
            decision_category=decision_category,
            decision_value=decision_value,
            delta_percent=delta_percent,
        )

        guardrails = self.report_guardrails(
            metrics=metrics,
            trm_confidence=trm_confidence,
            trm_confidence_threshold=trm_confidence_threshold,
            agent_mode=agent_mode,
        )

        policy = self._policy_resolver.resolve(policy_params)

        conformal = self._conformal_formatter.format(
            prediction=prediction,
            interval_lower=interval_lower,
            interval_upper=interval_upper,
            coverage=coverage,
            empirical_coverage=empirical_coverage,
            nonconformity_score=nonconformity_score,
            drift_detected=drift_detected,
        )

        decision_context = {
            'trm_confidence': trm_confidence,
            'trm_confidence_threshold': trm_confidence_threshold,
            'decision_category': decision_category,
            'cost_delta': decision_value,
        }
        counterfactuals = self._counterfactual_gen.generate(
            guardrails=guardrails,
            authority=authority,
            decision_context=decision_context,
        )

        # Build explanation text at requested level
        from app.services.explanation_templates import render_explanation
        explanation_text = render_explanation(
            agent_type=self.agent_type,
            level=level,
            decision_summary=decision_summary,
            confidence=confidence,
            authority=authority,
            guardrails=guardrails,
            policy=policy,
            attribution=attribution,
            conformal=conformal,
            counterfactuals=counterfactuals,
        )

        # SUCCINCT is always the first sentence
        summary = decision_summary
        if confidence > 0:
            summary += f" (confidence {confidence:.0%})"

        return ContextAwareExplanation(
            summary=summary,
            explanation=explanation_text,
            confidence=confidence,
            authority=authority,
            guardrails=guardrails,
            policy_parameters=policy,
            attribution=attribution,
            prediction_interval=conformal,
            counterfactuals=counterfactuals,
        )

    async def generate_rich_explanation(
        self,
        decision_summary: str,
        confidence: float,
        level: ExplainabilityLevel = ExplainabilityLevel.VERBOSE,
        use_llm: bool = False,
        **kwargs,
    ) -> ContextAwareExplanation:
        """
        Generate a rich on-demand explanation (for Ask Why API).

        Same as inline but defaults to VERBOSE and optionally enhanced by LLM.
        """
        explanation = self.generate_inline_explanation(
            decision_summary=decision_summary,
            confidence=confidence,
            level=level,
            **kwargs,
        )

        if use_llm:
            # TODO: When Qwen 3 via vLLM is available, send structured context
            # to LLM for natural language summarization.
            # Fallback to template-based explanation if LLM unavailable.
            logger.info("LLM enhancement requested but not yet available; using template")

        return explanation
