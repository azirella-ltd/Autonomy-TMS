"""
Enhanced Recommendations Scoring Algorithms
Sprint 7: Algorithm Refinements

Replaces heuristic scoring with actual calculations for:
- Distance (Haversine formula using site coordinates)
- Sustainability (CO2 emissions based on transport mode and distance)
- Cost (Transport + holding + expedite costs)
- Impact simulation (Analytical model with probabilistic estimates)
"""

import math
from typing import Dict, Optional, Tuple
from datetime import timedelta
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import select
import logging

from app.models.sc_entities import Product
from app.models.supply_chain_config import Site

logger = logging.getLogger(__name__)


# ============================================================================
# Distance Calculation
# ============================================================================

def calculate_haversine_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    """
    Calculate great-circle distance between two points using Haversine formula

    Args:
        lat1: Latitude of point 1 (degrees)
        lon1: Longitude of point 1 (degrees)
        lat2: Latitude of point 2 (degrees)
        lon2: Longitude of point 2 (degrees)

    Returns:
        Distance in kilometers
    """
    # Earth radius in kilometers
    R = 6371.0

    # Convert to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    # Differences
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    # Haversine formula
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance_km = R * c

    return distance_km


async def calculate_site_distance(
    db: Session,
    from_site_id: str,
    to_site_id: str
) -> Optional[float]:
    """
    Calculate distance between two sites using their coordinates

    Args:
        db: Database session
        from_site_id: Source site ID
        to_site_id: Destination site ID

    Returns:
        Distance in kilometers, or None if coordinates missing
    """
    try:
        # Get sites
        from_site = await db.get(Site, from_site_id)
        to_site = await db.get(Site, to_site_id)

        if not from_site or not to_site:
            logger.warning(f"Site not found: from={from_site_id}, to={to_site_id}")
            return None

        # Check for coordinates
        if (from_site.latitude is None or from_site.longitude is None or
            to_site.latitude is None or to_site.longitude is None):
            logger.warning(f"Missing coordinates for sites: from={from_site_id}, to={to_site_id}")
            return None

        # Calculate distance
        distance = calculate_haversine_distance(
            from_site.latitude,
            from_site.longitude,
            to_site.latitude,
            to_site.longitude
        )

        return distance

    except Exception as e:
        logger.error(f"Error calculating site distance: {e}")
        return None


def score_distance(distance_km: float, max_weight: float = 20.0) -> float:
    """
    Score transfer by distance (shorter = better)

    Scoring logic:
    - 0-100 km: Full score (excellent - local transfer)
    - 100-500 km: 80-100% score (good - regional transfer)
    - 500-1500 km: 50-80% score (medium - inter-regional)
    - 1500-3000 km: 25-50% score (poor - cross-country)
    - 3000+ km: 0-25% score (very poor - international)

    Args:
        distance_km: Distance in kilometers
        max_weight: Maximum possible score (default: 20)

    Returns:
        Score from 0 to max_weight
    """
    if distance_km <= 100:
        score_pct = 1.0
    elif distance_km <= 500:
        # Linear decay from 100% to 80%
        score_pct = 1.0 - 0.2 * (distance_km - 100) / 400
    elif distance_km <= 1500:
        # Linear decay from 80% to 50%
        score_pct = 0.8 - 0.3 * (distance_km - 500) / 1000
    elif distance_km <= 3000:
        # Linear decay from 50% to 25%
        score_pct = 0.5 - 0.25 * (distance_km - 1500) / 1500
    else:
        # Linear decay from 25% to 0% (max 10,000 km)
        score_pct = max(0, 0.25 - 0.25 * (distance_km - 3000) / 7000)

    return max_weight * score_pct


# ============================================================================
# Sustainability / CO2 Calculation
# ============================================================================

# CO2 emission factors (kg CO2 per ton-km)
CO2_FACTORS = {
    "truck": 0.062,      # Average truck
    "rail": 0.022,       # Freight rail
    "ship": 0.008,       # Ocean freight
    "air": 0.500,        # Air cargo
    "intermodal": 0.030, # Mixed truck/rail
}


