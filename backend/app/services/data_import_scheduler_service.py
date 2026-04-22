"""
Data Import Scheduler Service - Powell Framework Integration

Implements tiered data import scheduling with CDC integration:

Tier 1 - TRANSACTIONAL (hourly):
- Sales orders, purchase orders, inventory transactions
- Triggers: Order confirmation, ATP check

Tier 2 - OPERATIONAL (daily):
- Inventory levels, shipments, production orders
- Triggers: Rebalancing, PO creation, exception alerts

Tier 3 - TACTICAL/STRATEGIC (weekly):
- Forecasts, network changes, policy parameters
- Triggers: S&OP cycle, policy recalibration

Each tier has:
- Configurable cadence per data type
- CDC (Change Data Capture) for detecting meaningful changes
- Workflow triggering based on CDC results
- Versioning for audit trail

Integration with Powell Framework:
- CDC triggers condition monitoring
- Condition monitoring triggers agent execution
- Agents can request scenario evaluation
- Scenario results feed back to planning decisions
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import logging
import hashlib
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from app.models.sync_job import (
    SyncJobConfig, SyncJobExecution, SyncTableResult,
    SyncDataType, SyncStatus
)
from app.models.planning_cycle import (
    PlanningSnapshot, SnapshotType, SnapshotTier
)

logger = logging.getLogger(__name__)


# =============================================================================
# Import Tier Configuration
# =============================================================================

class ImportTier(str, Enum):
    """Data import frequency tiers."""
    TRANSACTIONAL = "transactional"  # Hourly - high-frequency transaction data
    OPERATIONAL = "operational"       # Daily - operational planning data
    TACTICAL = "tactical"             # Weekly - strategic planning data


@dataclass
class TierConfig:
    """Configuration for an import tier."""
    tier: ImportTier
    default_cron: str
    description: str
    data_types: List[SyncDataType]
    workflow_chain: List[str]
    snapshot_tier: SnapshotTier


# Default tier configurations
TIER_CONFIGS = {
    ImportTier.TRANSACTIONAL: TierConfig(
        tier=ImportTier.TRANSACTIONAL,
        default_cron="0 * * * *",  # Every hour
        description="High-frequency transactional data for real-time decisions",
        data_types=[
            SyncDataType.SALES_ORDERS,
            SyncDataType.PURCHASE_ORDERS,
            SyncDataType.INVENTORY,
            SyncDataType.DELIVERIES,
            SyncDataType.RESERVATIONS,
        ],
        workflow_chain=["validate", "cdc_detect", "condition_monitor", "alert"],
        # Hourly transactional snapshots are freshest → HOT retention tier.
        # (Earlier revision used medallion-architecture names BRONZE/SILVER/GOLD;
        # the actual SnapshotTier enum is HOT/WARM/COLD retention semantics.)
        snapshot_tier=SnapshotTier.HOT,
    ),
    ImportTier.OPERATIONAL: TierConfig(
        tier=ImportTier.OPERATIONAL,
        default_cron="0 6 * * *",  # Daily at 6 AM
        description="Daily operational data for execution planning",
        data_types=[
            SyncDataType.PRODUCTION_ORDERS,
            SyncDataType.ATP_DATA,
        ],
        workflow_chain=["validate", "cdc_detect", "aggregate", "analytics", "condition_monitor", "agent_trigger"],
        snapshot_tier=SnapshotTier.WARM,
    ),
    ImportTier.TACTICAL: TierConfig(
        tier=ImportTier.TACTICAL,
        default_cron="0 2 * * 0",  # Weekly on Sunday at 2 AM
        description="Weekly strategic data for S&OP planning",
        data_types=[
            SyncDataType.DEMAND_FORECAST,
            SyncDataType.SUPPLY_PLAN,
            SyncDataType.MATERIAL_MASTER,
            SyncDataType.VENDOR_MASTER,
            SyncDataType.CUSTOMER_MASTER,
            SyncDataType.BOM_MASTER,
            SyncDataType.ROUTING_MASTER,
        ],
        workflow_chain=["validate", "cdc_detect", "version", "aggregate", "analytics", "soop_trigger"],
        snapshot_tier=SnapshotTier.COLD,
    ),
}


# =============================================================================
# CDC (Change Data Capture) Structures
# =============================================================================

@dataclass
class CDCChange:
    """A detected change from CDC."""
    entity_type: str          # product, site, order, etc.
    entity_id: str
    change_type: str          # insert, update, delete
    old_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None
    changed_fields: List[str] = field(default_factory=list)
    significance_score: float = 0.0  # 0-1, how significant is this change
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CDCResult:
    """Result of CDC analysis on imported data."""
    execution_id: int
    tier: ImportTier
    data_type: SyncDataType
    total_records: int
    changed_records: int
    changes: List[CDCChange]
    significant_changes: int  # Changes above threshold
    version_hash: str         # Hash for versioning
    previous_version_hash: Optional[str] = None
    analyzed_at: datetime = field(default_factory=datetime.utcnow)


# Significance scoring weights by field type
FIELD_SIGNIFICANCE = {
    # High significance - triggers immediate action
    "quantity": 0.9,
    "available_atp": 0.95,
    "inventory_level": 0.85,
    "safety_stock": 0.8,
    "forecast_value": 0.85,
    "order_status": 0.9,
    "delivery_date": 0.85,
    "lead_time": 0.8,

    # Medium significance - triggers analysis
    "price": 0.6,
    "cost": 0.6,
    "supplier": 0.7,
    "location": 0.7,
    "priority": 0.75,

    # Low significance - informational only
    "description": 0.2,
    "name": 0.2,
    "updated_at": 0.1,
    "updated_by": 0.1,
}


# =============================================================================
# Main Service
# =============================================================================

class DataImportSchedulerService:
    """
    Orchestrates tiered data import with CDC integration.

    Responsibilities:
    1. Configure import schedules by tier
    2. Detect changes via CDC
    3. Trigger workflows based on change significance
    4. Maintain version history for audit
    5. Coordinate with condition monitoring
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.significance_threshold = 0.5  # Changes above this trigger workflows

    # =========================================================================
    # Tier Configuration
    # =========================================================================

    async def configure_tier_schedules(
        self,
        tenant_id: int,
        tier_overrides: Optional[Dict[ImportTier, str]] = None,
    ) -> List[SyncJobConfig]:
        """
        Configure sync jobs for all data types in each tier.

        Args:
            tenant_id: Customer to configure
            tier_overrides: Optional cron expression overrides by tier

        Returns:
            List of created/updated SyncJobConfig records
        """
        configs = []

        for tier, tier_config in TIER_CONFIGS.items():
            cron = (tier_overrides or {}).get(tier, tier_config.default_cron)

            for data_type in tier_config.data_types:
                config = await self._create_or_update_config(
                    tenant_id=tenant_id,
                    data_type=data_type,
                    tier=tier,
                    cron=cron,
                    workflow_chain=tier_config.workflow_chain,
                )
                configs.append(config)

        await self.db.flush()
        logger.info(f"Configured {len(configs)} sync jobs for tenant {tenant_id}")
        return configs

    async def _create_or_update_config(
        self,
        tenant_id: int,
        data_type: SyncDataType,
        tier: ImportTier,
        cron: str,
        workflow_chain: List[str],
    ) -> SyncJobConfig:
        """Create or update a sync job configuration."""
        # Check for existing config
        result = await self.db.execute(
            select(SyncJobConfig).where(
                SyncJobConfig.tenant_id == tenant_id,
                SyncJobConfig.data_type == data_type,
            )
        )
        config = result.scalar_one_or_none()

        # Get default settings for this data type
        from app.models.sync_job import DEFAULT_SYNC_CADENCES
        defaults = DEFAULT_SYNC_CADENCES.get(data_type, {})

        if config:
            # Update existing
            config.cron_expression = cron
            config.workflow_chain = workflow_chain
            config.updated_at = datetime.utcnow()
        else:
            # Create new
            config = SyncJobConfig(
                tenant_id=tenant_id,
                data_type=data_type,
                name=defaults.get("name", f"{data_type.value} Sync"),
                description=f"{tier.value.capitalize()} tier import",
                cron_expression=cron,
                is_enabled=True,
                use_delta_load=True,
                lookback_days=defaults.get("delta_days", 1),
                sap_tables=defaults.get("tables", []),
                trigger_workflow=True,
                workflow_chain=workflow_chain,
            )
            self.db.add(config)

        return config

    async def get_tier_status(
        self,
        tenant_id: int,
    ) -> Dict[ImportTier, Dict[str, Any]]:
        """
        Get status summary for each import tier.

        Returns:
            Dict mapping tier to status info (last run, next run, health)
        """
        status = {}

        for tier, tier_config in TIER_CONFIGS.items():
            # Get configs for this tier
            result = await self.db.execute(
                select(SyncJobConfig).where(
                    SyncJobConfig.tenant_id == tenant_id,
                    SyncJobConfig.data_type.in_(tier_config.data_types),
                )
            )
            configs = result.scalars().all()

            # Get latest executions
            config_ids = [c.id for c in configs]
            if config_ids:
                exec_result = await self.db.execute(
                    select(SyncJobExecution)
                    .where(SyncJobExecution.config_id.in_(config_ids))
                    .order_by(desc(SyncJobExecution.created_at))
                    .limit(len(config_ids))
                )
                executions = exec_result.scalars().all()
            else:
                executions = []

            # Calculate health
            total = len(configs)
            enabled = sum(1 for c in configs if c.is_enabled)
            recent_success = sum(
                1 for e in executions
                if e.status == SyncStatus.COMPLETED
                and e.created_at > datetime.utcnow() - timedelta(days=1)
            )

            status[tier] = {
                "tier": tier.value,
                "description": tier_config.description,
                "total_jobs": total,
                "enabled_jobs": enabled,
                "recent_successful": recent_success,
                "health_score": recent_success / enabled if enabled > 0 else 0,
                "last_execution": max(
                    (e.created_at for e in executions), default=None
                ),
                "cron_expression": tier_config.default_cron,
            }

        return status

    # =========================================================================
    # CDC (Change Data Capture)
    # =========================================================================

    async def perform_cdc_analysis(
        self,
        execution: SyncJobExecution,
        current_data: List[Dict[str, Any]],
        previous_snapshot: Optional[PlanningSnapshot] = None,
    ) -> CDCResult:
        """
        Perform CDC analysis comparing current data to previous snapshot.

        Args:
            execution: The sync job execution record
            current_data: The newly imported data
            previous_snapshot: Previous version snapshot for comparison

        Returns:
            CDCResult with detected changes
        """
        config = execution.config
        tier = self._get_tier_for_data_type(config.data_type)

        # Calculate version hash for current data
        version_hash = self._calculate_version_hash(current_data)

        # Get previous data if available
        previous_data = []
        previous_hash = None
        if previous_snapshot:
            previous_data = previous_snapshot.data.get("records", [])
            previous_hash = previous_snapshot.version_hash

        # Quick check - if hash matches, no changes
        if version_hash == previous_hash:
            return CDCResult(
                execution_id=execution.id,
                tier=tier,
                data_type=config.data_type,
                total_records=len(current_data),
                changed_records=0,
                changes=[],
                significant_changes=0,
                version_hash=version_hash,
                previous_version_hash=previous_hash,
            )

        # Detect changes
        changes = self._detect_changes(
            current_data=current_data,
            previous_data=previous_data,
            entity_type=self._get_entity_type_for_data_type(config.data_type),
        )

        # Count significant changes
        significant_changes = sum(
            1 for c in changes
            if c.significance_score >= self.significance_threshold
        )

        logger.info(
            f"CDC analysis for {config.data_type.value}: "
            f"{len(changes)} changes, {significant_changes} significant"
        )

        return CDCResult(
            execution_id=execution.id,
            tier=tier,
            data_type=config.data_type,
            total_records=len(current_data),
            changed_records=len(changes),
            changes=changes,
            significant_changes=significant_changes,
            version_hash=version_hash,
            previous_version_hash=previous_hash,
        )

    def _detect_changes(
        self,
        current_data: List[Dict[str, Any]],
        previous_data: List[Dict[str, Any]],
        entity_type: str,
    ) -> List[CDCChange]:
        """Detect changes between current and previous data."""
        changes = []

        # Index previous data by ID
        id_field = self._get_id_field_for_entity(entity_type)
        previous_by_id = {
            str(r.get(id_field)): r
            for r in previous_data
            if r.get(id_field) is not None
        }

        current_ids = set()

        for record in current_data:
            record_id = str(record.get(id_field))
            if not record_id:
                continue

            current_ids.add(record_id)

            if record_id not in previous_by_id:
                # New record (insert)
                changes.append(CDCChange(
                    entity_type=entity_type,
                    entity_id=record_id,
                    change_type="insert",
                    new_value=record,
                    significance_score=0.8,  # New records are significant
                ))
            else:
                # Check for updates
                old_record = previous_by_id[record_id]
                changed_fields = self._find_changed_fields(old_record, record)

                if changed_fields:
                    significance = self._calculate_change_significance(changed_fields)
                    changes.append(CDCChange(
                        entity_type=entity_type,
                        entity_id=record_id,
                        change_type="update",
                        old_value=old_record,
                        new_value=record,
                        changed_fields=changed_fields,
                        significance_score=significance,
                    ))

        # Check for deletions
        for record_id in previous_by_id:
            if record_id not in current_ids:
                changes.append(CDCChange(
                    entity_type=entity_type,
                    entity_id=record_id,
                    change_type="delete",
                    old_value=previous_by_id[record_id],
                    significance_score=0.9,  # Deletions are significant
                ))

        return changes

    def _find_changed_fields(
        self,
        old_record: Dict[str, Any],
        new_record: Dict[str, Any],
    ) -> List[str]:
        """Find fields that changed between old and new record."""
        changed = []
        all_fields = set(old_record.keys()) | set(new_record.keys())

        for field in all_fields:
            old_val = old_record.get(field)
            new_val = new_record.get(field)

            # Skip timestamp fields for comparison
            if field in ["updated_at", "created_at", "modified_at"]:
                continue

            if old_val != new_val:
                changed.append(field)

        return changed

    def _calculate_change_significance(
        self,
        changed_fields: List[str],
    ) -> float:
        """Calculate significance score based on changed fields."""
        if not changed_fields:
            return 0.0

        scores = []
        for field in changed_fields:
            # Check for exact match
            if field in FIELD_SIGNIFICANCE:
                scores.append(FIELD_SIGNIFICANCE[field])
            else:
                # Check for partial match (e.g., "inventory_qty" matches "inventory")
                for key, score in FIELD_SIGNIFICANCE.items():
                    if key in field.lower() or field.lower() in key:
                        scores.append(score)
                        break
                else:
                    scores.append(0.3)  # Default for unknown fields

        # Return max significance among changed fields
        return max(scores) if scores else 0.3

    def _calculate_version_hash(
        self,
        data: List[Dict[str, Any]],
    ) -> str:
        """Calculate a hash for data versioning."""
        # Sort data by ID for consistent hashing
        sorted_data = sorted(data, key=lambda x: str(x.get("id", "")))
        data_str = json.dumps(sorted_data, sort_keys=True, default=str)
        return hashlib.sha256(data_str.encode()).hexdigest()[:16]

    # =========================================================================
    # Workflow Triggering
    # =========================================================================

    async def trigger_workflows_from_cdc(
        self,
        cdc_result: CDCResult,
        tenant_id: int,
    ) -> Dict[str, Any]:
        """
        Trigger appropriate workflows based on CDC results.

        Args:
            cdc_result: The CDC analysis result
            tenant_id: Customer ID

        Returns:
            Summary of triggered workflows
        """
        triggered = {
            "condition_checks": [],
            "agent_triggers": [],
            "notifications": [],
        }

        if cdc_result.significant_changes == 0:
            logger.info(f"No significant changes, skipping workflows")
            return triggered

        tier_config = TIER_CONFIGS.get(cdc_result.tier)
        if not tier_config:
            return triggered

        # Execute workflow chain
        for workflow_step in tier_config.workflow_chain:
            if workflow_step == "condition_monitor":
                # Trigger condition monitoring
                conditions = await self._trigger_condition_monitoring(
                    cdc_result, tenant_id
                )
                triggered["condition_checks"] = conditions

            elif workflow_step == "agent_trigger":
                # Trigger execution agents (TRMs)
                agents = await self._trigger_execution_agents(
                    cdc_result, tenant_id
                )
                triggered["agent_triggers"] = agents

            elif workflow_step == "soop_trigger":
                # Trigger S&OP cycle
                soop = await self._trigger_soop_cycle(
                    cdc_result, tenant_id
                )
                triggered["agent_triggers"].extend(soop)

            elif workflow_step == "alert":
                # Send notifications
                alerts = await self._send_change_alerts(
                    cdc_result, tenant_id
                )
                triggered["notifications"] = alerts

        return triggered

    async def _trigger_condition_monitoring(
        self,
        cdc_result: CDCResult,
        tenant_id: int,
    ) -> List[str]:
        """Trigger condition monitoring based on CDC changes."""
        # This will be implemented by ConditionMonitorService
        # For now, return the conditions to check
        conditions_to_check = []

        for change in cdc_result.changes:
            if change.significance_score >= self.significance_threshold:
                if change.entity_type == "inventory":
                    conditions_to_check.append("inventory_below_target")
                    conditions_to_check.append("inventory_above_max")
                elif change.entity_type == "order":
                    conditions_to_check.append("atp_shortfall")
                    conditions_to_check.append("order_past_due")
                elif change.entity_type == "production":
                    conditions_to_check.append("capacity_overload")

        return list(set(conditions_to_check))

    async def _trigger_execution_agents(
        self,
        cdc_result: CDCResult,
        tenant_id: int,
    ) -> List[str]:
        """Trigger TRM agents based on changes."""
        agents_to_trigger = []

        for change in cdc_result.changes:
            if change.significance_score < self.significance_threshold:
                continue

            if cdc_result.data_type in [SyncDataType.SALES_ORDERS, SyncDataType.ATP_DATA]:
                agents_to_trigger.append("trm_atp")
            elif cdc_result.data_type == SyncDataType.INVENTORY:
                agents_to_trigger.append("trm_rebalance")
            elif cdc_result.data_type == SyncDataType.PURCHASE_ORDERS:
                agents_to_trigger.append("trm_po_creation")
            elif cdc_result.data_type in [SyncDataType.DELIVERIES, SyncDataType.PRODUCTION_ORDERS]:
                agents_to_trigger.append("trm_order_tracking")

        return list(set(agents_to_trigger))

    async def _trigger_soop_cycle(
        self,
        cdc_result: CDCResult,
        tenant_id: int,
    ) -> List[str]:
        """Trigger S&OP planning cycle."""
        agents = []

        if cdc_result.data_type in [SyncDataType.DEMAND_FORECAST, SyncDataType.SUPPLY_PLAN]:
            agents.append("gnn_soop")
            agents.append("gnn_execution")
        elif cdc_result.data_type in [SyncDataType.BOM_MASTER, SyncDataType.ROUTING_MASTER]:
            agents.append("gnn_soop")  # Network structure changed

        return agents

    async def _send_change_alerts(
        self,
        cdc_result: CDCResult,
        tenant_id: int,
    ) -> List[str]:
        """Send alerts for significant changes."""
        alerts = []

        for change in cdc_result.changes:
            if change.significance_score >= 0.8:  # High significance
                alert_type = f"{change.change_type}_{change.entity_type}"
                alerts.append(alert_type)

        return alerts

    # =========================================================================
    # Version Management
    # =========================================================================

    async def create_snapshot(
        self,
        execution: SyncJobExecution,
        cdc_result: CDCResult,
        data: List[Dict[str, Any]],
    ) -> PlanningSnapshot:
        """
        Create a snapshot for version control.

        Args:
            execution: The sync execution
            cdc_result: CDC analysis result
            data: The imported data

        Returns:
            Created PlanningSnapshot
        """
        tier_config = TIER_CONFIGS.get(cdc_result.tier)

        snapshot = PlanningSnapshot(
            # Note: planning_cycle_id would be set if within a cycle
            name=f"{cdc_result.data_type.value}_{cdc_result.version_hash}",
            description=f"Import from {execution.config.name or 'sync'}",
            snapshot_type=SnapshotType.AUTOMATED,
            tier=tier_config.snapshot_tier if tier_config else SnapshotTier.HOT,
            data={"records": data, "metadata": {"execution_id": execution.id}},
            version_hash=cdc_result.version_hash,
            previous_version_id=None,  # Would link to previous snapshot
            diff_from_previous={"changes_count": cdc_result.changed_records},
        )

        self.db.add(snapshot)
        await self.db.flush()

        return snapshot

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _get_tier_for_data_type(self, data_type: SyncDataType) -> ImportTier:
        """Get the tier for a data type."""
        for tier, config in TIER_CONFIGS.items():
            if data_type in config.data_types:
                return tier
        return ImportTier.OPERATIONAL  # Default

    def _get_entity_type_for_data_type(self, data_type: SyncDataType) -> str:
        """Map data type to entity type."""
        mapping = {
            SyncDataType.INVENTORY: "inventory",
            SyncDataType.SALES_ORDERS: "order",
            SyncDataType.PURCHASE_ORDERS: "purchase_order",
            SyncDataType.PRODUCTION_ORDERS: "production",
            SyncDataType.DELIVERIES: "delivery",
            SyncDataType.DEMAND_FORECAST: "forecast",
            SyncDataType.SUPPLY_PLAN: "supply_plan",
            SyncDataType.MATERIAL_MASTER: "product",
            SyncDataType.VENDOR_MASTER: "vendor",
            SyncDataType.CUSTOMER_MASTER: "customer",
            SyncDataType.BOM_MASTER: "bom",
            SyncDataType.ATP_DATA: "atp",
        }
        return mapping.get(data_type, "unknown")

    def _get_id_field_for_entity(self, entity_type: str) -> str:
        """Get the ID field name for an entity type."""
        mapping = {
            "inventory": "material_site_id",
            "order": "order_id",
            "purchase_order": "po_id",
            "production": "production_order_id",
            "delivery": "delivery_id",
            "forecast": "forecast_id",
            "supply_plan": "plan_id",
            "product": "material_id",
            "vendor": "vendor_id",
            "customer": "customer_id",
            "bom": "bom_id",
            "atp": "atp_id",
        }
        return mapping.get(entity_type, "id")
