"""
Unit Tests for Recommendations Scoring Algorithms
Tests distance, sustainability, cost, and impact simulation calculations
"""

import pytest
import math
from app.services.recommendations_scoring import (
    calculate_haversine_distance,
    score_distance,
    calculate_co2_emissions,
    score_sustainability,
    calculate_transport_cost,
    calculate_holding_cost_savings,
    calculate_expedite_cost_avoided,
    calculate_total_cost_impact,
    score_cost,
    simulate_service_level_impact,
    simulate_stockout_risk_reduction,
    CO2_FACTORS
)


# ============================================================================
# Distance Calculation Tests
# ============================================================================

class TestHaversineDistance:
    """Test Haversine distance calculation"""

    def test_zero_distance(self):
        """Same point should have zero distance"""
        distance = calculate_haversine_distance(40.7128, -74.0060, 40.7128, -74.0060)
        assert distance == 0.0

    def test_known_distance_ny_la(self):
        """Test known distance: New York to Los Angeles"""
        # New York: 40.7128° N, 74.0060° W
        # Los Angeles: 34.0522° N, 118.2437° W
        distance = calculate_haversine_distance(40.7128, -74.0060, 34.0522, -118.2437)

        # Actual great-circle distance is ~3,944 km
        # Allow 1% tolerance
        assert 3900 < distance < 4000

    def test_known_distance_london_paris(self):
        """Test known distance: London to Paris"""
        # London: 51.5074° N, 0.1278° W
        # Paris: 48.8566° N, 2.3522° E
        distance = calculate_haversine_distance(51.5074, -0.1278, 48.8566, 2.3522)

        # Actual distance is ~344 km
        assert 340 < distance < 350

    def test_antipodal_points(self):
        """Test maximum distance (opposite sides of Earth)"""
        # Point and its antipode
        distance = calculate_haversine_distance(0, 0, 0, 180)

        # Half Earth's circumference (~20,000 km)
        assert 19800 < distance < 20200

    def test_negative_coordinates(self):
        """Test with negative coordinates (Southern/Western hemispheres)"""
        # Sydney: 33.8688° S, 151.2093° E
        # Buenos Aires: 34.6037° S, 58.3816° W
        distance = calculate_haversine_distance(-33.8688, 151.2093, -34.6037, -58.3816)

        # Actual distance is ~11,600 km
        assert 11400 < distance < 11800


class TestDistanceScoring:
    """Test distance-based scoring logic"""

    def test_local_transfer_full_score(self):
        """Local transfer (< 100 km) should get full score"""
        score = score_distance(50, max_weight=20.0)
        assert score == 20.0

    def test_regional_transfer_high_score(self):
        """Regional transfer (100-500 km) should get 80-100% score"""
        score = score_distance(300, max_weight=20.0)
        assert 16.0 <= score <= 20.0

    def test_inter_regional_medium_score(self):
        """Inter-regional (500-1500 km) should get 50-80% score"""
        score = score_distance(1000, max_weight=20.0)
        assert 10.0 <= score <= 16.0

    def test_cross_country_low_score(self):
        """Cross-country (1500-3000 km) should get 25-50% score"""
        score = score_distance(2000, max_weight=20.0)
        assert 5.0 <= score <= 10.0

    def test_international_very_low_score(self):
        """International (3000+ km) should get 0-25% score"""
        score = score_distance(5000, max_weight=20.0)
        assert 0.0 <= score <= 5.0

    def test_extreme_distance_non_negative(self):
        """Extreme distance should not produce negative score"""
        score = score_distance(15000, max_weight=20.0)
        assert score >= 0.0

    def test_custom_max_weight(self):
        """Score should scale with max_weight"""
        score_10 = score_distance(50, max_weight=10.0)
        score_20 = score_distance(50, max_weight=20.0)
        assert score_10 == 10.0
        assert score_20 == 20.0


# ============================================================================
# CO2 Emissions Tests
# ============================================================================

