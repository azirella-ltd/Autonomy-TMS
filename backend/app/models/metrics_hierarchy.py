"""
Gartner SCOR Metric Hierarchy

Defines the 4-level SCOR-aligned metric hierarchy used across all Powell
Framework layers:
  L1 Strategic  → S&OP GraphSAGE objective
  L2 Functional → Execution tGNN objective
  L3 Operational → TRM reward-shaping context
  L4 Execution  → TRM primary reward metrics (per TRM type, lowest relevant level)

Metric weights and selections are configurable per SupplyChainConfig via the
`metric_config` JSONB column.  Call `get_metric_config(config.metric_config)`
to get a merged MetricConfig that overlays per-config overrides on the defaults.

References:
  - Gartner Supply Chain Top 25 (2025)
  - APICS/ASCM SCOR DS v4.0 metric taxonomy
  - Powell SDAM 2nd Ed, Ch 10-11 (supply chain objective functions)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Level enum
# ---------------------------------------------------------------------------

class GartnerLevel(str, Enum):
    L1_STRATEGIC  = "L1"
    L2_FUNCTIONAL = "L2"
    L3_OPERATIONAL = "L3"
    L4_EXECUTION  = "L4"


# ---------------------------------------------------------------------------
# Metric definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricDefinition:
    code: str
    name: str
    level: GartnerLevel
    unit: str                  # "%" | "$" | "days" | "ratio" | "hours" | "score"
    higher_is_better: bool
    description: str
    scor_process: str = ""     # Plan / Source / Make / Deliver / Return / Enable


# ---------------------------------------------------------------------------
# Full metric catalogue
# ---------------------------------------------------------------------------

GARTNER_METRICS: Dict[str, MetricDefinition] = {

    # ── L1 Strategic ────────────────────────────────────────────────────────
    "POF": MetricDefinition(
        code="POF", name="Perfect Order Fulfillment",
        level=GartnerLevel.L1_STRATEGIC, unit="%", higher_is_better=True,
        description="% of orders delivered complete, on-time, undamaged, with correct docs.",
        scor_process="Deliver",
    ),
    "SCCT": MetricDefinition(
        code="SCCT", name="Supply Chain Cycle Time",
        level=GartnerLevel.L1_STRATEGIC, unit="days", higher_is_better=False,
        description="Time to source, make and deliver from a completely stock-out state.",
        scor_process="Plan",
    ),
    "SCMC": MetricDefinition(
        code="SCMC", name="Supply Chain Management Cost",
        level=GartnerLevel.L1_STRATEGIC, unit="%", higher_is_better=False,
        description="Total SC management cost as % of revenue (planning + execution).",
        scor_process="Enable",
    ),
    "C2C": MetricDefinition(
        code="C2C", name="Cash-to-Cash Cycle Time",
        level=GartnerLevel.L1_STRATEGIC, unit="days", higher_is_better=False,
        description="Inventory days + receivable days – payable days.",
        scor_process="Enable",
    ),

    # ── L2 Functional ───────────────────────────────────────────────────────
    "FR": MetricDefinition(
        code="FR", name="Fill Rate",
        level=GartnerLevel.L2_FUNCTIONAL, unit="%", higher_is_better=True,
        description="% of demand fulfilled from available inventory (line/unit/order).",
        scor_process="Deliver",
    ),
    "OTD": MetricDefinition(
        code="OTD", name="On-Time Delivery",
        level=GartnerLevel.L2_FUNCTIONAL, unit="%", higher_is_better=True,
        description="% of orders delivered on or before the promised/requested date.",
        scor_process="Deliver",
    ),
    "DOS": MetricDefinition(
        code="DOS", name="Days of Supply",
        level=GartnerLevel.L2_FUNCTIONAL, unit="days", higher_is_better=False,
        description="Current inventory divided by average daily demand.",
        scor_process="Plan",
    ),
    "FA": MetricDefinition(
        code="FA", name="Forecast Accuracy",
        level=GartnerLevel.L2_FUNCTIONAL, unit="%", higher_is_better=True,
        description="1 – MAPE; measures how closely forecast tracks actual demand.",
        scor_process="Plan",
    ),
    "SOLD": MetricDefinition(
        code="SOLD", name="Stock-Out Lost Demand",
        level=GartnerLevel.L2_FUNCTIONAL, unit="$", higher_is_better=False,
        description="Revenue lost due to inventory stock-outs in the period.",
        scor_process="Deliver",
    ),

    # ── L3 Operational ──────────────────────────────────────────────────────
    "SSFR": MetricDefinition(
        code="SSFR", name="Safety Stock Fill Rate",
        level=GartnerLevel.L3_OPERATIONAL, unit="%", higher_is_better=True,
        description="% of time safety stock buffer is at or above target.",
        scor_process="Plan",
    ),
    "POLTA": MetricDefinition(
        code="POLTA", name="Purchase Order Lead Time Actual",
        level=GartnerLevel.L3_OPERATIONAL, unit="days", higher_is_better=False,
        description="Actual elapsed time from PO issue to confirmed receipt.",
        scor_process="Source",
    ),
    "MSA": MetricDefinition(
        code="MSA", name="Manufacturing Schedule Adherence",
        level=GartnerLevel.L3_OPERATIONAL, unit="%", higher_is_better=True,
        description="% of production orders completed as scheduled (qty + date).",
        scor_process="Make",
    ),
    "FPYR": MetricDefinition(
        code="FPYR", name="First Pass Yield Rate",
        level=GartnerLevel.L3_OPERATIONAL, unit="%", higher_is_better=True,
        description="% of units passing quality inspection on the first attempt.",
        scor_process="Make",
    ),
    "IRA": MetricDefinition(
        code="IRA", name="Inventory Record Accuracy",
        level=GartnerLevel.L3_OPERATIONAL, unit="%", higher_is_better=True,
        description="% of locations where system quantity matches physical count.",
        scor_process="Plan",
    ),
    "LTBIAS": MetricDefinition(
        code="LTBIAS", name="Lead Time Bias",
        level=GartnerLevel.L3_OPERATIONAL, unit="days", higher_is_better=False,
        description="Systematic over- or under-estimation of lead time vs. actuals.",
        scor_process="Source",
    ),
    "EXPRT": MetricDefinition(
        code="EXPRT", name="Expedite Rate",
        level=GartnerLevel.L3_OPERATIONAL, unit="%", higher_is_better=False,
        description="% of orders requiring expediting due to planning gaps.",
        scor_process="Enable",
    ),
    "BLA": MetricDefinition(
        code="BLA", name="Buffer Level Adequacy",
        level=GartnerLevel.L3_OPERATIONAL, unit="ratio", higher_is_better=True,
        description="Actual buffer / target buffer; 1.0 = on target, <1 = insufficient.",
        scor_process="Plan",
    ),

    # ── L4 Execution — ATP Executor ─────────────────────────────────────────
    "ATPA": MetricDefinition(
        code="ATPA", name="ATP Accuracy",
        level=GartnerLevel.L4_EXECUTION, unit="%", higher_is_better=True,
        description="% of ATP promises that were fulfilled as committed.",
        scor_process="Deliver",
    ),
    "PFR_LINE": MetricDefinition(
        code="PFR_LINE", name="Perfect Fill Rate by Line",
        level=GartnerLevel.L4_EXECUTION, unit="%", higher_is_better=True,
        description="% of order lines fulfilled complete, on-time, first-fill.",
        scor_process="Deliver",
    ),
    "PHR": MetricDefinition(
        code="PHR", name="Priority Hit Rate",
        level=GartnerLevel.L4_EXECUTION, unit="%", higher_is_better=True,
        description="% of high-priority orders (P1/P2) fulfilled before lower-priority.",
        scor_process="Deliver",
    ),

    # ── L4 Execution — Rebalancing ──────────────────────────────────────────
    "NBS": MetricDefinition(
        code="NBS", name="Net Balance Score",
        level=GartnerLevel.L4_EXECUTION, unit="ratio", higher_is_better=True,
        description="Aggregate inventory balance across locations; 1.0 = perfectly balanced.",
        scor_process="Plan",
    ),
    "TER": MetricDefinition(
        code="TER", name="Transfer Efficiency Ratio",
        level=GartnerLevel.L4_EXECUTION, unit="%", higher_is_better=True,
        description="Service level improvement achieved per $ of transfer cost incurred.",
        scor_process="Deliver",
    ),
    "CSLD": MetricDefinition(
        code="CSLD", name="Cross-Site Lead time Delta",
        level=GartnerLevel.L4_EXECUTION, unit="days", higher_is_better=False,
        description="Difference between planned and actual inter-site transfer lead time.",
        scor_process="Deliver",
    ),

    # ── L4 Execution — PO Creation ──────────────────────────────────────────
    "DOSA": MetricDefinition(
        code="DOSA", name="Days of Supply Actual",
        level=GartnerLevel.L4_EXECUTION, unit="days", higher_is_better=False,
        description="Actual DOS after PO receipt vs. target DOS.",
        scor_process="Source",
    ),
    "SOCR": MetricDefinition(
        code="SOCR", name="Supplier Order Compliance Rate",
        level=GartnerLevel.L4_EXECUTION, unit="%", higher_is_better=True,
        description="% of POs where supplier delivered within agreed qty and date tolerance.",
        scor_process="Source",
    ),

    # ── L4 Execution — Order Tracking ───────────────────────────────────────
    "ERCT": MetricDefinition(
        code="ERCT", name="Exception Resolution Cycle Time",
        level=GartnerLevel.L4_EXECUTION, unit="hours", higher_is_better=False,
        description="Mean time from exception detection to resolution action.",
        scor_process="Enable",
    ),
    "OAR": MetricDefinition(
        code="OAR", name="Order Anomaly Rate",
        level=GartnerLevel.L4_EXECUTION, unit="%", higher_is_better=False,
        description="% of orders flagged as anomalies requiring intervention.",
        scor_process="Deliver",
    ),
    "PAR": MetricDefinition(
        code="PAR", name="Proactive Alert Rate",
        level=GartnerLevel.L4_EXECUTION, unit="%", higher_is_better=True,
        description="% of exceptions detected proactively (before SLA breach).",
        scor_process="Enable",
    ),

    # ── L4 Execution — MO Execution ─────────────────────────────────────────
    "MSA_MO": MetricDefinition(
        code="MSA_MO", name="MO Schedule Adherence",
        level=GartnerLevel.L4_EXECUTION, unit="%", higher_is_better=True,
        description="% of manufacturing orders started and completed per schedule.",
        scor_process="Make",
    ),
    "WOCT": MetricDefinition(
        code="WOCT", name="Work Order Cycle Time",
        level=GartnerLevel.L4_EXECUTION, unit="hours", higher_is_better=False,
        description="Actual elapsed time from work order release to completion.",
        scor_process="Make",
    ),
    "PE": MetricDefinition(
        code="PE", name="Production Efficiency",
        level=GartnerLevel.L4_EXECUTION, unit="ratio", higher_is_better=True,
        description="Standard hours earned / actual hours worked; OEE-aligned.",
        scor_process="Make",
    ),

    # ── L4 Execution — TO Execution ─────────────────────────────────────────
    "TOOTD": MetricDefinition(
        code="TOOTD", name="Transfer Order On-Time Delivery",
        level=GartnerLevel.L4_EXECUTION, unit="%", higher_is_better=True,
        description="% of transfer orders arriving at destination by planned date.",
        scor_process="Deliver",
    ),
    "TQA": MetricDefinition(
        code="TQA", name="Transfer Quality Acceptance",
        level=GartnerLevel.L4_EXECUTION, unit="%", higher_is_better=True,
        description="% of transferred units accepted without quality hold.",
        scor_process="Deliver",
    ),
    "TPCR": MetricDefinition(
        code="TPCR", name="Transfer Plan Compliance Rate",
        level=GartnerLevel.L4_EXECUTION, unit="%", higher_is_better=True,
        description="% of transfer orders executed as originally planned (no splits/cancels).",
        scor_process="Deliver",
    ),

    # ── L4 Execution — Quality Disposition ──────────────────────────────────
    "DCA": MetricDefinition(
        code="DCA", name="Disposition Cycle Time Actual",
        level=GartnerLevel.L4_EXECUTION, unit="hours", higher_is_better=False,
        description="Elapsed time from quality hold creation to final disposition decision.",
        scor_process="Return",
    ),
    "RWCT": MetricDefinition(
        code="RWCT", name="Rework Cost Total",
        level=GartnerLevel.L4_EXECUTION, unit="$", higher_is_better=False,
        description="Total cost incurred for rework vs. projected scrap/accept cost.",
        scor_process="Return",
    ),

    # ── L4 Execution — Maintenance Scheduling ───────────────────────────────
    "PMSA": MetricDefinition(
        code="PMSA", name="Preventive Maintenance Schedule Adherence",
        level=GartnerLevel.L4_EXECUTION, unit="%", higher_is_better=True,
        description="% of planned preventive maintenance tasks executed on schedule.",
        scor_process="Enable",
    ),
    "AAR": MetricDefinition(
        code="AAR", name="Asset Availability Rate",
        level=GartnerLevel.L4_EXECUTION, unit="%", higher_is_better=True,
        description="% of scheduled production time asset is available (not in maintenance).",
        scor_process="Enable",
    ),
    "MAINT_COST": MetricDefinition(
        code="MAINT_COST", name="Maintenance Cost Ratio",
        level=GartnerLevel.L4_EXECUTION, unit="%", higher_is_better=False,
        description="Maintenance spend as % of asset replacement value.",
        scor_process="Enable",
    ),

    # ── L4 Execution — Subcontracting ────────────────────────────────────────
    "MBCV": MetricDefinition(
        code="MBCV", name="Make-vs-Buy Cost Variance",
        level=GartnerLevel.L4_EXECUTION, unit="$", higher_is_better=False,
        description="Actual total cost vs. optimal make-vs-buy cost plan.",
        scor_process="Source",
    ),
    "XOTD": MetricDefinition(
        code="XOTD", name="External On-Time Delivery",
        level=GartnerLevel.L4_EXECUTION, unit="%", higher_is_better=True,
        description="% of subcontracted work orders returned on time.",
        scor_process="Source",
    ),
    "SSA": MetricDefinition(
        code="SSA", name="Subcontractor Score Average",
        level=GartnerLevel.L4_EXECUTION, unit="score", higher_is_better=True,
        description="Composite supplier scorecard (quality, lead time, cost, responsiveness).",
        scor_process="Source",
    ),

    # ── L4 Execution — Forecast Adjustment ──────────────────────────────────
    "SFACI": MetricDefinition(
        code="SFACI", name="Signal Forecast Adjustment Cycle Index",
        level=GartnerLevel.L4_EXECUTION, unit="ratio", higher_is_better=True,
        description="Ratio of forecast error reduction from signal adjustments vs. unadjusted baseline.",
        scor_process="Plan",
    ),
    "FBI": MetricDefinition(
        code="FBI", name="Forecast Bias Index",
        level=GartnerLevel.L4_EXECUTION, unit="ratio", higher_is_better=False,
        description="Systematic over/under-forecast ratio after adjustment; target = 1.0.",
        scor_process="Plan",
    ),
    "SLAR": MetricDefinition(
        code="SLAR", name="Signal-to-Lift Accuracy Ratio",
        level=GartnerLevel.L4_EXECUTION, unit="ratio", higher_is_better=True,
        description="% of applied signals that produced a measurable accuracy lift.",
        scor_process="Plan",
    ),

    # ── L4 Execution — Inventory Buffer ─────────────────────────────────────
    "SR": MetricDefinition(
        code="SR", name="Stock Replenishment Rate",
        level=GartnerLevel.L4_EXECUTION, unit="ratio", higher_is_better=True,
        description="Ratio of replenishment orders triggered at correct buffer zone.",
        scor_process="Plan",
    ),
    "ICD": MetricDefinition(
        code="ICD", name="Inventory Coverage Delta",
        level=GartnerLevel.L4_EXECUTION, unit="days", higher_is_better=False,
        description="Absolute deviation between actual DOS and target DOS after buffer action.",
        scor_process="Plan",
    ),
}


# ---------------------------------------------------------------------------
# Per-TRM lowest-level metric mapping
# ---------------------------------------------------------------------------

TRM_METRIC_MAPPING: Dict[str, List[str]] = {
    "atp_executor":           ["ATPA", "PFR_LINE", "PHR"],
    "rebalancing":            ["NBS", "TER", "CSLD"],
    "po_creation":            ["POLTA", "DOSA", "SOCR"],
    "order_tracking":         ["ERCT", "OAR", "PAR"],
    "mo_execution":           ["MSA_MO", "WOCT", "PE"],
    "to_execution":           ["TOOTD", "TQA", "TPCR"],
    "quality_disposition":    ["FPYR", "DCA", "RWCT"],
    "maintenance_scheduling": ["PMSA", "AAR", "MAINT_COST"],
    "subcontracting":         ["MBCV", "XOTD", "SSA"],
    "forecast_adjustment":    ["SFACI", "FBI", "SLAR"],
    "inventory_buffer":       ["BLA", "SR", "ICD"],
}


# ---------------------------------------------------------------------------
# Default Powell-layer metric weights
# ---------------------------------------------------------------------------

POWELL_LAYER_METRICS: Dict[str, Dict[str, float]] = {
    # S&OP GraphSAGE (L1) — Strategic objective
    "sop": {
        "POF":  0.40,
        "SCCT": 0.20,
        "SCMC": 0.25,
        "C2C":  0.15,
    },
    # Execution tGNN (L2) — Functional objective
    "tgnn": {
        "FR":   0.30,
        "OTD":  0.25,
        "DOS":  0.20,
        "FA":   0.15,
        "SOLD": 0.10,
    },
}


# ---------------------------------------------------------------------------
# MetricConfig — stored as JSON in SupplyChainConfig.metric_config
# ---------------------------------------------------------------------------

@dataclass
class MetricConfig:
    """
    Resolved metric configuration for a supply chain config.

    Merges per-config overrides on top of POWELL_LAYER_METRICS defaults.
    Stored as a plain dict in SupplyChainConfig.metric_config (JSONB).

    Fields:
        sop_weights   — L1 metric weights for S&OP GraphSAGE objective.
        tgnn_weights  — L2 metric weights for Execution tGNN objective.
        trm_weights   — Per-TRM L4 metric weights.
                        Keys: TRM type strings from TRM_METRIC_MAPPING.
                        Values: dict of metric_code → float weight.
                        Missing TRM types fall back to equal weights over
                        TRM_METRIC_MAPPING[trm_type].
    """
    sop_weights:  Dict[str, float] = field(default_factory=dict)
    tgnn_weights: Dict[str, float] = field(default_factory=dict)
    trm_weights:  Dict[str, Dict[str, float]] = field(default_factory=dict)

    def get_trm_weights(self, trm_type: str) -> Dict[str, float]:
        """Return per-metric weights for a given TRM type.

        Falls back to equal weights over the TRM's default metrics if not configured.
        """
        if trm_type in self.trm_weights:
            return self.trm_weights[trm_type]
        metrics = TRM_METRIC_MAPPING.get(trm_type, [])
        if not metrics:
            return {}
        equal = round(1.0 / len(metrics), 6)
        return {m: equal for m in metrics}

    def to_dict(self) -> dict:
        """Serialize to plain dict for JSON storage."""
        return {
            "sop_weights": self.sop_weights,
            "tgnn_weights": self.tgnn_weights,
            "trm_weights": self.trm_weights,
        }


def get_metric_config(raw_json: Optional[dict]) -> MetricConfig:
    """
    Build a resolved MetricConfig by merging raw_json overrides on top of defaults.

    Args:
        raw_json: Value of SupplyChainConfig.metric_config (may be None).

    Returns:
        MetricConfig with defaults populated, overridden by any values in raw_json.
    """
    defaults = MetricConfig(
        sop_weights=dict(POWELL_LAYER_METRICS["sop"]),
        tgnn_weights=dict(POWELL_LAYER_METRICS["tgnn"]),
        trm_weights={},
    )
    if not raw_json:
        return defaults

    sop = dict(defaults.sop_weights)
    sop.update(raw_json.get("sop_weights") or {})

    tgnn = dict(defaults.tgnn_weights)
    tgnn.update(raw_json.get("tgnn_weights") or {})

    trm = dict(defaults.trm_weights)
    trm.update(raw_json.get("trm_weights") or {})

    return MetricConfig(sop_weights=sop, tgnn_weights=tgnn, trm_weights=trm)


__all__ = [
    "GartnerLevel",
    "MetricDefinition",
    "GARTNER_METRICS",
    "TRM_METRIC_MAPPING",
    "POWELL_LAYER_METRICS",
    "MetricConfig",
    "get_metric_config",
]