def calculate_co2_emissions(
    distance_km: float,
    quantity: float,
    unit_weight_kg: float = 10.0,
    transport_mode: str = "truck"
) -> float:
    """
    Calculate CO2 emissions for a transfer

    Args:
        distance_km: Distance in kilometers
        quantity: Number of units being transferred
        unit_weight_kg: Weight per unit in kg (default: 10 kg)
        transport_mode: truck, rail, ship, air, intermodal

    Returns:
        CO2 emissions in kg
    """
    # Total weight in tons
    total_weight_tons = (quantity * unit_weight_kg) / 1000.0

    # Emission factor
    emission_factor = CO2_FACTORS.get(transport_mode, CO2_FACTORS["truck"])

    # Total emissions (kg CO2)
    emissions_kg = distance_km * total_weight_tons * emission_factor

    return emissions_kg


def score_sustainability(
    co2_emissions_kg: float,
    max_weight: float = 15.0
) -> float:
    """
    Score transfer by sustainability (lower emissions = better)

    Scoring logic:
    - 0-50 kg CO2: Full score (excellent)
    - 50-200 kg CO2: 75-100% score (good)
    - 200-500 kg CO2: 50-75% score (medium)
    - 500-1000 kg CO2: 25-50% score (poor)
    - 1000+ kg CO2: 0-25% score (very poor)

    Args:
        co2_emissions_kg: CO2 emissions in kg
        max_weight: Maximum possible score (default: 15)

    Returns:
        Score from 0 to max_weight
    """
    if co2_emissions_kg <= 50:
        score_pct = 1.0
    elif co2_emissions_kg <= 200:
        # Linear decay from 100% to 75%
        score_pct = 1.0 - 0.25 * (co2_emissions_kg - 50) / 150
    elif co2_emissions_kg <= 500:
        # Linear decay from 75% to 50%
        score_pct = 0.75 - 0.25 * (co2_emissions_kg - 200) / 300
    elif co2_emissions_kg <= 1000:
        # Linear decay from 50% to 25%
        score_pct = 0.5 - 0.25 * (co2_emissions_kg - 500) / 500
    else:
        # Linear decay from 25% to 0% (max 5000 kg)
        score_pct = max(0, 0.25 - 0.25 * (co2_emissions_kg - 1000) / 4000)

    return max_weight * score_pct


# ============================================================================
# Cost Calculation
# ============================================================================

def calculate_transport_cost(
    distance_km: float,
    quantity: float,
    unit_weight_kg: float = 10.0,
    transport_mode: str = "truck"
) -> float:
    """
    Calculate transport cost for a transfer

    Cost model:
    - Truck: $0.15/km/ton + $50 fixed
    - Rail: $0.08/km/ton + $200 fixed
    - Ship: $0.02/km/ton + $500 fixed
    - Air: $1.50/km/ton + $300 fixed

    Args:
        distance_km: Distance in kilometers
        quantity: Number of units
        unit_weight_kg: Weight per unit in kg
        transport_mode: truck, rail, ship, air

    Returns:
        Total transport cost in USD
    """
    # Total weight in tons
    total_weight_tons = (quantity * unit_weight_kg) / 1000.0

    # Cost per ton-km and fixed cost by mode
    cost_rates = {
        "truck": (0.15, 50),
        "rail": (0.08, 200),
        "ship": (0.02, 500),
        "air": (1.50, 300),
        "intermodal": (0.10, 150),
    }

    per_km_cost, fixed_cost = cost_rates.get(transport_mode, cost_rates["truck"])

    # Total cost
    variable_cost = distance_km * total_weight_tons * per_km_cost
    total_cost = variable_cost + fixed_cost

    return total_cost


def calculate_holding_cost_savings(
    excess_quantity: float,
    unit_holding_cost_per_day: float = 0.10,
    days_saved: int = 30
) -> float:
    """
    Calculate holding cost savings from reducing excess inventory

    Args:
        excess_quantity: Excess units being transferred out
        unit_holding_cost_per_day: Cost per unit per day (default: $0.10)
        days_saved: Days of holding cost avoided (default: 30)

    Returns:
        Holding cost savings in USD
    """
    savings = excess_quantity * unit_holding_cost_per_day * days_saved
    return savings


