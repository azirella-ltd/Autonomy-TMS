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

