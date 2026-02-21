"""
Explanation Templates — Per-Agent-Type × Verbosity Level

Template-based explanation generation for real-time (<1ms) inline use.
Each template can reference variables populated by AgentContextExplainer.

Template variables available:
- {decision_summary}: Core decision text
- {confidence}: 0-1 float
- {authority_statement}: From AuthorityContextResolver
- {authority_classification}: UNILATERAL / REQUIRES_AUTHORIZATION / ADVISORY
- {guardrail_summary}: One-line summary of guardrail statuses
- {guardrail_detail}: Multi-line guardrail breakdown
- {policy_detail}: Active policy parameters
- {top_feature_name}: Highest-importance feature name
- {top_feature_value}: Highest-importance feature value
- {attribution_detail}: Full attribution breakdown
- {interval_detail}: Conformal prediction interval text
- {counterfactual_detail}: Counterfactual statements
- {alternatives_detail}: Alternative actions considered
"""

from typing import Dict, List, Optional, Any
from app.services.agent_context_explainer import (
    AgentType,
    AuthorityContext,
    GuardrailStatus,
    FeatureAttribution,
)
from app.models.explainability import ExplainabilityLevel


# ---------------------------------------------------------------------------
# Template Definitions
# ---------------------------------------------------------------------------

TEMPLATES: Dict[str, Dict[str, str]] = {
    # -----------------------------------------------------------------------
    # TRM: ATP Executor
    # -----------------------------------------------------------------------
    AgentType.TRM_ATP.value: {
        ExplainabilityLevel.SUCCINCT.value: (
            "{decision_summary} (confidence {confidence:.0%}, {authority_classification})."
        ),
        ExplainabilityLevel.NORMAL.value: (
            "{decision_summary}. "
            "{authority_statement} "
            "{guardrail_summary} "
            "Confidence: {confidence:.0%}."
        ),
        ExplainabilityLevel.VERBOSE.value: (
            "{decision_summary}.\n\n"
            "**Authority**: {authority_statement}\n\n"
            "**Guardrails**: {guardrail_detail}\n\n"
            "**Policy Parameters**: {policy_detail}\n\n"
            "**Model Attribution**: {attribution_detail}\n\n"
            "**Prediction Interval**: {interval_detail}\n\n"
            "**What Would Change**: {counterfactual_detail}"
        ),
    },

    # -----------------------------------------------------------------------
    # TRM: Purchase Order Creation
    # -----------------------------------------------------------------------
    AgentType.TRM_PO.value: {
        ExplainabilityLevel.SUCCINCT.value: (
            "{decision_summary} (confidence {confidence:.0%}, {authority_classification})."
        ),
        ExplainabilityLevel.NORMAL.value: (
            "{decision_summary}. "
            "{authority_statement} "
            "Top driver: {top_feature_name} ({top_feature_value:.0%} importance). "
            "{guardrail_summary} "
            "Policy: {policy_summary}."
        ),
        ExplainabilityLevel.VERBOSE.value: (
            "{decision_summary}.\n\n"
            "**Authority**: {authority_statement}\n\n"
            "**Guardrails**: {guardrail_detail}\n\n"
            "**Policy Parameters**: {policy_detail}\n\n"
            "**Model Attribution**: {attribution_detail}\n\n"
            "**Prediction Interval**: {interval_detail}\n\n"
            "**What Would Change**: {counterfactual_detail}\n\n"
            "**Alternatives**: {alternatives_detail}"
        ),
    },

    # -----------------------------------------------------------------------
    # TRM: Inventory Rebalancing
    # -----------------------------------------------------------------------
    AgentType.TRM_REBALANCE.value: {
        ExplainabilityLevel.SUCCINCT.value: (
            "{decision_summary} (confidence {confidence:.0%}, {authority_classification})."
        ),
        ExplainabilityLevel.NORMAL.value: (
            "{decision_summary}. "
            "{authority_statement} "
            "{guardrail_summary} "
            "Confidence: {confidence:.0%}."
        ),
        ExplainabilityLevel.VERBOSE.value: (
            "{decision_summary}.\n\n"
            "**Authority**: {authority_statement}\n\n"
            "**Guardrails**: {guardrail_detail}\n\n"
            "**Policy Parameters**: {policy_detail}\n\n"
            "**Model Attribution**: {attribution_detail}\n\n"
            "**Prediction Interval**: {interval_detail}\n\n"
            "**What Would Change**: {counterfactual_detail}"
        ),
    },

    # -----------------------------------------------------------------------
    # TRM: Order Tracking
    # -----------------------------------------------------------------------
    AgentType.TRM_ORDER_TRACKING.value: {
        ExplainabilityLevel.SUCCINCT.value: (
            "{decision_summary} (confidence {confidence:.0%}, {authority_classification})."
        ),
        ExplainabilityLevel.NORMAL.value: (
            "{decision_summary}. "
            "{authority_statement} "
            "{guardrail_summary} "
            "Confidence: {confidence:.0%}."
        ),
        ExplainabilityLevel.VERBOSE.value: (
            "{decision_summary}.\n\n"
            "**Authority**: {authority_statement}\n\n"
            "**Guardrails**: {guardrail_detail}\n\n"
            "**Policy Parameters**: {policy_detail}\n\n"
            "**Model Attribution**: {attribution_detail}\n\n"
            "**Prediction Interval**: {interval_detail}\n\n"
            "**What Would Change**: {counterfactual_detail}"
        ),
    },

    # -----------------------------------------------------------------------
    # TRM: Manufacturing Order Execution
    # -----------------------------------------------------------------------
    AgentType.TRM_MO_EXECUTION.value: {
        ExplainabilityLevel.SUCCINCT.value: (
            "{decision_summary} (confidence {confidence:.0%}, {authority_classification})."
        ),
        ExplainabilityLevel.NORMAL.value: (
            "{decision_summary}. "
            "{authority_statement} "
            "{guardrail_summary} "
            "Confidence: {confidence:.0%}."
        ),
        ExplainabilityLevel.VERBOSE.value: (
            "{decision_summary}.\n\n"
            "**Authority**: {authority_statement}\n\n"
            "**Guardrails**: {guardrail_detail}\n\n"
            "**Policy Parameters**: {policy_detail}\n\n"
            "**Model Attribution**: {attribution_detail}\n\n"
            "**Prediction Interval**: {interval_detail}\n\n"
            "**What Would Change**: {counterfactual_detail}"
        ),
    },

    # -----------------------------------------------------------------------
    # TRM: Transfer Order Execution
    # -----------------------------------------------------------------------
    AgentType.TRM_TO_EXECUTION.value: {
        ExplainabilityLevel.SUCCINCT.value: (
            "{decision_summary} (confidence {confidence:.0%}, {authority_classification})."
        ),
        ExplainabilityLevel.NORMAL.value: (
            "{decision_summary}. "
            "{authority_statement} "
            "{guardrail_summary} "
            "Confidence: {confidence:.0%}."
        ),
        ExplainabilityLevel.VERBOSE.value: (
            "{decision_summary}.\n\n"
            "**Authority**: {authority_statement}\n\n"
            "**Guardrails**: {guardrail_detail}\n\n"
            "**Policy Parameters**: {policy_detail}\n\n"
            "**Model Attribution**: {attribution_detail}\n\n"
            "**Prediction Interval**: {interval_detail}\n\n"
            "**What Would Change**: {counterfactual_detail}"
        ),
    },

    # -----------------------------------------------------------------------
    # TRM: Quality Disposition
    # -----------------------------------------------------------------------
    AgentType.TRM_QUALITY.value: {
        ExplainabilityLevel.SUCCINCT.value: (
            "{decision_summary} (confidence {confidence:.0%}, {authority_classification})."
        ),
        ExplainabilityLevel.NORMAL.value: (
            "{decision_summary}. "
            "{authority_statement} "
            "{guardrail_summary} "
            "Confidence: {confidence:.0%}."
        ),
        ExplainabilityLevel.VERBOSE.value: (
            "{decision_summary}.\n\n"
            "**Authority**: {authority_statement}\n\n"
            "**Guardrails**: {guardrail_detail}\n\n"
            "**Policy Parameters**: {policy_detail}\n\n"
            "**Model Attribution**: {attribution_detail}\n\n"
            "**Prediction Interval**: {interval_detail}\n\n"
            "**What Would Change**: {counterfactual_detail}"
        ),
    },

    # -----------------------------------------------------------------------
    # TRM: Maintenance Scheduling
    # -----------------------------------------------------------------------
    AgentType.TRM_MAINTENANCE.value: {
        ExplainabilityLevel.SUCCINCT.value: (
            "{decision_summary} (confidence {confidence:.0%}, {authority_classification})."
        ),
        ExplainabilityLevel.NORMAL.value: (
            "{decision_summary}. "
            "{authority_statement} "
            "{guardrail_summary} "
            "Confidence: {confidence:.0%}."
        ),
        ExplainabilityLevel.VERBOSE.value: (
            "{decision_summary}.\n\n"
            "**Authority**: {authority_statement}\n\n"
            "**Guardrails**: {guardrail_detail}\n\n"
            "**Policy Parameters**: {policy_detail}\n\n"
            "**Model Attribution**: {attribution_detail}\n\n"
            "**Prediction Interval**: {interval_detail}\n\n"
            "**What Would Change**: {counterfactual_detail}"
        ),
    },

    # -----------------------------------------------------------------------
    # TRM: Subcontracting
    # -----------------------------------------------------------------------
    AgentType.TRM_SUBCONTRACTING.value: {
        ExplainabilityLevel.SUCCINCT.value: (
            "{decision_summary} (confidence {confidence:.0%}, {authority_classification})."
        ),
        ExplainabilityLevel.NORMAL.value: (
            "{decision_summary}. "
            "{authority_statement} "
            "{guardrail_summary} "
            "Confidence: {confidence:.0%}."
        ),
        ExplainabilityLevel.VERBOSE.value: (
            "{decision_summary}.\n\n"
            "**Authority**: {authority_statement}\n\n"
            "**Guardrails**: {guardrail_detail}\n\n"
            "**Policy Parameters**: {policy_detail}\n\n"
            "**Model Attribution**: {attribution_detail}\n\n"
            "**Prediction Interval**: {interval_detail}\n\n"
            "**What Would Change**: {counterfactual_detail}"
        ),
    },

    # -----------------------------------------------------------------------
    # TRM: Forecast Adjustment
    # -----------------------------------------------------------------------
    AgentType.TRM_FORECAST_ADJUSTMENT.value: {
        ExplainabilityLevel.SUCCINCT.value: (
            "{decision_summary} (confidence {confidence:.0%}, {authority_classification})."
        ),
        ExplainabilityLevel.NORMAL.value: (
            "{decision_summary}. "
            "{authority_statement} "
            "Top driver: {top_feature_name} ({top_feature_value:.0%} importance). "
            "{guardrail_summary}"
        ),
        ExplainabilityLevel.VERBOSE.value: (
            "{decision_summary}.\n\n"
            "**Authority**: {authority_statement}\n\n"
            "**Guardrails**: {guardrail_detail}\n\n"
            "**Policy Parameters**: {policy_detail}\n\n"
            "**Model Attribution**: {attribution_detail}\n\n"
            "**Prediction Interval**: {interval_detail}\n\n"
            "**What Would Change**: {counterfactual_detail}\n\n"
            "**Alternatives**: {alternatives_detail}"
        ),
    },

    # -----------------------------------------------------------------------
    # TRM: Safety Stock
    # -----------------------------------------------------------------------
    AgentType.TRM_SAFETY_STOCK.value: {
        ExplainabilityLevel.SUCCINCT.value: (
            "{decision_summary} (confidence {confidence:.0%}, {authority_classification})."
        ),
        ExplainabilityLevel.NORMAL.value: (
            "{decision_summary}. "
            "{authority_statement} "
            "Policy: {policy_summary}. "
            "{guardrail_summary}"
        ),
        ExplainabilityLevel.VERBOSE.value: (
            "{decision_summary}.\n\n"
            "**Authority**: {authority_statement}\n\n"
            "**Guardrails**: {guardrail_detail}\n\n"
            "**Policy Parameters**: {policy_detail}\n\n"
            "**Model Attribution**: {attribution_detail}\n\n"
            "**Prediction Interval**: {interval_detail}\n\n"
            "**What Would Change**: {counterfactual_detail}"
        ),
    },

    # -----------------------------------------------------------------------
    # GNN: S&OP GraphSAGE
    # -----------------------------------------------------------------------
    AgentType.GNN_SOP.value: {
        ExplainabilityLevel.SUCCINCT.value: (
            "{decision_summary} ({authority_classification})."
        ),
        ExplainabilityLevel.NORMAL.value: (
            "{decision_summary}. "
            "{authority_statement} "
            "Top influencing neighbor: {top_neighbor_name} (attention {top_neighbor_value:.0%}). "
            "{guardrail_summary}"
        ),
        ExplainabilityLevel.VERBOSE.value: (
            "{decision_summary}.\n\n"
            "**Authority**: {authority_statement}\n\n"
            "**Neighbor Attention**: {neighbor_detail}\n\n"
            "**Input Feature Saliency**: {attribution_detail}\n\n"
            "**Guardrails**: {guardrail_detail}\n\n"
            "**Policy Parameters**: {policy_detail}\n\n"
            "**What Would Change**: {counterfactual_detail}"
        ),
    },

    # -----------------------------------------------------------------------
    # GNN: Execution tGNN
    # -----------------------------------------------------------------------
    AgentType.GNN_EXECUTION.value: {
        ExplainabilityLevel.SUCCINCT.value: (
            "{decision_summary} (confidence {confidence:.0%}, {authority_classification})."
        ),
        ExplainabilityLevel.NORMAL.value: (
            "{decision_summary}. "
            "{authority_statement} "
            "Most influential period: {top_temporal_label} (attention {top_temporal_value:.0%}). "
            "{guardrail_summary}"
        ),
        ExplainabilityLevel.VERBOSE.value: (
            "{decision_summary}.\n\n"
            "**Authority**: {authority_statement}\n\n"
            "**Temporal Attention**: {temporal_detail}\n\n"
            "**Neighbor Attention**: {neighbor_detail}\n\n"
            "**Input Feature Saliency**: {attribution_detail}\n\n"
            "**Guardrails**: {guardrail_detail}\n\n"
            "**Policy Parameters**: {policy_detail}\n\n"
            "**Prediction Interval**: {interval_detail}\n\n"
            "**What Would Change**: {counterfactual_detail}"
        ),
    },
}