def calculate_expedite_cost_avoided(
    deficit_quantity: float,
    unit_cost: float = 100.0,
    expedite_premium: float = 0.20
) -> float:
    """
    Calculate expedite cost avoided by transferring from excess

    Args:
        deficit_quantity: Deficit units being fulfilled
        unit_cost: Base unit cost (default: $100)
        expedite_premium: % premium for expedited orders (default: 20%)

    Returns:
        Expedite cost avoided in USD
    """
    avoided_cost = deficit_quantity * unit_cost * expedite_premium
    return avoided_cost


def calculate_total_cost_impact(
    distance_km: float,
    quantity: float,
    excess_quantity: float,
    deficit_quantity: float,
    unit_weight_kg: float = 10.0,
    unit_cost: float = 100.0,
    transport_mode: str = "truck"
) -> Dict[str, float]:
    """
    Calculate comprehensive cost impact of a transfer

    Args:
        distance_km: Distance in kilometers
        quantity: Transfer quantity
        excess_quantity: Excess at source site
        deficit_quantity: Deficit at destination site
        unit_weight_kg: Weight per unit
        unit_cost: Base unit cost
        transport_mode: Transport mode

    Returns:
        Dict with cost breakdown
    """
    # Transport cost (negative - incurred)
    transport_cost = calculate_transport_cost(
        distance_km, quantity, unit_weight_kg, transport_mode
    )

    # Holding cost savings (positive - avoided)
    holding_savings = calculate_holding_cost_savings(
        quantity,  # Use actual transfer quantity
        unit_holding_cost_per_day=unit_cost * 0.001,  # 0.1% of unit cost per day
        days_saved=30
    )

    # Expedite cost avoided (positive - avoided)
    expedite_savings = calculate_expedite_cost_avoided(
        min(quantity, deficit_quantity),
        unit_cost=unit_cost,
        expedite_premium=0.20
    )

    # Net savings
    net_savings = holding_savings + expedite_savings - transport_cost

    return {
        "transport_cost": transport_cost,
        "holding_cost_savings": holding_savings,
        "expedite_cost_avoided": expedite_savings,
        "net_savings": net_savings,
        "roi": (net_savings / transport_cost * 100) if transport_cost > 0 else 0
    }


def score_cost(net_savings: float, max_weight: float = 10.0) -> float:
    """
    Score transfer by cost impact (higher savings = better)

    Scoring logic:
    - Net savings > $5000: Full score
    - Net savings $1000-$5000: 60-100% score
    - Net savings $0-$1000: 30-60% score
    - Net savings -$500-$0: 10-30% score
    - Net savings < -$500: 0-10% score

    Args:
        net_savings: Net cost savings in USD (positive = savings)
        max_weight: Maximum possible score (default: 10)

    Returns:
        Score from 0 to max_weight
    """
    if net_savings >= 5000:
        score_pct = 1.0
    elif net_savings >= 1000:
        # Linear from 60% to 100%
        score_pct = 0.6 + 0.4 * (net_savings - 1000) / 4000
    elif net_savings >= 0:
        # Linear from 30% to 60%
        score_pct = 0.3 + 0.3 * net_savings / 1000
    elif net_savings >= -500:
        # Linear from 10% to 30%
        score_pct = 0.1 + 0.2 * (net_savings + 500) / 500
    else:
        # Linear from 0% to 10% (max -$2000 loss)
        score_pct = max(0, 0.1 + 0.1 * (net_savings + 2000) / 1500)

    return max_weight * score_pct


# ============================================================================
# Impact Simulation (Analytical Model)
# ============================================================================

