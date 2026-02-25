"""
Tests for SupplyBaselineService (unified supply baseline generation).

Validates:
- FULL mode generates 5+ candidates
- INPUT mode with customer plan
- BOM explosion conditionally invoked for manufacturer configs
- PolicyEnvelope safety stock integration
- Tradeoff frontier computation
- EOQ calculation
"""

import pytest
import math
from datetime import date, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

from app.services.planning_cascade.supply_baseline_service import (
    SupplyBaselineService,
    ProductInventoryState,
    SupplierInfo,
    CandidatePlan,
    ReplenishmentOrder,
)


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 0
    db.query.return_value.filter_by.return_value.first.return_value = None
    return db


@pytest.fixture
def sample_inventory():
    return [
        ProductInventoryState(
            sku="SKU-001",
            category="ambient",
            on_hand=500,
            in_transit=100,
            committed=50,
            avg_daily_demand=30,
            demand_std=10,
            unit_cost=10.0,
            min_order_qty=50,
        ),
        ProductInventoryState(
            sku="SKU-002",
            category="chilled",
            on_hand=200,
            in_transit=50,
            committed=20,
            avg_daily_demand=15,
            demand_std=5,
            unit_cost=25.0,
            min_order_qty=25,
        ),
    ]


@pytest.fixture
def sample_suppliers():
    return {
        "SKU-001": [
            SupplierInfo(
                supplier_id="SUP-A",
                lead_time_days=5,
                lead_time_variability=0.2,
                reliability=0.95,
                min_order_value=1000,
                unit_cost=10.0,
            )
        ],
        "SKU-002": [
            SupplierInfo(
                supplier_id="SUP-B",
                lead_time_days=7,
                lead_time_variability=0.3,
                reliability=0.90,
                min_order_value=500,
                unit_cost=25.0,
            )
        ],
    }


@pytest.fixture
def sample_forecast():
    return {
        "SKU-001": [30.0] * 28,
        "SKU-002": [15.0] * 28,
    }


@pytest.fixture
def service(mock_db):
    return SupplyBaselineService(mock_db, mode="FULL")


@pytest.fixture
def input_service(mock_db):
    return SupplyBaselineService(mock_db, mode="INPUT")


# ── FULL Mode Tests ───────────────────────────────────────────────────

class TestFullModeGeneration:
    """Test FULL mode candidate generation"""

    def test_generates_five_candidates_without_bom(
        self, service, sample_inventory, sample_suppliers, sample_forecast
    ):
        """Without manufacturer sites, generates exactly 5 candidates."""
        inv_by_sku = {p.sku: p for p in sample_inventory}
        candidates = service._generate_candidates(
            sample_inventory, sample_suppliers, sample_forecast,
        )
        assert len(candidates) == 5

    def test_candidate_methods_cover_all_strategies(
        self, service, sample_inventory, sample_suppliers, sample_forecast
    ):
        """All 5 standard methods are represented."""
        candidates = service._generate_candidates(
            sample_inventory, sample_suppliers, sample_forecast,
        )
        methods = {c.method for c in candidates}
        expected = {
            "REORDER_POINT_V1",
            "PERIODIC_REVIEW_V1",
            "MIN_COST_EOQ_V1",
            "SERVICE_MAXIMIZED_V1",
            "PARAMETRIC_CFA_V1",
        }
        assert methods == expected

    def test_each_candidate_has_orders(
        self, service, sample_inventory, sample_suppliers, sample_forecast
    ):
        """Each candidate produces at least some orders."""
        candidates = service._generate_candidates(
            sample_inventory, sample_suppliers, sample_forecast,
        )
        for c in candidates:
            assert isinstance(c.orders, list)
            assert isinstance(c.projected_inventory, dict)
            assert c.projected_cost >= 0
            assert 0 <= c.projected_otif <= 1.0
            assert c.projected_dos >= 0

    def test_candidate_to_dict_roundtrip(
        self, service, sample_inventory, sample_suppliers, sample_forecast
    ):
        """CandidatePlan.to_dict() produces serializable output."""
        candidates = service._generate_candidates(
            sample_inventory, sample_suppliers, sample_forecast,
        )
        for c in candidates:
            d = c.to_dict()
            assert d["method"] == c.method
            assert isinstance(d["orders"], list)
            assert "projected_cost" in d

    def test_tradeoff_frontier_sorted_by_cost(
        self, service, sample_inventory, sample_suppliers, sample_forecast
    ):
        """Tradeoff frontier is sorted by cost ascending."""
        candidates = service._generate_candidates(
            sample_inventory, sample_suppliers, sample_forecast,
        )
        frontier = service._compute_tradeoff_frontier(candidates)
        costs = [f["cost"] for f in frontier]
        assert costs == sorted(costs)
        assert len(frontier) == len(candidates)

    def test_min_cost_cheaper_than_service_max(
        self, service, sample_inventory, sample_suppliers, sample_forecast
    ):
        """Min cost plan should have lower cost than service-maximized."""
        candidates = service._generate_candidates(
            sample_inventory, sample_suppliers, sample_forecast,
        )
        by_method = {c.method: c for c in candidates}
        assert by_method["MIN_COST_EOQ_V1"].projected_cost < by_method["SERVICE_MAXIMIZED_V1"].projected_cost

    def test_service_max_higher_otif_than_min_cost(
        self, service, sample_inventory, sample_suppliers, sample_forecast
    ):
        """Service-maximized should have higher OTIF than min-cost."""
        candidates = service._generate_candidates(
            sample_inventory, sample_suppliers, sample_forecast,
        )
        by_method = {c.method: c for c in candidates}
        assert by_method["SERVICE_MAXIMIZED_V1"].projected_otif > by_method["MIN_COST_EOQ_V1"].projected_otif