# ---------------------------------------------------------------------------
# Helper formatters
# ---------------------------------------------------------------------------

def _format_guardrail_summary(guardrails: List[GuardrailStatus]) -> str:
    """One-line guardrail status summary."""
    exceeded = [g for g in guardrails if g.status == 'EXCEEDED' and g.name != 'agent_mode']
    approaching = [g for g in guardrails if g.status == 'APPROACHING']

    if exceeded:
        names = ', '.join(g.name for g in exceeded)
        return f"Guardrails exceeded: {names}."
    elif approaching:
        names = ', '.join(g.name for g in approaching)
        return f"Guardrails approaching threshold: {names}."
    else:
        return "All guardrails within thresholds."


def _format_guardrail_detail(guardrails: List[GuardrailStatus]) -> str:
    """Multi-line guardrail breakdown."""
    if not guardrails:
        return "No guardrails configured."
    lines = []
    for g in guardrails:
        if g.name == 'agent_mode':
            lines.append(f"- Agent mode: {g.status}")
            continue
        icon = {'WITHIN': 'OK', 'APPROACHING': 'WARN', 'EXCEEDED': 'ALERT'}.get(g.status, '?')
        lines.append(
            f"- [{icon}] {g.name}: actual={g.actual:.3f}, "
            f"threshold={g.threshold:.3f}, status={g.status}"
        )
        if g.action_if_exceeded and g.status != 'WITHIN':
            lines.append(f"  Action: {g.action_if_exceeded}")
    return '\n'.join(lines)


