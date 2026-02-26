"""
Hierarchical DAG Builder for GNN Models

This service builds graph structures at different hierarchy levels for planning:
- S&OP: Region × Family with monthly buckets
- MPS: Site × Group with weekly buckets
- Execution: Site × SKU with hourly buckets

The DAG structure changes based on the planning hierarchy configuration,
enabling the same GNN architecture to work at different aggregation levels.

Powell Framework Alignment:
- Higher hierarchy levels → CFA (compute aggregated policy parameters θ)
- Lower hierarchy levels → VFA (make detailed decisions Q(s,a))
- Hierarchical consistency enforced through constraint propagation
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Set
from datetime import datetime, date, timedelta
from enum import Enum
import numpy as np
import logging

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from ..models.planning_hierarchy import (
    PlanningHierarchyConfig,
    SiteHierarchyNode,
    ProductHierarchyNode,
    AggregatedPlan,
    SiteHierarchyLevel,
    ProductHierarchyLevel,
    TimeBucketType,
    PlanningType,
)
from ..models.sc_entities import (
    Site, Product, ProductHierarchy, Geography, SourcingRules, InvLevel
)
from ..models.supply_chain_config import SupplyChainConfig, Node, TransportationLane

logger = logging.getLogger(__name__)


@dataclass
class HierarchicalNode:
    """A node in the hierarchical DAG"""
    id: str
    name: str
    node_type: str  # 'site' or 'product' or 'combined'
    hierarchy_level: str
    hierarchy_path: str
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)

    # Aggregated features
    features: Dict[str, float] = field(default_factory=dict)

    # Child entities at leaf level
    leaf_site_ids: List[str] = field(default_factory=list)
    leaf_product_ids: List[str] = field(default_factory=list)

    # GNN-specific
    gnn_index: Optional[int] = None


@dataclass
class HierarchicalEdge:
    """An edge in the hierarchical DAG"""
    source_id: str
    target_id: str
    edge_type: str  # 'flow', 'hierarchy', 'supply'

    # Aggregated edge features
    features: Dict[str, float] = field(default_factory=dict)

    # Underlying detailed edges
    detail_edges: List[Tuple[str, str]] = field(default_factory=list)


@dataclass
class HierarchicalDAG:
    """
    A DAG built at a specific hierarchy level for planning.

    Contains aggregated nodes and edges appropriate for the planning type.
    """
    planning_type: PlanningType
    site_level: SiteHierarchyLevel
    product_level: ProductHierarchyLevel
    time_bucket: TimeBucketType

    nodes: Dict[str, HierarchicalNode] = field(default_factory=dict)
    edges: List[HierarchicalEdge] = field(default_factory=list)

    # Time dimension
    periods: List[date] = field(default_factory=list)
    horizon_months: int = 6

    # Mappings for aggregation/disaggregation
    leaf_to_aggregate: Dict[str, str] = field(default_factory=dict)  # leaf_id -> aggregate_id
    aggregate_to_leaves: Dict[str, List[str]] = field(default_factory=dict)  # aggregate_id -> [leaf_ids]

    # Powell parameters from parent level (if hierarchical consistency enabled)
    parent_constraints: Optional[Dict[str, Any]] = None

    def to_pyg_data(self) -> 'torch_geometric.data.Data':
        """Convert to PyTorch Geometric Data object"""
        try:
            import torch
            from torch_geometric.data import Data
        except ImportError:
            raise ImportError("PyTorch Geometric required for GNN models")

        # Build node index mapping
        node_ids = list(self.nodes.keys())
        node_to_idx = {nid: idx for idx, nid in enumerate(node_ids)}

        # Extract node features
        feature_keys = list(self.nodes[node_ids[0]].features.keys()) if node_ids else []
        x = torch.zeros(len(node_ids), len(feature_keys) + 5)  # +5 for hierarchy encoding

        for idx, nid in enumerate(node_ids):
            node = self.nodes[nid]
            # Feature values
            for fidx, fkey in enumerate(feature_keys):
                x[idx, fidx] = node.features.get(fkey, 0.0)
            # Hierarchy level encoding (one-hot style)
            x[idx, -5] = float(hash(node.hierarchy_level) % 10) / 10.0
            x[idx, -4] = float(node.gnn_index or idx) / max(len(node_ids), 1)
            x[idx, -3] = len(node.leaf_site_ids)
            x[idx, -2] = len(node.leaf_product_ids)
            x[idx, -1] = len(node.children_ids)

        # Build edge index
        edge_sources = []
        edge_targets = []
        edge_attr_list = []

        for edge in self.edges:
            if edge.source_id in node_to_idx and edge.target_id in node_to_idx:
                edge_sources.append(node_to_idx[edge.source_id])
                edge_targets.append(node_to_idx[edge.target_id])
                edge_attr_list.append([
                    1.0 if edge.edge_type == 'flow' else 0.0,
                    1.0 if edge.edge_type == 'hierarchy' else 0.0,
                    edge.features.get('lead_time', 0.0),
                    edge.features.get('capacity', 100.0),
                    len(edge.detail_edges),
                ])

        edge_index = torch.tensor([edge_sources, edge_targets], dtype=torch.long)
        edge_attr = torch.tensor(edge_attr_list, dtype=torch.float32) if edge_attr_list else torch.zeros(0, 5)

        return Data(x=x, edge_index=edge_index, edge_attr=edge_attr)


class HierarchicalDAGBuilder:
    """
    Builds DAGs at different hierarchy levels for GNN-based planning.

    Usage:
    1. Load planning configuration for the desired planning type
    2. Build hierarchical DAG at the configured levels
    3. Feed DAG to appropriate GNN model (S&OP GraphSAGE or Execution tGNN)

    Example:
        builder = HierarchicalDAGBuilder(db_session, tenant_id=1)
        dag = builder.build_dag(planning_type=PlanningType.SOP)
        pyg_data = dag.to_pyg_data()
        sop_outputs = sop_model(pyg_data)
    """

    def __init__(self, db: Session, tenant_id: int, config_id: Optional[int] = None):
        self.db = db
        self.tenant_id = tenant_id
        self.config_id = config_id

        # Cache hierarchy nodes
        self._site_hierarchy_cache: Dict[str, SiteHierarchyNode] = {}
        self._product_hierarchy_cache: Dict[str, ProductHierarchyNode] = {}

    def get_planning_config(self, planning_type: PlanningType) -> Optional[PlanningHierarchyConfig]:
        """Get planning hierarchy configuration for the specified type"""
        query = select(PlanningHierarchyConfig).where(
            PlanningHierarchyConfig.tenant_id == self.tenant_id,
            PlanningHierarchyConfig.planning_type == planning_type,
            PlanningHierarchyConfig.is_active == True
        )
        if self.config_id:
            query = query.where(PlanningHierarchyConfig.config_id == self.config_id)

        return self.db.execute(query).scalar_one_or_none()

    def build_dag(
        self,
        planning_type: PlanningType,
        as_of_date: Optional[date] = None,
        include_parent_constraints: bool = True
    ) -> HierarchicalDAG:
        """
        Build hierarchical DAG for the specified planning type.

        Args:
            planning_type: Type of planning (S&OP, MPS, MRP, Execution)
            as_of_date: Reference date for time buckets (default: today)
            include_parent_constraints: Whether to include constraints from parent plan

        Returns:
            HierarchicalDAG at the configured hierarchy levels
        """
        config = self.get_planning_config(planning_type)
        if not config:
            # Use defaults if no configuration exists
            config = self._get_default_config(planning_type)

        as_of_date = as_of_date or date.today()

        # Create DAG structure
        dag = HierarchicalDAG(
            planning_type=planning_type,
            site_level=config.site_hierarchy_level,
            product_level=config.product_hierarchy_level,
            time_bucket=config.time_bucket,
            horizon_months=config.horizon_months,
        )

        # Generate time periods
        dag.periods = self._generate_periods(
            as_of_date,
            config.time_bucket,
            config.horizon_months
        )

        # Build site hierarchy nodes
        site_nodes = self._build_site_hierarchy_nodes(config.site_hierarchy_level)

        # Build product hierarchy nodes
        product_nodes = self._build_product_hierarchy_nodes(config.product_hierarchy_level)

        # Create combined nodes (site × product at appropriate level)
        self._create_combined_nodes(dag, site_nodes, product_nodes)

        # Build edges from sourcing rules / lanes
        self._build_edges(dag, site_nodes, product_nodes)

        # Aggregate features to hierarchy level
        self._aggregate_features(dag, as_of_date)

        # Load parent constraints if hierarchical consistency enabled
        if include_parent_constraints and config.parent_planning_type:
            parent_type = PlanningType(config.parent_planning_type)
            dag.parent_constraints = self._load_parent_constraints(
                parent_type,
                dag,
                config.consistency_tolerance
            )

        return dag

    def _get_default_config(self, planning_type: PlanningType) -> PlanningHierarchyConfig:
        """Get default configuration for planning type"""
        defaults = {
            PlanningType.EXECUTION: (SiteHierarchyLevel.SITE, ProductHierarchyLevel.PRODUCT, TimeBucketType.HOUR, 1),
            PlanningType.MRP: (SiteHierarchyLevel.SITE, ProductHierarchyLevel.PRODUCT, TimeBucketType.DAY, 3),
            PlanningType.MPS: (SiteHierarchyLevel.SITE, ProductHierarchyLevel.GROUP, TimeBucketType.WEEK, 6),
            PlanningType.SOP: (SiteHierarchyLevel.COUNTRY, ProductHierarchyLevel.FAMILY, TimeBucketType.MONTH, 24),
            PlanningType.CAPACITY: (SiteHierarchyLevel.SITE, ProductHierarchyLevel.GROUP, TimeBucketType.MONTH, 18),
            PlanningType.INVENTORY: (SiteHierarchyLevel.SITE, ProductHierarchyLevel.GROUP, TimeBucketType.MONTH, 12),
            PlanningType.NETWORK: (SiteHierarchyLevel.REGION, ProductHierarchyLevel.CATEGORY, TimeBucketType.QUARTER, 60),
        }

        site_level, product_level, bucket, horizon = defaults.get(
            planning_type,
            (SiteHierarchyLevel.SITE, ProductHierarchyLevel.PRODUCT, TimeBucketType.WEEK, 6)
        )

        config = PlanningHierarchyConfig(
            tenant_id=self.tenant_id,
            planning_type=planning_type,
            site_hierarchy_level=site_level,
            product_hierarchy_level=product_level,
            time_bucket=bucket,
            horizon_months=horizon,
            name=f"Default {planning_type.value}",
        )
        return config

    def _generate_periods(
        self,
        start_date: date,
        bucket_type: TimeBucketType,
        horizon_months: int
    ) -> List[date]:
        """Generate list of period start dates"""
        periods = []
        current = start_date

        # Calculate end date
        end_date = start_date + timedelta(days=horizon_months * 30)

        while current < end_date:
            periods.append(current)

            if bucket_type == TimeBucketType.HOUR:
                current += timedelta(hours=1)
            elif bucket_type == TimeBucketType.DAY:
                current += timedelta(days=1)
            elif bucket_type == TimeBucketType.WEEK:
                current += timedelta(weeks=1)
            elif bucket_type == TimeBucketType.MONTH:
                # Add roughly a month
                if current.month == 12:
                    current = date(current.year + 1, 1, 1)
                else:
                    current = date(current.year, current.month + 1, 1)
            elif bucket_type == TimeBucketType.QUARTER:
                # Add 3 months
                month = current.month + 3
                year = current.year
                if month > 12:
                    month -= 12
                    year += 1
                current = date(year, month, 1)
            elif bucket_type == TimeBucketType.YEAR:
                current = date(current.year + 1, 1, 1)

        return periods

    def _build_site_hierarchy_nodes(
        self,
        target_level: SiteHierarchyLevel
    ) -> Dict[str, HierarchicalNode]:
        """Build site hierarchy nodes at target level"""
        nodes: Dict[str, HierarchicalNode] = {}

        # First try to load from SiteHierarchyNode table
        hierarchy_nodes = self.db.execute(
            select(SiteHierarchyNode).where(
                SiteHierarchyNode.tenant_id == self.tenant_id,
                SiteHierarchyNode.hierarchy_level == target_level
            )
        ).scalars().all()

        if hierarchy_nodes:
            for hnode in hierarchy_nodes:
                node = HierarchicalNode(
                    id=f"site_{hnode.code}",
                    name=hnode.name,
                    node_type='site',
                    hierarchy_level=target_level.value,
                    hierarchy_path=hnode.hierarchy_path,
                    parent_id=f"site_{hnode.parent_id}" if hnode.parent_id else None,
                    leaf_site_ids=self._get_leaf_sites(hnode),
                )
                nodes[node.id] = node
                self._site_hierarchy_cache[hnode.code] = hnode
        else:
            # Fall back to building from Site/Geography directly
            if target_level == SiteHierarchyLevel.SITE:
                # Load sites from SupplyChainConfig
                if self.config_id:
                    config_nodes = self.db.execute(
                        select(Node).where(Node.config_id == self.config_id)
                    ).scalars().all()
                    for cnode in config_nodes:
                        node = HierarchicalNode(
                            id=f"site_{cnode.id}",
                            name=cnode.name,
                            node_type='site',
                            hierarchy_level=target_level.value,
                            hierarchy_path=f"/{cnode.id}",
                            leaf_site_ids=[str(cnode.id)],
                        )
                        nodes[node.id] = node

        return nodes

    def _build_product_hierarchy_nodes(
        self,
        target_level: ProductHierarchyLevel
    ) -> Dict[str, HierarchicalNode]:
        """Build product hierarchy nodes at target level"""
        nodes: Dict[str, HierarchicalNode] = {}

        # First try to load from ProductHierarchyNode table
        hierarchy_nodes = self.db.execute(
            select(ProductHierarchyNode).where(
                ProductHierarchyNode.tenant_id == self.tenant_id,
                ProductHierarchyNode.hierarchy_level == target_level
            )
        ).scalars().all()

        if hierarchy_nodes:
            for hnode in hierarchy_nodes:
                node = HierarchicalNode(
                    id=f"product_{hnode.code}",
                    name=hnode.name,
                    node_type='product',
                    hierarchy_level=target_level.value,
                    hierarchy_path=hnode.hierarchy_path,
                    parent_id=f"product_{hnode.parent_id}" if hnode.parent_id else None,
                    leaf_product_ids=self._get_leaf_products(hnode),
                )
                nodes[node.id] = node
                self._product_hierarchy_cache[hnode.code] = hnode
        else:
            # Fall back to ProductHierarchy or Product
            if target_level == ProductHierarchyLevel.PRODUCT:
                # Load products from Product table (linked to config)
                products = self.db.execute(
                    select(Product).where(Product.config_id == self.config_id)
                ).scalars().all() if self.config_id else []

                for prod in products:
                    node = HierarchicalNode(
                        id=f"product_{prod.id}",
                        name=prod.description or prod.id,
                        node_type='product',
                        hierarchy_level=target_level.value,
                        hierarchy_path=f"/{prod.product_group_id or 'default'}/{prod.id}",
                        leaf_product_ids=[prod.id],
                    )
                    nodes[node.id] = node
            else:
                # Load from ProductHierarchy at appropriate level
                level_map = {
                    ProductHierarchyLevel.CATEGORY: 1,
                    ProductHierarchyLevel.FAMILY: 2,
                    ProductHierarchyLevel.GROUP: 3,
                }
                target_depth = level_map.get(target_level, 3)

                hierarchies = self.db.execute(
                    select(ProductHierarchy).where(ProductHierarchy.level == target_depth)
                ).scalars().all()

                for ph in hierarchies:
                    node = HierarchicalNode(
                        id=f"product_{ph.id}",
                        name=ph.description or ph.id,
                        node_type='product',
                        hierarchy_level=target_level.value,
                        hierarchy_path=f"/{ph.id}",
                        parent_id=f"product_{ph.parent_product_group_id}" if ph.parent_product_group_id else None,
                        leaf_product_ids=self._get_products_in_hierarchy(ph.id),
                    )
                    nodes[node.id] = node

        return nodes

    def _create_combined_nodes(
        self,
        dag: HierarchicalDAG,
        site_nodes: Dict[str, HierarchicalNode],
        product_nodes: Dict[str, HierarchicalNode]
    ):
        """Create combined site×product nodes for the DAG"""
        idx = 0
        for site_id, site_node in site_nodes.items():
            for product_id, product_node in product_nodes.items():
                combined_id = f"{site_id}|{product_id}"

                combined = HierarchicalNode(
                    id=combined_id,
                    name=f"{site_node.name} × {product_node.name}",
                    node_type='combined',
                    hierarchy_level=f"{site_node.hierarchy_level}_{product_node.hierarchy_level}",
                    hierarchy_path=f"{site_node.hierarchy_path}|{product_node.hierarchy_path}",
                    leaf_site_ids=site_node.leaf_site_ids,
                    leaf_product_ids=product_node.leaf_product_ids,
                    gnn_index=idx,
                )

                dag.nodes[combined_id] = combined
                idx += 1

                # Build mapping for aggregation/disaggregation
                for leaf_site in site_node.leaf_site_ids:
                    for leaf_product in product_node.leaf_product_ids:
                        leaf_id = f"site_{leaf_site}|product_{leaf_product}"
                        dag.leaf_to_aggregate[leaf_id] = combined_id

                        if combined_id not in dag.aggregate_to_leaves:
                            dag.aggregate_to_leaves[combined_id] = []
                        dag.aggregate_to_leaves[combined_id].append(leaf_id)

    def _build_edges(
        self,
        dag: HierarchicalDAG,
        site_nodes: Dict[str, HierarchicalNode],
        product_nodes: Dict[str, HierarchicalNode]
    ):
        """Build edges between combined nodes based on sourcing rules / lanes"""
        # Load sourcing rules or lanes
        if self.config_id:
            lanes = self.db.execute(
                select(TransportationLane).where(TransportationLane.config_id == self.config_id)
            ).scalars().all()

            for lane in lanes:
                from_site = f"site_{lane.source_node_id}"
                to_site = f"site_{lane.target_node_id}"

                # Find which aggregate nodes these belong to
                from_aggregates = [
                    nid for nid, node in dag.nodes.items()
                    if str(lane.source_node_id) in node.leaf_site_ids
                ]
                to_aggregates = [
                    nid for nid, node in dag.nodes.items()
                    if str(lane.target_node_id) in node.leaf_site_ids
                ]

                for from_agg in from_aggregates:
                    for to_agg in to_aggregates:
                        if from_agg != to_agg:
                            # Check if edge already exists
                            existing = [e for e in dag.edges if e.source_id == from_agg and e.target_id == to_agg]
                            if existing:
                                existing[0].detail_edges.append((str(lane.source_node_id), str(lane.target_node_id)))
                            else:
                                edge = HierarchicalEdge(
                                    source_id=from_agg,
                                    target_id=to_agg,
                                    edge_type='flow',
                                    features={
                                        'lead_time': lane.lead_time or 0,
                                        'capacity': 1000.0,  # Default capacity
                                    },
                                    detail_edges=[(str(lane.source_node_id), str(lane.target_node_id))],
                                )
                                dag.edges.append(edge)

    def _aggregate_features(self, dag: HierarchicalDAG, as_of_date: date):
        """Aggregate features from leaf level to hierarchy level"""
        for node_id, node in dag.nodes.items():
            # Aggregate inventory
            total_inventory = 0.0
            total_demand = 0.0

            for leaf_site in node.leaf_site_ids:
                for leaf_product in node.leaf_product_ids:
                    # Query inventory levels
                    inv = self.db.execute(
                        select(func.sum(InvLevel.on_hand_qty)).where(
                            InvLevel.site_id == leaf_site,
                            InvLevel.product_id == leaf_product,
                            InvLevel.inventory_date <= as_of_date
                        )
                    ).scalar()
                    if inv:
                        total_inventory += float(inv)

            node.features['inventory'] = total_inventory
            node.features['demand'] = total_demand
            node.features['num_leaf_sites'] = len(node.leaf_site_ids)
            node.features['num_leaf_products'] = len(node.leaf_product_ids)

    def _load_parent_constraints(
        self,
        parent_type: PlanningType,
        child_dag: HierarchicalDAG,
        tolerance: float
    ) -> Dict[str, Any]:
        """Load constraints from parent planning level (Powell hierarchical consistency)"""
        # Query aggregated plans from parent level
        parent_plans = self.db.execute(
            select(AggregatedPlan).where(
                AggregatedPlan.tenant_id == self.tenant_id,
                AggregatedPlan.status == 'approved'
            ).order_by(AggregatedPlan.period_start.desc())
        ).scalars().all()

        constraints = {
            'type': parent_type.value,
            'tolerance': tolerance,
            'bounds': {},
        }

        for plan in parent_plans[:10]:  # Last 10 periods
            key = f"{plan.site_node_id}|{plan.product_node_id}"
            constraints['bounds'][key] = {
                'demand_min': plan.demand_quantity * (1 - tolerance),
                'demand_max': plan.demand_quantity * (1 + tolerance),
                'production_min': plan.production_quantity * (1 - tolerance),
                'production_max': plan.production_quantity * (1 + tolerance),
                'safety_stock_multiplier': plan.safety_stock_multiplier,
                'criticality_score': plan.criticality_score,
            }

        return constraints

    def _get_leaf_sites(self, node: SiteHierarchyNode) -> List[str]:
        """Get all leaf site IDs under a hierarchy node"""
        if node.site_id:
            return [node.site_id]

        # Recursively get children
        children = self.db.execute(
            select(SiteHierarchyNode).where(
                SiteHierarchyNode.parent_id == node.id
            )
        ).scalars().all()

        leaves = []
        for child in children:
            leaves.extend(self._get_leaf_sites(child))

        return leaves

    def _get_leaf_products(self, node: ProductHierarchyNode) -> List[str]:
        """Get all leaf product IDs under a hierarchy node"""
        if node.product_id:
            return [node.product_id]

        # Recursively get children
        children = self.db.execute(
            select(ProductHierarchyNode).where(
                ProductHierarchyNode.parent_id == node.id
            )
        ).scalars().all()

        leaves = []
        for child in children:
            leaves.extend(self._get_leaf_products(child))

        return leaves

    def _get_products_in_hierarchy(self, hierarchy_id: str) -> List[str]:
        """Get all product IDs in a product hierarchy"""
        products = self.db.execute(
            select(Product.id).where(Product.product_group_id == hierarchy_id)
        ).scalars().all()
        return list(products)


# ============================================================================
# Convenience Functions
# ============================================================================

def build_sop_dag(
    db: Session,
    tenant_id: int,
    config_id: Optional[int] = None,
    as_of_date: Optional[date] = None
) -> HierarchicalDAG:
    """Build DAG for S&OP planning (monthly buckets, family × country level)"""
    builder = HierarchicalDAGBuilder(db, tenant_id, config_id)
    return builder.build_dag(PlanningType.SOP, as_of_date)


def build_mps_dag(
    db: Session,
    tenant_id: int,
    config_id: Optional[int] = None,
    as_of_date: Optional[date] = None
) -> HierarchicalDAG:
    """Build DAG for MPS planning (weekly buckets, group × site level)"""
    builder = HierarchicalDAGBuilder(db, tenant_id, config_id)
    return builder.build_dag(PlanningType.MPS, as_of_date)


def build_execution_dag(
    db: Session,
    tenant_id: int,
    config_id: Optional[int] = None,
    as_of_date: Optional[date] = None
) -> HierarchicalDAG:
    """Build DAG for Execution (hourly buckets, SKU × site level)"""
    builder = HierarchicalDAGBuilder(db, tenant_id, config_id)
    return builder.build_dag(PlanningType.EXECUTION, as_of_date)