# ── INPUT Mode Tests ──────────────────────────────────────────────────

class TestInputMode:
    """Test INPUT mode with customer plans"""

    def test_input_mode_requires_customer_plan(self, input_service):
        """INPUT mode raises if no customer plan provided."""
        with pytest.raises(ValueError, match="Customer plan required"):
            input_service.generate_supply_baseline_pack(
                config_id=1,
                customer_id=1,
                policy_envelope_id=1,
                policy_envelope_hash="abc123",
                inventory_state=[],
                supplier_info={},
                demand_forecast={},
            )

    def test_parse_customer_plan(self, input_service, sample_inventory):
        """Customer plan is parsed into a CandidatePlan."""
        customer_plan = [
            {
                "sku": "SKU-001",
                "supplier_id": "SUP-A",
                "destination_id": "DC-001",
                "qty": 100,
                "order_date": date.today().isoformat(),
                "receipt_date": (date.today() + timedelta(days=5)).isoformat(),
            }
        ]
        result = input_service._parse_customer_plan(customer_plan, sample_inventory)
        assert result.method == "CUSTOMER_UPLOAD"
        assert len(result.orders) == 1
        assert result.orders[0].sku == "SKU-001"
        assert result.orders[0].order_qty == 100


# ── BOM-Aware Tests ───────────────────────────────────────────────────

class TestBOMAwareCandidateGeneration:
    """Test conditional BOM explosion for manufacturer configs"""

    def test_no_mrp_candidate_without_manufacturers(
        self, service, sample_inventory, sample_suppliers, sample_forecast
    ):
        """No MRP_STANDARD_V1 candidate when no manufacturer sites."""
        candidates = service._generate_candidates(
            sample_inventory, sample_suppliers, sample_forecast,
            config_id=1,
        )
        methods = {c.method for c in candidates}
        assert "MRP_STANDARD_V1" not in methods

    def test_mrp_candidate_with_manufacturers(
        self, mock_db, sample_inventory, sample_suppliers, sample_forecast
    ):
        """MRP_STANDARD_V1 candidate added when manufacturers + BOM exist."""
        service = SupplyBaselineService(mock_db, mode="FULL")

        # Mock _has_manufacturer_sites to return True
        # Mock _generate_mrp_standard_plan to return a candidate
        with patch.object(service, '_has_manufacturer_sites', return_value=True):
            mrp_plan = CandidatePlan(
                method="MRP_STANDARD_V1",
                orders=[],
                projected_inventory={},
                projected_cost=100.0,
                projected_otif=0.93,
                projected_dos=14.0,
                policy_params={"strategy": "mrp_standard", "bom_levels": 2},
            )
            with patch.object(service, '_generate_mrp_standard_plan', return_value=mrp_plan):
                candidates = service._generate_candidates(
                    sample_inventory, sample_suppliers, sample_forecast,
                    config_id=1,
                )

        methods = {c.method for c in candidates}
        assert "MRP_STANDARD_V1" in methods
        assert len(candidates) == 6

    def test_has_manufacturer_sites_false_when_no_nodes(self, mock_db):
        """Returns False when no manufacturer nodes exist."""
        service = SupplyBaselineService(mock_db, mode="FULL")
        mock_db.query.return_value.filter.return_value.count.return_value = 0
        assert service._has_manufacturer_sites(config_id=1) is False

    def test_mrp_standard_graceful_failure(self, mock_db, sample_inventory, sample_suppliers, sample_forecast):
        """MRP standard candidate returns None on failure instead of crashing."""
        service = SupplyBaselineService(mock_db, mode="FULL")
        inv_by_sku = {p.sku: p for p in sample_inventory}

        # Force an exception in BOM query
        mock_db.query.side_effect = Exception("DB error")
        result = service._generate_mrp_standard_plan(
            config_id=1,
            inv_by_sku=inv_by_sku,
            supplier_info=sample_suppliers,
            demand_forecast=sample_forecast,
        )
        assert result is None


