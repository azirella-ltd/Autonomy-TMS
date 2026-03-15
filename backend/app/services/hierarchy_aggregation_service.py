"""
Hierarchy Aggregation Service

Provides data aggregation and disaggregation across planning hierarchies:
- Aggregate detailed data (SKU × Site) to higher levels (Family × Country)
- Disaggregate plans from higher levels back to detailed levels
- Build GraphSAGE DAGs at appropriate hierarchy levels

This service enables planning at different granularity levels while maintaining
consistency per Powell's hierarchical framework.
"""

from typing import Dict, List, Optional, Tuple, Any
from datetime import date, datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import logging
from collections import defaultdict

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.planning_hierarchy import (
    PlanningHierarchyConfig,
    SiteHierarchyNode,
    ProductHierarchyNode,
    AggregatedPlan,
    PlanningType,
    SiteHierarchyLevel,
    ProductHierarchyLevel,
    TimeBucketType
)
from app.models.sc_entities import (
    Site, Product, ProductHierarchy, Geography,
    Forecast, InvLevel, InvPolicy
)
from app.models.supply_chain_config import SupplyChainConfig, Site, TransportationLane, Item

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class AggregatedNode:
    """Represents an aggregated node in the hierarchical DAG."""
    id: str
    site_level: SiteHierarchyLevel
    product_level: ProductHierarchyLevel
    site_code: str
    product_code: str
    name: str

    # Aggregated metrics
    total_demand: float = 0.0
    total_inventory: float = 0.0
    total_capacity: float = 0.0
    avg_lead_time: float = 0.0

    # Statistical measures
    demand_mean: float = 0.0
    demand_std: float = 0.0
    demand_p10: float = 0.0
    demand_p50: float = 0.0
    demand_p90: float = 0.0

    # Member details (for disaggregation)
    member_sites: List[str] = field(default_factory=list)
    member_products: List[str] = field(default_factory=list)
    member_weights: Dict[str, float] = field(default_factory=dict)  # For disaggregation

    # GNN features
    node_features: Dict[str, float] = field(default_factory=dict)


@dataclass
class AggregatedEdge:
    """Represents an aggregated edge (lane) in the hierarchical DAG."""
    source_id: str
    target_id: str

    # Aggregated metrics
    total_flow: float = 0.0
    avg_lead_time: float = 0.0
    avg_cost: float = 0.0

    # Member details
    member_lanes: List[int] = field(default_factory=list)

    # Edge features
    edge_features: Dict[str, float] = field(default_factory=dict)


@dataclass
class HierarchicalPlanningDAG:
    """DAG built at a specific hierarchy level for GNN processing."""
    planning_type: PlanningType
    site_level: SiteHierarchyLevel
    product_level: ProductHierarchyLevel
    time_bucket: TimeBucketType
    as_of_date: date

    nodes: Dict[str, AggregatedNode] = field(default_factory=dict)
    edges: List[AggregatedEdge] = field(default_factory=list)

    # Parent constraints (from higher-level plans)
    parent_constraints: Optional[Dict[str, Any]] = None

    def get_node_features_tensor(self) -> List[List[float]]:
        """Get node features as tensor for GNN input."""
        features = []
        for node_id in sorted(self.nodes.keys()):
            node = self.nodes[node_id]
            features.append([
                node.total_demand,
                node.total_inventory,
                node.total_capacity,
                node.avg_lead_time,
                node.demand_mean,
                node.demand_std
            ])
        return features

    def get_edge_index(self) -> Tuple[List[int], List[int]]:
        """Get edge indices for GNN input."""
        node_ids = sorted(self.nodes.keys())
        node_to_idx = {nid: idx for idx, nid in enumerate(node_ids)}

        sources = []
        targets = []
        for edge in self.edges:
            if edge.source_id in node_to_idx and edge.target_id in node_to_idx:
                sources.append(node_to_idx[edge.source_id])
                targets.append(node_to_idx[edge.target_id])

        return sources, targets


# ============================================================================
# Hierarchy Aggregation Service
# ============================================================================