class TestCO2Emissions:
    """Test CO2 emissions calculation"""

    def test_truck_emissions(self):
        """Test truck emissions calculation"""
        # 100 km, 100 units of 10 kg each = 1 ton
        emissions = calculate_co2_emissions(
            distance_km=100,
            quantity=100,
            unit_weight_kg=10.0,
            transport_mode="truck"
        )

        # Expected: 100 km * 1 ton * 0.062 kg/ton-km = 6.2 kg CO2
        assert abs(emissions - 6.2) < 0.01

    def test_rail_lower_than_truck(self):
        """Rail should have lower emissions than truck"""
        params = {
            "distance_km": 500,
            "quantity": 200,
            "unit_weight_kg": 10.0
        }

        truck_emissions = calculate_co2_emissions(**params, transport_mode="truck")
        rail_emissions = calculate_co2_emissions(**params, transport_mode="rail")

        assert rail_emissions < truck_emissions

    def test_air_highest_emissions(self):
        """Air cargo should have highest emissions"""
        params = {
            "distance_km": 1000,
            "quantity": 100,
            "unit_weight_kg=": 10.0
        }

        truck = calculate_co2_emissions(distance_km=1000, quantity=100, unit_weight_kg=10.0, transport_mode="truck")
        rail = calculate_co2_emissions(distance_km=1000, quantity=100, unit_weight_kg=10.0, transport_mode="rail")
        ship = calculate_co2_emissions(distance_km=1000, quantity=100, unit_weight_kg=10.0, transport_mode="ship")
        air = calculate_co2_emissions(distance_km=1000, quantity=100, unit_weight_kg=10.0, transport_mode="air")

        assert air > truck > rail > ship

    def test_zero_quantity(self):
        """Zero quantity should produce zero emissions"""
        emissions = calculate_co2_emissions(
            distance_km=1000,
            quantity=0,
            unit_weight_kg=10.0,
            transport_mode="truck"
        )
        assert emissions == 0.0

    def test_linear_scaling_with_quantity(self):
        """Emissions should scale linearly with quantity"""
        base = calculate_co2_emissions(100, 100, 10.0, "truck")
        double = calculate_co2_emissions(100, 200, 10.0, "truck")

        assert abs(double - 2 * base) < 0.01

    def test_linear_scaling_with_distance(self):
        """Emissions should scale linearly with distance"""
        base = calculate_co2_emissions(100, 100, 10.0, "truck")
        double = calculate_co2_emissions(200, 100, 10.0, "truck")

        assert abs(double - 2 * base) < 0.01


class TestSustainabilityScoring:
    """Test sustainability scoring logic"""

    def test_excellent_low_emissions(self):
        """Low emissions (< 50 kg) should get full score"""
        score = score_sustainability(30, max_weight=15.0)
        assert score == 15.0

    def test_good_medium_emissions(self):
        """Medium emissions (50-200 kg) should get 75-100% score"""
        score = score_sustainability(100, max_weight=15.0)
        assert 11.25 <= score <= 15.0

    def test_poor_high_emissions(self):
        """High emissions (500-1000 kg) should get 25-50% score"""
        score = score_sustainability(750, max_weight=15.0)
        assert 3.75 <= score <= 7.5

    def test_very_poor_extreme_emissions(self):
        """Very high emissions (1000+ kg) should get 0-25% score"""
        score = score_sustainability(2000, max_weight=15.0)
        assert 0.0 <= score <= 3.75

    def test_non_negative_score(self):
        """Score should never be negative"""
        score = score_sustainability(10000, max_weight=15.0)
        assert score >= 0.0


# ============================================================================
# Cost Calculation Tests
# ============================================================================

class TestTransportCost:
    """Test transport cost calculation"""

    def test_truck_cost_components(self):
        """Truck cost should include variable + fixed components"""
        cost = calculate_transport_cost(
            distance_km=100,
            quantity=100,  # 1 ton
            unit_weight_kg=10.0,
            transport_mode="truck"
        )

        # Expected: 100 km * 1 ton * $0.15/km/ton + $50 = $65
        assert abs(cost - 65.0) < 0.01

    def test_rail_higher_fixed_cost(self):
        """Rail should have higher fixed cost than truck"""
        truck_cost = calculate_transport_cost(10, 10, 10.0, "truck")  # Short distance
        rail_cost = calculate_transport_cost(10, 10, 10.0, "rail")

        # For very short distance, rail fixed cost dominates
        assert rail_cost > truck_cost

    def test_rail_cheaper_long_distance(self):
        """Rail should be cheaper than truck for long distances"""
        truck_cost = calculate_transport_cost(2000, 1000, 10.0, "truck")
        rail_cost = calculate_transport_cost(2000, 1000, 10.0, "rail")

        assert rail_cost < truck_cost

    def test_ship_cheapest_variable_cost(self):
        """Ship should have lowest variable cost"""
        # For very long distance with high weight, ship should be cheapest
        distance = 5000
        quantity = 10000  # 100 tons

        truck = calculate_transport_cost(distance, quantity, 10.0, "truck")
        rail = calculate_transport_cost(distance, quantity, 10.0, "rail")
        ship = calculate_transport_cost(distance, quantity, 10.0, "ship")

        assert ship < rail < truck