# ── PolicyEnvelope Safety Stock Tests ─────────────────────────────────

class TestPolicyEnvelopeSafetyStock:
    """Test that PolicyEnvelope safety stock targets override defaults"""

    def test_default_safety_factors(self, service):
        """Default safety factors when no envelope provided."""
        assert service._get_safety_factor("low", "ambient") == 1.0
        assert service._get_safety_factor("medium", "ambient") == 1.65
        assert service._get_safety_factor("high", "ambient") == 2.33

    def test_envelope_overrides_safety_factor(self, service):
        """PolicyEnvelope safety_stock_targets override defaults."""
        envelope = {
            "safety_stock_targets": {
                "ambient": 3.0,  # 3 WOS → maps to high (2.33)
                "chilled": 0.5,  # 0.5 WOS → maps to low (1.0)
            }
        }
        assert service._get_safety_factor("medium", "ambient", envelope) == 2.33
        assert service._get_safety_factor("medium", "chilled", envelope) == 1.0

    def test_envelope_default_category(self, service):
        """Falls back to 'default' key in envelope when category not found."""
        envelope = {
            "safety_stock_targets": {
                "default": 1.5,
            }
        }
        assert service._get_safety_factor("medium", "unknown_category", envelope) == 1.65

    def test_reorder_point_uses_envelope(
        self, service, sample_inventory, sample_suppliers, sample_forecast
    ):
        """ROP plan uses envelope safety factors when provided."""
        inv_by_sku = {p.sku: p for p in sample_inventory}
        envelope = {"safety_stock_targets": {"ambient": 3.5, "chilled": 3.5}}

        plan = service._generate_reorder_point_plan(
            inv_by_sku, sample_suppliers, sample_forecast, envelope
        )
        # With high WOS (3.5 → maps to 2.33), safety factor should be 2.33
        assert plan.policy_params["safety_factor"] == 2.33


# ── EOQ Calculation Tests ─────────────────────────────────────────────