class HierarchyAggregationService:
    """
    Service for aggregating and disaggregating data across planning hierarchies.

    Key responsibilities:
    1. Build site and product hierarchy trees
    2. Aggregate detailed data to higher hierarchy levels
    3. Build DAGs at appropriate hierarchy levels for GNN
    4. Disaggregate plans from higher levels to detailed levels
    """

    def __init__(self, db: AsyncSession, tenant_id: int, config_id: Optional[int] = None):
        self.db = db
        self.tenant_id = tenant_id
        self.config_id = config_id

        # Cached hierarchy data
        self._site_tree: Dict[str, Dict] = {}
        self._product_tree: Dict[str, Dict] = {}
        self._site_to_parent: Dict[str, Dict[SiteHierarchyLevel, str]] = {}
        self._product_to_parent: Dict[str, Dict[ProductHierarchyLevel, str]] = {}

    async def load_hierarchies(self):
        """Load and cache site and product hierarchy structures."""
        await self._load_site_hierarchy()
        await self._load_product_hierarchy()

    async def _load_site_hierarchy(self):
        """Load site hierarchy from database."""
        # Load site hierarchy nodes
        result = await self.db.execute(
            select(SiteHierarchyNode).where(
                SiteHierarchyNode.tenant_id == self.tenant_id
            ).order_by(SiteHierarchyNode.depth)
        )
        nodes = result.scalars().all()

        # Build tree structure
        for node in nodes:
            self._site_tree[node.code] = {
                'id': node.id,
                'code': node.code,
                'name': node.name,
                'level': node.hierarchy_level,
                'parent_id': node.parent_id,
                'path': node.hierarchy_path,
                'children': []
            }

        # Build parent relationships and children
        for node in nodes:
            if node.parent_id:
                parent = next(
                    (n for n in nodes if n.id == node.parent_id),
                    None
                )
                if parent:
                    self._site_tree[parent.code]['children'].append(node.code)

            # Build lookup for each level
            path_parts = node.hierarchy_path.split('/')
            self._site_to_parent[node.code] = {}

            for i, level in enumerate([
                SiteHierarchyLevel.COMPANY,
                SiteHierarchyLevel.REGION,
                SiteHierarchyLevel.COUNTRY,
                SiteHierarchyLevel.STATE,
                SiteHierarchyLevel.SITE
            ]):
                if i < len(path_parts):
                    self._site_to_parent[node.code][level] = path_parts[i]

    async def _load_product_hierarchy(self):
        """Load product hierarchy from database."""
        # Load product hierarchy nodes
        result = await self.db.execute(
            select(ProductHierarchyNode).where(
                ProductHierarchyNode.tenant_id == self.tenant_id
            ).order_by(ProductHierarchyNode.depth)
        )
        nodes = result.scalars().all()

        # Build tree structure
        for node in nodes:
            self._product_tree[node.code] = {
                'id': node.id,
                'code': node.code,
                'name': node.name,
                'level': node.hierarchy_level,
                'parent_id': node.parent_id,
                'path': node.hierarchy_path,
                'children': [],
                'split_factors': node.demand_split_factors or {}
            }

        # Build parent relationships
        for node in nodes:
            if node.parent_id:
                parent = next(
                    (n for n in nodes if n.id == node.parent_id),
                    None
                )
                if parent:
                    self._product_tree[parent.code]['children'].append(node.code)

            # Build lookup for each level
            path_parts = node.hierarchy_path.split('/')
            self._product_to_parent[node.code] = {}

            for i, level in enumerate([
                ProductHierarchyLevel.CATEGORY,
                ProductHierarchyLevel.FAMILY,
                ProductHierarchyLevel.GROUP,
                ProductHierarchyLevel.PRODUCT
            ]):
                if i < len(path_parts):
                    self._product_to_parent[node.code][level] = path_parts[i]

    def get_site_parent(self, site_code: str, target_level: SiteHierarchyLevel) -> Optional[str]:
        """Get the parent at a specific hierarchy level for a site."""
        if site_code in self._site_to_parent:
            return self._site_to_parent[site_code].get(target_level)
        return None

    def get_product_parent(self, product_code: str, target_level: ProductHierarchyLevel) -> Optional[str]:
        """Get the parent at a specific hierarchy level for a product."""
        if product_code in self._product_to_parent:
            return self._product_to_parent[product_code].get(target_level)
        return None

    def get_sites_at_level(self, level: SiteHierarchyLevel) -> List[str]:
        """Get all site codes at a specific hierarchy level."""
        return [
            code for code, data in self._site_tree.items()
            if data['level'] == level
        ]

    def get_products_at_level(self, level: ProductHierarchyLevel) -> List[str]:
        """Get all product codes at a specific hierarchy level."""
        return [
            code for code, data in self._product_tree.items()
            if data['level'] == level
        ]

    async def build_dag_for_planning_type(
        self,
        planning_type: PlanningType,
        as_of_date: Optional[date] = None,
        parent_constraints: Optional[Dict[str, Any]] = None
    ) -> HierarchicalPlanningDAG:
        """
        Build a DAG at the appropriate hierarchy level for the planning type.

        Args:
            planning_type: Type of planning (SOP, MPS, MRP, etc.)
            as_of_date: Reference date for the plan
            parent_constraints: Constraints from higher-level plan

        Returns:
            HierarchicalPlanningDAG ready for GNN processing
        """
        # Get planning configuration
        config = await self._get_planning_config(planning_type)
        if not config:
            raise ValueError(f"No planning configuration found for {planning_type.value}")

        if as_of_date is None:
            as_of_date = date.today()

        # Ensure hierarchies are loaded
        if not self._site_tree:
            await self.load_hierarchies()

        # Build DAG at configured hierarchy level
        dag = HierarchicalPlanningDAG(
            planning_type=planning_type,
            site_level=config.site_hierarchy_level,
            product_level=config.product_hierarchy_level,
            time_bucket=config.time_bucket,
            as_of_date=as_of_date,
            parent_constraints=parent_constraints
        )

        # Build nodes by aggregating to the target hierarchy level
        await self._build_aggregated_nodes(dag, config)

        # Build edges by aggregating lanes
        await self._build_aggregated_edges(dag, config)

        return dag

    async def _get_planning_config(self, planning_type: PlanningType) -> Optional[PlanningHierarchyConfig]:
        """Get the planning hierarchy configuration for a planning type."""
        result = await self.db.execute(
            select(PlanningHierarchyConfig).where(
                and_(
                    PlanningHierarchyConfig.tenant_id == self.tenant_id,
                    PlanningHierarchyConfig.planning_type == planning_type,
                    PlanningHierarchyConfig.is_active == True
                )
            )
        )
        return result.scalar_one_or_none()

    async def _build_aggregated_nodes(
        self,
        dag: HierarchicalPlanningDAG,
        config: PlanningHierarchyConfig
    ):
        """Build aggregated nodes at the target hierarchy level."""
        target_site_level = config.site_hierarchy_level
        target_product_level = config.product_hierarchy_level

        # Get detailed data (SKU × Site level)
        detailed_data = await self._get_detailed_data(dag.as_of_date, config.horizon_months)

        # Aggregate to target level
        aggregated: Dict[Tuple[str, str], AggregatedNode] = {}

        for (site_code, product_code), data in detailed_data.items():
            # Get parent codes at target level
            parent_site = self.get_site_parent(site_code, target_site_level)
            parent_product = self.get_product_parent(product_code, target_product_level)

            if not parent_site or not parent_product:
                continue

            key = (parent_site, parent_product)

            if key not in aggregated:
                aggregated[key] = AggregatedNode(
                    id=f"{parent_site}_{parent_product}",
                    site_level=target_site_level,
                    product_level=target_product_level,
                    site_code=parent_site,
                    product_code=parent_product,
                    name=f"{parent_site} × {parent_product}"
                )

            node = aggregated[key]

            # Aggregate metrics
            node.total_demand += data.get('demand', 0)
            node.total_inventory += data.get('inventory', 0)
            node.total_capacity += data.get('capacity', 0)

            # Track members for disaggregation
            if site_code not in node.member_sites:
                node.member_sites.append(site_code)
            if product_code not in node.member_products:
                node.member_products.append(product_code)

            # Calculate weight for disaggregation (based on demand proportion)
            member_key = f"{site_code}_{product_code}"
            node.member_weights[member_key] = data.get('demand', 1)

        # Calculate statistical measures and normalize weights
        for node in aggregated.values():
            # Normalize disaggregation weights
            total_weight = sum(node.member_weights.values())
            if total_weight > 0:
                node.member_weights = {
                    k: v / total_weight
                    for k, v in node.member_weights.items()
                }

            # Calculate average lead time
            member_count = len(node.member_sites) * len(node.member_products)
            if member_count > 0:
                node.avg_lead_time = node.avg_lead_time / member_count if node.avg_lead_time else 7.0

            # Set demand statistics (would be calculated from historical data)
            node.demand_mean = node.total_demand
            node.demand_p50 = node.total_demand
            node.demand_p10 = node.total_demand * 0.7
            node.demand_p90 = node.total_demand * 1.3

            # Compute GNN node features
            node.node_features = {
                'demand': node.total_demand,
                'inventory': node.total_inventory,
                'capacity': node.total_capacity,
                'lead_time': node.avg_lead_time,
                'member_count': member_count
            }

            dag.nodes[node.id] = node

    async def _build_aggregated_edges(
        self,
        dag: HierarchicalPlanningDAG,
        config: PlanningHierarchyConfig
    ):
        """Build aggregated edges (lanes) at the target hierarchy level."""
        target_site_level = config.site_hierarchy_level

        # Load detailed transportation lanes
        if self.config_id:
            result = await self.db.execute(
                select(TransportationLane).where(TransportationLane.config_id == self.config_id)
            )
            lanes = result.scalars().all()
        else:
            return

        # Aggregate lanes to target level
        aggregated_edges: Dict[Tuple[str, str], AggregatedEdge] = {}

        for lane in lanes:
            # Get source and target node codes
            source_node = await self._get_node_by_id(lane.source_node_id)
            target_node = await self._get_node_by_id(lane.target_node_id)

            if not source_node or not target_node:
                continue

            # Get parent site codes at target level
            source_parent = self.get_site_parent(source_node.name, target_site_level)
            target_parent = self.get_site_parent(target_node.name, target_site_level)

            if not source_parent or not target_parent:
                continue

            # Skip self-loops at aggregated level
            if source_parent == target_parent:
                continue

            key = (source_parent, target_parent)

            if key not in aggregated_edges:
                aggregated_edges[key] = AggregatedEdge(
                    source_id=source_parent,
                    target_id=target_parent
                )

            edge = aggregated_edges[key]
            edge.member_lanes.append(lane.id)
            edge.total_flow += 1  # Would be actual flow data
            edge.avg_lead_time += lane.lead_time if lane.lead_time else 0

        # Calculate averages
        for edge in aggregated_edges.values():
            lane_count = len(edge.member_lanes)
            if lane_count > 0:
                edge.avg_lead_time /= lane_count

            edge.edge_features = {
                'flow': edge.total_flow,
                'lead_time': edge.avg_lead_time,
                'lane_count': lane_count
            }

            # Only add edges where both nodes exist in DAG
            source_key = f"{edge.source_id}_{list(dag.nodes.values())[0].product_code if dag.nodes else ''}"
            target_key = f"{edge.target_id}_{list(dag.nodes.values())[0].product_code if dag.nodes else ''}"

            dag.edges.append(edge)

    async def _get_node_by_id(self, node_id: int) -> Optional[Site]:
        """Get a supply chain node by ID."""
        result = await self.db.execute(
            select(Site).where(Site.id == node_id)
        )
        return result.scalar_one_or_none()

    async def _get_detailed_data(
        self,
        as_of_date: date,
        horizon_months: int
    ) -> Dict[Tuple[str, str], Dict[str, float]]:
        """
        Get detailed data at SKU × Site level.

        Returns dict of (site_code, product_code) -> {demand, inventory, capacity, ...}
        """
        detailed: Dict[Tuple[str, str], Dict[str, float]] = {}

        # Load inventory levels
        inv_result = await self.db.execute(
            select(InvLevel).where(
                InvLevel.connection_id == self.tenant_id  # Using tenant_id as connection
            )
        )
        inv_levels = inv_result.scalars().all()

        for inv in inv_levels:
            key = (inv.site_id or 'UNKNOWN', inv.product_id or 'UNKNOWN')
            if key not in detailed:
                detailed[key] = {'demand': 0, 'inventory': 0, 'capacity': 0}
            detailed[key]['inventory'] = inv.on_hand_inventory or 0

        # Load forecasts
        end_date = as_of_date + timedelta(days=horizon_months * 30)
        forecast_result = await self.db.execute(
            select(Forecast).where(
                and_(
                    Forecast.forecast_date >= as_of_date,
                    Forecast.forecast_date <= end_date
                )
            )
        )
        forecasts = forecast_result.scalars().all()

        for fc in forecasts:
            key = (fc.site_id or 'UNKNOWN', fc.product_id or 'UNKNOWN')
            if key not in detailed:
                detailed[key] = {'demand': 0, 'inventory': 0, 'capacity': 0}
            detailed[key]['demand'] += fc.forecast_quantity or 0

        # If no data, load from supply chain config nodes
        if not detailed and self.config_id:
            nodes_result = await self.db.execute(
                select(Site).where(Site.config_id == self.config_id)
            )
            nodes = nodes_result.scalars().all()

            items_result = await self.db.execute(
                select(Item).where(Item.config_id == self.config_id)
            )
            items = items_result.scalars().all()

            for node in nodes:
                for item in items:
                    key = (node.name, item.name)
                    detailed[key] = {
                        'demand': 100,  # Default demand
                        'inventory': node.initial_inventory or 0,
                        'capacity': node.capacity or 1000
                    }

        return detailed

    async def disaggregate_plan(
        self,
        aggregated_plan: Dict[str, float],
        dag: HierarchicalPlanningDAG,
        target_site_level: SiteHierarchyLevel = SiteHierarchyLevel.SITE,
        target_product_level: ProductHierarchyLevel = ProductHierarchyLevel.PRODUCT
    ) -> Dict[Tuple[str, str], float]:
        """
        Disaggregate a plan from higher hierarchy level to detailed level.

        Args:
            aggregated_plan: Plan values at aggregated level {node_id: value}
            dag: The DAG used for aggregation (contains disaggregation weights)
            target_site_level: Target site hierarchy level
            target_product_level: Target product hierarchy level

        Returns:
            Disaggregated plan at detailed level {(site, product): value}
        """
        detailed_plan: Dict[Tuple[str, str], float] = {}

        for node_id, plan_value in aggregated_plan.items():
            if node_id not in dag.nodes:
                continue

            node = dag.nodes[node_id]

            # Distribute value using stored weights
            for member_key, weight in node.member_weights.items():
                parts = member_key.split('_')
                if len(parts) >= 2:
                    site_code = parts[0]
                    product_code = '_'.join(parts[1:])
                    detailed_plan[(site_code, product_code)] = plan_value * weight

        return detailed_plan


