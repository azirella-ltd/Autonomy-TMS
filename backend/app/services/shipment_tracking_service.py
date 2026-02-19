"""
Shipment Tracking Service
Real-time tracking of in-transit inventory with delivery risk analytics
Sprint 2: Material Visibility

Production implementation using Shipment, TransportationLane, and Site models.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, desc, func, select
import statistics

from app.models.sc_entities import Shipment, Product
from app.models.supply_chain_config import TransportationLane, Site


class ShipmentTrackingService:
    """
    Service for tracking shipments and calculating delivery risks
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def track_shipment(self, shipment_id: str) -> Dict:
        """
        Get real-time shipment status with risk assessment

        Args:
            shipment_id: Unique shipment identifier

        Returns:
            Dict containing:
            - shipment_id, order_id, product_id
            - from_site, to_site
            - carrier, tracking_number
            - status, ship_date, expected_delivery_date
            - current_location, last_update
            - delivery_risk_score, risk_level
            - risk_factors
            - recommended_actions
        """
        stmt = select(Shipment).where(Shipment.id == shipment_id)
        result = await self.db.execute(stmt)
        shipment = result.scalar_one_or_none()

        if not shipment:
            return {"error": "Shipment not found", "shipment_id": shipment_id}

        # Calculate current risk if shipment is in transit
        if shipment.status == "in_transit":
            risk_data = await self.calculate_delivery_risk(shipment_id)
            shipment.delivery_risk_score = risk_data.get("delivery_risk_score")
            shipment.risk_level = risk_data.get("risk_level")
            shipment.risk_factors = risk_data.get("risk_factors")
            await self.db.commit()

        return {
            "shipment_id": shipment.id,
            "order_id": shipment.order_id,
            "product_id": shipment.product_id,
            "quantity": shipment.quantity,
            "uom": shipment.uom,
            "from_site_id": shipment.from_site_id,
            "to_site_id": shipment.to_site_id,
            "carrier_name": shipment.carrier_name,
            "tracking_number": shipment.tracking_number,
            "status": shipment.status,
            "ship_date": shipment.ship_date.isoformat() if shipment.ship_date else None,
            "expected_delivery_date": shipment.expected_delivery_date.isoformat() if shipment.expected_delivery_date else None,
            "actual_delivery_date": shipment.actual_delivery_date.isoformat() if shipment.actual_delivery_date else None,
            "current_location": shipment.current_location,
            "last_tracking_update": shipment.last_tracking_update.isoformat() if shipment.last_tracking_update else None,
            "delivery_risk_score": shipment.delivery_risk_score,
            "risk_level": shipment.risk_level,
            "risk_factors": shipment.risk_factors or {},
            "tracking_events": shipment.tracking_events or [],
            "recommended_actions": shipment.recommended_actions or [],
            "mitigation_status": shipment.mitigation_status,
        }

    async def get_in_transit_inventory(
        self,
        product_id: Optional[str] = None,
        site_id: Optional[str] = None,
        risk_level: Optional[str] = None,
    ) -> List[Dict]:
        """
        Get all in-transit inventory with optional filters

        Args:
            product_id: Filter by product
            site_id: Filter by destination site
            risk_level: Filter by risk level (LOW, MEDIUM, HIGH, CRITICAL)

        Returns:
            List of shipments with aggregated quantities by product/destination
        """
        stmt = select(Shipment).where(
            Shipment.status.in_(["planned", "in_transit", "delayed"])
        )

        if product_id:
            stmt = stmt.where(Shipment.product_id == product_id)

        if site_id:
            stmt = stmt.where(Shipment.to_site_id == site_id)

        if risk_level:
            stmt = stmt.where(Shipment.risk_level == risk_level)

        stmt = stmt.order_by(desc(Shipment.expected_delivery_date))
        result = await self.db.execute(stmt)
        shipments = result.scalars().all()

        return [
            {
                "shipment_id": s.id,
                "order_id": s.order_id,
                "product_id": s.product_id,
                "quantity": s.quantity,
                "uom": s.uom,
                "from_site_id": s.from_site_id,
                "to_site_id": s.to_site_id,
                "carrier_name": s.carrier_name,
                "status": s.status,
                "expected_delivery_date": s.expected_delivery_date.isoformat() if s.expected_delivery_date else None,
                "delivery_risk_score": s.delivery_risk_score,
                "risk_level": s.risk_level,
                "days_in_transit": (datetime.utcnow() - s.ship_date).days if s.ship_date else None,
            }
            for s in shipments
        ]

    async def calculate_delivery_risk(self, shipment_id: str) -> Dict:
        """
        Calculate delivery risk using historical carrier performance and route analysis

        Algorithm:
        1. Get carrier historical on-time delivery rate
        2. Calculate expected transit time vs actual elapsed time
        3. Analyze route congestion (number of shipments on same lane)
        4. Check for delays in tracking events
        5. Combine factors into risk score (0-100)

        Returns:
            {
                "shipment_id": str,
                "delivery_risk_score": float (0-100),
                "risk_level": str (LOW/MEDIUM/HIGH/CRITICAL),
                "probability_on_time": float (0-1),
                "risk_factors": {
                    "carrier_performance": float,
                    "transit_time_variance": float,
                    "route_congestion": float,
                    "tracking_delays": float
                }
            }
        """
        stmt = select(Shipment).where(Shipment.id == shipment_id)
        result = await self.db.execute(stmt)
        shipment = result.scalar_one_or_none()

        if not shipment:
            return {"error": "Shipment not found"}

        risk_factors = {}
        risk_score = 0.0

        # Factor 1: Carrier Performance (40% weight)
        carrier_risk = await self._assess_carrier_performance(
            shipment.carrier_id, shipment.product_id
        )
        risk_factors["carrier_performance"] = carrier_risk
        risk_score += carrier_risk * 0.4

        # Factor 2: Transit Time Variance (30% weight)
        transit_risk = await self._assess_transit_time_variance(shipment)
        risk_factors["transit_time_variance"] = transit_risk
        risk_score += transit_risk * 0.3

        # Factor 3: Route Congestion (20% weight)
        congestion_risk = await self._assess_route_congestion(
            shipment.transportation_lane_id
        )
        risk_factors["route_congestion"] = congestion_risk
        risk_score += congestion_risk * 0.2

        # Factor 4: Tracking Delays (10% weight)
        tracking_risk = self._assess_tracking_delays(shipment)
        risk_factors["tracking_delays"] = tracking_risk
        risk_score += tracking_risk * 0.1

        # Classify risk level
        if risk_score >= 75:
            risk_level = "CRITICAL"
        elif risk_score >= 50:
            risk_level = "HIGH"
        elif risk_score >= 25:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        # Probability of on-time delivery (inverse of risk)
        probability_on_time = (100 - risk_score) / 100.0

        return {
            "shipment_id": shipment_id,
            "delivery_risk_score": round(risk_score, 2),
            "risk_level": risk_level,
            "probability_on_time": round(probability_on_time, 3),
            "risk_factors": risk_factors,
        }

    async def _assess_carrier_performance(
        self, carrier_id: Optional[str], product_id: str
    ) -> float:
        """
        Assess carrier performance based on historical lead times

        Returns risk score 0-100 based on:
        - Lead time variance (higher variance = higher risk)
        - Average delay vs expected transit time
        """
        if not carrier_id:
            return 50.0  # Default medium risk if no carrier data

        # Get historical shipments from this carrier
        stmt = select(Shipment).where(
            and_(
                Shipment.carrier_id == carrier_id,
                Shipment.status == "delivered",
                Shipment.actual_delivery_date.isnot(None),
                Shipment.expected_delivery_date.isnot(None),
            )
        ).limit(100)
        result = await self.db.execute(stmt)
        historical = result.scalars().all()

        if not historical or len(historical) < 3:
            return 50.0  # Insufficient data

        # Calculate delays (actual - expected in days)
        delays = []
        for shipment in historical:
            delay_days = (
                shipment.actual_delivery_date - shipment.expected_delivery_date
            ).days
            delays.append(delay_days)

        # Calculate statistics
        avg_delay = statistics.mean(delays)
        delay_variance = statistics.variance(delays) if len(delays) > 1 else 0

        # High variance = unreliable carrier
        variance_risk = min(delay_variance * 5, 50)  # Cap at 50

        # Average delay = late carrier
        delay_risk = max(0, avg_delay * 10)  # 1 day delay = 10 points
        delay_risk = min(delay_risk, 50)  # Cap at 50

        return variance_risk + delay_risk

    async def _assess_transit_time_variance(self, shipment: Shipment) -> float:
        """
        Assess if shipment is taking longer than expected

        Returns risk score based on:
        - Days in transit vs expected transit time
        - Percentage of expected time elapsed
        """
        if not shipment.ship_date or not shipment.expected_delivery_date:
            return 25.0  # Default low-medium risk

        now = datetime.utcnow()
        expected_transit_days = (
            shipment.expected_delivery_date - shipment.ship_date
        ).days
        actual_elapsed_days = (now - shipment.ship_date).days
        days_remaining = (shipment.expected_delivery_date - now).days

        # If already late
        if days_remaining < 0:
            return 100.0

        # If less than 1 day remaining
        if days_remaining < 1:
            return 80.0

        # Calculate percentage of time elapsed
        if expected_transit_days > 0:
            pct_elapsed = actual_elapsed_days / expected_transit_days

            # Risk increases as we approach deadline
            if pct_elapsed >= 0.9:
                return 70.0
            elif pct_elapsed >= 0.75:
                return 50.0
            elif pct_elapsed >= 0.5:
                return 30.0
            else:
                return 10.0
        else:
            return 25.0

    async def _assess_route_congestion(
        self, transportation_lane_id: Optional[str]
    ) -> float:
        """
        Assess route congestion based on active shipments on same lane

        High congestion = higher risk of delays
        """
        if not transportation_lane_id:
            return 25.0  # Default

        # Count active shipments on this lane
        stmt = select(func.count(Shipment.id)).where(
            and_(
                Shipment.transportation_lane_id == transportation_lane_id,
                Shipment.status.in_(["planned", "in_transit"]),
            )
        )
        result = await self.db.execute(stmt)
        active_count = result.scalar()

        # Risk increases with congestion
        if active_count > 50:
            return 80.0
        elif active_count > 25:
            return 50.0
        elif active_count > 10:
            return 30.0
        else:
            return 10.0

    def _assess_tracking_delays(self, shipment: Shipment) -> float:
        """
        Assess tracking freshness - if no recent updates, risk is higher

        Returns risk score based on time since last tracking update
        """
        if not shipment.last_tracking_update:
            return 50.0  # No tracking data = medium risk

        hours_since_update = (
            datetime.utcnow() - shipment.last_tracking_update
        ).total_seconds() / 3600

        # Risk increases with staleness
        if hours_since_update > 48:
            return 80.0
        elif hours_since_update > 24:
            return 50.0
        elif hours_since_update > 12:
            return 30.0
        else:
            return 10.0

    async def recommend_mitigation(self, shipment_id: str) -> List[Dict]:
        """
        Recommend mitigation actions for at-risk shipments

        Actions depend on risk factors:
        - Expedite shipping (if carrier delay risk)
        - Reroute via alternate carrier (if current carrier unreliable)
        - Increase safety stock at destination (if high stockout risk)
        - Notify customer of delay (if already late)

        Returns:
            List of recommended actions with impact and cost estimates
        """
        stmt = select(Shipment).where(Shipment.id == shipment_id)
        result = await self.db.execute(stmt)
        shipment = result.scalar_one_or_none()

        if not shipment:
            return []

        # Calculate risk if not already done
        risk_data = await self.calculate_delivery_risk(shipment_id)
        risk_score = risk_data.get("delivery_risk_score", 0)
        risk_factors = risk_data.get("risk_factors", {})

        actions = []

        # Action 1: Expedite shipping (if high risk and still early enough)
        if risk_score > 50 and shipment.status == "in_transit":
            days_remaining = (
                shipment.expected_delivery_date - datetime.utcnow()
            ).days if shipment.expected_delivery_date else 0

            if days_remaining > 1:
                actions.append({
                    "action": "expedite_shipping",
                    "description": "Upgrade to expedited shipping service",
                    "impact": "Reduces delivery risk by 30-40%",
                    "estimated_cost": "$50-150 per shipment",
                    "priority": "HIGH",
                })

        # Action 2: Reroute to alternate carrier (if carrier performance poor)
        if risk_factors.get("carrier_performance", 0) > 50:
            actions.append({
                "action": "reroute_carrier",
                "description": "Switch to alternate carrier with better performance",
                "impact": "Reduces delivery risk by 40-50%",
                "estimated_cost": "$25-75 per shipment",
                "priority": "MEDIUM",
            })

        # Action 3: Increase safety stock (if destination site at risk)
        if risk_score > 60:
            actions.append({
                "action": "increase_safety_stock",
                "description": f"Increase safety stock at destination site {shipment.to_site_id}",
                "impact": "Prevents stockout if shipment delayed",
                "estimated_cost": "10-20% increase in holding costs",
                "priority": "MEDIUM",
            })

        # Action 4: Notify customer (if already late or will be late)
        days_remaining = (
            shipment.expected_delivery_date - datetime.utcnow()
        ).days if shipment.expected_delivery_date else 0

        if days_remaining < 0 or risk_score > 75:
            actions.append({
                "action": "notify_customer",
                "description": "Proactively notify customer of potential delay",
                "impact": "Maintains customer satisfaction and trust",
                "estimated_cost": "Minimal (communication only)",
                "priority": "HIGH",
            })

        # Action 5: Split shipment (if large quantity and high risk)
        if shipment.quantity > 1000 and risk_score > 60:
            actions.append({
                "action": "split_shipment",
                "description": "Split shipment across multiple carriers to reduce risk",
                "impact": "Ensures partial delivery even if one shipment fails",
                "estimated_cost": "$100-300 (additional handling)",
                "priority": "MEDIUM",
            })

        return actions

    async def update_shipment_status(
        self,
        shipment_id: str,
        status: str,
        current_location: Optional[str] = None,
        tracking_event: Optional[Dict] = None,
    ) -> Dict:
        """
        Update shipment status and add tracking event

        Args:
            shipment_id: Shipment identifier
            status: New status (planned, in_transit, delivered, delayed, exception)
            current_location: Current location description
            tracking_event: Event to add to history

        Returns:
            Updated shipment data
        """
        stmt = select(Shipment).where(Shipment.id == shipment_id)
        result = await self.db.execute(stmt)
        shipment = result.scalar_one_or_none()

        if not shipment:
            return {"error": "Shipment not found"}

        # Update status
        shipment.status = status
        shipment.last_tracking_update = datetime.utcnow()

        if current_location:
            shipment.current_location = current_location

        # Add tracking event
        if tracking_event:
            events = shipment.tracking_events or []
            events.append({
                "timestamp": datetime.utcnow().isoformat(),
                **tracking_event
            })
            shipment.tracking_events = events

        # If delivered, set actual delivery date
        if status == "delivered" and not shipment.actual_delivery_date:
            shipment.actual_delivery_date = datetime.utcnow()

        await self.db.commit()

        return await self.track_shipment(shipment_id)