class TestEOQCalculation:
    """Test Economic Order Quantity calculation"""

    def test_eoq_basic(self, service):
        """Basic EOQ calculation with known inputs."""
        inv = ProductInventoryState(
            sku="TEST", category="default",
            on_hand=100, in_transit=0, committed=0,
            avg_daily_demand=10, demand_std=3,
            unit_cost=20.0, min_order_qty=10,
        )
        supplier = SupplierInfo(
            supplier_id="S1", lead_time_days=5,
            lead_time_variability=0.2, reliability=0.95,
            min_order_value=100, unit_cost=20.0,
        )
        eoq = service._calculate_eoq(inv, supplier)
        # EOQ = sqrt(2 * 3650 * 50 / 5.0) = sqrt(73000) ≈ 270
        expected = math.sqrt(2 * 3650 * 50 / 5.0)
        assert abs(eoq - expected) < 1.0

    def test_eoq_respects_min_order_qty(self, service):
        """EOQ never goes below min_order_qty."""
        inv = ProductInventoryState(
            sku="TEST", category="default",
            on_hand=100, in_transit=0, committed=0,
            avg_daily_demand=0.1, demand_std=0.01,
            unit_cost=1000.0, min_order_qty=500,
        )
        supplier = SupplierInfo(
            supplier_id="S1", lead_time_days=5,
            lead_time_variability=0.2, reliability=0.95,
            min_order_value=100, unit_cost=1000.0,
        )
        eoq = service._calculate_eoq(inv, supplier)
        assert eoq >= 500

    def test_eoq_zero_demand_returns_moq(self, service):
        """Zero demand returns min_order_qty."""
        inv = ProductInventoryState(
            sku="TEST", category="default",
            on_hand=100, in_transit=0, committed=0,
            avg_daily_demand=0, demand_std=0,
            unit_cost=10.0, min_order_qty=50,
        )
        supplier = SupplierInfo(
            supplier_id="S1", lead_time_days=5,
            lead_time_variability=0.2, reliability=0.95,
            min_order_value=100, unit_cost=10.0,
        )
        assert service._calculate_eoq(inv, supplier) == 50


# ── Helper Calculation Tests ──────────────────────────────────────────

class TestHelperCalculations:
    """Test cost and DOS calculations"""

    def test_total_cost_calculation(self, service, sample_inventory):
        """Total holding cost is positive for non-empty inventory."""
        inv_by_sku = {p.sku: p for p in sample_inventory}
        projected = {"SKU-001": [100.0] * 28, "SKU-002": [50.0] * 28}
        cost = service._calculate_total_cost(projected, inv_by_sku)
        assert cost > 0

    def test_avg_dos_calculation(self, service, sample_inventory):
        """Average DOS is computed correctly."""
        inv_by_sku = {p.sku: p for p in sample_inventory}
        projected = {"SKU-001": [300.0] * 28}  # 300 units / 30 demand = 10 DOS
        dos = service._calculate_avg_dos(projected, inv_by_sku)
        assert abs(dos - 10.0) < 0.1

    def test_avg_dos_empty_returns_default(self, service, sample_inventory):
        """Empty projection returns default 14 DOS."""
        inv_by_sku = {p.sku: p for p in sample_inventory}
        dos = service._calculate_avg_dos({}, inv_by_sku)
        assert dos == 14

    def test_inventory_position_property(self):
        """ProductInventoryState.inventory_position computed correctly."""
        inv = ProductInventoryState(
            sku="X", category="test",
            on_hand=500, in_transit=100, committed=50,
            avg_daily_demand=30, demand_std=10,
            unit_cost=10.0, min_order_qty=50,
        )
        assert inv.inventory_position == 550

    def test_days_of_supply_property(self):
        """ProductInventoryState.days_of_supply computed correctly."""
        inv = ProductInventoryState(
            sku="X", category="test",
            on_hand=300, in_transit=0, committed=0,
            avg_daily_demand=30, demand_std=10,
            unit_cost=10.0, min_order_qty=50,
        )
        assert inv.days_of_supply == 10.0

    def test_days_of_supply_zero_demand(self):
        """Zero demand returns infinity for DOS."""
        inv = ProductInventoryState(
            sku="X", category="test",
            on_hand=300, in_transit=0, committed=0,
            avg_daily_demand=0, demand_std=0,
            unit_cost=10.0, min_order_qty=50,
        )
        assert inv.days_of_supply == float('inf')


# ── CFA Parameters Test ──────────────────────────────────────────────

class TestCFAParameters:
    """Test CFA parameter loading and plan generation"""

    def test_default_cfa_parameters(self, service):
        """Default CFA parameters are loaded."""
        params = service._load_cfa_parameters()
        assert "safety_multiplier" in params
        assert "reorder_multiplier" in params
        assert "service_weight" in params

    def test_cfa_plan_uses_theta(
        self, service, sample_inventory, sample_suppliers, sample_forecast
    ):
        """CFA plan policy_params contain the theta values."""
        inv_by_sku = {p.sku: p for p in sample_inventory}
        plan = service._generate_cfa_plan(
            inv_by_sku, sample_suppliers, sample_forecast
        )
        assert plan.method == "PARAMETRIC_CFA_V1"
        assert "safety_multiplier" in plan.policy_params