def _format_policy_detail(policy: Dict[str, Any]) -> str:
    """Format policy parameters for display."""
    if policy.get('status') == 'No active policy parameters':
        return "No active policy parameters."
    params = policy.get('parameters', {})
    method = policy.get('optimization_method', 'unknown')
    objective = policy.get('optimization_objective', 'unknown')
    valid_from = policy.get('valid_from', '')
    valid_to = policy.get('valid_to', '')

    param_strs = [f"{k}={v}" for k, v in params.items()] if params else ['(none)']
    return (
        f"Theta: {', '.join(param_strs)}. "
        f"Optimized via {method} for {objective}"
        + (f" (valid {valid_from} to {valid_to})" if valid_from else "")
        + "."
    )


def _format_policy_summary(policy: Dict[str, Any]) -> str:
    """Short policy summary for NORMAL level."""
    params = policy.get('parameters', {})
    if not params:
        return "no active theta"
    top_params = list(params.items())[:2]
    return ', '.join(f"{k}={v}" for k, v in top_params)


def _format_attribution_detail(attribution: Optional[FeatureAttribution]) -> str:
    """Format feature attribution for display."""
    if not attribution:
        return "No model attribution available (on-demand only)."
    lines = [f"Method: {attribution.method}"]
    if attribution.features:
        top = attribution.top_features(5)
        for name, value in top:
            bar = '█' * int(abs(value) * 20)
            lines.append(f"- {name}: {value:.3f} {bar}")
    return '\n'.join(lines)


