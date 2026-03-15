"""
Scenario Branching Service

Implements git-like configuration inheritance for supply chain configurations.
Inspired by Kinaxis RapidResponse scenario management patterns.

Key Operations:
- create_branch: Copy-on-write branching from parent
- get_effective_config: Merge parent + all ancestor deltas
- update_scenario: Record changes as deltas
- commit_scenario: Materialize working scenario to baseline
- rollback_scenario: Discard changes
- diff_scenarios: Compare two configurations
- merge_scenarios: Merge with conflict resolution
"""
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import datetime
import json
import hashlib

from app.models.supply_chain_config import (
    SupplyChainConfig,
    ConfigDelta,
    ConfigLineage,
    Node,
    TransportationLane,
    Market,
    MarketDemand,
)
from app.models.sc_entities import Product, ProductBom


class ScenarioType:
    """Scenario type constants"""
    BASELINE = "BASELINE"
    WORKING = "WORKING"
    SIMULATION = "SIMULATION"


class EntityType:
    """Entity type constants"""
    NODE = "node"
    LANE = "lane"
    CUSTOMER = "customer"
    VENDOR = "vendor"
    BOM = "bom"
    ITEM = "item"
    CONFIG = "config"
    SOURCING_RULE = "sourcing_rule"


class Operation:
    """Delta operation constants"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class ScenarioBranchingService:
    """Service for managing scenario branching with delta storage"""

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # Core Operations
    # =========================================================================

    def create_branch(
        self,
        parent_config_id: int,
        name: str,
        description: str,
        scenario_type: str = ScenarioType.WORKING,
        created_by: Optional[int] = None,
    ) -> SupplyChainConfig:
        """
        Create a new branch (child configuration) from a parent.

        Uses copy-on-write semantics: child config initially has no entities,
        only a parent reference. Entities are inherited from parent until modified.

        Args:
            parent_config_id: ID of parent configuration
            name: Name for new branch
            description: Description of branch purpose
            scenario_type: BASELINE, WORKING, or SIMULATION
            created_by: User ID creating the branch

        Returns:
            New SupplyChainConfig instance

        Example:
            TBG Root (id=1) → Case TBG (id=2)
            - Case TBG inherits all nodes/lanes from TBG Root
            - Changes to Case TBG stored as deltas
        """
        # Get parent config
        parent = self.db.query(SupplyChainConfig).filter_by(id=parent_config_id).first()
        if not parent:
            raise ValueError(f"Parent config {parent_config_id} not found")

        # Determine base config (root of lineage)
        base_config_id = parent.base_config_id if parent.base_config_id else parent_config_id

        # Create child config
        # Branches (WORKING/SIMULATION) are NOT active — only BASELINE configs
        # can be active, enforced by uq_tenant_active_baseline partial index.
        child = SupplyChainConfig(
            name=name,
            description=description,
            tenant_id=parent.tenant_id,
            time_bucket=parent.time_bucket,
            parent_config_id=parent_config_id,
            base_config_id=base_config_id,
            scenario_type=scenario_type,
            uses_delta_storage=True,
            version=1,
            is_active=False,
            branched_at=datetime.datetime.utcnow(),
            created_by=created_by,
            validation_status="unchecked",
            training_status="pending",
            needs_training=True,
            site_type_definitions=parent.site_type_definitions,
        )

        self.db.add(child)
        self.db.flush()  # Get child.id

        # Build lineage (add self + all parent's ancestors)
        self._build_lineage(child.id, parent_config_id)

        self.db.commit()
        return child

    def get_effective_config(self, config_id: int) -> Dict[str, Any]:
        """
        Compute effective configuration by merging parent + all ancestor deltas.

        Returns a dictionary with:
        - config: SupplyChainConfig metadata
        - nodes: List of nodes (merged from ancestors + deltas)
        - lanes: List of lanes
        - markets: List of markets
        - market_demands: List of market demands
        - products: List of products (items)
        - boms: List of BOMs

        Algorithm:
        1. Get lineage (self → parent → grandparent → ... → root)
        2. Start with root config's entities
        3. Apply deltas in order (root → parent → self)
        4. Return merged configuration

        Args:
            config_id: Configuration to compute

        Returns:
            Dictionary with effective configuration
        """
        config = self.db.query(SupplyChainConfig).filter_by(id=config_id).first()
        if not config:
            raise ValueError(f"Config {config_id} not found")

        # If not using delta storage or no parent, return config as-is
        if not config.uses_delta_storage or not config.parent_config_id:
            return self._serialize_config(config)

        # Get lineage (ordered root → ... → parent → self)
        lineage = self._get_lineage(config_id)

        # Start with root config's entities
        root_config_id = lineage[-1]  # Last in lineage is root
        effective = self._serialize_config(
            self.db.query(SupplyChainConfig).filter_by(id=root_config_id).first()
        )

        # Apply deltas from each ancestor (root → parent → self)
        for ancestor_id in reversed(lineage[:-1]):
            deltas = self.db.query(ConfigDelta).filter_by(config_id=ancestor_id).order_by(ConfigDelta.created_at).all()
            for delta in deltas:
                self._apply_delta(effective, delta)

        return effective

    def update_scenario(
        self,
        config_id: int,
        entity_type: str,
        operation: str,
        delta_data: Dict[str, Any],
        entity_id: Optional[int] = None,
        created_by: Optional[int] = None,
        description: Optional[str] = None,
    ) -> ConfigDelta:
        """
        Record a change to a scenario as a delta.

        Args:
            config_id: Configuration being modified
            entity_type: Type of entity (node, lane, market_demand, etc.)
            operation: create, update, or delete
            delta_data: Full entity data for create, partial for update, minimal for delete
            entity_id: ID of entity (NULL for create)
            created_by: User making the change
            description: Human-readable description

        Returns:
            ConfigDelta record

        Example:
            update_scenario(
                config_id=2,
                entity_type='node',
                operation='create',
                delta_data={'name': 'Case Manufacturer', 'type': 'MANUFACTURER', ...},
                description='Add Case Manufacturer node'
            )
        """
        config = self.db.query(SupplyChainConfig).filter_by(id=config_id).first()
        if not config:
            raise ValueError(f"Config {config_id} not found")

        # For update operations, compute changed fields and original values
        changed_fields = None
        original_values = None
        if operation == Operation.UPDATE and entity_id:
            original_values = self._get_entity_data(entity_type, entity_id)
            changed_fields = [k for k in delta_data.keys() if delta_data[k] != original_values.get(k)]

        # Create delta record
        delta = ConfigDelta(
            config_id=config_id,
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation,
            delta_data=delta_data,
            changed_fields=changed_fields,
            original_values=original_values,
            created_by=str(created_by) if created_by else None,
            description=description,
        )

        self.db.add(delta)
        self.db.commit()
        return delta

    def commit_scenario(self, config_id: int, committed_by: Optional[int] = None) -> SupplyChainConfig:
        """
        Commit a working scenario to its baseline.

        Materializes all deltas into parent config and marks scenario as committed.
        For WORKING scenarios that branch from BASELINE, this promotes changes to baseline.

        Args:
            config_id: Working scenario to commit
            committed_by: User committing the scenario

        Returns:
            Updated parent configuration

        Raises:
            ValueError: If scenario is not WORKING type or has no parent
        """
        config = self.db.query(SupplyChainConfig).filter_by(id=config_id).first()
        if not config:
            raise ValueError(f"Config {config_id} not found")

        if config.scenario_type != ScenarioType.WORKING:
            raise ValueError(f"Only WORKING scenarios can be committed (got {config.scenario_type})")

        if not config.parent_config_id:
            raise ValueError("Cannot commit root configuration (no parent)")

        # Get effective configuration
        effective = self.get_effective_config(config_id)

        # Get parent
        parent = self.db.query(SupplyChainConfig).filter_by(id=config.parent_config_id).first()

        # Apply all changes to parent (this materializes the deltas)
        deltas = self.db.query(ConfigDelta).filter_by(config_id=config_id).all()
        for delta in deltas:
            self._materialize_delta_to_parent(parent, delta)

        # Mark scenario as committed
        config.committed_at = datetime.datetime.utcnow()
        config.is_active = False  # Deactivate after commit

        self.db.commit()
        return parent

    def rollback_scenario(self, config_id: int) -> None:
        """
        Rollback all changes to a scenario (delete all deltas).

        Args:
            config_id: Scenario to rollback

        Raises:
            ValueError: If scenario is BASELINE (cannot rollback baseline)
        """
        config = self.db.query(SupplyChainConfig).filter_by(id=config_id).first()
        if not config:
            raise ValueError(f"Config {config_id} not found")

        if config.scenario_type == ScenarioType.BASELINE:
            raise ValueError("Cannot rollback BASELINE scenarios")

        # Delete all deltas
        self.db.query(ConfigDelta).filter_by(config_id=config_id).delete()
        self.db.commit()

    def diff_scenarios(self, config_id_a: int, config_id_b: int) -> Dict[str, List[Dict]]:
        """
        Compare two configurations and return differences.

        Returns:
            Dictionary with:
            - added: Entities in B but not in A
            - removed: Entities in A but not in B
            - modified: Entities in both but with different values
        """
        effective_a = self.get_effective_config(config_id_a)
        effective_b = self.get_effective_config(config_id_b)

        diff = {"added": [], "removed": [], "modified": []}

        # Compare each entity type (including sourcing rules for alternate sourcing diffs)
        for entity_type in ["nodes", "lanes", "markets", "market_demands", "products", "boms", "sourcing_rules"]:
            entities_a = {e["id"]: e for e in effective_a.get(entity_type, [])}
            entities_b = {e["id"]: e for e in effective_b.get(entity_type, [])}

            # Added in B
            for eid, entity in entities_b.items():
                if eid not in entities_a:
                    diff["added"].append({"type": entity_type, "entity": entity})

            # Removed from A
            for eid, entity in entities_a.items():
                if eid not in entities_b:
                    diff["removed"].append({"type": entity_type, "entity": entity})

            # Modified
            for eid in entities_a.keys() & entities_b.keys():
                if entities_a[eid] != entities_b[eid]:
                    diff["modified"].append({
                        "type": entity_type,
                        "before": entities_a[eid],
                        "after": entities_b[eid],
                    })

        return diff

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _build_lineage(self, config_id: int, parent_config_id: int) -> None:
        """Build lineage table for efficient ancestor queries"""
        # Add self-reference (depth=0)
        self.db.add(ConfigLineage(config_id=config_id, ancestor_id=config_id, depth=0))

        # Add parent's lineage with incremented depth
        parent_lineage = self.db.query(ConfigLineage).filter_by(config_id=parent_config_id).all()
        for lineage in parent_lineage:
            self.db.add(
                ConfigLineage(
                    config_id=config_id,
                    ancestor_id=lineage.ancestor_id,
                    depth=lineage.depth + 1,
                )
            )

    def _get_lineage(self, config_id: int) -> List[int]:
        """Get ordered list of ancestor IDs (self → parent → grandparent → root)"""
        lineage = (
            self.db.query(ConfigLineage)
            .filter_by(config_id=config_id)
            .order_by(ConfigLineage.depth)
            .all()
        )
        return [l.ancestor_id for l in lineage]

    def _serialize_config(self, config: SupplyChainConfig) -> Dict[str, Any]:
        """Serialize a configuration to a dictionary"""
        return {
            "config": {
                "id": config.id,
                "name": config.name,
                "description": config.description,
                "tenant_id": config.tenant_id,
                "time_bucket": config.time_bucket.value if config.time_bucket else None,
                "scenario_type": config.scenario_type,
                "parent_config_id": config.parent_config_id,
            },
            "sites": [self._serialize_node(n) for n in config.nodes],
            "lanes": [self._serialize_lane(l) for l in config.lanes],
            "markets": [self._serialize_market(m) for m in config.markets],
            "market_demands": [self._serialize_market_demand(md) for md in config.market_demands],
            "products": self._load_products(config.id),
            "boms": self._load_boms(config.id),
            "sourcing_rules": self._load_sourcing_rules(config.id),
        }

    def _serialize_node(self, node: Node) -> Dict[str, Any]:
        """Serialize a Node to dict"""
        return {
            "id": node.id,
            "name": node.name,
            "type": node.type,
            "params": node.params,
            "priority": node.priority,
            "x": node.x,
            "y": node.y,
        }

    def _serialize_lane(self, lane: TransportationLane) -> Dict[str, Any]:
        """Serialize a TransportationLane to dict"""
        return {
            "id": lane.id,
            "from_site_id": lane.from_site_id,
            "to_site_id": lane.to_site_id,
            "demand_lead_time": lane.demand_lead_time,
            "supply_lead_time": lane.supply_lead_time,
            "cost_per_unit": lane.cost_per_unit,
        }

    def _serialize_market(self, market: Market) -> Dict[str, Any]:
        """Serialize a Market to dict"""
        return {
            "id": market.id,
            "name": market.name,
            "type": market.type,
        }

    def _serialize_market_demand(self, md: MarketDemand) -> Dict[str, Any]:
        """Serialize a MarketDemand to dict"""
        return {
            "id": md.id,
            "market_id": md.market_id,
            "demand_distribution": md.demand_distribution,
            "num_rounds": md.num_rounds,
        }

    def _load_products(self, config_id: int) -> List[Dict[str, Any]]:
        """Load products for a config from the Product table."""
        try:
            products = self.db.query(Product).filter(Product.config_id == config_id).all()
            return [
                {
                    "id": p.id,
                    "description": getattr(p, "description", None),
                    "product_group_id": getattr(p, "product_group_id", None),
                    "unit_cost": float(getattr(p, "unit_cost", 0) or 0),
                }
                for p in products
            ]
        except Exception:
            return []

    def _load_boms(self, config_id: int) -> List[Dict[str, Any]]:
        """Load BOMs for a config from the ProductBom table."""
        try:
            boms = self.db.query(ProductBom).filter(ProductBom.config_id == config_id).all()
            return [
                {
                    "id": b.id,
                    "parent_product_id": b.parent_product_id,
                    "component_product_id": b.component_product_id,
                    "quantity_per": float(getattr(b, "quantity_per", 1) or 1),
                    "scrap_rate": float(getattr(b, "scrap_rate", 0) or 0),
                }
                for b in boms
            ]
        except Exception:
            return []

    def _load_sourcing_rules(self, config_id: int) -> List[Dict[str, Any]]:
        """Load sourcing rules for a config from the SourcingRules table."""
        try:
            from app.models.sc_entities import SourcingRules
            rules = self.db.query(SourcingRules).filter(
                SourcingRules.config_id == config_id
            ).all()
            return [
                {
                    "id": r.id,
                    "product_id": r.product_id,
                    "product_group_id": getattr(r, "product_group_id", None),
                    "from_site_id": getattr(r, "from_site_id", None),
                    "to_site_id": getattr(r, "to_site_id", None),
                    "tpartner_id": getattr(r, "tpartner_id", None),
                    "sourcing_rule_type": r.sourcing_rule_type,
                    "sourcing_priority": r.sourcing_priority,
                    "sourcing_ratio": float(getattr(r, "sourcing_ratio", 0) or 0),
                    "min_quantity": float(getattr(r, "min_quantity", 0) or 0),
                    "max_quantity": float(getattr(r, "max_quantity", 0) or 0),
                    "is_active": getattr(r, "is_active", "Y"),
                }
                for r in rules
            ]
        except Exception:
            return []

    def get_effective_sourcing_rules(self, config_id: int) -> List[Dict[str, Any]]:
        """Get sourcing rules with parent-fallback for branch configs.

        Branch-specific rules override parent rules.  Override key is
        (product_id, to_site_id, sourcing_rule_type).
        """
        config = self.db.query(SupplyChainConfig).filter_by(id=config_id).first()
        if not config:
            return []

        branch_rules = self._load_sourcing_rules(config_id)
        if not config.parent_config_id:
            return branch_rules

        # Build set of keys that the branch overrides
        overridden = {
            (r["product_id"], r["to_site_id"], r["sourcing_rule_type"])
            for r in branch_rules
        }

        parent_rules = self._load_sourcing_rules(config.parent_config_id)
        inherited = [
            r for r in parent_rules
            if (r["product_id"], r["to_site_id"], r["sourcing_rule_type"]) not in overridden
        ]

        return branch_rules + inherited

    def _apply_delta(self, effective: Dict[str, Any], delta: ConfigDelta) -> None:
        """Apply a delta to an effective configuration"""
        entity_list_key = f"{delta.entity_type}s"  # e.g., "nodes", "lanes"
        if entity_list_key not in effective:
            effective[entity_list_key] = []

        entities = effective[entity_list_key]

        if delta.operation == Operation.CREATE:
            # Add new entity
            entities.append(delta.delta_data)

        elif delta.operation == Operation.UPDATE:
            # Update existing entity
            for i, entity in enumerate(entities):
                if entity.get("id") == delta.entity_id:
                    # Merge delta_data into entity
                    entities[i] = {**entity, **delta.delta_data}
                    break

        elif delta.operation == Operation.DELETE:
            # Remove entity
            effective[entity_list_key] = [e for e in entities if e.get("id") != delta.entity_id]

    def _get_entity_data(self, entity_type: str, entity_id: int) -> Dict[str, Any]:
        """Get current data for an entity"""
        if entity_type == EntityType.NODE:
            entity = self.db.query(Node).filter_by(id=entity_id).first()
            return self._serialize_node(entity) if entity else {}
        elif entity_type == EntityType.LANE:
            entity = self.db.query(TransportationLane).filter_by(id=entity_id).first()
            return self._serialize_lane(entity) if entity else {}
        # Add other entity types as needed
        return {}

    def _materialize_delta_to_parent(self, parent: SupplyChainConfig, delta: ConfigDelta) -> None:
        """Materialize a delta by applying it to the parent configuration"""
        if delta.entity_type == EntityType.NODE:
            if delta.operation == Operation.CREATE:
                node = Node(**delta.delta_data, config_id=parent.id)
                self.db.add(node)
            elif delta.operation == Operation.UPDATE:
                node = self.db.query(Node).filter_by(id=delta.entity_id).first()
                if node:
                    for key, value in delta.delta_data.items():
                        setattr(node, key, value)
            elif delta.operation == Operation.DELETE:
                self.db.query(Node).filter_by(id=delta.entity_id).delete()

        # Add other entity types as needed