class TestHoldingCostSavings:
    """Test holding cost savings calculation"""

    def test_basic_calculation(self):
        """Test basic holding cost savings"""
        savings = calculate_holding_cost_savings(
            excess_quantity=100,
            unit_holding_cost_per_day=0.10,
            days_saved=30
        )

        # 100 units * $0.10/day * 30 days = $300
        assert savings == 300.0

    def test_zero_quantity(self):
        """Zero quantity should produce zero savings"""
        savings = calculate_holding_cost_savings(0, 0.10, 30)
        assert savings == 0.0

    def test_linear_scaling(self):
        """Savings should scale linearly with quantity and days"""
        base = calculate_holding_cost_savings(100, 0.10, 30)
        double_qty = calculate_holding_cost_savings(200, 0.10, 30)
        double_days = calculate_holding_cost_savings(100, 0.10, 60)

        assert double_qty == 2 * base
        assert double_days == 2 * base


class TestExpediteCostAvoided:
    """Test expedite cost avoided calculation"""

    def test_basic_calculation(self):
        """Test basic expedite cost calculation"""
        avoided = calculate_expedite_cost_avoided(
            deficit_quantity=100,
            unit_cost=100.0,
            expedite_premium=0.20
        )

        # 100 units * $100/unit * 20% = $2000
        assert avoided == 2000.0

    def test_higher_premium(self):
        """Higher expedite premium should increase cost avoided"""
        low_premium = calculate_expedite_cost_avoided(100, 100.0, 0.10)
        high_premium = calculate_expedite_cost_avoided(100, 100.0, 0.30)

        assert high_premium > low_premium


class TestTotalCostImpact:
    """Test comprehensive cost impact calculation"""

    def test_positive_net_savings(self):
        """Test scenario with positive net savings"""
        impact = calculate_total_cost_impact(
            distance_km=100,      # Short distance
            quantity=100,
            excess_quantity=500,
            deficit_quantity=100,
            unit_weight_kg=10.0,
            unit_cost=100.0,
            transport_mode="truck"
        )

        assert "transport_cost" in impact
        assert "holding_cost_savings" in impact
        assert "expedite_cost_avoided" in impact
        assert "net_savings" in impact
        assert "roi" in impact

        # Holding + expedite should exceed transport cost
        assert impact["net_savings"] > 0

    def test_negative_net_savings_long_distance(self):
        """Long distance might produce negative net savings"""
        impact = calculate_total_cost_impact(
            distance_km=5000,     # Very long distance
            quantity=10,          # Small quantity
            excess_quantity=20,
            deficit_quantity=10,
            unit_weight_kg=10.0,
            unit_cost=100.0,
            transport_mode="air"  # Expensive mode
        )

        # High transport cost might exceed savings
        assert impact["transport_cost"] > 0


class TestCostScoring:
    """Test cost-based scoring logic"""

    def test_high_savings_full_score(self):
        """High savings (> $5000) should get full score"""
        score = score_cost(6000, max_weight=10.0)
        assert score == 10.0

    def test_medium_savings_medium_score(self):
        """Medium savings ($1000-$5000) should get 60-100% score"""
        score = score_cost(3000, max_weight=10.0)
        assert 6.0 <= score <= 10.0

    def test_break_even_low_score(self):
        """Break-even (near $0) should get 30% score"""
        score = score_cost(0, max_weight=10.0)
        assert abs(score - 3.0) < 0.5

    def test_loss_very_low_score(self):
        """Loss (negative savings) should get 0-30% score"""
        score = score_cost(-300, max_weight=10.0)
        assert 0.0 <= score <= 3.0

    def test_large_loss_minimal_score(self):
        """Large loss should approach zero score"""
        score = score_cost(-2000, max_weight=10.0)
        assert 0.0 <= score <= 1.0


# ============================================================================
# Impact Simulation Tests
# ============================================================================

