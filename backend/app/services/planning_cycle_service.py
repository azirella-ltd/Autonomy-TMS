"""
Planning Cycle Service

Manages planning cycles and snapshots:
- Create/update planning cycles
- Create snapshots with git-like versioning
- Materialize snapshots from delta chain
- Compare snapshots

Part of the Planning Cycle Management system.
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, date, timedelta
import logging
import hashlib
import json

from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.models.planning_cycle import (
    PlanningCycle, PlanningSnapshot, SnapshotDelta, SnapshotLineage,
    CycleType, CycleStatus, SnapshotType, SnapshotTier,
    DeltaOperation, DeltaEntityType
)
from app.models.sync_job import SyncJobExecution

logger = logging.getLogger(__name__)


class PlanningCycleService:
    """
    Service for managing planning cycles and snapshots.

    Implements git-like versioning with parent chains and delta storage.
    """

    def __init__(self, db: Session):
        """
        Initialize planning cycle service.

        Args:
            db: Database session
        """
        self.db = db

    # ==================== Cycle Management ====================

    def create_cycle(
        self,
        tenant_id: int,
        name: str,
        cycle_type: CycleType,
        period_start: date,
        period_end: date,
        config_id: Optional[int] = None,
        created_by: Optional[int] = None,
        planning_horizon_weeks: int = 52,
        previous_cycle_id: Optional[int] = None
    ) -> PlanningCycle:
        """
        Create a new planning cycle.

        Args:
            tenant_id: Customer ID
            name: Cycle name
            cycle_type: Type of cycle (weekly, monthly, etc.)
            period_start: Period start date
            period_end: Period end date
            config_id: Supply chain config ID
            created_by: User ID who created
            planning_horizon_weeks: Planning horizon in weeks
            previous_cycle_id: Previous cycle for linking

        Returns:
            Created PlanningCycle
        """
        # Generate code based on type and period
        code = self._generate_cycle_code(cycle_type, period_start)

        # Check for duplicate
        existing = self.db.query(PlanningCycle).filter(
            and_(
                PlanningCycle.tenant_id == tenant_id,
                PlanningCycle.code == code
            )
        ).first()

        if existing:
            raise ValueError(f"Planning cycle with code {code} already exists for this customer")

        cycle = PlanningCycle(
            tenant_id=tenant_id,
            name=name,
            code=code,
            cycle_type=cycle_type,
            period_start=period_start,
            period_end=period_end,
            config_id=config_id,
            planning_horizon_weeks=planning_horizon_weeks,
            status=CycleStatus.DRAFT,
            previous_cycle_id=previous_cycle_id,
            created_by=created_by
        )
        self.db.add(cycle)
        self.db.commit()
        self.db.refresh(cycle)

        logger.info(f"Created planning cycle {cycle.id}: {cycle.code}")

        return cycle

    def update_cycle_status(
        self,
        cycle_id: int,
        new_status: CycleStatus,
        changed_by: int,
        notes: Optional[str] = None
    ) -> PlanningCycle:
        """
        Update planning cycle status.

        Args:
            cycle_id: Cycle ID
            new_status: New status
            changed_by: User ID making the change
            notes: Optional status notes

        Returns:
            Updated PlanningCycle
        """
        cycle = self.db.query(PlanningCycle).filter_by(id=cycle_id).first()
        if not cycle:
            raise ValueError(f"Planning cycle {cycle_id} not found")

        # Validate status transition
        self._validate_status_transition(cycle.status, new_status)

        old_status = cycle.status
        cycle.status = new_status
        cycle.status_changed_at = datetime.utcnow()
        cycle.status_changed_by = changed_by
        cycle.status_notes = notes

        # Update timeline fields based on status
        if new_status == CycleStatus.DATA_COLLECTION:
            cycle.data_collection_started_at = datetime.utcnow()
        elif new_status == CycleStatus.PLANNING:
            cycle.data_collection_completed_at = datetime.utcnow()
            cycle.planning_started_at = datetime.utcnow()
        elif new_status == CycleStatus.REVIEW:
            cycle.planning_completed_at = datetime.utcnow()
            cycle.review_started_at = datetime.utcnow()
        elif new_status == CycleStatus.APPROVED:
            cycle.approved_at = datetime.utcnow()
            cycle.approved_by = changed_by
        elif new_status == CycleStatus.PUBLISHED:
            cycle.published_at = datetime.utcnow()
        elif new_status == CycleStatus.CLOSED:
            cycle.closed_at = datetime.utcnow()
        elif new_status == CycleStatus.ARCHIVED:
            cycle.archived_at = datetime.utcnow()
            cycle.retention_tier = SnapshotTier.COLD

        self.db.commit()

        logger.info(f"Updated cycle {cycle_id} status: {old_status.value} -> {new_status.value}")

        return cycle

    def get_active_cycle(self, tenant_id: int) -> Optional[PlanningCycle]:
        """
        Get the active planning cycle for a customer.

        Args:
            tenant_id: Customer ID

        Returns:
            Active cycle or None
        """
        active_statuses = [
            CycleStatus.DATA_COLLECTION,
            CycleStatus.PLANNING,
            CycleStatus.REVIEW
        ]

        return self.db.query(PlanningCycle).filter(
            and_(
                PlanningCycle.tenant_id == tenant_id,
                PlanningCycle.status.in_(active_statuses)
            )
        ).order_by(PlanningCycle.created_at.desc()).first()

    # ==================== Snapshot Management ====================

    def create_snapshot(
        self,
        cycle_id: int,
        snapshot_type: SnapshotType,
        commit_message: Optional[str] = None,
        created_by: Optional[int] = None,
        parent_snapshot_id: Optional[int] = None,
        sync_execution_id: Optional[int] = None,
        workflow_execution_id: Optional[int] = None,
        tags: Optional[List[str]] = None
    ) -> PlanningSnapshot:
        """
        Create a new planning snapshot.

        Args:
            cycle_id: Planning cycle ID
            snapshot_type: Type of snapshot
            commit_message: Git-style commit message
            created_by: User ID
            parent_snapshot_id: Parent snapshot for delta chain
            sync_execution_id: Related sync execution
            workflow_execution_id: Related workflow execution
            tags: Optional tags

        Returns:
            Created PlanningSnapshot
        """
        cycle = self.db.query(PlanningCycle).filter_by(id=cycle_id).first()
        if not cycle:
            raise ValueError(f"Planning cycle {cycle_id} not found")

        # Get next version number
        max_version = self.db.query(func.max(PlanningSnapshot.version)).filter(
            PlanningSnapshot.cycle_id == cycle_id
        ).scalar() or 0
        version = max_version + 1

        # Determine parent snapshot
        if parent_snapshot_id is None and version > 1:
            # Use current snapshot as parent
            parent_snapshot_id = cycle.current_snapshot_id

        snapshot = PlanningSnapshot(
            cycle_id=cycle_id,
            version=version,
            parent_snapshot_id=parent_snapshot_id,
            base_snapshot_id=cycle.baseline_snapshot_id,
            snapshot_type=snapshot_type,
            commit_message=commit_message or f"Snapshot v{version}",
            tags=tags,
            sync_execution_id=sync_execution_id,
            workflow_execution_id=workflow_execution_id,
            storage_tier=SnapshotTier.HOT,
            uses_delta_storage=(parent_snapshot_id is not None),
            created_by=created_by
        )
        self.db.add(snapshot)
        self.db.commit()
        self.db.refresh(snapshot)

        # Update lineage
        self._update_lineage(snapshot)

        # Update cycle references
        if snapshot_type == SnapshotType.BASELINE:
            cycle.baseline_snapshot_id = snapshot.id
        elif snapshot_type == SnapshotType.PUBLISHED:
            cycle.published_snapshot_id = snapshot.id

        cycle.current_snapshot_id = snapshot.id
        self.db.commit()

        logger.info(f"Created snapshot {snapshot.id} (v{version}) for cycle {cycle_id}")

        return snapshot

    def create_baseline_from_sync(
        self,
        cycle_id: int,
        sync_execution_id: int,
        created_by: Optional[int] = None
    ) -> PlanningSnapshot:
        """
        Create baseline snapshot from SAP sync execution.

        Args:
            cycle_id: Planning cycle ID
            sync_execution_id: Sync execution ID
            created_by: User ID

        Returns:
            Created baseline snapshot
        """
        sync_exec = self.db.query(SyncJobExecution).filter_by(id=sync_execution_id).first()
        if not sync_exec:
            raise ValueError(f"Sync execution {sync_execution_id} not found")

        snapshot = self.create_snapshot(
            cycle_id=cycle_id,
            snapshot_type=SnapshotType.BASELINE,
            commit_message=f"Baseline from SAP sync (execution {sync_execution_id})",
            created_by=created_by,
            sync_execution_id=sync_execution_id,
            tags=["baseline", "sap-sync"]
        )

        # Mark as materialized (full data, not deltas)
        snapshot.is_materialized = True
        snapshot.uses_delta_storage = False

        # Capture current planning data
        self._capture_snapshot_data(snapshot)

        self.db.commit()

        return snapshot

    def add_delta(
        self,
        snapshot_id: int,
        entity_type: DeltaEntityType,
        entity_key: str,
        operation: DeltaOperation,
        delta_data: Dict[str, Any],
        changed_fields: Optional[List[str]] = None,
        original_values: Optional[Dict[str, Any]] = None,
        change_reason: Optional[str] = None,
        decision_id: Optional[int] = None,
        created_by: Optional[int] = None
    ) -> SnapshotDelta:
        """
        Add a delta (change) to a snapshot.

        Args:
            snapshot_id: Snapshot ID
            entity_type: Type of entity changed
            entity_key: Entity identifier
            operation: Type of operation
            delta_data: Changed data
            changed_fields: List of changed field names
            original_values: Original values before change
            change_reason: Reason for change
            decision_id: Related decision ID
            created_by: User ID

        Returns:
            Created SnapshotDelta
        """
        snapshot = self.db.query(PlanningSnapshot).filter_by(id=snapshot_id).first()
        if not snapshot:
            raise ValueError(f"Snapshot {snapshot_id} not found")

        delta = SnapshotDelta(
            snapshot_id=snapshot_id,
            entity_type=entity_type,
            entity_key=entity_key,
            operation=operation,
            delta_data=delta_data,
            changed_fields=changed_fields,
            original_values=original_values,
            change_reason=change_reason,
            decision_id=decision_id,
            created_by=created_by
        )
        self.db.add(delta)

        # Update snapshot delta count
        snapshot.delta_count = (snapshot.delta_count or 0) + 1

        self.db.commit()
        self.db.refresh(delta)

        return delta

    def materialize_snapshot(self, snapshot_id: int) -> Dict[str, Any]:
        """
        Materialize a snapshot by resolving all deltas from parent chain.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            Full materialized data
        """
        snapshot = self.db.query(PlanningSnapshot).filter_by(id=snapshot_id).first()
        if not snapshot:
            raise ValueError(f"Snapshot {snapshot_id} not found")

        # If already materialized, return stored data
        if snapshot.is_materialized:
            return {
                "demand_plan": snapshot.demand_plan_data,
                "supply_plan": snapshot.supply_plan_data,
                "inventory": snapshot.inventory_data,
                "forecast": snapshot.forecast_data,
                "kpi": snapshot.kpi_data
            }

        # Get snapshot chain from baseline
        chain = self._get_snapshot_chain(snapshot_id)

        # Start with baseline data
        base_snapshot = chain[0]
        materialized = {
            "demand_plan": base_snapshot.demand_plan_data or {},
            "supply_plan": base_snapshot.supply_plan_data or {},
            "inventory": base_snapshot.inventory_data or {},
            "forecast": base_snapshot.forecast_data or {},
            "kpi": base_snapshot.kpi_data or {}
        }

        # Apply deltas from each snapshot in chain
        for snap in chain[1:]:
            deltas = self.db.query(SnapshotDelta).filter(
                SnapshotDelta.snapshot_id == snap.id
            ).order_by(SnapshotDelta.created_at).all()

            for delta in deltas:
                self._apply_delta(materialized, delta)

        return materialized

    def compare_snapshots(
        self,
        snapshot_a_id: int,
        snapshot_b_id: int
    ) -> Dict[str, Any]:
        """
        Compare two snapshots and return differences.

        Args:
            snapshot_a_id: First snapshot ID
            snapshot_b_id: Second snapshot ID

        Returns:
            Comparison result with differences
        """
        data_a = self.materialize_snapshot(snapshot_a_id)
        data_b = self.materialize_snapshot(snapshot_b_id)

        snapshot_a = self.db.query(PlanningSnapshot).filter_by(id=snapshot_a_id).first()
        snapshot_b = self.db.query(PlanningSnapshot).filter_by(id=snapshot_b_id).first()

        comparison = {
            "snapshot_a": {
                "id": snapshot_a_id,
                "version": snapshot_a.version,
                "type": snapshot_a.snapshot_type.value,
                "created_at": snapshot_a.created_at.isoformat()
            },
            "snapshot_b": {
                "id": snapshot_b_id,
                "version": snapshot_b.version,
                "type": snapshot_b.snapshot_type.value,
                "created_at": snapshot_b.created_at.isoformat()
            },
            "differences": {},
            "summary": {}
        }

        # Compare each data type
        for key in ["demand_plan", "supply_plan", "inventory", "forecast", "kpi"]:
            diff = self._compare_data(data_a.get(key, {}), data_b.get(key, {}))
            if diff["has_changes"]:
                comparison["differences"][key] = diff

        # Generate summary
        total_changes = sum(
            len(d.get("added", [])) + len(d.get("removed", [])) + len(d.get("modified", []))
            for d in comparison["differences"].values()
        )
        comparison["summary"] = {
            "total_changes": total_changes,
            "data_types_changed": list(comparison["differences"].keys())
        }

        return comparison

    def get_snapshot_chain(self, snapshot_id: int) -> List[PlanningSnapshot]:
        """
        Get the snapshot chain from baseline to specified snapshot.

        Args:
            snapshot_id: Target snapshot ID

        Returns:
            List of snapshots in order from baseline
        """
        return self._get_snapshot_chain(snapshot_id)

    # ==================== Private Methods ====================

    def _generate_cycle_code(self, cycle_type: CycleType, period_start: date) -> str:
        """Generate cycle code based on type and period."""
        year = period_start.year

        if cycle_type == CycleType.WEEKLY:
            week = period_start.isocalendar()[1]
            return f"{year}-W{week:02d}"
        elif cycle_type == CycleType.BIWEEKLY:
            week = period_start.isocalendar()[1]
            biweek = (week + 1) // 2
            return f"{year}-BW{biweek:02d}"
        elif cycle_type == CycleType.MONTHLY:
            return f"{year}-M{period_start.month:02d}"
        elif cycle_type == CycleType.QUARTERLY:
            quarter = (period_start.month - 1) // 3 + 1
            return f"{year}-Q{quarter}"
        elif cycle_type == CycleType.ANNUAL:
            return f"{year}"
        else:
            return f"{year}-{period_start.strftime('%m%d')}"

    def _validate_status_transition(
        self,
        current_status: CycleStatus,
        new_status: CycleStatus
    ) -> None:
        """Validate status transition is allowed."""
        valid_transitions = {
            CycleStatus.DRAFT: [CycleStatus.DATA_COLLECTION],
            CycleStatus.DATA_COLLECTION: [CycleStatus.PLANNING, CycleStatus.DRAFT],
            CycleStatus.PLANNING: [CycleStatus.REVIEW, CycleStatus.DATA_COLLECTION],
            CycleStatus.REVIEW: [CycleStatus.APPROVED, CycleStatus.PLANNING],
            CycleStatus.APPROVED: [CycleStatus.PUBLISHED, CycleStatus.REVIEW],
            CycleStatus.PUBLISHED: [CycleStatus.CLOSED],
            CycleStatus.CLOSED: [CycleStatus.ARCHIVED],
            CycleStatus.ARCHIVED: []
        }

        allowed = valid_transitions.get(current_status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Invalid status transition: {current_status.value} -> {new_status.value}. "
                f"Allowed transitions: {[s.value for s in allowed]}"
            )

    def _update_lineage(self, snapshot: PlanningSnapshot) -> None:
        """Update snapshot lineage table for ancestor tracking."""
        # Add self-reference
        self_lineage = SnapshotLineage(
            snapshot_id=snapshot.id,
            ancestor_id=snapshot.id,
            depth=0
        )
        self.db.add(self_lineage)

        # Copy parent's lineage with incremented depth
        if snapshot.parent_snapshot_id:
            parent_lineages = self.db.query(SnapshotLineage).filter(
                SnapshotLineage.snapshot_id == snapshot.parent_snapshot_id
            ).all()

            for pl in parent_lineages:
                lineage = SnapshotLineage(
                    snapshot_id=snapshot.id,
                    ancestor_id=pl.ancestor_id,
                    depth=pl.depth + 1
                )
                self.db.add(lineage)

        self.db.commit()

    def _get_snapshot_chain(self, snapshot_id: int) -> List[PlanningSnapshot]:
        """Get ordered chain of snapshots from baseline to target."""
        # Get all ancestors ordered by depth (descending = oldest first)
        lineages = self.db.query(SnapshotLineage).filter(
            SnapshotLineage.snapshot_id == snapshot_id
        ).order_by(SnapshotLineage.depth.desc()).all()

        snapshot_ids = [l.ancestor_id for l in lineages]

        # Fetch snapshots in order
        snapshots = []
        for sid in snapshot_ids:
            snap = self.db.query(PlanningSnapshot).filter_by(id=sid).first()
            if snap:
                snapshots.append(snap)

        return snapshots

    def _capture_snapshot_data(self, snapshot: PlanningSnapshot) -> None:
        """Capture current planning data into snapshot."""
        # This would integrate with actual planning data services
        # For now, capture basic structure

        snapshot.demand_plan_data = {}
        snapshot.supply_plan_data = {}
        snapshot.inventory_data = {}
        snapshot.forecast_data = {}
        snapshot.kpi_data = {}

        # Calculate data hash for integrity
        data_str = json.dumps({
            "demand": snapshot.demand_plan_data,
            "supply": snapshot.supply_plan_data,
            "inventory": snapshot.inventory_data,
            "forecast": snapshot.forecast_data,
            "kpi": snapshot.kpi_data
        }, sort_keys=True, default=str)

        snapshot.data_hash = hashlib.sha256(data_str.encode()).hexdigest()

    def _apply_delta(self, data: Dict[str, Any], delta: SnapshotDelta) -> None:
        """Apply a single delta to materialized data."""
        entity_type = delta.entity_type.value
        if entity_type not in data:
            data[entity_type] = {}

        target = data[entity_type]

        if delta.operation == DeltaOperation.CREATE:
            if delta.entity_key:
                target[delta.entity_key] = delta.delta_data
            else:
                # List append
                if not isinstance(target, list):
                    target = []
                target.append(delta.delta_data)

        elif delta.operation == DeltaOperation.UPDATE:
            if delta.entity_key and delta.entity_key in target:
                if isinstance(target[delta.entity_key], dict):
                    target[delta.entity_key].update(delta.delta_data)
                else:
                    target[delta.entity_key] = delta.delta_data

        elif delta.operation == DeltaOperation.DELETE:
            if delta.entity_key and delta.entity_key in target:
                del target[delta.entity_key]

    def _compare_data(
        self,
        data_a: Dict[str, Any],
        data_b: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compare two data dictionaries."""
        result = {
            "has_changes": False,
            "added": [],
            "removed": [],
            "modified": []
        }

        keys_a = set(data_a.keys()) if isinstance(data_a, dict) else set()
        keys_b = set(data_b.keys()) if isinstance(data_b, dict) else set()

        # Added keys
        for key in keys_b - keys_a:
            result["added"].append(key)
            result["has_changes"] = True

        # Removed keys
        for key in keys_a - keys_b:
            result["removed"].append(key)
            result["has_changes"] = True

        # Modified keys
        for key in keys_a & keys_b:
            if data_a.get(key) != data_b.get(key):
                result["modified"].append({
                    "key": key,
                    "old": data_a.get(key),
                    "new": data_b.get(key)
                })
                result["has_changes"] = True

        return result