def simulate_service_level_impact(
    from_site_dos_before: float,
    to_site_dos_before: float,
    transfer_quantity: float,
    from_site_demand_rate: float,
    to_site_demand_rate: float,
    safety_stock: float
) -> Dict[str, float]:
    """
    Simulate service level impact using analytical model

    Args:
        from_site_dos_before: Days of supply at source (before transfer)
        to_site_dos_before: Days of supply at destination (before transfer)
        transfer_quantity: Transfer amount
        from_site_demand_rate: Daily demand at source
        to_site_demand_rate: Daily demand at destination
        safety_stock: Safety stock target

    Returns:
        Dict with before/after service levels
    """
    # Convert DOS to inventory
    from_inv_before = from_site_dos_before * from_site_demand_rate
    to_inv_before = to_site_dos_before * to_site_demand_rate

    # After transfer
    from_inv_after = from_inv_before - transfer_quantity
    to_inv_after = to_inv_before + transfer_quantity

    # Service level estimation (simplified)
    # Assumes service level correlates with inventory position relative to safety stock
    def estimate_service_level(inventory, demand_rate, safety_stock_target):
        dos = inventory / max(demand_rate, 1)
        if dos >= safety_stock_target * 2:
            return 99.5  # Excess inventory
        elif dos >= safety_stock_target:
            return 95.0 + 4.5 * (dos - safety_stock_target) / safety_stock_target
        elif dos >= safety_stock_target * 0.5:
            return 85.0 + 10.0 * (dos / safety_stock_target - 0.5)
        elif dos > 0:
            return 70.0 + 15.0 * (dos / (safety_stock_target * 0.5))
        else:
            return 50.0  # Stockout

    from_sl_before = estimate_service_level(from_inv_before, from_site_demand_rate, safety_stock)
    from_sl_after = estimate_service_level(from_inv_after, from_site_demand_rate, safety_stock)

    to_sl_before = estimate_service_level(to_inv_before, to_site_demand_rate, safety_stock)
    to_sl_after = estimate_service_level(to_inv_after, to_site_demand_rate, safety_stock)

    return {
        "from_site_service_level_before": from_sl_before,
        "from_site_service_level_after": from_sl_after,
        "from_site_sl_change": from_sl_after - from_sl_before,
        "to_site_service_level_before": to_sl_before,
        "to_site_service_level_after": to_sl_after,
        "to_site_sl_change": to_sl_after - to_sl_before,
        "net_sl_improvement": (to_sl_after - to_sl_before) - abs(from_sl_after - from_sl_before)
    }


def simulate_stockout_risk_reduction(
    to_site_dos_before: float,
    to_site_dos_after: float,
    safety_stock_days: float,
    demand_variability_cv: float = 0.3
) -> Dict[str, float]:
    """
    Estimate stockout risk reduction using probabilistic model

    Uses normal distribution assumption for demand variability.

    Args:
        to_site_dos_before: Days of supply before (at destination)
        to_site_dos_after: Days of supply after
        safety_stock_days: Safety stock in days
        demand_variability_cv: Coefficient of variation for demand (default: 0.3)

    Returns:
        Dict with stockout risk before/after and reduction percentage
    """
    def stockout_probability(dos, safety_stock_days, cv):
        """Estimate stockout probability using normal distribution"""
        if dos <= 0:
            return 0.95  # Very high risk

        # Z-score: how many standard deviations above zero
        # Higher DOS and lower variability = lower risk
        z = (dos - safety_stock_days) / (safety_stock_days * cv)

        # Approximate cumulative normal distribution
        # Using approximation: P(X < 0) ≈ 1 / (1 + exp(1.7*z))
        prob_stockout = 1.0 / (1.0 + math.exp(1.7 * z))

        # Clamp between 0.01 and 0.95
        return max(0.01, min(0.95, prob_stockout))

    risk_before = stockout_probability(to_site_dos_before, safety_stock_days, demand_variability_cv)
    risk_after = stockout_probability(to_site_dos_after, safety_stock_days, demand_variability_cv)

    risk_reduction_pct = ((risk_before - risk_after) / max(risk_before, 0.01)) * 100

    return {
        "stockout_risk_before": risk_before,
        "stockout_risk_after": risk_after,
        "risk_reduction_absolute": risk_before - risk_after,
        "risk_reduction_pct": risk_reduction_pct
    }


# ============================================================================
# Integrated Impact Simulation
# ============================================================================

