"""
Analytics Service for SC Phase 3+ Features

This service computes analytics metrics for:
- Order aggregation (Sprint 3)
- Capacity constraints (Sprint 2)
- Policy effectiveness
- Comparative analysis

Usage:
    service = AnalyticsService(db)
    metrics = await service.get_aggregation_metrics(scenario_id)
"""

from typing import Dict, List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scenario import Scenario

# Aliases for backwards compatibility
Game = Scenario
from app.models.sc_planning import (
    AggregatedOrder,
    ProductionCapacity,
    InboundOrderLine,
    OrderAggregationPolicy
)


class AnalyticsService:
    """
    Service for computing analytics metrics from SC execution data
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize analytics service

        Args:
            db: Database session
        """
        self.db = db

    # ============================================================================
    # AGGREGATION METRICS
    # ============================================================================

    async def get_aggregation_metrics(self, scenario_id: int) -> Dict:
        """
        Get order aggregation metrics for a game

        Args:
            scenario_id: Game ID

        Returns:
            Dictionary with aggregation metrics:
            {
                'scenario_id': int,
                'total_rounds': int,
                'aggregation_summary': {...},
                'by_round': [...],
                'by_site_pair': [...]
            }
        """
        # Get all aggregated orders
        result = await self.db.execute(
            select(AggregatedOrder)
            .filter(AggregatedOrder.scenario_id == scenario_id)
            .order_by(AggregatedOrder.round_number)
        )
        agg_orders = result.scalars().all()

        if not agg_orders:
            return {
                'scenario_id': scenario_id,
                'total_rounds': 0,
                'aggregation_summary': {
                    'total_orders_aggregated': 0,
                    'total_groups_created': 0,
                    'total_cost_savings': 0.0,
                    'avg_cost_savings_per_round': 0.0
                },
                'by_round': [],
                'by_site_pair': []
            }

        # Calculate summary
        total_orders_aggregated = sum(o.num_orders_aggregated for o in agg_orders)
        total_groups_created = len(agg_orders)
        total_cost_savings = sum(o.fixed_cost_saved or 0.0 for o in agg_orders)

        max_round = max(o.round_number for o in agg_orders)
        avg_cost_savings_per_round = total_cost_savings / max_round if max_round > 0 else 0.0

        # Group by round
        by_round = {}
        for order in agg_orders:
            round_num = order.round_number
            if round_num not in by_round:
                by_round[round_num] = {
                    'round': round_num,
                    'orders_aggregated': 0,
                    'groups_created': 0,
                    'cost_savings': 0.0,
                    'quantity_adjustments': []
                }

            by_round[round_num]['orders_aggregated'] += order.num_orders_aggregated
            by_round[round_num]['groups_created'] += 1
            by_round[round_num]['cost_savings'] += order.fixed_cost_saved or 0.0

            # Get site names
            from_site = await self._get_site_name(order.from_site_id)
            to_site = await self._get_site_name(order.to_site_id)

            adjustment_reason = []
            if order.total_quantity != order.adjusted_quantity:
                if order.adjusted_quantity > order.total_quantity:
                    adjustment_reason.append('increased')
                else:
                    adjustment_reason.append('decreased')

            by_round[round_num]['quantity_adjustments'].append({
                'from_site': from_site,
                'to_site': to_site,
                'total_quantity': float(order.total_quantity or 0),
                'adjusted_quantity': float(order.adjusted_quantity or 0),
                'reason': ','.join(adjustment_reason) if adjustment_reason else 'none'
            })

        # Group by site pair
        site_pairs = {}
        for order in agg_orders:
            from_site = await self._get_site_name(order.from_site_id)
            to_site = await self._get_site_name(order.to_site_id)
            key = f"{from_site}→{to_site}"

            if key not in site_pairs:
                site_pairs[key] = {
                    'from_site': from_site,
                    'to_site': to_site,
                    'total_aggregated': 0,
                    'total_savings': 0.0,
                    'adjustments': []
                }

            site_pairs[key]['total_aggregated'] += order.num_orders_aggregated
            site_pairs[key]['total_savings'] += order.fixed_cost_saved or 0.0
            site_pairs[key]['adjustments'].append(
                float(order.adjusted_quantity - order.total_quantity)
            )

        # Calculate average adjustment
        for pair in site_pairs.values():
            adjustments = pair.pop('adjustments')
            pair['avg_quantity_adjustment'] = (
                sum(adjustments) / len(adjustments) if adjustments else 0.0
            )

        return {
            'scenario_id': scenario_id,
            'total_rounds': max_round,
            'aggregation_summary': {
                'total_orders_aggregated': total_orders_aggregated,
                'total_groups_created': total_groups_created,
                'total_cost_savings': round(total_cost_savings, 2),
                'avg_cost_savings_per_round': round(avg_cost_savings_per_round, 2)
            },
            'by_round': sorted(by_round.values(), key=lambda x: x['round']),
            'by_site_pair': list(site_pairs.values())
        }

    # ============================================================================
    # CAPACITY METRICS
    # ============================================================================

    async def get_capacity_metrics(self, scenario_id: int) -> Dict:
        """
        Get capacity constraint metrics for a game

        Args:
            scenario_id: Game ID

        Returns:
            Dictionary with capacity metrics
        """
        # Get game and config
        game = await self.db.get(Game, scenario_id)
        if not game:
            return {'error': 'Game not found'}

        # Get all capacity constraints for this game's config
        result = await self.db.execute(
            select(ProductionCapacity).filter(
                ProductionCapacity.config_id == game.supply_chain_config_id,
                ProductionCapacity.group_id == game.group_id
            )
        )
        capacities = result.scalars().all()

        if not capacities:
            return {
                'scenario_id': scenario_id,
                'capacity_summary': {
                    'sites_with_capacity': 0,
                    'total_capacity': 0.0,
                    'avg_utilization': 0.0,
                    'orders_queued': 0,
                    'overflow_events': 0
                },
                'by_site': [],
                'by_round': []
            }

        # Get all work orders for this game
        result = await self.db.execute(
            select(InboundOrderLine).filter(
                InboundOrderLine.scenario_id == scenario_id
            ).order_by(InboundOrderLine.round_number)
        )
        work_orders = result.scalars().all()

        # Calculate capacity usage by site and round
        usage_by_site_round = {}  # {(site_id, round): total_qty}
        for order in work_orders:
            key = (order.from_site_id, order.round_number)
            if key not in usage_by_site_round:
                usage_by_site_round[key] = 0.0
            usage_by_site_round[key] += order.quantity_submitted or 0.0

        # Calculate metrics by site
        by_site = []
        total_capacity = 0.0
        utilizations = []

        for capacity in capacities:
            site_name = await self._get_site_name(capacity.site_id)
            max_capacity = capacity.max_capacity_per_period or 0.0
            total_capacity += max_capacity

            # Get all rounds for this site
            site_usages = [
                usage for (site_id, round_num), usage in usage_by_site_round.items()
                if site_id == capacity.site_id
            ]

            if site_usages:
                avg_utilization = (sum(site_usages) / len(site_usages) / max_capacity * 100) if max_capacity > 0 else 0.0
                peak_utilization = (max(site_usages) / max_capacity * 100) if max_capacity > 0 else 0.0
                rounds_at_capacity = sum(1 for usage in site_usages if usage >= max_capacity)
                utilizations.append(avg_utilization)
            else:
                avg_utilization = 0.0
                peak_utilization = 0.0
                rounds_at_capacity = 0

            by_site.append({
                'site_id': capacity.site_id,
                'site_name': site_name,
                'capacity': float(max_capacity),
                'avg_utilization': round(avg_utilization, 1),
                'peak_utilization': round(peak_utilization, 1),
                'rounds_at_capacity': rounds_at_capacity,
                'orders_queued': 0  # TODO: Track queued orders
            })

        # Calculate by round
        rounds_data = {}
        for (site_id, round_num), usage in usage_by_site_round.items():
            if round_num not in rounds_data:
                rounds_data[round_num] = {
                    'round': round_num,
                    'total_used': 0.0,
                    'total_capacity': total_capacity,
                    'utilization_pct': 0.0,
                    'queued': 0
                }
            rounds_data[round_num]['total_used'] += usage

        for round_data in rounds_data.values():
            round_data['utilization_pct'] = (
                round(round_data['total_used'] / round_data['total_capacity'] * 100, 1)
                if round_data['total_capacity'] > 0 else 0.0
            )

        return {
            'scenario_id': scenario_id,
            'capacity_summary': {
                'sites_with_capacity': len(capacities),
                'total_capacity': float(total_capacity),
                'avg_utilization': round(sum(utilizations) / len(utilizations), 1) if utilizations else 0.0,
                'orders_queued': 0,  # TODO: Track queued orders
                'overflow_events': 0  # TODO: Track overflow events
            },
            'by_site': by_site,
            'by_round': sorted(rounds_data.values(), key=lambda x: x['round'])
        }

    # ============================================================================
    # POLICY EFFECTIVENESS
    # ============================================================================

    async def get_policy_effectiveness(self, config_id: int, group_id: int) -> Dict:
        """
        Get policy effectiveness metrics

        Args:
            config_id: Supply chain config ID
            group_id: Group ID

        Returns:
            Dictionary with policy effectiveness metrics
        """
        policies = []

        # Get aggregation policies
        result = await self.db.execute(
            select(OrderAggregationPolicy).filter(
                OrderAggregationPolicy.config_id == config_id,
                OrderAggregationPolicy.group_id == group_id,
                OrderAggregationPolicy.is_active == True
            )
        )
        agg_policies = result.scalars().all()

        for policy in agg_policies:
            # Get usage count and savings
            result = await self.db.execute(
                select(
                    func.count(AggregatedOrder.id),
                    func.sum(AggregatedOrder.fixed_cost_saved)
                ).filter(
                    AggregatedOrder.policy_id == policy.id
                )
            )
            usage_count, total_savings = result.one()
            usage_count = usage_count or 0
            total_savings = float(total_savings or 0.0)

            from_site = await self._get_site_name(policy.from_site_id)
            to_site = await self._get_site_name(policy.to_site_id)

            policies.append({
                'policy_id': policy.id,
                'type': 'aggregation',
                'from_site': from_site,
                'to_site': to_site,
                'usage_count': usage_count,
                'total_savings': round(total_savings, 2),
                'avg_savings_per_use': round(total_savings / usage_count, 2) if usage_count > 0 else 0.0,
                'effectiveness_score': min(100.0, (usage_count * 10))  # Simple scoring
            })

        # Get capacity policies
        result = await self.db.execute(
            select(ProductionCapacity).filter(
                ProductionCapacity.config_id == config_id,
                ProductionCapacity.group_id == group_id
            )
        )
        cap_policies = result.scalars().all()

        for capacity in cap_policies:
            site_name = await self._get_site_name(capacity.site_id)

            # Calculate average utilization
            # TODO: Compute from actual game data
            avg_utilization = 0.0

            policies.append({
                'policy_id': capacity.id,
                'type': 'capacity',
                'site': site_name,
                'capacity': float(capacity.max_capacity_per_period or 0),
                'avg_utilization': avg_utilization,
                'bottleneck_severity': 'unknown'  # TODO: Calculate
            })

        return {
            'config_id': config_id,
            'group_id': group_id,
            'policies': policies
        }

    # ============================================================================
    # COMPARATIVE ANALYTICS
    # ============================================================================

    async def get_comparative_analytics(self, scenario_id: int) -> Dict:
        """
        Get comparative analytics (with vs. without features)

        Args:
            scenario_id: Game ID

        Returns:
            Dictionary with comparative metrics
        """
        # Get game config
        game = await self.db.get(Game, scenario_id)
        if not game:
            return {'error': 'Game not found'}

        features_enabled = {
            'capacity_constraints': game.config.get('use_capacity_constraints', False),
            'order_aggregation': game.config.get('use_order_aggregation', False)
        }

        # Get aggregation data
        result = await self.db.execute(
            select(AggregatedOrder).filter(
                AggregatedOrder.scenario_id == scenario_id
            )
        )
        agg_orders = result.scalars().all()

        # Calculate theoretical without aggregation
        total_individual_orders = sum(o.num_orders_aggregated for o in agg_orders)
        total_aggregated_orders = len(agg_orders)
        total_cost_saved = sum(o.fixed_cost_saved or 0.0 for o in agg_orders)

        # Estimate costs (assuming $100 fixed cost per order)
        fixed_cost_per_order = 100.0
        theoretical_cost = total_individual_orders * fixed_cost_per_order
        actual_cost = total_aggregated_orders * fixed_cost_per_order

        # Get capacity impact
        # TODO: Query actual queued orders
        orders_fulfilled = 0
        orders_queued = 0
        fulfillment_rate = 0.0

        return {
            'scenario_id': scenario_id,
            'features_enabled': features_enabled,
            'comparison': {
                'theoretical_without_aggregation': {
                    'total_orders': total_individual_orders,
                    'total_cost': round(theoretical_cost, 2)
                },
                'actual_with_aggregation': {
                    'total_orders': total_aggregated_orders,
                    'total_cost': round(actual_cost, 2)
                },
                'savings': {
                    'orders_reduced': total_individual_orders - total_aggregated_orders,
                    'cost_saved': round(total_cost_saved, 2),
                    'efficiency_gain_pct': round(
                        (total_cost_saved / theoretical_cost * 100) if theoretical_cost > 0 else 0.0,
                        1
                    )
                }
            },
            'capacity_impact': {
                'orders_fulfilled': orders_fulfilled,
                'orders_queued': orders_queued,
                'fulfillment_rate_pct': fulfillment_rate
            }
        }

    # ============================================================================
    # HELPER METHODS
    # ============================================================================

    async def _get_site_name(self, site_id: int) -> str:
        """
        Get site name from site ID

        Args:
            site_id: Node/site ID

        Returns:
            Site name or 'Unknown'
        """
        from app.models.supply_chain_config import Node

        result = await self.db.execute(
            select(Node).filter(Node.id == site_id)
        )
        node = result.scalar_one_or_none()
        return node.name if node else f'Site_{site_id}'