def _format_neighbor_detail(attribution: Optional[FeatureAttribution]) -> str:
    """Format neighbor attention for GNN models."""
    if not attribution or not attribution.neighbor_attention:
        return "No neighbor attention available."
    top = attribution.top_neighbors(5)
    lines = []
    for name, value in top:
        bar = '█' * int(value * 20)
        lines.append(f"- {name}: {value:.3f} {bar}")
    return '\n'.join(lines)


def _format_temporal_detail(attribution: Optional[FeatureAttribution]) -> str:
    """Format temporal attention for tGNN."""
    if not attribution or not attribution.temporal_attention:
        return "No temporal attention available."
    sorted_periods = sorted(
        attribution.temporal_attention.items(),
        key=lambda x: x[1], reverse=True
    )
    lines = []
    for period, weight in sorted_periods[:5]:
        bar = '█' * int(weight * 20)
        lines.append(f"- {period}: {weight:.3f} {bar}")
    return '\n'.join(lines)


def _format_interval_detail(conformal: Optional[Dict[str, Any]]) -> str:
    """Format conformal prediction interval."""
    if not conformal:
        return "No prediction interval available."
    est = conformal.get('estimate', 0)
    lower = conformal.get('lower', 0)
    upper = conformal.get('upper', 0)
    coverage = conformal.get('coverage', 0)
    quality = conformal.get('calibration_quality', 'UNKNOWN')
    return (
        f"Estimate: {est:.1f} [{lower:.1f}, {upper:.1f}] "
        f"at {coverage:.0%} coverage. Calibration: {quality}."
    )