class TestServiceLevelImpact:
    """Test service level impact simulation"""

    def test_improving_deficit_site(self):
        """Transfer should improve service level at deficit site"""
        impact = simulate_service_level_impact(
            from_site_dos_before=120,  # Excess
            to_site_dos_before=20,     # Deficit
            transfer_quantity=500,
            from_site_demand_rate=10,
            to_site_demand_rate=50,
            safety_stock=30
        )

        assert impact["to_site_sl_change"] > 0  # Improvement
        assert impact["to_site_service_level_after"] > impact["to_site_service_level_before"]

    def test_minimal_impact_on_source(self):
        """Transfer from excess should minimally impact source"""
        impact = simulate_service_level_impact(
            from_site_dos_before=180,  # Large excess
            to_site_dos_before=15,
            transfer_quantity=100,
            from_site_demand_rate=5,
            to_site_demand_rate=20,
            safety_stock=30
        )

        # Source should still have good service level
        assert impact["from_site_service_level_after"] > 90.0

    def test_net_improvement_positive(self):
        """Net improvement should be positive for good transfers"""
        impact = simulate_service_level_impact(
            from_site_dos_before=150,
            to_site_dos_before=10,
            transfer_quantity=300,
            from_site_demand_rate=10,
            to_site_demand_rate=30,
            safety_stock=30
        )

        # Benefit at destination > harm at source
        assert impact["net_sl_improvement"] > 0


class TestStockoutRiskReduction:
    """Test stockout risk reduction calculation"""

    def test_risk_reduction_from_transfer(self):
        """Transfer should reduce stockout risk"""
        impact = simulate_stockout_risk_reduction(
            to_site_dos_before=15,   # Low DOS
            to_site_dos_after=45,    # Improved DOS
            safety_stock_days=30,
            demand_variability_cv=0.3
        )

        assert impact["stockout_risk_after"] < impact["stockout_risk_before"]
        assert impact["risk_reduction_pct"] > 0

    def test_high_risk_when_low_dos(self):
        """Low DOS should produce high stockout risk"""
        impact = simulate_stockout_risk_reduction(
            to_site_dos_before=5,    # Very low
            to_site_dos_after=10,
            safety_stock_days=30,
            demand_variability_cv=0.3
        )

        assert impact["stockout_risk_before"] > 0.5  # High risk

    def test_low_risk_when_high_dos(self):
        """High DOS should produce low stockout risk"""
        impact = simulate_stockout_risk_reduction(
            to_site_dos_before=90,   # High DOS
            to_site_dos_after=100,
            safety_stock_days=30,
            demand_variability_cv=0.3
        )

        assert impact["stockout_risk_before"] < 0.2  # Low risk

    def test_higher_variability_increases_risk(self):
        """Higher demand variability should increase risk"""
        low_cv = simulate_stockout_risk_reduction(20, 30, 30, 0.1)
        high_cv = simulate_stockout_risk_reduction(20, 30, 30, 0.5)

        assert high_cv["stockout_risk_before"] > low_cv["stockout_risk_before"]


# ============================================================================
# Integration Tests
# ============================================================================

class TestScoringIntegration:
    """Test integrated scoring scenarios"""

    def test_optimal_local_transfer(self):
        """Local transfer with high savings should score highly"""
        # Distance score
        dist_score = score_distance(50, max_weight=20.0)

        # CO2 score
        co2 = calculate_co2_emissions(50, 100, 10.0, "truck")
        sust_score = score_sustainability(co2, max_weight=15.0)

        # Cost score
        cost_impact = calculate_total_cost_impact(50, 100, 500, 100, 10.0, 100.0, "truck")
        cost_score = score_cost(cost_impact["net_savings"], max_weight=10.0)

        total = dist_score + sust_score + cost_score

        # Should be high score (> 35/45 points)
        assert total > 35.0

    def test_poor_international_transfer(self):
        """Long-distance expensive transfer should score poorly"""
        # Distance score
        dist_score = score_distance(8000, max_weight=20.0)

        # CO2 score
        co2 = calculate_co2_emissions(8000, 100, 10.0, "air")
        sust_score = score_sustainability(co2, max_weight=15.0)

        # Cost score (likely negative savings)
        cost_impact = calculate_total_cost_impact(8000, 100, 200, 100, 10.0, 100.0, "air")
        cost_score = score_cost(cost_impact["net_savings"], max_weight=10.0)

        total = dist_score + sust_score + cost_score

        # Should be low score (< 15/45 points)
        assert total < 15.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
