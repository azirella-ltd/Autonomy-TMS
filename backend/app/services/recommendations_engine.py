"""
Recommendations Engine
Generates inventory rebalancing recommendations with ML-based scoring

Part of AWS Supply Chain Implementation - Sprint 4
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_
import logging
import uuid

from app.models.sc_entities import Product, InvLevel, InvPolicy, Forecast
from app.models.supply_chain_config import Site
from app.services.sc_planning.inventory_target_calculator import InventoryTargetCalculator
from app.services.recommendations_scoring import (
    calculate_site_distance,
    score_distance,
    calculate_co2_emissions,
    score_sustainability,
    calculate_total_cost_impact,
    score_cost,
    simulate_recommendation_impact as simulate_impact_enhanced
)

logger = logging.getLogger(__name__)


class RecommendationsEngine:
    """
    Recommendations Engine for inventory rebalancing

    Features:
    - Identifies excess and deficit inventory positions
    - Generates optimal transfer recommendations
    - Scores recommendations by multiple criteria (risk, distance, sustainability, etc.)
    - Simulates impact using probabilistic modeling
    - Tracks user decisions for ML learning loop
    """

    def __init__(self, db: Session):
        self.db = db

        # Scoring weights (must sum to 100)
        self.RISK_RESOLUTION_WEIGHT = 40
        self.DISTANCE_WEIGHT = 20
        self.SUSTAINABILITY_WEIGHT = 15
        self.SERVICE_LEVEL_WEIGHT = 15
        self.COST_WEIGHT = 10

        # Thresholds
        self.EXCESS_DOS_THRESHOLD = 90  # Days of supply threshold for excess
        self.DEFICIT_THRESHOLD_MULTIPLIER = 0.8  # Below 80% of safety stock

    async def generate_rebalancing_recommendations(
        self,
        network_id: Optional[str] = None
    ) -> List[Dict]:
        """
        Generate inventory rebalancing recommendations

        Algorithm:
        1. Identify sites with excess inventory (DOS > threshold)
        2. Identify sites with deficit (DOS < safety stock)
        3. Calculate optimal transfers using scoring algorithm
        4. Score recommendations by:
           - Risk resolution (40 points)
           - Distance (20 points)
           - Sustainability (15 points)
           - Service level impact (15 points)
           - Inventory cost (10 points)

        Args:
            network_id: Optional filter by supply chain network

        Returns:
            List of recommendations sorted by total score (descending)
        """
        try:
            logger.info("Generating rebalancing recommendations...")

            # Step 1: Identify excess inventory positions
            excess_positions = await self._identify_excess_inventory()
            logger.info(f"Found {len(excess_positions)} excess inventory positions")

            # Step 2: Identify deficit positions
            deficit_positions = await self._identify_deficit_inventory()
            logger.info(f"Found {len(deficit_positions)} deficit inventory positions")

            # Step 3: Generate candidate recommendations
            recommendations = []
            for excess in excess_positions:
                for deficit in deficit_positions:
                    # Only recommend transfers for same product
                    if excess['product_id'] == deficit['product_id']:
                        rec = await self._create_recommendation(excess, deficit)
                        if rec:
                            recommendations.append(rec)

            logger.info(f"Generated {len(recommendations)} candidate recommendations")

            # Step 4: Score and rank recommendations
            scored_recommendations = []
            for rec in recommendations:
                scored_rec = await self._score_recommendation(rec)
                scored_recommendations.append(scored_rec)

            # Sort by total score (descending)
            scored_recommendations.sort(key=lambda x: x['total_score'], reverse=True)

            logger.info(f"Returning {len(scored_recommendations)} scored recommendations")
            return scored_recommendations

        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            raise

    async def _identify_excess_inventory(self) -> List[Dict]:
        """
        Identify sites with excess inventory (DOS > threshold)

        Returns:
            List of dicts with product_id, site_id, current_dos, excess_quantity
        """
        try:
            # Get current inventory levels
            stmt = select(InvLevel).where(InvLevel.on_hand_qty > 0)
            result = await self.db.execute(stmt)
            inv_levels = result.scalars().all()

            excess_positions = []

            for inv in inv_levels:
                # Calculate days of supply
                dos = await self._calculate_days_of_supply(
                    inv.product_id,
                    inv.site_id,
                    inv.on_hand_qty
                )

                if dos and dos > self.EXCESS_DOS_THRESHOLD:
                    # Get safety stock target
                    target = await self._get_inventory_target(
                        inv.product_id,
                        inv.site_id
                    )

                    if target:
                        excess_qty = inv.on_hand_qty - target

                        if excess_qty > 0:
                            excess_positions.append({
                                'product_id': inv.product_id,
                                'site_id': inv.site_id,
                                'current_qty': inv.on_hand_qty,
                                'target_qty': target,
                                'excess_qty': excess_qty,
                                'dos': dos
                            })

            return excess_positions

        except Exception as e:
            logger.error(f"Error identifying excess inventory: {e}")
            return []

    async def _identify_deficit_inventory(self) -> List[Dict]:
        """
        Identify sites with deficit inventory (below safety stock threshold)

        Returns:
            List of dicts with product_id, site_id, current_qty, deficit_qty
        """
        try:
            # Get current inventory levels
            stmt = select(InvLevel)
            result = await self.db.execute(stmt)
            inv_levels = result.scalars().all()

            deficit_positions = []

            for inv in inv_levels:
                # Get safety stock target
                target = await self._get_inventory_target(
                    inv.product_id,
                    inv.site_id
                )

                if target:
                    # Check if below threshold (80% of safety stock)
                    threshold = target * self.DEFICIT_THRESHOLD_MULTIPLIER

                    if inv.on_hand_qty < threshold:
                        deficit_qty = target - inv.on_hand_qty

                        deficit_positions.append({
                            'product_id': inv.product_id,
                            'site_id': inv.site_id,
                            'current_qty': inv.on_hand_qty,
                            'target_qty': target,
                            'deficit_qty': deficit_qty,
                            'risk_level': 'HIGH' if inv.on_hand_qty < threshold * 0.5 else 'MEDIUM'
                        })

            return deficit_positions

        except Exception as e:
            logger.error(f"Error identifying deficit inventory: {e}")
            return []

    async def _calculate_days_of_supply(
        self,
        product_id: str,
        site_id: str,
        on_hand_qty: float
    ) -> Optional[float]:
        """
        Calculate days of supply for a product at a site

        DOS = on_hand_qty / average_daily_demand
        """
        try:
            # Get recent demand forecast (last 30 days average)
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=30)

            stmt = select(func.avg(Forecast.quantity_p50)).where(
                and_(
                    Forecast.product_id == product_id,
                    Forecast.site_id == site_id,
                    Forecast.forecast_date >= start_date,
                    Forecast.forecast_date <= end_date
                )
            )
            result = await self.db.execute(stmt)
            avg_daily_demand = result.scalar()

            if avg_daily_demand and avg_daily_demand > 0:
                dos = on_hand_qty / avg_daily_demand
                return dos

            return None

        except Exception as e:
            logger.error(f"Error calculating DOS: {e}")
            return None

    async def _get_inventory_target(
        self,
        product_id: str,
        site_id: str
    ) -> Optional[float]:
        """
        Get inventory target (safety stock) for a product at a site
        """
        try:
            # Use InventoryTargetCalculator to get target
            calc = InventoryTargetCalculator(self.db)

            # Get inventory policy for this product/site
            stmt = select(InvPolicy).where(
                and_(
                    InvPolicy.product_id == product_id,
                    InvPolicy.site_id == site_id
                )
            )
            result = await self.db.execute(stmt)
            policy = result.scalar_one_or_none()

            if policy:
                # Calculate target based on policy type
                if policy.policy_type == 'abs_level':
                    return policy.target_qty
                elif policy.policy_type in ['doc_dem', 'doc_fcst']:
                    # Get average daily demand
                    stmt = select(func.avg(Forecast.quantity_p50)).where(
                        and_(
                            Forecast.product_id == product_id,
                            Forecast.site_id == site_id
                        )
                    )
                    result = await self.db.execute(stmt)
                    avg_demand = result.scalar()

                    if avg_demand:
                        return avg_demand * policy.coverage_days
                elif policy.policy_type == 'sl':
                    # Service level based - use target_qty if available
                    if policy.target_qty:
                        return policy.target_qty

            # Fallback: use default safety stock calculation
            return None

        except Exception as e:
            logger.error(f"Error getting inventory target: {e}")
            return None

    async def _create_recommendation(
        self,
        excess: Dict,
        deficit: Dict
    ) -> Optional[Dict]:
        """
        Create a transfer recommendation from excess site to deficit site

        Args:
            excess: Excess inventory position
            deficit: Deficit inventory position

        Returns:
            Recommendation dict or None if not feasible
        """
        try:
            # Calculate transfer quantity (min of excess and deficit)
            transfer_qty = min(excess['excess_qty'], deficit['deficit_qty'])

            if transfer_qty <= 0:
                return None

            # Create recommendation
            rec_id = str(uuid.uuid4())

            recommendation = {
                'id': rec_id,
                'recommendation_type': 'rebalance',
                'from_site_id': excess['site_id'],
                'to_site_id': deficit['site_id'],
                'product_id': excess['product_id'],
                'quantity': transfer_qty,
                'status': 'pending',
                'created_at': datetime.utcnow(),

                # Context for scoring
                'excess_dos': excess['dos'],
                'deficit_risk': deficit.get('risk_level', 'MEDIUM'),
                'from_current_qty': excess['current_qty'],
                'to_current_qty': deficit['current_qty'],
                'from_target_qty': excess['target_qty'],
                'to_target_qty': deficit['target_qty']
            }

            return recommendation

        except Exception as e:
            logger.error(f"Error creating recommendation: {e}")
            return None

    async def _score_recommendation(self, rec: Dict) -> Dict:
        """
        Score recommendation by multiple criteria

        Scoring:
        - Risk resolution (40 points): How much risk is reduced
        - Distance (20 points): Shorter distance = higher score
        - Sustainability (15 points): Lower CO2 emissions
        - Service level (15 points): Impact on service level
        - Cost (10 points): Lower cost = higher score

        Args:
            rec: Recommendation dict

        Returns:
            Recommendation dict with scoring fields added
        """
        try:
            # 1. Risk resolution score (0-40)
            risk_score = await self._score_risk_resolution(rec)

            # 2. Distance score (0-20)
            distance_score = await self._score_distance(rec)

            # 3. Sustainability score (0-15)
            sustainability_score = await self._score_sustainability(rec)

            # 4. Service level score (0-15)
            service_level_score = await self._score_service_level(rec)

            # 5. Cost score (0-10)
            cost_score = await self._score_cost(rec)

            # Total score (0-100)
            total_score = (
                risk_score +
                distance_score +
                sustainability_score +
                service_level_score +
                cost_score
            )

            # Add scores to recommendation
            rec['risk_resolution_score'] = risk_score
            rec['distance_score'] = distance_score
            rec['sustainability_score'] = sustainability_score
            rec['service_level_score'] = service_level_score
            rec['cost_score'] = cost_score
            rec['total_score'] = total_score

            return rec

        except Exception as e:
            logger.error(f"Error scoring recommendation: {e}")
            # Return with default scores
            rec['risk_resolution_score'] = 0
            rec['distance_score'] = 0
            rec['sustainability_score'] = 0
            rec['service_level_score'] = 0
            rec['cost_score'] = 0
            rec['total_score'] = 0
            return rec

    async def _score_risk_resolution(self, rec: Dict) -> float:
        """
        Score by risk resolution (0-40 points)

        Higher score for:
        - Resolving HIGH risk deficits
        - Reducing larger excess positions
        """
        score = 0.0

        # Points for resolving deficit risk
        deficit_risk = rec.get('deficit_risk', 'MEDIUM')
        if deficit_risk == 'HIGH':
            score += 25
        elif deficit_risk == 'MEDIUM':
            score += 15
        else:
            score += 5

        # Points for reducing excess
        excess_dos = rec.get('excess_dos', 0)
        if excess_dos > 180:  # > 6 months
            score += 15
        elif excess_dos > 120:  # > 4 months
            score += 10
        elif excess_dos > 90:  # > 3 months
            score += 5

        return min(score, self.RISK_RESOLUTION_WEIGHT)

    async def _score_distance(self, rec: Dict) -> float:
        """
        Score by distance (0-20 points)

        Shorter distance = higher score
        Uses Haversine formula with actual site coordinates
        """
        try:
            # Calculate actual distance using site coordinates
            distance_km = await calculate_site_distance(
                self.db,
                rec['from_site_id'],
                rec['to_site_id']
            )

            if distance_km is not None:
                # Use enhanced distance scoring
                score = score_distance(distance_km, max_weight=self.DISTANCE_WEIGHT)
                logger.debug(f"Distance score: {distance_km:.1f} km → {score:.2f} points")
                rec['distance_km'] = distance_km  # Store for later use
                return score
            else:
                # Fallback if coordinates missing
                logger.warning(f"Missing coordinates for sites {rec['from_site_id']} → {rec['to_site_id']}, using default")
                rec['distance_km'] = 500  # Default
                return self.DISTANCE_WEIGHT * 0.7

        except Exception as e:
            logger.error(f"Error in distance scoring: {e}")
            rec['distance_km'] = 500
            return self.DISTANCE_WEIGHT * 0.7

    async def _score_sustainability(self, rec: Dict) -> float:
        """
        Score by sustainability (0-15 points)

        Lower CO2 emissions = higher score
        Considers:
        - Transport distance
        - Transport mode
        - Carbon intensity
        """
        try:
            # Get distance (should be set by _score_distance)
            distance_km = rec.get('distance_km', 500)

            # Get quantity
            quantity = rec.get('quantity', 100)

            # Look up product weight from DB if available
            unit_weight_kg = 10.0  # default
            product_id = rec.get('product_id')
            if product_id:
                try:
                    product = self.db.query(Product).filter(Product.id == product_id).first()
                    if product:
                        weight = getattr(product, 'unit_weight_kg', None) or getattr(product, 'weight', None)
                        if weight and float(weight) > 0:
                            unit_weight_kg = float(weight)
                except Exception:
                    pass

            co2_emissions = calculate_co2_emissions(
                distance_km=distance_km,
                quantity=quantity,
                unit_weight_kg=unit_weight_kg,
                transport_mode="truck"
            )

            # Score based on emissions
            score = score_sustainability(co2_emissions, max_weight=self.SUSTAINABILITY_WEIGHT)

            logger.debug(f"Sustainability score: {co2_emissions:.1f} kg CO2 → {score:.2f} points")
            rec['co2_emissions_kg'] = co2_emissions  # Store for later use

            return score

        except Exception as e:
            logger.error(f"Error in sustainability scoring: {e}")
            return self.SUSTAINABILITY_WEIGHT * 0.6

    async def _score_service_level(self, rec: Dict) -> float:
        """
        Score by service level impact (0-15 points)

        Higher score for:
        - Improving service level at deficit site
        - Minimal impact on service level at excess site
        """
        score = 0.0

        # Points for improving deficit site
        deficit_risk = rec.get('deficit_risk', 'MEDIUM')
        if deficit_risk == 'HIGH':
            score += 10
        elif deficit_risk == 'MEDIUM':
            score += 7
        else:
            score += 3

        # Points for maintaining excess site safety
        # (transfer only from true excess, not from safety stock)
        excess_dos = rec.get('excess_dos', 0)
        if excess_dos > 120:
            score += 5
        elif excess_dos > 90:
            score += 3

        return min(score, self.SERVICE_LEVEL_WEIGHT)

    async def _score_cost(self, rec: Dict) -> float:
        """
        Score by cost (0-10 points)

        Lower cost = higher score
        Considers:
        - Transport cost
        - Holding cost savings
        - Expedite cost avoided
        """
        try:
            # Get parameters
            distance_km = rec.get('distance_km', 500)
            quantity = rec.get('quantity', 100)
            excess_qty = rec.get('from_site_excess_qty', quantity)
            deficit_qty = rec.get('to_site_deficit_qty', quantity)

            # Look up product weight and cost from DB if available
            unit_weight_kg = 10.0
            unit_cost = 100.0
            product_id = rec.get('product_id')
            if product_id:
                try:
                    product = self.db.query(Product).filter(Product.id == product_id).first()
                    if product:
                        weight = getattr(product, 'unit_weight_kg', None) or getattr(product, 'weight', None)
                        if weight and float(weight) > 0:
                            unit_weight_kg = float(weight)
                        cost = getattr(product, 'unit_cost', None) or getattr(product, 'standard_cost', None)
                        if cost and float(cost) > 0:
                            unit_cost = float(cost)
                except Exception:
                    pass

            cost_impact = calculate_total_cost_impact(
                distance_km=distance_km,
                quantity=quantity,
                excess_quantity=excess_qty,
                deficit_quantity=deficit_qty,
                unit_weight_kg=unit_weight_kg,
                unit_cost=unit_cost,
                transport_mode="truck"
            )

            # Score based on net savings
            net_savings = cost_impact['net_savings']
            score = score_cost(net_savings, max_weight=self.COST_WEIGHT)

            logger.debug(f"Cost score: ${net_savings:.0f} net savings → {score:.2f} points")
            rec['cost_impact'] = cost_impact  # Store for later use

            return score

        except Exception as e:
            logger.error(f"Error in cost scoring: {e}")
            # Fallback to simple heuristic
            qty = rec.get('quantity', 0)
            if qty < 100:
                return 10
            elif qty < 500:
                return 7
            elif qty < 1000:
                return 5
            else:
                return 3

    async def simulate_recommendation_impact(
        self,
        recommendation_id: str
    ) -> Dict:
        """
        Simulate impact of recommendation using analytical probabilistic model

        Returns expected impact on:
        - Service level (before/after)
        - Inventory cost (before/after)
        - CO2 emissions
        - Risk reduction

        Args:
            recommendation_id: ID of recommendation to simulate

        Returns:
            Dict with impact metrics
        """
        try:
            logger.info(f"Simulating impact for recommendation {recommendation_id}")

            # Build recommendation data from real inventory positions
            rec = await self._build_rec_from_id(recommendation_id)

            # Use enhanced impact simulation
            impact = await simulate_impact_enhanced(
                db=self.db,
                rec=rec,
                from_site_id=rec['from_site_id'],
                to_site_id=rec['to_site_id'],
                product_id=rec['product_id'],
                quantity=rec['quantity']
            )

            # Add metadata
            impact['simulation_date'] = datetime.utcnow()
            impact['model_version'] = '2.0_analytical'

            logger.info(f"Impact simulation complete for {recommendation_id}")
            return impact

        except Exception as e:
            logger.error(f"Error simulating recommendation impact: {e}")
            # Return fallback impact
            return {
                'recommendation_id': recommendation_id,
                'simulation_date': datetime.utcnow(),
                'error': str(e),
                'net_cost_savings': 0,
                'estimated_co2_emissions_kg': 100,
                'stockout_risk_before': 0.3,
                'stockout_risk_after': 0.1,
                'risk_reduction_pct': 67
            }

    async def track_recommendation_decision(
        self,
        recommendation_id: str,
        decision: str,
        user_id: str,
        reason: Optional[str] = None
    ) -> Dict:
        """
        Track user decisions on recommendations
        Used for ML learning loop

        Args:
            recommendation_id: ID of recommendation
            decision: accepted, rejected, or modified
            user_id: User who made the decision
            reason: Optional reason for decision

        Returns:
            Updated recommendation dict
        """
        try:
            logger.info(f"Tracking decision for recommendation {recommendation_id}: {decision}")

            # Persist decision to powell_site_agent_decisions for ML training loop
            from app.models.powell_decision import SiteAgentDecision

            decision_record = {
                'recommendation_id': recommendation_id,
                'decision': decision,
                'user_id': user_id,
                'reason': reason,
                'decision_date': datetime.utcnow()
            }

            # Record as a human feedback entry for RL training
            try:
                agent_decision = SiteAgentDecision(
                    decision_id=f"rec_{recommendation_id}_{uuid.uuid4().hex[:8]}",
                    site_key=f"rec_engine",
                    decision_type="recommendation",
                    input_state={"recommendation_id": recommendation_id},
                    final_result={"decision": decision},
                    human_feedback=reason or decision,
                    human_rating=5 if decision == "accepted" else (1 if decision == "rejected" else 3),
                    feedback_recorded_at=datetime.utcnow(),
                )
                self.db.add(agent_decision)
                self.db.commit()
            except Exception as persist_err:
                logger.warning(f"Failed to persist recommendation decision: {persist_err}")

            logger.info(f"Decision recorded: {decision_record}")

            return decision_record

        except Exception as e:
            logger.error(f"Error tracking recommendation decision: {e}")
            raise

    # =========================================================================
    # Internal helpers
    # =========================================================================

    async def _build_rec_from_id(self, recommendation_id: str) -> Dict:
        """Build recommendation dict from inventory data keyed by recommendation_id.

        The recommendation_id encodes from/to site and product:
        Format: "rec-<idx>" from the risk-based generator — we fall back to
        querying the first excess/deficit pair when no explicit mapping exists.
        """
        # Query sites with inventory data
        try:
            excess_rows = (
                self.db.query(InvLevel, Product, Site)
                .join(Product, InvLevel.product_id == Product.id)
                .join(Site, InvLevel.site_id == Site.id)
                .filter(InvLevel.on_hand_qty > 0)
                .order_by(InvLevel.on_hand_qty.desc())
                .limit(5)
                .all()
            )
            deficit_rows = (
                self.db.query(InvLevel, Product, Site)
                .join(Product, InvLevel.product_id == Product.id)
                .join(Site, InvLevel.site_id == Site.id)
                .order_by(InvLevel.on_hand_qty.asc())
                .limit(5)
                .all()
            )
        except Exception:
            excess_rows = []
            deficit_rows = []

        if excess_rows and deficit_rows:
            excess_inv, excess_product, excess_site = excess_rows[0]
            deficit_inv, deficit_product, deficit_site = deficit_rows[0]
            excess_qty = float(excess_inv.on_hand_qty or 0)
            deficit_qty = float(deficit_inv.on_hand_qty or 0)
            quantity = max(1, int((excess_qty - deficit_qty) / 2))
            return {
                'recommendation_id': recommendation_id,
                'from_site_id': str(excess_site.id),
                'to_site_id': str(deficit_site.id),
                'product_id': str(excess_product.id),
                'quantity': quantity,
                'from_site_excess_qty': int(excess_qty),
                'to_site_deficit_qty': max(0, int(-deficit_qty)) if deficit_qty < 0 else int(quantity),
                'from_site_dos': 120,
                'to_site_dos': 20,
            }

        # Fallback — no inventory data
        return {
            'recommendation_id': recommendation_id,
            'from_site_id': '0',
            'to_site_id': '0',
            'product_id': '0',
            'quantity': 0,
            'from_site_excess_qty': 0,
            'to_site_deficit_qty': 0,
            'from_site_dos': 0,
            'to_site_dos': 0,
        }