def _format_counterfactual_detail(counterfactuals: List[str]) -> str:
    if not counterfactuals:
        return "No counterfactuals identified."
    return '\n'.join(f"- {cf}" for cf in counterfactuals)


def _format_alternatives_detail(alternatives: List[Dict[str, Any]]) -> str:
    if not alternatives:
        return "No alternatives considered."
    lines = []
    for alt in alternatives[:3]:
        score = alt.get('score', '')
        reason = alt.get('why_not_chosen', '')
        lines.append(f"- {alt.get('alternative', '?')}: score={score}, rejected because {reason}")
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_explanation(
    agent_type: AgentType,
    level: ExplainabilityLevel,
    decision_summary: str,
    confidence: float,
    authority: AuthorityContext,
    guardrails: List[GuardrailStatus],
    policy: Dict[str, Any],
    attribution: Optional[FeatureAttribution] = None,
    conformal: Optional[Dict[str, Any]] = None,
    counterfactuals: Optional[List[str]] = None,
    alternatives: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Render a context-aware explanation using the appropriate template.

    Returns formatted explanation string at the requested verbosity level.
    """
    template_set = TEMPLATES.get(agent_type.value)
    if not template_set:
        return f"{decision_summary}. Confidence: {confidence:.0%}."

    template = template_set.get(level.value, template_set.get(ExplainabilityLevel.NORMAL.value, ''))

    # Extract top attribution values for NORMAL-level templates
    top_feature_name = 'N/A'
    top_feature_value = 0.0
    top_neighbor_name = 'N/A'
    top_neighbor_value = 0.0
    top_temporal_label = 'N/A'
    top_temporal_value = 0.0

    if attribution:
        top_features = attribution.top_features(1)
        if top_features:
            top_feature_name, top_feature_value = top_features[0]
        top_neighbors = attribution.top_neighbors(1)
        if top_neighbors:
            top_neighbor_name, top_neighbor_value = top_neighbors[0]
        if attribution.temporal_attention:
            sorted_t = sorted(attribution.temporal_attention.items(), key=lambda x: x[1], reverse=True)
            if sorted_t:
                top_temporal_label, top_temporal_value = sorted_t[0]

    # Build all template variables
    variables = {
        'decision_summary': decision_summary,
        'confidence': confidence,
        'authority_statement': authority.authority_statement,
        'authority_classification': authority.decision_classification,
        'guardrail_summary': _format_guardrail_summary(guardrails),
        'guardrail_detail': _format_guardrail_detail(guardrails),
        'policy_detail': _format_policy_detail(policy),
        'policy_summary': _format_policy_summary(policy),
        'top_feature_name': top_feature_name,
        'top_feature_value': top_feature_value,
        'top_neighbor_name': top_neighbor_name,
        'top_neighbor_value': top_neighbor_value,
        'top_temporal_label': top_temporal_label,
        'top_temporal_value': top_temporal_value,
        'attribution_detail': _format_attribution_detail(attribution),
        'neighbor_detail': _format_neighbor_detail(attribution),
        'temporal_detail': _format_temporal_detail(attribution),
        'interval_detail': _format_interval_detail(conformal),
        'counterfactual_detail': _format_counterfactual_detail(counterfactuals or []),
        'alternatives_detail': _format_alternatives_detail(alternatives or []),
    }

    try:
        return template.format(**variables)
    except (KeyError, ValueError) as e:
        logger.warning("Template rendering failed for %s/%s: %s", agent_type, level, e)
        return f"{decision_summary}. Confidence: {confidence:.0%}. {authority.authority_statement}"


import logging
logger = logging.getLogger(__name__)
