"""
CDT Calibration Service

Bridges the gap between powell_*_decisions tables (which store estimated and
actual costs) and the ConformalDecisionWrapper instances (which need
DecisionOutcomePair data to calibrate).

Two modes:
  1. Batch calibration (startup / periodic): Reads all decisions with outcomes
     from DB and calls wrapper.calibrate()
  2. Incremental calibration (after outcome collection): Adds newly collected
     outcomes via wrapper.add_calibration_pair()

Architecture:
    powell_*_decisions (DB)
           ↓ extract (estimated_cost, actual_cost)
    DecisionOutcomePair[]
           ↓ calibrate / add_calibration_pair
    ConformalDecisionWrapper (in-memory)
           ↓ compute_risk_bound() on new decisions
    TRM Response.risk_bound

Scheduled: Runs after outcome collection (hourly at :35).
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging

import numpy as np
from sqlalchemy.orm import Session

from app.services.conformal_prediction.conformal_decision import (
    get_cdt_registry,
    DecisionOutcomePair,
    ConformalDecisionWrapper,
)

logger = logging.getLogger(__name__)


# Maps agent_type → (model_class_name, estimated_cost_extractor, actual_cost_extractor)
# Each extractor is a function: (row) -> Optional[float]
TRM_COST_MAPPING = {
    "atp": {
        "model": "PowellATPDecision",
        "outcome_filter": "was_committed",
        "estimated": lambda r: float(r.promised_qty or 0),
        "actual": lambda r: float(r.actual_fulfilled_qty or 0),
        # Loss = |promised - fulfilled| / max(promised, 1)
        "loss": lambda r: abs(
            (r.promised_qty or 0) - (r.actual_fulfilled_qty or 0)
        ) / max(r.promised_qty or 1, 1),
    },
    "inventory_rebalancing": {
        "model": "PowellRebalanceDecision",
        "outcome_filter": "was_executed",
        "estimated": lambda r: float(r.expected_cost or 0),
        "actual": lambda r: float(r.actual_cost or 0),
        "loss": lambda r: (
            (r.actual_cost or 0) - (r.expected_cost or 0)
        ) / max(r.expected_cost or 1, 1),
    },
    "po_creation": {
        "model": "PowellPODecision",
        "outcome_filter": "was_executed",
        "estimated": lambda r: float(r.expected_cost or 0),
        "actual": lambda r: float(r.actual_cost or 0),
        "loss": lambda r: (
            (r.actual_cost or 0) - (r.expected_cost or 0)
        ) / max(r.expected_cost or 1, 1),
    },
    "order_tracking": {
        "model": "PowellOrderException",
        "outcome_filter": "action_taken",
        "estimated": lambda r: float(r.estimated_impact_cost or 0),
        "actual": lambda r: float(r.actual_impact_cost or 0),
        "loss": lambda r: (
            (r.actual_impact_cost or 0) - (r.estimated_impact_cost or 0)
        ) / max(r.estimated_impact_cost or 1, 1),
    },
    "mo_execution": {
        "model": "PowellMODecision",
        "outcome_filter": "was_executed",
        # Service risk proxy: yield loss = (planned - actual) / planned
        "estimated": lambda r: float(r.planned_qty or 0),
        "actual": lambda r: float(r.actual_qty or 0),
        "loss": lambda r: max(0, (
            (r.planned_qty or 0) - (r.actual_qty or 0)
        )) / max(r.planned_qty or 1, 1),
    },
    "to_execution": {
        "model": "PowellTODecision",
        "outcome_filter": "was_executed",
        # Transit time deviation
        "estimated": lambda r: float(r.estimated_transit_days or 0),
        "actual": lambda r: float(r.actual_transit_days or 0),
        "loss": lambda r: max(0, (
            (r.actual_transit_days or 0) - (r.estimated_transit_days or 0)
        )) / max(r.estimated_transit_days or 1, 1),
    },
    "quality_disposition": {
        "model": "PowellQualityDecision",
        "outcome_filter": "was_executed",
        "estimated": lambda r: float((r.rework_cost_estimate or 0) + (r.scrap_cost_estimate or 0)),
        "actual": lambda r: float((r.actual_rework_cost or 0) + (r.actual_scrap_cost or 0)),
        "loss": lambda r: (
            ((r.actual_rework_cost or 0) + (r.actual_scrap_cost or 0))
            - ((r.rework_cost_estimate or 0) + (r.scrap_cost_estimate or 0))
        ) / max((r.rework_cost_estimate or 0) + (r.scrap_cost_estimate or 0), 1),
    },
    "maintenance_scheduling": {
        "model": "PowellMaintenanceDecision",
        "outcome_filter": "was_executed",
        "estimated": lambda r: float(r.estimated_downtime_hours or 0),
        "actual": lambda r: float(r.actual_downtime_hours or 0),
        # Loss includes breakdown penalty
        "loss": lambda r: (
            max(0, (r.actual_downtime_hours or 0) - (r.estimated_downtime_hours or 0))
            / max(r.estimated_downtime_hours or 1, 1)
            + (1.0 if r.breakdown_occurred else 0.0)
        ),
    },
    "subcontracting": {
        "model": "PowellSubcontractingDecision",
        "outcome_filter": "was_executed",
        "estimated": lambda r: float((r.subcontractor_cost_per_unit or 0) * (r.planned_qty or 0)),
        "actual": lambda r: float(r.actual_cost or 0),
        "loss": lambda r: (
            (r.actual_cost or 0) - (r.subcontractor_cost_per_unit or 0) * (r.planned_qty or 0)
        ) / max((r.subcontractor_cost_per_unit or 0) * (r.planned_qty or 0), 1),
    },
    "forecast_adjustment": {
        "model": "PowellForecastAdjustmentDecision",
        "outcome_filter": "was_applied",
        "estimated": lambda r: float(r.adjustment_magnitude or 0),
        "actual": lambda r: float(r.forecast_error_after or 0) - float(r.forecast_error_before or 0),
        # Loss = forecast error increased (positive = bad)
        "loss": lambda r: max(0, (r.forecast_error_after or 0) - (r.forecast_error_before or 0)),
    },
    "inventory_buffer": {
        "model": "PowellBufferDecision",
        "outcome_filter": "was_applied",
        "estimated": lambda r: float(r.adjusted_ss or 0),
        "actual": lambda r: (
            float(r.excess_holding_cost or 0)
            + (10.0 if r.actual_stockout_occurred else 0.0)
        ),
        # Loss = stockout penalty + excess cost relative to adjusted SS
        "loss": lambda r: (
            (1.0 if r.actual_stockout_occurred else 0.0) * 0.5
            + float(r.excess_holding_cost or 0) / max(r.adjusted_ss or 1, 1)
        ),
    },
}


def _get_model_class(model_name: str):
    """Lazy import of model class from powell_decisions module."""
    from app.models import powell_decisions as pd
    return getattr(pd, model_name)


# ═══════════════════════════════════════════════════════════════════════
# Historical-corpus adapters: training_corpus sample_data → (estimated, actual)
# ═══════════════════════════════════════════════════════════════════════
#
# Each adapter maps a single historical sample from the unified training
# corpus into the (decision_cost_estimate, actual_cost) pair that
# DecisionOutcomePair needs. The shape of sample_data is defined by the
# historical extractor for that TRM (see app/services/training_corpus/historical/).
#
# Returns None → skip this sample (outcome missing, etc.).
# Returns (estimated, actual) → use this pair for calibration.
#
# The residual = actual - estimated is the conformal score. We construct
# residuals that reflect the *quality* of the decision: higher residual
# = worse outcome (stockout occurred, order late, yield below plan, etc.).
# ═══════════════════════════════════════════════════════════════════════

def _adapter_po_creation(sd: Dict[str, Any]):
    action = sd.get("action") or {}
    outcome = sd.get("outcome") or {}
    ordered = float(action.get("ordered_quantity") or 0)
    if ordered <= 0:
        return None
    stockout = outcome.get("stockout_qty_during_window")
    lateness = outcome.get("lateness_days") or 0
    # Estimated "cost" = ordered qty (what the agent committed to).
    # Actual "cost" = ordered qty + stockout penalty + lateness penalty.
    # A perfect PO has actual == estimated; a PO that failed to prevent
    # stockout or arrived late has actual > estimated.
    penalty = 0.0
    if stockout is not None:
        penalty += float(stockout)
    if lateness and lateness > 0:
        penalty += float(lateness) * ordered * 0.05  # 5% daily tardiness weight
    return (ordered, ordered + penalty)


def _adapter_to_execution(sd: Dict[str, Any]):
    action = sd.get("action") or {}
    outcome = sd.get("outcome") or {}
    qty = float(action.get("quantity") or 0)
    if qty <= 0:
        return None
    dst_stockout = float(outcome.get("dst_stockout_during_window") or 0)
    lateness = outcome.get("lateness_days") or 0
    penalty = dst_stockout + (float(lateness) * qty * 0.05 if lateness and lateness > 0 else 0)
    return (qty, qty + penalty)


def _adapter_mo_execution(sd: Dict[str, Any]):
    action = sd.get("action") or {}
    outcome = sd.get("outcome") or {}
    planned = float(action.get("planned_quantity") or 0)
    if planned <= 0:
        return None
    actual_qty = outcome.get("actual_quantity")
    scrap = float(outcome.get("scrap_quantity") or 0)
    if actual_qty is None:
        return None
    shortfall = max(0.0, planned - float(actual_qty)) + scrap
    return (planned, planned + shortfall)


def _adapter_atp_allocation(sd: Dict[str, Any]):
    action = sd.get("action") or {}
    outcome = sd.get("outcome") or {}
    promised = float(action.get("promised_quantity") or 0)
    if promised <= 0:
        return None
    shipped = float(outcome.get("shipped_quantity") or 0)
    backlog = float(outcome.get("backlog_quantity") or 0)
    # Residual reflects broken promise: under-ship or backlog.
    underdelivery = max(0.0, promised - shipped) + backlog
    return (promised, promised + underdelivery)


def _adapter_inventory_buffer(sd: Dict[str, Any]):
    action = sd.get("action") or {}
    outcome = sd.get("outcome") or {}
    target_sl = action.get("target_service_level")
    achieved_sl = outcome.get("achieved_service_level")
    if target_sl is None or achieved_sl is None:
        return None
    try:
        target_sl = float(target_sl)
        achieved_sl = float(achieved_sl)
    except (TypeError, ValueError):
        return None
    # Estimated = target service level, actual = shortfall added on top.
    # A well-chosen buffer has achieved ~ target. A poor buffer has
    # achieved < target, so residual > 0.
    base = 1.0  # normalised baseline
    shortfall = max(0.0, target_sl - achieved_sl)
    return (base, base + shortfall)


def _adapter_quality_disposition(sd: Dict[str, Any]):
    sf = sd.get("state_features") or {}
    outcome = sd.get("outcome") or {}
    inspected = float(sf.get("inspection_quantity") or 0)
    if inspected <= 0:
        return None
    cost = float(outcome.get("total_quality_cost") or 0)
    # Residual = normalised quality cost per inspected unit.
    return (inspected, inspected + cost / max(inspected, 1))


def _adapter_maintenance(sd: Dict[str, Any]):
    outcome = sd.get("outcome") or {}
    # Estimated = 1 (planned maintenance). Actual = 1 + penalty when
    # maintenance was reactive/corrective instead of preventive.
    was_corrective = bool(outcome.get("was_corrective"))
    return (1.0, 2.0 if was_corrective else 1.0)


def _adapter_order_tracking(sd: Dict[str, Any]):
    outcome = sd.get("outcome") or {}
    lateness = outcome.get("lateness_days")
    if lateness is None:
        return None
    # Estimated = expected on-time (1), actual = 1 + normalized lateness.
    return (1.0, 1.0 + max(0.0, float(lateness)) / 7.0)


def _adapter_rebalancing(sd: Dict[str, Any]):
    action = sd.get("action") or {}
    outcome = sd.get("outcome") or {}
    qty = float(action.get("quantity") or 0)
    if qty <= 0:
        return None
    justified = bool(outcome.get("justified"))
    # A justified transfer = actual matches estimated (no penalty).
    # An unjustified transfer = wasted capacity (residual > 0).
    return (qty, qty if justified else qty * 1.5)


def _adapter_forecast_baseline(sd: Dict[str, Any]):
    action = sd.get("action") or {}
    outcome = sd.get("outcome") or {}
    p50 = action.get("forecast_p50")
    realized = outcome.get("realized")
    if p50 is None or realized is None:
        return None
    try:
        return (float(p50), float(realized))
    except (TypeError, ValueError):
        return None


def _adapter_forecast_adjustment(sd: Dict[str, Any]):
    outcome = sd.get("outcome") or {}
    ape_orig = outcome.get("ape_original")
    ape_new = outcome.get("ape_new")
    if ape_orig is None or ape_new is None:
        return None
    try:
        # Estimated = original error, actual = post-adjustment error.
        # A good adjustment has actual < estimated (residual negative).
        return (float(ape_orig), float(ape_new))
    except (TypeError, ValueError):
        return None


# Map corpus trm_type → (cdt registry agent_type key, adapter function).
# Registry keys follow the convention used by TRM_COST_MAPPING above.
_HISTORICAL_CORPUS_ADAPTERS = {
    "po_creation":          ("po_creation",           _adapter_po_creation),
    "to_execution":         ("to_execution",          _adapter_to_execution),
    "mo_execution":         ("mo_execution",          _adapter_mo_execution),
    "atp_allocation":       ("atp",                   _adapter_atp_allocation),
    "inventory_buffer":     ("inventory_buffer",      _adapter_inventory_buffer),
    "quality_disposition":  ("quality_disposition",   _adapter_quality_disposition),
    "maintenance_scheduling": ("maintenance_scheduling", _adapter_maintenance),
    "order_tracking":       ("order_tracking",        _adapter_order_tracking),
    "rebalancing":          ("inventory_rebalancing", _adapter_rebalancing),
    "forecast_baseline":    ("forecast_baseline",     _adapter_forecast_baseline),
    "forecast_adjustment":  ("forecast_adjustment",   _adapter_forecast_adjustment),
}


class CDTCalibrationService:
    """
    Calibrates CDT wrappers for all 11 TRM agents from historical decision data.

    TENANT-SCOPED: Each tenant gets its own CDT registry so calibration data
    from one tenant does not leak into another tenant's risk bounds.

    Usage:
        svc = CDTCalibrationService(db, tenant_id=3)
        stats = svc.calibrate_all()  # Batch calibration from tenant's decisions
        stats = svc.calibrate_incremental(since=last_run)  # Incremental
    """

    def __init__(self, db: Session, tenant_id: Optional[int] = None):
        self.db = db
        self.tenant_id = tenant_id
        self.registry = get_cdt_registry(tenant_id=tenant_id)

        # Cache config_ids for this tenant (for filtering decision tables)
        self._tenant_config_ids: Optional[List[int]] = None

    def calibrate_all(self, limit_per_type: int = 1000) -> Dict[str, Any]:
        """
        Batch calibrate all CDT wrappers from historical decisions with outcomes.

        Reads from all 11 powell_*_decisions tables, extracts (estimated, actual)
        pairs, and calls wrapper.calibrate().

        Args:
            limit_per_type: Max decisions to load per TRM type.

        Returns:
            Stats dict with per-type calibration results.
        """
        stats = {}

        for agent_type, mapping in TRM_COST_MAPPING.items():
            try:
                pairs = self._extract_pairs(agent_type, mapping, limit=limit_per_type)
                wrapper = self.registry.get_or_create(agent_type)

                if len(pairs) >= ConformalDecisionWrapper.MIN_CALIBRATION_SIZE:
                    wrapper.calibrate(pairs)
                    stats[agent_type] = {
                        "status": "calibrated",
                        "pairs": len(pairs),
                        "diagnostics": wrapper.get_diagnostics(),
                    }
                elif pairs:
                    # Add what we have — wrapper will auto-calibrate at threshold
                    for pair in pairs:
                        wrapper.add_calibration_pair(pair)
                    stats[agent_type] = {
                        "status": "partial",
                        "pairs": len(pairs),
                        "min_required": ConformalDecisionWrapper.MIN_CALIBRATION_SIZE,
                    }
                else:
                    stats[agent_type] = {"status": "no_data", "pairs": 0}

                logger.info(
                    f"CDT calibration {agent_type}: {stats[agent_type]['status']} "
                    f"({stats[agent_type]['pairs']} pairs)"
                )

            except Exception as e:
                logger.warning(f"CDT calibration failed for {agent_type}: {e}")
                stats[agent_type] = {"status": "error", "error": str(e)}

        calibrated_count = sum(
            1 for s in stats.values() if s.get("status") == "calibrated"
        )
        logger.info(
            f"CDT batch calibration complete: {calibrated_count}/{len(TRM_COST_MAPPING)} "
            f"agents calibrated"
        )
        return stats

    def calibrate_incremental(
        self,
        since: Optional[datetime] = None,
        limit_per_type: int = 200,
    ) -> Dict[str, Any]:
        """
        Incrementally add new decision-outcome pairs since last calibration.

        Called after each outcome collection run to keep CDT wrappers current.

        Args:
            since: Only include decisions created after this timestamp.
                   Defaults to 24h ago.
            limit_per_type: Max new pairs per TRM type.

        Returns:
            Stats dict with per-type update counts.
        """
        if since is None:
            since = datetime.utcnow() - timedelta(hours=24)

        stats = {}

        for agent_type, mapping in TRM_COST_MAPPING.items():
            try:
                pairs = self._extract_pairs(
                    agent_type, mapping,
                    limit=limit_per_type,
                    since=since,
                )
                wrapper = self.registry.get_or_create(agent_type)

                added = 0
                for pair in pairs:
                    wrapper.add_calibration_pair(pair)
                    added += 1

                stats[agent_type] = {
                    "added": added,
                    "is_calibrated": wrapper.is_calibrated,
                    "calibration_size": wrapper.calibration_size,
                }

            except Exception as e:
                logger.debug(f"CDT incremental update failed for {agent_type}: {e}")
                stats[agent_type] = {"added": 0, "error": str(e)}

        total_added = sum(s.get("added", 0) for s in stats.values())
        if total_added > 0:
            logger.info(f"CDT incremental: {total_added} new pairs added across all agents")
        return stats

    def get_all_diagnostics(self) -> Dict[str, Any]:
        """Get calibration diagnostics for all CDT wrappers."""
        return self.registry.get_all_diagnostics()

    def _get_tenant_config_ids(self) -> Optional[List[int]]:
        """Lazily resolve config IDs belonging to this tenant."""
        if self.tenant_id is None:
            return None
        if self._tenant_config_ids is not None:
            return self._tenant_config_ids
        try:
            from app.models.supply_chain_config import SupplyChainConfig
            rows = self.db.query(SupplyChainConfig.id).filter(
                SupplyChainConfig.tenant_id == self.tenant_id,
            ).all()
            self._tenant_config_ids = [r[0] for r in rows]
        except Exception:
            self._tenant_config_ids = []
        return self._tenant_config_ids

    def _extract_pairs(
        self,
        agent_type: str,
        mapping: Dict[str, Any],
        limit: int = 1000,
        since: Optional[datetime] = None,
    ) -> List[DecisionOutcomePair]:
        """
        Extract DecisionOutcomePair list from a powell_*_decisions table.

        Tenant-scoped: if tenant_id was provided, only reads decisions
        belonging to configs owned by that tenant.

        Args:
            agent_type: TRM agent type name
            mapping: Cost mapping config from TRM_COST_MAPPING
            limit: Max rows to read
            since: Only include rows created after this datetime

        Returns:
            List of DecisionOutcomePair for calibration
        """
        model_class = _get_model_class(mapping["model"])
        outcome_col = getattr(model_class, mapping["outcome_filter"])

        query = self.db.query(model_class).filter(
            outcome_col.isnot(None),
        )

        # Tenant isolation: filter by config_id if tenant is set
        config_ids = self._get_tenant_config_ids()
        if config_ids is not None:
            config_id_col = getattr(model_class, "config_id", None)
            if config_id_col is not None and config_ids:
                query = query.filter(config_id_col.in_(config_ids))
            elif config_ids is not None and not config_ids:
                return []  # No configs for this tenant

        if since:
            query = query.filter(model_class.created_at > since)

        query = query.order_by(model_class.created_at.desc()).limit(limit)

        pairs = []
        for row in query.all():
            try:
                estimated = mapping["estimated"](row)
                actual_loss = mapping["loss"](row)

                # Build minimal features from state_features if available
                state_features = getattr(row, "state_features", None)
                if state_features and isinstance(state_features, (list, dict)):
                    if isinstance(state_features, dict):
                        features = np.array(list(state_features.values()), dtype=np.float32)
                    else:
                        features = np.array(state_features, dtype=np.float32)
                else:
                    features = np.array([estimated], dtype=np.float32)

                pair = DecisionOutcomePair(
                    decision_features=features,
                    decision_cost_estimate=estimated,
                    actual_cost=estimated + actual_loss * max(estimated, 1.0),
                    agent_type=agent_type,
                    timestamp=getattr(row, "created_at", None),
                )
                pairs.append(pair)

            except Exception as e:
                logger.debug(f"Failed to extract pair from {agent_type} row {getattr(row, 'id', '?')}: {e}")
                continue

        return pairs

    # ═══════════════════════════════════════════════════════════════════
    # Calibration from the unified training corpus (historical stream).
    #
    # Why this exists:
    #   calibrate_all() reads powell_*_decisions tables, which only have
    #   ~20 seed rows per TRM from the decision_seed provisioning step and
    #   no realized outcomes. The conformal wrappers never reach the
    #   MIN_CALIBRATION_SIZE=30 threshold and the "0/N agents ready" banner
    #   never clears until live outcomes accumulate over days/weeks.
    #
    #   The two-stream training corpus (UNIFIED_TRAINING_CORPUS.md §2a)
    #   already contains tens of thousands of (action, outcome) pairs per
    #   TRM extracted from the tenant's real ERP transaction history. Each
    #   historical sample has a real action taken by the ERP and a real
    #   realized outcome computed from forward-looking queries (e.g., did
    #   a stockout occur in the lead-time window, was the PO on-time,
    #   what was the actual service level of that policy). Those are
    #   exactly the (estimated_cost, actual_cost) pairs conformal
    #   calibration needs.
    #
    # Per-TRM adapters below convert each historical sample_data payload
    # into a DecisionOutcomePair. The adapter contract:
    #     adapter(sample_data_dict) -> (estimated_cost, actual_cost) or None
    # Returning None means "skip this sample" (missing outcome data).
    # ═══════════════════════════════════════════════════════════════════

    def calibrate_from_historical_corpus(
        self,
        config_id: Optional[int] = None,
        limit_per_type: int = 5000,
    ) -> Dict[str, Any]:
        """Calibrate CDT wrappers from training_corpus historical samples.

        Reads samples with origin='historical' grouped by trm_type, applies
        the per-TRM sample→DecisionOutcomePair adapter, and calls
        wrapper.calibrate() for each TRM that meets MIN_CALIBRATION_SIZE.

        This is the preferred calibration source during provisioning because
        it is backed by real tenant ERP transactions, not 20 seed rows or a
        digital-twin bootstrap. Runs BEFORE calibrate_all() / simulation
        bootstrap in the provisioning step.
        """
        from sqlalchemy import text as _text

        stats: Dict[str, Any] = {}

        config_ids = self._get_tenant_config_ids()
        if config_ids is not None and not config_ids:
            return {"error": "No configs for tenant"}

        # corpus trm_type → (cdt registry key, adapter function)
        adapters = _HISTORICAL_CORPUS_ADAPTERS

        # One query per TRM type so we stream and can filter by config.
        where_config = ""
        params: Dict[str, Any] = {"limit": limit_per_type}
        if config_id is not None:
            where_config = " AND config_id = :cid"
            params["cid"] = config_id
        elif config_ids:
            where_config = " AND config_id = ANY(:cids)"
            params["cids"] = config_ids

        for corpus_trm, (cdt_agent_type, adapter) in adapters.items():
            q = _text(f"""
                SELECT sample_data
                FROM training_corpus
                WHERE layer = 1.0
                  AND origin = 'historical'
                  AND trm_type = :trm
                  AND weight >= 0.3
                  {where_config}
                ORDER BY created_at DESC
                LIMIT :limit
            """)
            try:
                rows = self.db.execute(q, {**params, "trm": corpus_trm}).fetchall()
            except Exception as e:
                logger.warning("Historical corpus query failed for %s: %s", corpus_trm, e)
                stats[cdt_agent_type] = {"status": "error", "error": str(e)[:200], "source": "historical"}
                continue

            pairs: List[DecisionOutcomePair] = []
            for (sample_data,) in rows:
                try:
                    if not isinstance(sample_data, dict):
                        continue
                    result = adapter(sample_data)
                    if result is None:
                        continue
                    estimated, actual_cost_pair = result
                    if estimated is None or actual_cost_pair is None:
                        continue
                    # Build a minimal feature vector from state_features
                    sf = sample_data.get("state_features") or {}
                    if isinstance(sf, dict) and sf:
                        feats = np.array(
                            [float(v) if isinstance(v, (int, float)) else 0.0
                             for v in sf.values()],
                            dtype=np.float32,
                        )
                    else:
                        feats = np.array([float(estimated)], dtype=np.float32)
                    pairs.append(DecisionOutcomePair(
                        decision_features=feats,
                        decision_cost_estimate=float(estimated),
                        actual_cost=float(actual_cost_pair),
                        agent_type=cdt_agent_type,
                        timestamp=None,
                    ))
                except Exception as e:
                    logger.debug("Adapter failed for %s: %s", corpus_trm, e)
                    continue

            wrapper = self.registry.get_or_create(cdt_agent_type)
            if len(pairs) >= ConformalDecisionWrapper.MIN_CALIBRATION_SIZE:
                wrapper.calibrate(pairs)
                stats[cdt_agent_type] = {
                    "status": "calibrated",
                    "pairs": len(pairs),
                    "source": "historical",
                    "diagnostics": wrapper.get_diagnostics(),
                }
            elif pairs:
                for p in pairs:
                    wrapper.add_calibration_pair(p)
                stats[cdt_agent_type] = {
                    "status": "partial",
                    "pairs": len(pairs),
                    "min_required": ConformalDecisionWrapper.MIN_CALIBRATION_SIZE,
                    "source": "historical",
                }
            else:
                stats[cdt_agent_type] = {"status": "no_data", "pairs": 0, "source": "historical"}

            logger.info(
                "CDT historical-corpus calibration %s (corpus trm=%s): %s (%d pairs)",
                cdt_agent_type, corpus_trm,
                stats[cdt_agent_type]["status"], stats[cdt_agent_type]["pairs"],
            )

        n_calibrated = sum(1 for s in stats.values() if s.get("status") == "calibrated")
        logger.info(
            "CDT historical-corpus calibration complete: %d/%d agents calibrated",
            n_calibrated, len(adapters),
        )
        return stats

    def calibrate_from_simulation(
        self,
        simulation_pairs: Dict[str, List[Tuple[float, float]]],
    ) -> Dict[str, Any]:
        """Bootstrap CDT calibration directly from simulation reward/confidence pairs.

        Called during provisioning when no real production outcomes exist yet.
        The digital twin provides (reward, confidence) for each TRM decision
        without requiring real feedback-horizon delays.

        Args:
            simulation_pairs: {agent_type: [(reward, confidence), ...]}
                reward:     Normalized outcome quality [0-1]; 1.0 = perfect outcome.
                confidence: Agent's confidence in the decision [0-1].
                            These map to (actual_loss = 1 - reward,
                                          estimated_cost = 1 - confidence).

        Returns:
            Stats dict with per-type calibration results.
        """
        stats = {}

        for agent_type, pairs_raw in simulation_pairs.items():
            if not pairs_raw:
                stats[agent_type] = {"status": "no_data", "pairs": 0, "source": "simulation"}
                continue

            pairs = []
            for reward, confidence in pairs_raw:
                reward = max(0.0, min(1.0, float(reward)))
                confidence = max(0.0, min(1.0, float(confidence)))
                # Loss is the complement of reward — how far from perfect outcome
                actual_loss = 1.0 - reward
                # Estimated cost is the complement of confidence — agent's uncertainty
                estimated_cost = max(1e-6, 1.0 - confidence)
                actual_cost = estimated_cost + actual_loss * estimated_cost

                pairs.append(
                    DecisionOutcomePair(
                        decision_features=np.array([confidence, reward], dtype=np.float32),
                        decision_cost_estimate=estimated_cost,
                        actual_cost=actual_cost,
                        agent_type=agent_type,
                        metadata={"source": "simulation_bootstrap"},
                    )
                )

            wrapper = self.registry.get_or_create(agent_type)

            if len(pairs) >= ConformalDecisionWrapper.MIN_CALIBRATION_SIZE:
                wrapper.calibrate(pairs)
                stats[agent_type] = {
                    "status": "calibrated",
                    "pairs": len(pairs),
                    "source": "simulation",
                    "diagnostics": wrapper.get_diagnostics(),
                }
            else:
                for pair in pairs:
                    wrapper.add_calibration_pair(pair)
                stats[agent_type] = {
                    "status": "partial",
                    "pairs": len(pairs),
                    "min_required": ConformalDecisionWrapper.MIN_CALIBRATION_SIZE,
                    "source": "simulation",
                }

            logger.info(
                "CDT simulation calibration %s: %s (%d pairs from digital twin)",
                agent_type,
                stats[agent_type]["status"],
                stats[agent_type]["pairs"],
            )

        calibrated = sum(1 for s in stats.values() if s.get("status") == "calibrated")
        logger.info(
            "CDT simulation bootstrap complete: %d/%d agents calibrated from digital twin",
            calibrated,
            len(stats),
        )
        return stats

