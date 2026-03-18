"""
ATP Calculation Service for Simulation Execution

Provides real-time ATP (Available-to-Promise) calculations during
simulation order promising and fulfillment. Integrates with order
management and fulfillment services.

This service is specialized for simulation execution, complementing
the broader ATP/CTP view endpoints used for planning.
"""

from typing import List, Optional, Dict, Any, Tuple
from datetime import date, datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func

from app.models.sc_entities import OutboundOrderLine, InvLevel
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem
from app.models.transfer_order import TransferOrder, TransferOrderLineItem
from app.models.supply_chain_config import Site, TransportationLane


class ATPCalculationService:
    """Service for calculating ATP during simulation execution."""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    # ========================================================================
    # Real-Time ATP Calculation
    # ========================================================================

    async def calculate_atp(
        self,
        site_id: int,
        product_id: str,
        config_id: Optional[int] = None,
        scenario_id: Optional[int] = None,
        current_round: Optional[int] = None,
        horizon_rounds: int = 4,
    ) -> Dict[str, Any]:
        """
        Calculate real-time ATP for simulation order promising.

        ATP = On-hand + In-transit receipts - Committed - Backlog

        Args:
            site_id: Site ID
            product_id: Product ID
            config_id: Supply chain configuration ID
            scenario_id: Scenario ID
            current_round: Current round number
            horizon_rounds: Number of future rounds to project (default: 4)

        Returns:
            Dictionary with ATP details:
            {
                'current_atp': float,
                'on_hand': float,
                'in_transit': float,
                'committed': float,
                'backlog': float,
                'future_receipts': List[Dict],  # Per-round receipts
                'projected_atp': List[Dict],    # Per-round ATP projection
            }
        """
        # Get current inventory level
        on_hand = await self._get_on_hand_inventory(
            site_id=site_id,
            product_id=product_id,
            config_id=config_id,
            scenario_id=scenario_id,
        )

        # Get in-transit quantity (arriving this round or next)
        in_transit = await self._get_in_transit_quantity(
            site_id=site_id,
            product_id=product_id,
            scenario_id=scenario_id,
            arrival_round=current_round,
            horizon_rounds=2,  # Current + next round
        )

        # Get committed quantity (promised but not shipped)
        committed = await self._get_committed_quantity(
            site_id=site_id,
            product_id=product_id,
            scenario_id=scenario_id,
        )

        # Get backlog quantity
        backlog = await self._get_backlog_quantity(
            site_id=site_id,
            product_id=product_id,
            scenario_id=scenario_id,
        )

        # Current ATP
        current_atp = max(0.0, on_hand + in_transit - committed - backlog)

        # Project future receipts
        future_receipts = await self._project_future_receipts(
            site_id=site_id,
            product_id=product_id,
            scenario_id=scenario_id,
            current_round=current_round,
            horizon_rounds=horizon_rounds,
        )

        # Project future ATP (simple rolling projection)
        projected_atp = self._project_future_atp(
            current_atp=current_atp,
            future_receipts=future_receipts,
        )

        return {
            'current_atp': current_atp,
            'on_hand': on_hand,
            'in_transit': in_transit,
            'committed': committed,
            'backlog': backlog,
            'future_receipts': future_receipts,
            'projected_atp': projected_atp,
        }

    async def calculate_promise_date(
        self,
        site_id: int,
        product_id: str,
        requested_quantity: float,
        requested_date: date,
        config_id: Optional[int] = None,
        scenario_id: Optional[int] = None,
        current_round: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Calculate promise date for an order quantity.

        Determines when the requested quantity can be fulfilled based on
        current ATP and projected receipts.

        Args:
            site_id: Site ID
            product_id: Product ID
            requested_quantity: Requested order quantity
            requested_date: Customer's requested delivery date
            config_id: Supply chain configuration ID
            scenario_id: Scenario ID
            current_round: Current round number

        Returns:
            Dictionary with promise details:
            {
                'can_promise': bool,
                'promised_quantity': float,
                'promised_date': date,
                'promised_round': int,
                'shortfall_quantity': float,
                'confidence': float,  # 0.0-1.0 confidence in promise
            }
        """
        # Calculate ATP projection
        atp_data = await self.calculate_atp(
            site_id=site_id,
            product_id=product_id,
            config_id=config_id,
            scenario_id=scenario_id,
            current_round=current_round,
            horizon_rounds=6,
        )

        current_atp = atp_data['current_atp']
        projected_atp = atp_data['projected_atp']

        # Check if we can promise immediately
        if current_atp >= requested_quantity:
            return {
                'can_promise': True,
                'promised_quantity': requested_quantity,
                'promised_date': requested_date,
                'promised_round': current_round,
                'shortfall_quantity': 0.0,
                'confidence': 1.0,
            }

        # Check future rounds for sufficient ATP
        cumulative_atp = current_atp

        for round_projection in projected_atp:
            cumulative_atp = round_projection['atp']

            if cumulative_atp >= requested_quantity:
                # Can promise in this future round
                promised_round = round_projection['round']
                # Convert round to date (1 week per round)
                weeks_ahead = promised_round - current_round if current_round else 0
                promised_date = date.today() + timedelta(weeks=weeks_ahead)

                return {
                    'can_promise': True,
                    'promised_quantity': requested_quantity,
                    'promised_date': promised_date,
                    'promised_round': promised_round,
                    'shortfall_quantity': 0.0,
                    'confidence': 0.8,  # Lower confidence for future promises
                }

        # Cannot fully promise - return partial promise
        max_promise = max(current_atp, cumulative_atp)
        shortfall = requested_quantity - max_promise

        return {
            'can_promise': False,
            'promised_quantity': max_promise,
            'promised_date': requested_date,
            'promised_round': current_round,
            'shortfall_quantity': shortfall,
            'confidence': 0.5,
        }

    async def check_fulfillment_feasibility(
        self,
        site_id: int,
        product_id: str,
        required_quantity: float,
        config_id: Optional[int] = None,
        scenario_id: Optional[int] = None,
    ) -> bool:
        """
        Check if a quantity can be fulfilled immediately.

        Quick boolean check for fulfillment feasibility without
        full ATP calculation.

        Args:
            site_id: Site ID
            product_id: Product ID
            required_quantity: Required quantity
            config_id: Supply chain configuration ID
            scenario_id: Scenario ID

        Returns:
            True if fulfillment is feasible, False otherwise
        """
        atp_data = await self.calculate_atp(
            site_id=site_id,
            product_id=product_id,
            config_id=config_id,
            scenario_id=scenario_id,
            horizon_rounds=1,
        )

        return atp_data['current_atp'] >= required_quantity

    # ========================================================================
    # Helper Methods
    # ========================================================================

    async def _get_on_hand_inventory(
        self,
        site_id: int,
        product_id: str,
        config_id: Optional[int] = None,
        scenario_id: Optional[int] = None,
    ) -> float:
        """Get current on-hand inventory quantity."""
        query = select(InvLevel).where(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.product_id == product_id,
            )
        )

        if config_id is not None:
            query = query.where(InvLevel.config_id == config_id)
        if scenario_id is not None:
            query = query.where(InvLevel.scenario_id == scenario_id)

        result = await self.db.execute(query)
        inv_level = result.scalar_one_or_none()

        return inv_level.quantity if inv_level else 0.0

    async def _get_in_transit_quantity(
        self,
        site_id: int,
        product_id: str,
        scenario_id: Optional[int] = None,
        arrival_round: Optional[int] = None,
        horizon_rounds: int = 2,
    ) -> float:
        """
        Get in-transit quantity arriving in current or next rounds.

        Args:
            site_id: Destination site ID
            product_id: Product ID
            scenario_id: Scenario ID
            arrival_round: Current round number
            horizon_rounds: Look ahead N rounds

        Returns:
            Total in-transit quantity
        """
        if arrival_round is None:
            # If no round specified, get all IN_TRANSIT TOs
            query = select(TransferOrder).where(
                and_(
                    TransferOrder.destination_site_id == site_id,
                    TransferOrder.status == "IN_TRANSIT",
                )
            )
            if scenario_id is not None:
                query = query.where(TransferOrder.scenario_id == scenario_id)

        else:
            # Get TOs arriving in current + next N rounds
            query = select(TransferOrder).where(
                and_(
                    TransferOrder.destination_site_id == site_id,
                    TransferOrder.scenario_id == scenario_id,
                    TransferOrder.arrival_round >= arrival_round,
                    TransferOrder.arrival_round <= arrival_round + horizon_rounds,
                    TransferOrder.status == "IN_TRANSIT",
                )
            )

        result = await self.db.execute(query)
        tos = result.scalars().all()

        total_in_transit = 0.0

        for to in tos:
            # Get line items
            line_items_query = select(TransferOrderLineItem).where(
                and_(
                    TransferOrderLineItem.to_id == to.id,
                    TransferOrderLineItem.product_id == product_id,
                )
            )
            line_result = await self.db.execute(line_items_query)
            line_items = line_result.scalars().all()

            for line in line_items:
                total_in_transit += line.quantity

        return total_in_transit

    async def _get_committed_quantity(
        self,
        site_id: int,
        product_id: str,
        scenario_id: Optional[int] = None,
    ) -> float:
        """
        Get committed quantity (promised but not yet shipped).

        Committed = Sum of promised_quantity for CONFIRMED orders
        """
        query = select(func.sum(OutboundOrderLine.promised_quantity)).where(
            and_(
                OutboundOrderLine.site_id == site_id,
                OutboundOrderLine.product_id == product_id,
                OutboundOrderLine.status.in_(['CONFIRMED', 'PARTIALLY_FULFILLED']),
                OutboundOrderLine.promised_quantity.isnot(None),
            )
        )

        if scenario_id is not None:
            query = query.where(OutboundOrderLine.scenario_id == scenario_id)

        result = await self.db.execute(query)
        committed = result.scalar()

        return float(committed) if committed else 0.0

    async def _get_backlog_quantity(
        self,
        site_id: int,
        product_id: str,
        scenario_id: Optional[int] = None,
    ) -> float:
        """Get total backlog quantity."""
        query = select(func.sum(OutboundOrderLine.backlog_quantity)).where(
            and_(
                OutboundOrderLine.site_id == site_id,
                OutboundOrderLine.product_id == product_id,
                OutboundOrderLine.status.in_(['CONFIRMED', 'PARTIALLY_FULFILLED']),
            )
        )

        if scenario_id is not None:
            query = query.where(OutboundOrderLine.scenario_id == scenario_id)

        result = await self.db.execute(query)
        backlog = result.scalar()

        return float(backlog) if backlog else 0.0

    async def _project_future_receipts(
        self,
        site_id: int,
        product_id: str,
        scenario_id: Optional[int] = None,
        current_round: Optional[int] = None,
        horizon_rounds: int = 4,
    ) -> List[Dict[str, Any]]:
        """
        Project future receipts by round.

        Returns list of receipts per round:
        [
            {'round': 1, 'quantity': 10.0},
            {'round': 2, 'quantity': 15.0},
            ...
        ]
        """
        if current_round is None:
            return []

        receipts = []

        for round_offset in range(horizon_rounds):
            future_round = current_round + round_offset + 1

            # Get TOs arriving in this round
            query = select(TransferOrder).where(
                and_(
                    TransferOrder.destination_site_id == site_id,
                    TransferOrder.scenario_id == scenario_id,
                    TransferOrder.arrival_round == future_round,
                    TransferOrder.status == "IN_TRANSIT",
                )
            )

            result = await self.db.execute(query)
            tos = result.scalars().all()

            round_quantity = 0.0

            for to in tos:
                # Get line items
                line_items_query = select(TransferOrderLineItem).where(
                    and_(
                        TransferOrderLineItem.to_id == to.id,
                        TransferOrderLineItem.product_id == product_id,
                    )
                )
                line_result = await self.db.execute(line_items_query)
                line_items = line_result.scalars().all()

                for line in line_items:
                    round_quantity += line.quantity

            receipts.append({
                'round': future_round,
                'quantity': round_quantity,
            })

        return receipts

    def _project_future_atp(
        self,
        current_atp: float,
        future_receipts: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Project future ATP based on receipts.

        Simple rolling projection: ATP[t] = ATP[t-1] + Receipts[t]

        Args:
            current_atp: Current ATP
            future_receipts: List of future receipts by round

        Returns:
            List of projected ATP by round:
            [
                {'round': 1, 'atp': 25.0, 'receipts': 10.0},
                {'round': 2, 'atp': 40.0, 'receipts': 15.0},
                ...
            ]
        """
        projected_atp = []
        cumulative_atp = current_atp

        for receipt in future_receipts:
            cumulative_atp += receipt['quantity']

            projected_atp.append({
                'round': receipt['round'],
                'atp': cumulative_atp,
                'receipts': receipt['quantity'],
            })

        return projected_atp

    async def get_lane_lead_time(
        self,
        source_site_id: int,
        destination_site_id: int,
        config_id: int,
    ) -> int:
        """
        Get lead time (in rounds) for a lane.

        Args:
            source_site_id: Source site ID
            destination_site_id: Destination site ID
            config_id: Supply chain configuration ID

        Returns:
            Lead time in rounds (default: 1)
        """
        query = select(TransportationLane).where(
            and_(
                TransportationLane.source_node_id == source_site_id,
                TransportationLane.destination_node_id == destination_site_id,
                TransportationLane.config_id == config_id,
            )
        )

        result = await self.db.execute(query)
        lane = result.scalar_one_or_none()

        if lane and hasattr(lane, 'lead_time_days'):
            # Convert days to rounds (1 round = 7 days in simulation)
            return max(1, lane.lead_time_days // 7)

        # Default: 1 round lead time
        return 1
