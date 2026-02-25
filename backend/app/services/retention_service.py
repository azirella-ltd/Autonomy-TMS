"""
Retention Service

History retention and collapse management:
- HOT (0-30 days): Full detail, immediate access
- WARM (30-90 days): Compressed, summary data
- COLD (90+ days): Archived, minimal detail

Automated jobs:
- Daily: Promote HOT -> WARM
- Weekly: Promote WARM -> COLD
- Monthly: Collapse intermediate snapshots

Part of the Planning Cycle Management system.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
import json
import gzip
from io import BytesIO

from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.models.planning_cycle import (
    PlanningCycle, PlanningSnapshot, SnapshotDelta, SnapshotLineage,
    CycleStatus, SnapshotType, SnapshotTier
)
from app.models.planning_decision import PlanningDecision

logger = logging.getLogger(__name__)


class RetentionPolicy:
    """Retention policy configuration."""

    # Tier thresholds (days)
    HOT_DAYS = 30
    WARM_DAYS = 90
    COLD_DAYS = 365

    # Collapse settings
    COLLAPSE_INTERMEDIATE_AFTER_DAYS = 45
    MIN_SNAPSHOTS_BETWEEN_COLLAPSE = 5

    # Archive settings
    ARCHIVE_CLOSED_CYCLES_AFTER_DAYS = 30
    DELETE_ARCHIVED_AFTER_DAYS = 730  # 2 years


class RetentionService:
    """
    Service for managing data retention and archival.

    Implements hot/warm/cold tier strategy with automated collapse.
    """

    def __init__(self, db: Session):
        """
        Initialize retention service.

        Args:
            db: Database session
        """
        self.db = db
        self.policy = RetentionPolicy()

    def run_daily_retention(self) -> Dict[str, Any]:
        """
        Run daily retention job: HOT -> WARM promotion.

        Returns:
            Results dict with promotion count
        """
        logger.info("Starting daily retention job")

        cutoff = datetime.utcnow() - timedelta(days=self.policy.HOT_DAYS)

        # Find HOT snapshots older than threshold
        snapshots = self.db.query(PlanningSnapshot).filter(
            and_(
                PlanningSnapshot.storage_tier == SnapshotTier.HOT,
                PlanningSnapshot.created_at < cutoff,
                # Keep published and baseline snapshots as HOT longer
                PlanningSnapshot.snapshot_type.notin_([
                    SnapshotType.PUBLISHED,
                    SnapshotType.BASELINE
                ])
            )
        ).all()

        promoted = 0
        errors = []

        for snapshot in snapshots:
            try:
                self._promote_to_warm(snapshot)
                promoted += 1
            except Exception as e:
                logger.error(f"Failed to promote snapshot {snapshot.id} to WARM: {e}")
                errors.append({"snapshot_id": snapshot.id, "error": str(e)})

        self.db.commit()

        result = {
            "job": "daily_retention",
            "promoted_to_warm": promoted,
            "errors": errors,
            "completed_at": datetime.utcnow().isoformat()
        }

        logger.info(f"Daily retention: promoted {promoted} snapshots to WARM tier")
        return result

    def run_weekly_retention(self) -> Dict[str, Any]:
        """
        Run weekly retention job: WARM -> COLD promotion.

        Returns:
            Results dict with promotion count
        """
        logger.info("Starting weekly retention job")

        cutoff = datetime.utcnow() - timedelta(days=self.policy.WARM_DAYS)

        # Find WARM snapshots older than threshold
        snapshots = self.db.query(PlanningSnapshot).filter(
            and_(
                PlanningSnapshot.storage_tier == SnapshotTier.WARM,
                PlanningSnapshot.created_at < cutoff
            )
        ).all()

        promoted = 0
        errors = []

        for snapshot in snapshots:
            try:
                self._promote_to_cold(snapshot)
                promoted += 1
            except Exception as e:
                logger.error(f"Failed to promote snapshot {snapshot.id} to COLD: {e}")
                errors.append({"snapshot_id": snapshot.id, "error": str(e)})

        self.db.commit()

        result = {
            "job": "weekly_retention",
            "promoted_to_cold": promoted,
            "errors": errors,
            "completed_at": datetime.utcnow().isoformat()
        }

        logger.info(f"Weekly retention: promoted {promoted} snapshots to COLD tier")
        return result

    def run_monthly_collapse(self) -> Dict[str, Any]:
        """
        Run monthly job: Collapse intermediate snapshots.

        Returns:
            Results dict with collapse count
        """
        logger.info("Starting monthly collapse job")

        cutoff = datetime.utcnow() - timedelta(days=self.policy.COLLAPSE_INTERMEDIATE_AFTER_DAYS)

        # Find cycles with many intermediate snapshots
        cycles_query = self.db.query(
            PlanningSnapshot.cycle_id,
            func.count(PlanningSnapshot.id).label('snapshot_count')
        ).filter(
            and_(
                PlanningSnapshot.snapshot_type.in_([
                    SnapshotType.WORKING,
                    SnapshotType.CHECKPOINT,
                    SnapshotType.AUTO
                ]),
                PlanningSnapshot.created_at < cutoff,
                PlanningSnapshot.collapsed_at.is_(None)
            )
        ).group_by(
            PlanningSnapshot.cycle_id
        ).having(
            func.count(PlanningSnapshot.id) > self.policy.MIN_SNAPSHOTS_BETWEEN_COLLAPSE
        ).all()

        total_collapsed = 0
        errors = []

        for cycle_id, count in cycles_query:
            try:
                result = self._collapse_cycle_snapshots(cycle_id)
                total_collapsed += result.get('collapsed', 0)
            except Exception as e:
                logger.error(f"Failed to collapse snapshots for cycle {cycle_id}: {e}")
                errors.append({"cycle_id": cycle_id, "error": str(e)})

        self.db.commit()

        result = {
            "job": "monthly_collapse",
            "collapsed_snapshots": total_collapsed,
            "cycles_processed": len(cycles_query),
            "errors": errors,
            "completed_at": datetime.utcnow().isoformat()
        }

        logger.info(f"Monthly collapse: collapsed {total_collapsed} intermediate snapshots")
        return result

    def run_archive_closed_cycles(self) -> Dict[str, Any]:
        """
        Archive closed planning cycles.

        Returns:
            Results dict with archive count
        """
        logger.info("Starting archive closed cycles job")

        cutoff = datetime.utcnow() - timedelta(days=self.policy.ARCHIVE_CLOSED_CYCLES_AFTER_DAYS)

        # Find closed cycles older than threshold
        cycles = self.db.query(PlanningCycle).filter(
            and_(
                PlanningCycle.status == CycleStatus.CLOSED,
                PlanningCycle.closed_at < cutoff,
                PlanningCycle.archived_at.is_(None)
            )
        ).all()

        archived = 0
        errors = []

        for cycle in cycles:
            try:
                self._archive_cycle(cycle)
                archived += 1
            except Exception as e:
                logger.error(f"Failed to archive cycle {cycle.id}: {e}")
                errors.append({"cycle_id": cycle.id, "error": str(e)})

        self.db.commit()

        result = {
            "job": "archive_closed_cycles",
            "archived_cycles": archived,
            "errors": errors,
            "completed_at": datetime.utcnow().isoformat()
        }

        logger.info(f"Archived {archived} closed cycles")
        return result

    def get_retention_stats(self, customer_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get retention statistics.

        Args:
            customer_id: Optional customer filter

        Returns:
            Statistics dict
        """
        base_query = self.db.query(PlanningSnapshot)
        if customer_id:
            base_query = base_query.join(PlanningCycle).filter(
                PlanningCycle.customer_id == customer_id
            )

        stats = {
            "total_snapshots": base_query.count(),
            "by_tier": {},
            "by_type": {},
            "storage_estimate": {}
        }

        # By tier
        for tier in SnapshotTier:
            count = base_query.filter(
                PlanningSnapshot.storage_tier == tier
            ).count()
            stats["by_tier"][tier.value] = count

        # By type
        for stype in SnapshotType:
            count = base_query.filter(
                PlanningSnapshot.snapshot_type == stype
            ).count()
            stats["by_type"][stype.value] = count

        # Storage estimate
        hot_size = base_query.filter(
            PlanningSnapshot.storage_tier == SnapshotTier.HOT
        ).with_entities(
            func.sum(PlanningSnapshot.data_size_bytes)
        ).scalar() or 0

        compressed_size = base_query.filter(
            PlanningSnapshot.storage_tier.in_([SnapshotTier.WARM, SnapshotTier.COLD])
        ).with_entities(
            func.sum(PlanningSnapshot.compressed_size_bytes)
        ).scalar() or 0

        stats["storage_estimate"] = {
            "hot_bytes": hot_size,
            "compressed_bytes": compressed_size,
            "total_bytes": hot_size + compressed_size
        }

        return stats

    # ==================== Private Methods ====================

    def _promote_to_warm(self, snapshot: PlanningSnapshot) -> None:
        """
        Promote snapshot from HOT to WARM tier.

        Compresses detailed data to summaries.
        """
        # Compress detailed data
        if snapshot.demand_plan_data:
            snapshot.demand_plan_data = self._compress_to_summary(
                snapshot.demand_plan_data, "demand"
            )
        if snapshot.supply_plan_data:
            snapshot.supply_plan_data = self._compress_to_summary(
                snapshot.supply_plan_data, "supply"
            )
        if snapshot.inventory_data:
            snapshot.inventory_data = self._compress_to_summary(
                snapshot.inventory_data, "inventory"
            )
        if snapshot.forecast_data:
            snapshot.forecast_data = self._compress_to_summary(
                snapshot.forecast_data, "forecast"
            )

        # Keep KPI data intact (small)

        snapshot.storage_tier = SnapshotTier.WARM
        snapshot.compressed_size_bytes = self._calculate_compressed_size(snapshot)

        logger.debug(f"Promoted snapshot {snapshot.id} to WARM tier")

    def _promote_to_cold(self, snapshot: PlanningSnapshot) -> None:
        """
        Promote snapshot from WARM to COLD tier.

        Keeps only KPI summary and removes detailed data.
        """
        # Create cold summary
        cold_summary = {
            "created_at": snapshot.created_at.isoformat(),
            "version": snapshot.version,
            "type": snapshot.snapshot_type.value,
            "kpi_summary": snapshot.kpi_data,
            "record_counts": snapshot.record_counts,
            "commit_message": snapshot.commit_message
        }

        # Clear detailed data
        snapshot.demand_plan_data = None
        snapshot.supply_plan_data = None
        snapshot.inventory_data = None
        snapshot.forecast_data = None
        snapshot.kpi_data = cold_summary

        # Remove deltas to save space
        self.db.query(SnapshotDelta).filter(
            SnapshotDelta.snapshot_id == snapshot.id
        ).delete()

        snapshot.storage_tier = SnapshotTier.COLD
        snapshot.compressed_size_bytes = self._calculate_compressed_size(snapshot)

        logger.debug(f"Promoted snapshot {snapshot.id} to COLD tier")

    def _collapse_cycle_snapshots(self, cycle_id: int) -> Dict[str, int]:
        """
        Collapse intermediate snapshots for a cycle.

        Keeps baseline, published, and manual checkpoints.
        """
        # Get all snapshots in order
        snapshots = self.db.query(PlanningSnapshot).filter(
            PlanningSnapshot.cycle_id == cycle_id
        ).order_by(PlanningSnapshot.version).all()

        if len(snapshots) <= self.policy.MIN_SNAPSHOTS_BETWEEN_COLLAPSE:
            return {"collapsed": 0}

        # Identify snapshots to keep
        keep_types = {SnapshotType.BASELINE, SnapshotType.PUBLISHED, SnapshotType.CHECKPOINT}

        # Get cycle's key snapshot IDs
        cycle = self.db.query(PlanningCycle).filter_by(id=cycle_id).first()
        keep_ids = set()
        if cycle:
            if cycle.baseline_snapshot_id:
                keep_ids.add(cycle.baseline_snapshot_id)
            if cycle.current_snapshot_id:
                keep_ids.add(cycle.current_snapshot_id)
            if cycle.published_snapshot_id:
                keep_ids.add(cycle.published_snapshot_id)

        to_collapse = []
        for snapshot in snapshots:
            # Keep snapshots of protected types
            if snapshot.snapshot_type in keep_types:
                continue
            # Keep explicitly referenced snapshots
            if snapshot.id in keep_ids:
                continue
            # Keep snapshots that are parents of kept snapshots
            # (This is simplified - full implementation would check lineage)
            to_collapse.append(snapshot)

        # Collapse identified snapshots
        collapsed = 0
        for snapshot in to_collapse:
            # Mark as collapsed
            snapshot.collapsed_at = datetime.utcnow()

            # Clear detailed data but keep metadata
            snapshot.demand_plan_data = None
            snapshot.supply_plan_data = None
            snapshot.inventory_data = None
            snapshot.forecast_data = None

            # Remove deltas
            self.db.query(SnapshotDelta).filter(
                SnapshotDelta.snapshot_id == snapshot.id
            ).delete()

            collapsed += 1

        logger.debug(f"Collapsed {collapsed} snapshots for cycle {cycle_id}")
        return {"collapsed": collapsed}

    def _archive_cycle(self, cycle: PlanningCycle) -> None:
        """Archive a closed planning cycle."""
        cycle.status = CycleStatus.ARCHIVED
        cycle.archived_at = datetime.utcnow()
        cycle.retention_tier = SnapshotTier.COLD

        # Promote all snapshots to COLD
        snapshots = self.db.query(PlanningSnapshot).filter(
            PlanningSnapshot.cycle_id == cycle.id
        ).all()

        for snapshot in snapshots:
            if snapshot.storage_tier != SnapshotTier.COLD:
                self._promote_to_cold(snapshot)

        logger.debug(f"Archived cycle {cycle.id}")

    def _compress_to_summary(self, data: Any, data_type: str) -> Dict[str, Any]:
        """
        Compress detailed data to summary.

        Args:
            data: Detailed data
            data_type: Type of data

        Returns:
            Compressed summary
        """
        if not data:
            return {}

        summary = {
            "compressed_at": datetime.utcnow().isoformat(),
            "original_type": data_type,
            "is_summary": True
        }

        if isinstance(data, dict):
            summary["record_count"] = len(data)
            summary["keys"] = list(data.keys())[:100]  # Keep first 100 keys
        elif isinstance(data, list):
            summary["record_count"] = len(data)

        # Add aggregated metrics based on type
        if data_type == "demand" and isinstance(data, dict):
            total_qty = sum(
                v.get("quantity", 0) if isinstance(v, dict) else 0
                for v in data.values()
            )
            summary["total_quantity"] = total_qty

        elif data_type == "inventory" and isinstance(data, dict):
            total_stock = sum(
                v.get("on_hand", 0) if isinstance(v, dict) else 0
                for v in data.values()
            )
            summary["total_on_hand"] = total_stock

        return summary

    def _calculate_compressed_size(self, snapshot: PlanningSnapshot) -> int:
        """Calculate compressed data size for a snapshot."""
        data = {
            "demand": snapshot.demand_plan_data,
            "supply": snapshot.supply_plan_data,
            "inventory": snapshot.inventory_data,
            "forecast": snapshot.forecast_data,
            "kpi": snapshot.kpi_data
        }

        # Filter out None values
        data = {k: v for k, v in data.items() if v is not None}

        if not data:
            return 0

        try:
            json_str = json.dumps(data, default=str)
            compressed = gzip.compress(json_str.encode())
            return len(compressed)
        except Exception:
            return 0