# ============================================================================
# Convenience Functions
# ============================================================================

async def build_sop_dag(
    db: AsyncSession,
    tenant_id: int,
    config_id: Optional[int] = None,
    as_of_date: Optional[date] = None
) -> HierarchicalPlanningDAG:
    """Build a DAG at S&OP level (Country × Family, Monthly)."""
    service = HierarchyAggregationService(db, tenant_id, config_id)
    await service.load_hierarchies()
    return await service.build_dag_for_planning_type(PlanningType.SOP, as_of_date)


async def build_mps_dag(
    db: AsyncSession,
    tenant_id: int,
    config_id: Optional[int] = None,
    as_of_date: Optional[date] = None,
    sop_constraints: Optional[Dict[str, Any]] = None
) -> HierarchicalPlanningDAG:
    """Build a DAG at MPS level (Site × Group, Weekly)."""
    service = HierarchyAggregationService(db, tenant_id, config_id)
    await service.load_hierarchies()
    return await service.build_dag_for_planning_type(
        PlanningType.MPS, as_of_date, parent_constraints=sop_constraints
    )


async def build_execution_dag(
    db: AsyncSession,
    tenant_id: int,
    config_id: Optional[int] = None,
    as_of_date: Optional[date] = None,
    mps_constraints: Optional[Dict[str, Any]] = None
) -> HierarchicalPlanningDAG:
    """Build a DAG at Execution level (Site × SKU, Hourly)."""
    service = HierarchyAggregationService(db, tenant_id, config_id)
    await service.load_hierarchies()
    return await service.build_dag_for_planning_type(
        PlanningType.EXECUTION, as_of_date, parent_constraints=mps_constraints
    )