async def simulate_recommendation_impact(
    db: Session,
    rec: Dict,
    from_site_id: str,
    to_site_id: str,
    product_id: str,
    quantity: float
) -> Dict:
    """
    Comprehensive impact simulation for a recommendation

    Combines all scoring models to provide realistic impact estimates.

    Args:
        db: Database session
        rec: Recommendation dict
        from_site_id: Source site ID
        to_site_id: Destination site ID
        product_id: Product ID
        quantity: Transfer quantity

    Returns:
        Dict with comprehensive impact metrics
    """
    try:
        # Get distance
        distance_km = await calculate_site_distance(db, from_site_id, to_site_id)
        if distance_km is None:
            distance_km = 500  # Default if coordinates missing

        # Get product for unit weight/cost
        product = await db.get(Product, product_id)
        unit_weight_kg = 10.0  # Default
        unit_cost = 100.0  # Default

        # Calculate costs
        cost_impact = calculate_total_cost_impact(
            distance_km=distance_km,
            quantity=quantity,
            excess_quantity=rec.get('from_site_excess_qty', quantity),
            deficit_quantity=rec.get('to_site_deficit_qty', quantity),
            unit_weight_kg=unit_weight_kg,
            unit_cost=unit_cost,
            transport_mode="truck"
        )

        # Calculate CO2
        co2_emissions = calculate_co2_emissions(
            distance_km=distance_km,
            quantity=quantity,
            unit_weight_kg=unit_weight_kg,
            transport_mode="truck"
        )

        # Service level impact (simplified - would need actual DOS data)
        from_dos = rec.get('from_site_dos', 120)  # Days
        to_dos = rec.get('to_site_dos', 20)  # Days
        from_demand_rate = rec.get('from_site_excess_qty', quantity) / max(from_dos, 1)
        to_demand_rate = rec.get('to_site_deficit_qty', quantity) / max(to_dos, 1)

        sl_impact = simulate_service_level_impact(
            from_site_dos_before=from_dos,
            to_site_dos_before=to_dos,
            transfer_quantity=quantity,
            from_site_demand_rate=from_demand_rate,
            to_site_demand_rate=to_demand_rate,
            safety_stock=30  # 30 days safety stock
        )

        # Stockout risk
        risk_impact = simulate_stockout_risk_reduction(
            to_site_dos_before=to_dos,
            to_site_dos_after=to_dos + (quantity / max(to_demand_rate, 1)),
            safety_stock_days=30,
            demand_variability_cv=0.3
        )

        return {
            "recommendation_id": rec.get('recommendation_id'),
            "distance_km": distance_km,

            # Service level
            "from_site_service_level_before": sl_impact["from_site_service_level_before"],
            "from_site_service_level_after": sl_impact["from_site_service_level_after"],
            "to_site_service_level_before": sl_impact["to_site_service_level_before"],
            "to_site_service_level_after": sl_impact["to_site_service_level_after"],
            "net_service_level_improvement": sl_impact["net_sl_improvement"],

            # Cost
            "transport_cost": cost_impact["transport_cost"],
            "holding_cost_savings": cost_impact["holding_cost_savings"],
            "expedite_cost_avoided": cost_impact["expedite_cost_avoided"],
            "net_cost_savings": cost_impact["net_savings"],
            "roi_percent": cost_impact["roi"],

            # Sustainability
            "estimated_co2_emissions_kg": co2_emissions,
            "co2_emissions_per_unit": co2_emissions / max(quantity, 1),

            # Risk
            "stockout_risk_before": risk_impact["stockout_risk_before"],
            "stockout_risk_after": risk_impact["stockout_risk_after"],
            "risk_reduction_pct": risk_impact["risk_reduction_pct"],
        }

    except Exception as e:
        logger.error(f"Error in impact simulation: {e}")
        # Return default impact if calculation fails
        return {
            "recommendation_id": rec.get('recommendation_id'),
            "error": str(e),
            "distance_km": 500,
            "net_cost_savings": 0,
            "estimated_co2_emissions_kg": 100,
            "stockout_risk_before": 0.3,
            "stockout_risk_after": 0.1,
            "risk_reduction_pct": 67
        }
