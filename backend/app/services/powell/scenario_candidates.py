"""
Scenario Candidate Generator — Template-Based What-If Generation

Generates concrete candidate action sets from a library of templates per
TRM type. Each template has a Beta(alpha, beta) posterior tracking its
historical success rate:

    prior_likelihood = alpha / (alpha + beta)

Templates are sorted by prior_likelihood DESC and tried in order.
The posterior is updated on each promoted/rejected scenario outcome,
implementing a learning flywheel that converges over time.

See SCENARIO_ENGINE.md Section 4 for architecture.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.agent_scenario import ScenarioTemplate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CandidateActions — a concrete set of actions to evaluate
# ---------------------------------------------------------------------------

class CandidateActions:
    """A set of proposed actions generated from a template.

    Attributes:
        template_id: DB ID of the source template (None for ad-hoc)
        template_key: Short key identifying the template pattern
        template_name: Human-readable name
        actions: List of action dicts, each containing:
            - trm_type: str
            - action_type: str (CREATE_PO, EXPEDITE_TO, etc.)
            - action_params: dict (product_id, quantity, supplier, etc.)
            - responsible_agent: str (which TRM must execute)
            - decision_likelihood: float (per-action CDT bound, if known)
            - estimated_cost: float
            - estimated_benefit: float
        prior_likelihood: float from Beta posterior
    """

    def __init__(
        self,
        template_id: Optional[int],
        template_key: str,
        template_name: str,
        actions: List[Dict[str, Any]],
        prior_likelihood: float = 0.5,
    ):
        self.template_id = template_id
        self.template_key = template_key
        self.template_name = template_name
        self.actions = actions
        self.prior_likelihood = prior_likelihood


# ---------------------------------------------------------------------------
# Default template definitions (seeded if table is empty)
# ---------------------------------------------------------------------------

DEFAULT_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    # --- ATP Shortfall Templates ---
    "atp_executor": [
        {
            "template_key": "split_fulfillment",
            "template_name": "Split Fulfillment (stock + PO remainder)",
            "template_params": {"stock_pct": 0.6, "po_remainder": True},
        },
        {
            "template_key": "fast_supplier_po",
            "template_name": "Fast Supplier PO (expedite inbound)",
            "template_params": {"supplier_selection": "fastest", "expedite": True},
        },
        {
            "template_key": "cheap_supplier_po",
            "template_name": "Cheap Supplier PO (accept delay)",
            "template_params": {"supplier_selection": "cheapest", "expedite": False},
        },
        {
            "template_key": "delay_fulfillment",
            "template_name": "Delay Fulfillment (promise later date)",
            "template_params": {"delay_days": 5},
        },
        {
            "template_key": "partial_backorder",
            "template_name": "Partial + Backorder (ship 60%, backorder 40%)",
            "template_params": {"ship_pct": 0.6, "backorder_pct": 0.4},
        },
    ],

    # --- PO Creation Templates ---
    "po_creation": [
        {
            "template_key": "primary_supplier_standard",
            "template_name": "Primary Supplier Standard",
            "template_params": {"supplier_selection": "primary", "expedite": False},
        },
        {
            "template_key": "alternate_supplier_fast",
            "template_name": "Alternate Supplier (faster, more expensive)",
            "template_params": {"supplier_selection": "alternate_fast", "expedite": True},
        },
        {
            "template_key": "split_suppliers",
            "template_name": "Split Across Suppliers",
            "template_params": {"split_strategy": "even", "supplier_count": 2},
        },
        {
            "template_key": "consolidate_existing_po",
            "template_name": "Consolidate with Existing Open PO",
            "template_params": {"consolidate": True},
        },
    ],

    # --- Inventory Rebalancing Templates ---
    "inventory_rebalancing": [
        {
            "template_key": "direct_transfer_nearest",
            "template_name": "Direct Transfer from Nearest Surplus",
            "template_params": {"strategy": "nearest_surplus"},
        },
        {
            "template_key": "crossdock_through_hub",
            "template_name": "Cross-Dock Through Hub",
            "template_params": {"strategy": "hub_crossdock"},
        },
        {
            "template_key": "emergency_shipment",
            "template_name": "Emergency Shipment (expedited)",
            "template_params": {"strategy": "emergency", "expedite": True},
        },
    ],

    # --- MO Execution Templates ---
    "mo_execution": [
        {
            "template_key": "standard_production",
            "template_name": "Standard Production Schedule",
            "template_params": {"schedule": "standard"},
        },
        {
            "template_key": "overtime_production",
            "template_name": "Overtime Production",
            "template_params": {"schedule": "overtime", "cost_multiplier": 1.5},
        },
        {
            "template_key": "subcontract_external",
            "template_name": "Subcontract Externally",
            "template_params": {"schedule": "subcontract"},
        },
        {
            "template_key": "split_internal_subcontract",
            "template_name": "Split: Partial Internal + Partial Subcontract",
            "template_params": {"schedule": "split", "internal_pct": 0.6},
        },
    ],

    # --- TO Execution Templates ---
    "to_execution": [
        {
            "template_key": "standard_transfer",
            "template_name": "Standard Transfer",
            "template_params": {"mode": "standard"},
        },
        {
            "template_key": "expedite_transfer",
            "template_name": "Expedited Transfer",
            "template_params": {"mode": "expedited", "cost_multiplier": 1.8},
        },
        {
            "template_key": "consolidated_transfer",
            "template_name": "Consolidated Transfer (batch with other TOs)",
            "template_params": {"mode": "consolidated"},
        },
    ],

    # --- Order Tracking Templates ---
    "order_tracking": [
        {
            "template_key": "escalate_supplier",
            "template_name": "Escalate to Supplier",
            "template_params": {"action": "escalate_supplier"},
        },
        {
            "template_key": "find_alternate_source",
            "template_name": "Find Alternate Source",
            "template_params": {"action": "alternate_source"},
        },
        {
            "template_key": "accept_delay",
            "template_name": "Accept Delay and Notify Customer",
            "template_params": {"action": "accept_delay"},
        },
    ],

    # --- Forecast Adjustment Templates ---
    "forecast_adjustment": [
        {
            "template_key": "adjust_proportional",
            "template_name": "Adjust Proportional to Signal Magnitude",
            "template_params": {"method": "proportional"},
        },
        {
            "template_key": "adjust_conservative",
            "template_name": "Conservative Adjustment (50% of signal)",
            "template_params": {"method": "conservative", "dampen_factor": 0.5},
        },
        {
            "template_key": "no_adjustment_monitor",
            "template_name": "No Adjustment — Monitor Only",
            "template_params": {"method": "monitor_only"},
        },
    ],

    # --- Inventory Buffer Templates ---
    "inventory_buffer": [
        {
            "template_key": "increase_buffer_10pct",
            "template_name": "Increase Buffer by 10%",
            "template_params": {"adjustment_pct": 0.10},
        },
        {
            "template_key": "increase_buffer_25pct",
            "template_name": "Increase Buffer by 25%",
            "template_params": {"adjustment_pct": 0.25},
        },
        {
            "template_key": "decrease_buffer_10pct",
            "template_name": "Decrease Buffer by 10%",
            "template_params": {"adjustment_pct": -0.10},
        },
    ],

    # --- Quality Disposition Templates ---
    "quality_disposition": [
        {
            "template_key": "rework_batch",
            "template_name": "Rework Batch",
            "template_params": {"disposition": "rework"},
        },
        {
            "template_key": "use_as_is",
            "template_name": "Use As-Is (accept deviation)",
            "template_params": {"disposition": "use_as_is"},
        },
        {
            "template_key": "scrap_reorder",
            "template_name": "Scrap and Reorder",
            "template_params": {"disposition": "scrap", "reorder": True},
        },
    ],

    # --- Maintenance Scheduling Templates ---
    "maintenance_scheduling": [
        {
            "template_key": "schedule_pm_now",
            "template_name": "Schedule Preventive Maintenance Now",
            "template_params": {"timing": "immediate"},
        },
        {
            "template_key": "defer_pm_7days",
            "template_name": "Defer PM by 7 Days",
            "template_params": {"timing": "defer", "defer_days": 7},
        },
        {
            "template_key": "outsource_maintenance",
            "template_name": "Outsource to External Contractor",
            "template_params": {"timing": "outsource"},
        },
    ],

    # --- Subcontracting Templates ---
    "subcontracting": [
        {
            "template_key": "keep_internal",
            "template_name": "Keep Internal (accept capacity constraint)",
            "template_params": {"routing": "internal"},
        },
        {
            "template_key": "full_subcontract",
            "template_name": "Full Subcontract to External",
            "template_params": {"routing": "external"},
        },
        {
            "template_key": "split_routing",
            "template_name": "Split: Internal + External",
            "template_params": {"routing": "split", "internal_pct": 0.5},
        },
    ],
}


# ---------------------------------------------------------------------------
# CandidateGenerator
# ---------------------------------------------------------------------------

class CandidateGenerator:
    """Generates candidate action sets from templates per TRM type.

    Templates are loaded from the ScenarioTemplate DB table (per tenant),
    falling back to DEFAULT_TEMPLATES if no tenant-specific templates exist.
    Templates are sorted by Beta prior likelihood and tried in order.
    """

    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    def generate_candidates(
        self,
        trm_type: str,
        context: Dict[str, Any],
        max_candidates: int = 3,
    ) -> List[CandidateActions]:
        """Generate candidate action sets for a TRM decision.

        Args:
            trm_type: TRM type that triggered the scenario
            context: Trigger context with order details, shortfall, etc.
            max_candidates: Maximum number of candidates to generate

        Returns:
            List of CandidateActions sorted by prior_likelihood DESC
        """
        # Load templates from DB
        templates = self._load_templates(trm_type)

        # Sort by Beta prior likelihood (descending)
        templates.sort(key=lambda t: t.prior_likelihood, reverse=True)

        # Generate concrete actions from top N templates
        candidates = []
        for template in templates[:max_candidates]:
            actions = self._instantiate_template(template, trm_type, context)
            candidate = CandidateActions(
                template_id=template.id,
                template_key=template.template_key,
                template_name=template.template_name,
                actions=actions,
                prior_likelihood=template.prior_likelihood,
            )
            candidates.append(candidate)

            # Update usage tracking
            template.uses_count = (template.uses_count or 0) + 1
            template.last_used_at = datetime.utcnow()

        if candidates:
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
                logger.warning("Failed to update template usage counts")

        return candidates

    def update_template_prior(self, template_id: int, success: bool) -> None:
        """Update Beta posterior for a template based on scenario outcome.

        Args:
            template_id: ID of the template used
            success: True if the scenario was promoted, False if rejected
        """
        template = self.db.query(ScenarioTemplate).filter(
            ScenarioTemplate.id == template_id
        ).first()
        if not template:
            logger.warning("Template %d not found for prior update", template_id)
            return

        if success:
            template.alpha = (template.alpha or 1.0) + 1.0
        else:
            template.beta_param = (template.beta_param or 1.0) + 1.0

        try:
            self.db.commit()
            logger.debug(
                "Updated template %s prior: alpha=%.1f beta=%.1f likelihood=%.3f",
                template.template_key, template.alpha, template.beta_param,
                template.prior_likelihood,
            )
        except Exception:
            self.db.rollback()
            logger.warning("Failed to update template prior for %d", template_id)

    def _load_templates(self, trm_type: str) -> List[ScenarioTemplate]:
        """Load templates from DB, seeding defaults if empty."""
        templates = (
            self.db.query(ScenarioTemplate)
            .filter(
                ScenarioTemplate.trm_type == trm_type,
                (ScenarioTemplate.tenant_id == self.tenant_id)
                | (ScenarioTemplate.tenant_id.is_(None)),
            )
            .all()
        )

        if not templates:
            templates = self._seed_defaults(trm_type)

        return templates

    def _seed_defaults(self, trm_type: str) -> List[ScenarioTemplate]:
        """Seed default templates for a TRM type if none exist."""
        defaults = DEFAULT_TEMPLATES.get(trm_type, [])
        if not defaults:
            logger.debug("No default templates for trm_type=%s", trm_type)
            return []

        seeded = []
        for defn in defaults:
            template = ScenarioTemplate(
                trm_type=trm_type,
                template_key=defn["template_key"],
                template_name=defn["template_name"],
                template_params=defn.get("template_params"),
                alpha=1.0,
                beta_param=1.0,
                uses_count=0,
                tenant_id=self.tenant_id,
            )
            self.db.add(template)
            seeded.append(template)

        try:
            self.db.commit()
            logger.info(
                "Seeded %d default templates for trm_type=%s tenant=%d",
                len(seeded), trm_type, self.tenant_id,
            )
        except Exception:
            self.db.rollback()
            logger.warning("Failed to seed defaults for %s", trm_type)
            return []

        return seeded

    def _instantiate_template(
        self,
        template: ScenarioTemplate,
        trm_type: str,
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Convert a template definition into concrete action dicts.

        Uses context (order details, product, site, shortfall) to fill
        in template parameters with real values.
        """
        params = template.template_params or {}
        actions = []

        product_id = context.get("product_id")
        site_id = context.get("site_id")
        quantity = context.get("quantity", 0)
        shortfall = context.get("shortfall", quantity)

        if trm_type == "atp_executor":
            actions = self._instantiate_atp(template.template_key, params, context)
        elif trm_type == "po_creation":
            actions = self._instantiate_po(template.template_key, params, context)
        elif trm_type == "inventory_rebalancing":
            actions = self._instantiate_rebalancing(template.template_key, params, context)
        elif trm_type == "mo_execution":
            actions = self._instantiate_mo(template.template_key, params, context)
        elif trm_type == "to_execution":
            actions = self._instantiate_to(template.template_key, params, context)
        else:
            # Generic template instantiation for remaining TRM types
            actions = [
                {
                    "trm_type": trm_type,
                    "action_type": template.template_key.upper(),
                    "action_params": {
                        "product_id": product_id,
                        "site_id": site_id,
                        "quantity": shortfall,
                        **params,
                    },
                    "responsible_agent": trm_type,
                    "decision_likelihood": None,
                    "estimated_cost": 0.0,
                    "estimated_benefit": 0.0,
                }
            ]

        return actions

    # -----------------------------------------------------------------------
    # Per-TRM-type template instantiation
    # -----------------------------------------------------------------------

    def _instantiate_atp(
        self, key: str, params: Dict, context: Dict,
    ) -> List[Dict[str, Any]]:
        product_id = context.get("product_id")
        site_id = context.get("site_id")
        quantity = context.get("quantity", 0)
        shortfall = context.get("shortfall", quantity)
        available = quantity - shortfall

        if key == "split_fulfillment":
            stock_pct = params.get("stock_pct", 0.6)
            ship_now = min(available, quantity * stock_pct)
            po_qty = quantity - ship_now
            return [
                {
                    "trm_type": "atp_executor",
                    "action_type": "PARTIAL_FULFILL",
                    "action_params": {"product_id": product_id, "site_id": site_id, "quantity": ship_now},
                    "responsible_agent": "atp_executor",
                    "decision_likelihood": None,
                    "estimated_cost": 0.0,
                    "estimated_benefit": ship_now * context.get("unit_value", 1.0),
                },
                {
                    "trm_type": "po_creation",
                    "action_type": "CREATE_PO",
                    "action_params": {"product_id": product_id, "site_id": site_id, "quantity": po_qty},
                    "responsible_agent": "po_creation",
                    "decision_likelihood": None,
                    "estimated_cost": po_qty * context.get("unit_cost", 1.0),
                    "estimated_benefit": po_qty * context.get("unit_value", 1.0),
                },
            ]

        elif key == "fast_supplier_po":
            return [
                {
                    "trm_type": "po_creation",
                    "action_type": "CREATE_PO",
                    "action_params": {
                        "product_id": product_id, "site_id": site_id,
                        "quantity": shortfall, "supplier_selection": "fastest", "expedite": True,
                    },
                    "responsible_agent": "po_creation",
                    "decision_likelihood": None,
                    "estimated_cost": shortfall * context.get("unit_cost", 1.0) * 1.2,
                    "estimated_benefit": shortfall * context.get("unit_value", 1.0),
                },
            ]

        elif key == "cheap_supplier_po":
            return [
                {
                    "trm_type": "po_creation",
                    "action_type": "CREATE_PO",
                    "action_params": {
                        "product_id": product_id, "site_id": site_id,
                        "quantity": shortfall, "supplier_selection": "cheapest", "expedite": False,
                    },
                    "responsible_agent": "po_creation",
                    "decision_likelihood": None,
                    "estimated_cost": shortfall * context.get("unit_cost", 1.0) * 0.9,
                    "estimated_benefit": shortfall * context.get("unit_value", 1.0) * 0.85,
                },
            ]

        elif key == "delay_fulfillment":
            delay_days = params.get("delay_days", 5)
            return [
                {
                    "trm_type": "atp_executor",
                    "action_type": "DELAY_PROMISE",
                    "action_params": {
                        "product_id": product_id, "site_id": site_id,
                        "quantity": quantity, "delay_days": delay_days,
                    },
                    "responsible_agent": "atp_executor",
                    "decision_likelihood": None,
                    "estimated_cost": 0.0,
                    "estimated_benefit": quantity * context.get("unit_value", 1.0) * 0.7,
                },
            ]

        elif key == "partial_backorder":
            ship_pct = params.get("ship_pct", 0.6)
            ship_qty = min(available, quantity * ship_pct)
            backorder_qty = quantity - ship_qty
            return [
                {
                    "trm_type": "atp_executor",
                    "action_type": "PARTIAL_FULFILL",
                    "action_params": {"product_id": product_id, "site_id": site_id, "quantity": ship_qty},
                    "responsible_agent": "atp_executor",
                    "decision_likelihood": None,
                    "estimated_cost": 0.0,
                    "estimated_benefit": ship_qty * context.get("unit_value", 1.0),
                },
                {
                    "trm_type": "atp_executor",
                    "action_type": "BACKORDER",
                    "action_params": {"product_id": product_id, "site_id": site_id, "quantity": backorder_qty},
                    "responsible_agent": "atp_executor",
                    "decision_likelihood": None,
                    "estimated_cost": backorder_qty * context.get("backlog_cost", 0.5),
                    "estimated_benefit": backorder_qty * context.get("unit_value", 1.0) * 0.6,
                },
            ]

        return []

    def _instantiate_po(
        self, key: str, params: Dict, context: Dict,
    ) -> List[Dict[str, Any]]:
        product_id = context.get("product_id")
        site_id = context.get("site_id")
        quantity = context.get("quantity", 0)
        unit_cost = context.get("unit_cost", 1.0)

        if key == "primary_supplier_standard":
            return [
                {
                    "trm_type": "po_creation",
                    "action_type": "CREATE_PO",
                    "action_params": {
                        "product_id": product_id, "site_id": site_id,
                        "quantity": quantity, "supplier_selection": "primary",
                    },
                    "responsible_agent": "po_creation",
                    "decision_likelihood": None,
                    "estimated_cost": quantity * unit_cost,
                    "estimated_benefit": quantity * unit_cost * 1.1,
                },
            ]

        elif key == "alternate_supplier_fast":
            return [
                {
                    "trm_type": "po_creation",
                    "action_type": "CREATE_PO",
                    "action_params": {
                        "product_id": product_id, "site_id": site_id,
                        "quantity": quantity, "supplier_selection": "alternate_fast", "expedite": True,
                    },
                    "responsible_agent": "po_creation",
                    "decision_likelihood": None,
                    "estimated_cost": quantity * unit_cost * 1.3,
                    "estimated_benefit": quantity * unit_cost * 1.2,
                },
            ]

        elif key == "split_suppliers":
            half = quantity / 2
            return [
                {
                    "trm_type": "po_creation",
                    "action_type": "CREATE_PO",
                    "action_params": {
                        "product_id": product_id, "site_id": site_id,
                        "quantity": half, "supplier_selection": "primary",
                    },
                    "responsible_agent": "po_creation",
                    "decision_likelihood": None,
                    "estimated_cost": half * unit_cost,
                    "estimated_benefit": half * unit_cost * 1.1,
                },
                {
                    "trm_type": "po_creation",
                    "action_type": "CREATE_PO",
                    "action_params": {
                        "product_id": product_id, "site_id": site_id,
                        "quantity": half, "supplier_selection": "alternate",
                    },
                    "responsible_agent": "po_creation",
                    "decision_likelihood": None,
                    "estimated_cost": half * unit_cost * 1.1,
                    "estimated_benefit": half * unit_cost * 1.1,
                },
            ]

        elif key == "consolidate_existing_po":
            return [
                {
                    "trm_type": "po_creation",
                    "action_type": "CONSOLIDATE_PO",
                    "action_params": {
                        "product_id": product_id, "site_id": site_id,
                        "quantity": quantity,
                    },
                    "responsible_agent": "po_creation",
                    "decision_likelihood": None,
                    "estimated_cost": quantity * unit_cost * 0.95,
                    "estimated_benefit": quantity * unit_cost * 1.05,
                },
            ]

        return []

    def _instantiate_rebalancing(
        self, key: str, params: Dict, context: Dict,
    ) -> List[Dict[str, Any]]:
        product_id = context.get("product_id")
        from_site_id = context.get("from_site_id") or context.get("site_id")
        to_site_id = context.get("to_site_id")
        quantity = context.get("quantity", 0)

        action_params = {
            "product_id": product_id,
            "from_site_id": from_site_id,
            "to_site_id": to_site_id,
            "quantity": quantity,
            "strategy": params.get("strategy", "nearest_surplus"),
        }
        if params.get("expedite"):
            action_params["expedite"] = True

        return [
            {
                "trm_type": "inventory_rebalancing",
                "action_type": "TRANSFER",
                "action_params": action_params,
                "responsible_agent": "inventory_rebalancing",
                "decision_likelihood": None,
                "estimated_cost": quantity * context.get("transfer_cost_per_unit", 0.5),
                "estimated_benefit": quantity * context.get("stockout_cost_per_unit", 2.0),
            },
        ]

    def _instantiate_mo(
        self, key: str, params: Dict, context: Dict,
    ) -> List[Dict[str, Any]]:
        product_id = context.get("product_id")
        site_id = context.get("site_id")
        quantity = context.get("quantity", 0)
        unit_cost = context.get("unit_cost", 1.0)
        cost_multiplier = params.get("cost_multiplier", 1.0)

        if key == "split_internal_subcontract":
            internal_pct = params.get("internal_pct", 0.6)
            internal_qty = quantity * internal_pct
            external_qty = quantity - internal_qty
            return [
                {
                    "trm_type": "mo_execution",
                    "action_type": "RELEASE_MO",
                    "action_params": {"product_id": product_id, "site_id": site_id, "quantity": internal_qty},
                    "responsible_agent": "mo_execution",
                    "decision_likelihood": None,
                    "estimated_cost": internal_qty * unit_cost,
                    "estimated_benefit": internal_qty * unit_cost * 1.1,
                },
                {
                    "trm_type": "subcontracting",
                    "action_type": "SUBCONTRACT",
                    "action_params": {"product_id": product_id, "quantity": external_qty},
                    "responsible_agent": "subcontracting",
                    "decision_likelihood": None,
                    "estimated_cost": external_qty * unit_cost * 1.4,
                    "estimated_benefit": external_qty * unit_cost * 1.1,
                },
            ]

        action_type = "RELEASE_MO"
        if key == "subcontract_external":
            action_type = "SUBCONTRACT"

        return [
            {
                "trm_type": "mo_execution" if action_type == "RELEASE_MO" else "subcontracting",
                "action_type": action_type,
                "action_params": {
                    "product_id": product_id, "site_id": site_id, "quantity": quantity,
                    "schedule": params.get("schedule", "standard"),
                },
                "responsible_agent": "mo_execution" if action_type == "RELEASE_MO" else "subcontracting",
                "decision_likelihood": None,
                "estimated_cost": quantity * unit_cost * cost_multiplier,
                "estimated_benefit": quantity * unit_cost * 1.1,
            },
        ]

    def _instantiate_to(
        self, key: str, params: Dict, context: Dict,
    ) -> List[Dict[str, Any]]:
        product_id = context.get("product_id")
        from_site_id = context.get("from_site_id") or context.get("site_id")
        to_site_id = context.get("to_site_id")
        quantity = context.get("quantity", 0)
        cost_multiplier = params.get("cost_multiplier", 1.0)

        return [
            {
                "trm_type": "to_execution",
                "action_type": "RELEASE_TO" if key != "consolidated_transfer" else "CONSOLIDATE_TO",
                "action_params": {
                    "product_id": product_id,
                    "from_site_id": from_site_id,
                    "to_site_id": to_site_id,
                    "quantity": quantity,
                    "mode": params.get("mode", "standard"),
                },
                "responsible_agent": "to_execution",
                "decision_likelihood": None,
                "estimated_cost": quantity * context.get("transfer_cost_per_unit", 0.5) * cost_multiplier,
                "estimated_benefit": quantity * context.get("unit_value", 1.0),
            },
        ]
