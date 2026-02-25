"""
Unit Tests for Simulation Execution Services

Tests the integration of OrderManagementService, FulfillmentService,
and ATPCalculationService for simulation execution refactoring.

All database access is mocked via AsyncMock/MagicMock so that tests run
without PostgreSQL.

Tests cover:
- Order lifecycle (DRAFT -> CONFIRMED -> FULFILLED)
- FIFO + priority fulfillment
- ATP calculation accuracy
- Inventory updates
- TransferOrder creation and receipt
- PurchaseOrder fulfillment
- Round-based receipt processing
"""

import pytest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.order_management_service import OrderManagementService
from app.services.fulfillment_service import FulfillmentService
from app.services.atp_calculation_service import ATPCalculationService


# ============================================================================
# Helpers
# ============================================================================

def _date(offset: int = 0) -> date:
    """Return a deterministic base date + offset days."""
    return date(2026, 3, 1) + timedelta(days=offset)


def _make_order(**overrides) -> SimpleNamespace:
    """Build a minimal OutboundOrderLine-like object."""
    defaults = dict(
        id=1,
        order_id="ORDER-001",
        line_number=1,
        product_id="BEER-CASE",
        site_id=1,
        ordered_quantity=50.0,
        requested_delivery_date=_date(7),
        order_date=_date(0),
        market_demand_site_id=3,
        priority_code="STANDARD",
        status="DRAFT",
        shipped_quantity=0.0,
        backlog_quantity=0.0,
        promised_quantity=None,
        first_ship_date=None,
        last_ship_date=None,
        promised_delivery_date=None,
        config_id=1,
        scenario_id=1,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_inv_level(quantity: float, **overrides) -> SimpleNamespace:
    """Build a minimal InvLevel-like object."""
    defaults = dict(
        id=1,
        site_id=1,
        product_id="BEER-CASE",
        quantity=quantity,
        on_hand_qty=quantity,
        config_id=1,
        scenario_id=1,
        as_of_date=_date(0),
        inventory_date=_date(0),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_po(**overrides) -> SimpleNamespace:
    """Build a minimal PurchaseOrder-like object."""
    line = SimpleNamespace(
        id=1,
        po_id=1,
        line_number=1,
        product_id=overrides.get("product_id", "BEER-CASE"),
        quantity=overrides.get("quantity", 75.0),
        shipped_quantity=0.0,
        received_quantity=0.0,
        unit_price=10.0,
        line_total=overrides.get("quantity", 75.0) * 10.0,
    )
    defaults = dict(
        id=1,
        po_number="PO-001",
        vendor_id=None,
        supplier_site_id=2,
        destination_site_id=1,
        config_id=1,
        customer_id=None,
        status="APPROVED",
        order_date=_date(0),
        requested_delivery_date=_date(7),
        promised_delivery_date=None,
        actual_delivery_date=None,
        received_at=None,
        scenario_id=1,
        order_round=1,
        line_items=[line],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_to(**overrides) -> SimpleNamespace:
    """Build a minimal TransferOrder-like object."""
    line = SimpleNamespace(
        id=1,
        to_id=1,
        line_number=1,
        product_id=overrides.get("product_id", "BEER-CASE"),
        quantity=overrides.get("quantity", 50.0),
        uom="CASE",
    )
    defaults = dict(
        id=1,
        to_number="TO-001",
        source_site_id=2,
        destination_site_id=1,
        config_id=1,
        order_date=_date(0),
        shipment_date=_date(0),
        estimated_delivery_date=_date(7),
        actual_delivery_date=None,
        received_at=None,
        status="IN_TRANSIT",
        scenario_id=1,
        order_round=1,
        arrival_round=2,
        source_po_id=None,
        customer_id=None,
        line_items=[line],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _mock_db_session():
    """Create a mock AsyncSession with common async methods."""
    session = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    return session


def _mock_scalar_result(value):
    """Create a mock result that returns a single scalar value."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar.return_value = value
    result.scalars.return_value.all.return_value = []
    return result


def _mock_list_result(items):
    """Create a mock result that returns a list via scalars().all()."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


# ============================================================================
# OrderManagementService Tests
# ============================================================================

class TestCreateCustomerOrder:
    """Test customer order creation."""

    @pytest.mark.asyncio
    async def test_create_customer_order(self):
        db = _mock_db_session()
        order_mgmt = OrderManagementService(db)

        # The service creates an OutboundOrderLine, adds it, flushes, refreshes.
        # We need to verify the returned object has the right fields.
        # The service sets status="DRAFT", shipped=0, backlog=0.
        created_order = None

        def capture_add(obj):
            nonlocal created_order
            created_order = obj

        db.add = capture_add

        order = await order_mgmt.create_customer_order(
            order_id="ORDER-001",
            line_number=1,
            product_id="BEER-CASE",
            site_id=1,
            ordered_quantity=50.0,
            requested_delivery_date=_date(7),
            market_demand_site_id=3,
            priority_code="HIGH",
            config_id=1,
            scenario_id=1,
        )

        assert order is not None
        assert order.order_id == "ORDER-001"
        assert order.ordered_quantity == 50.0
        assert order.status == "DRAFT"
        assert order.priority_code == "HIGH"
        assert order.shipped_quantity == 0.0
        assert order.backlog_quantity == 0.0


class TestGetUnfulfilledOrders:
    """Test FIFO + priority order retrieval."""

    @pytest.mark.asyncio
    async def test_get_unfulfilled_orders_fifo_priority(self):
        db = _mock_db_session()
        order_mgmt = OrderManagementService(db)

        # Create mock orders with different priorities and dates
        orders = [
            _make_order(id=1, order_id="ORDER-001", priority_code="LOW",
                        order_date=_date(-3), status="CONFIRMED", backlog_quantity=10.0),
            _make_order(id=2, order_id="ORDER-002", priority_code="HIGH",
                        order_date=_date(-2), status="CONFIRMED", backlog_quantity=10.0),
            _make_order(id=3, order_id="ORDER-003", priority_code="STANDARD",
                        order_date=_date(-1), status="CONFIRMED", backlog_quantity=10.0),
            _make_order(id=4, order_id="ORDER-004", priority_code="VIP",
                        order_date=_date(0), status="CONFIRMED", backlog_quantity=10.0),
        ]

        db.execute.return_value = _mock_list_result(orders)

        unfulfilled = await order_mgmt.get_unfulfilled_customer_orders(
            site_id=1,
            scenario_id=1,
            priority_order=True,
        )

        # Should return all 4 orders (the DB query returns them pre-sorted)
        assert len(unfulfilled) == 4
        # First: ORDER-001 (oldest date -- FIFO takes precedence)
        assert unfulfilled[0].order_id == "ORDER-001"


class TestUpdateOrderFulfillment:
    """Test order fulfillment status updates."""

    @pytest.mark.asyncio
    async def test_partial_then_full_fulfillment(self):
        db = _mock_db_session()
        order_mgmt = OrderManagementService(db)

        # Create a mutable order object
        order = _make_order(
            id=10,
            ordered_quantity=100.0,
            shipped_quantity=0.0,
            backlog_quantity=100.0,
            status="CONFIRMED",
        )
        db.get.return_value = order

        # Partial fulfillment: ship 60
        updated_order = await order_mgmt.update_order_fulfillment(
            order_id=10,
            shipped_quantity=60.0,
        )

        assert updated_order.shipped_quantity == 60.0
        assert updated_order.backlog_quantity == 40.0
        assert updated_order.status == "PARTIALLY_FULFILLED"

        # Complete fulfillment: ship remaining 40
        final_order = await order_mgmt.update_order_fulfillment(
            order_id=10,
            shipped_quantity=40.0,
        )

        assert final_order.shipped_quantity == 100.0
        assert final_order.backlog_quantity == 0.0
        assert final_order.status == "FULFILLED"


class TestPurchaseOrderLifecycle:
    """Test PO creation and fulfillment."""

    @pytest.mark.asyncio
    async def test_create_and_fulfill_purchase_order(self):
        db = _mock_db_session()
        order_mgmt = OrderManagementService(db)

        # Track objects added to session
        added_objects = []
        db.add = lambda obj: added_objects.append(obj)

        # After flush, simulate ID assignment
        po_ref = {}

        async def mock_flush():
            for obj in added_objects:
                if hasattr(obj, 'po_number'):
                    obj.id = 1
                    po_ref['po'] = obj
                elif hasattr(obj, 'po_id'):
                    obj.id = 1

        db.flush = mock_flush

        # refresh should populate line_items
        async def mock_refresh(obj):
            if hasattr(obj, 'po_number') and not hasattr(obj, 'line_items'):
                # Find line items
                lines = [o for o in added_objects if hasattr(o, 'po_id')]
                obj.line_items = lines

        db.refresh = mock_refresh

        po = await order_mgmt.create_purchase_order(
            po_number="PO-001",
            supplier_site_id=2,
            destination_site_id=1,
            product_id="BEER-CASE",
            quantity=75.0,
            requested_delivery_date=_date(7),
            config_id=1,
            scenario_id=1,
            order_round=1,
        )

        assert po is not None
        assert po.po_number == "PO-001"
        assert po.status == "APPROVED"
        assert len(po.line_items) == 1
        assert po.line_items[0].quantity == 75.0

        # Now test updating PO shipment
        # Reset mock for update_po_shipment
        db.get = AsyncMock(return_value=po)

        # Mock the line item query
        po_line = po.line_items[0]
        line_result = MagicMock()
        line_result.scalar_one_or_none.return_value = po_line
        db.execute = AsyncMock(return_value=line_result)
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        updated_po = await order_mgmt.update_po_shipment(
            po_id=po.id,
            line_number=1,
            shipped_quantity=75.0,
        )

        assert updated_po.status == "SHIPPED"


class TestTransferOrderLifecycle:
    """Test TO creation, arrival, and receipt."""

    @pytest.mark.asyncio
    async def test_transfer_order_lifecycle(self):
        db = _mock_db_session()
        order_mgmt = OrderManagementService(db)

        # Track objects added to session
        added_objects = []
        db.add = lambda obj: added_objects.append(obj)

        to_ref = {}

        async def mock_flush():
            for obj in added_objects:
                if hasattr(obj, 'to_number'):
                    obj.id = 1
                    to_ref['to'] = obj
                elif hasattr(obj, 'to_id'):
                    obj.id = 1

        db.flush = mock_flush

        async def mock_refresh(obj):
            if hasattr(obj, 'to_number') and not hasattr(obj, 'line_items'):
                lines = [o for o in added_objects if hasattr(o, 'to_id')]
                obj.line_items = lines

        db.refresh = mock_refresh

        # Create TO
        to = await order_mgmt.create_transfer_order(
            to_number="TO-001",
            source_site_id=2,
            destination_site_id=1,
            product_id="BEER-CASE",
            quantity=50.0,
            estimated_delivery_date=_date(7),
            config_id=1,
            scenario_id=1,
            order_round=1,
            arrival_round=2,
        )

        assert to is not None
        assert to.status == "IN_TRANSIT"
        assert to.arrival_round == 2

        # Get arriving TOs for round 2
        db.execute = AsyncMock(return_value=_mock_list_result([to]))

        arriving = await order_mgmt.get_arriving_transfer_orders(
            scenario_id=1,
            arrival_round=2,
        )

        assert len(arriving) == 1
        assert arriving[0].id == to.id

        # Receive TO
        db.get = AsyncMock(return_value=to)
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        received_to = await order_mgmt.receive_transfer_order(to_id=to.id)

        assert received_to.status == "RECEIVED"
        assert received_to.actual_delivery_date is not None


# ============================================================================
# FulfillmentService Tests
# ============================================================================

class TestATPCalculation:
    """Test ATP calculation via FulfillmentService."""

    @pytest.mark.asyncio
    async def test_atp_calculation(self):
        db = _mock_db_session()
        fulfillment = FulfillmentService(db)

        inv = _make_inv_level(100.0)

        # First call: get inventory level; second call: get committed qty
        db.execute = AsyncMock(side_effect=[
            _mock_scalar_result(inv),      # InvLevel query
            _mock_scalar_result(0.0),      # committed quantity (none)
        ])

        atp = await fulfillment.calculate_available_to_ship(
            site_id=1,
            product_id="BEER-CASE",
            config_id=1,
            scenario_id=1,
        )

        # Initial inventory is 100.0, no committed orders
        assert atp == 100.0


class TestFulfillCustomerOrdersFIFO:
    """Test FIFO customer order fulfillment."""

    @pytest.mark.asyncio
    async def test_fulfill_customer_orders_fifo(self):
        """Test FIFO fulfillment: 3 orders x 30 = 90, inventory = 100."""
        db = _mock_db_session()
        fulfillment = FulfillmentService(db)

        # Create 3 confirmed orders, each 30 units
        orders = [
            _make_order(id=i+1, order_id=f"ORDER-00{i+1}",
                        ordered_quantity=30.0, shipped_quantity=0.0,
                        backlog_quantity=30.0, status="CONFIRMED",
                        product_id="BEER-CASE")
            for i in range(3)
        ]

        inv = _make_inv_level(100.0)

        # We need to mock the internal calls the service makes.
        # The fulfillment service uses self.order_mgmt internally.
        # Patch the OrderManagementService methods on the fulfillment object.
        fulfillment.order_mgmt.get_unfulfilled_customer_orders = AsyncMock(
            return_value=orders
        )

        # Mock ATP: on_hand=100, committed=0
        fulfillment.calculate_available_to_ship = AsyncMock(return_value=100.0)

        # Track order updates
        update_calls = []

        async def mock_update_order(order_id, shipped_quantity, promised_delivery_date=None, customer_id=None):
            for o in orders:
                if o.id == order_id:
                    o.shipped_quantity += shipped_quantity
                    o.backlog_quantity = max(0, o.ordered_quantity - o.shipped_quantity)
                    if o.shipped_quantity >= o.ordered_quantity:
                        o.status = "FULFILLED"
                    elif o.shipped_quantity > 0:
                        o.status = "PARTIALLY_FULFILLED"
                    update_calls.append(order_id)
                    return o
            raise ValueError(f"Order {order_id} not found")

        fulfillment.order_mgmt.update_order_fulfillment = mock_update_order

        # Mock TO creation
        to_counter = [0]

        async def mock_create_to(**kwargs):
            to_counter[0] += 1
            return _make_to(id=to_counter[0], quantity=kwargs.get('quantity', 0))

        fulfillment.order_mgmt.create_transfer_order = mock_create_to

        # Mock inventory update
        fulfillment.update_inventory_level = AsyncMock()

        # Mock backlog calculation
        fulfillment.order_mgmt.get_backlog_for_site = AsyncMock(return_value=0.0)

        result = await fulfillment.fulfill_customer_orders_fifo(
            site_id=1,
            product_id="BEER-CASE",
            scenario_id=1,
            config_id=1,
            current_round=1,
        )

        # All 3 orders should be fulfilled (30+30+30 = 90 <= 100 ATP)
        assert result['orders_fulfilled'] == 3
        assert result['quantity_shipped'] == 90.0
        assert result['backlog_remaining'] == 0.0
        assert len(result['transfer_orders_created']) == 3

    @pytest.mark.asyncio
    async def test_fulfill_with_insufficient_inventory(self):
        """Test partial fulfillment with insufficient inventory."""
        db = _mock_db_session()
        fulfillment = FulfillmentService(db)

        # One order for 150 units, only 100 available
        order = _make_order(
            id=1, order_id="ORDER-001",
            ordered_quantity=150.0, shipped_quantity=0.0,
            backlog_quantity=150.0, status="CONFIRMED",
            product_id="BEER-CASE",
        )

        fulfillment.order_mgmt.get_unfulfilled_customer_orders = AsyncMock(
            return_value=[order]
        )
        fulfillment.calculate_available_to_ship = AsyncMock(return_value=100.0)

        async def mock_update_order(order_id, shipped_quantity, promised_delivery_date=None, customer_id=None):
            order.shipped_quantity += shipped_quantity
            order.backlog_quantity = max(0, order.ordered_quantity - order.shipped_quantity)
            if order.shipped_quantity >= order.ordered_quantity:
                order.status = "FULFILLED"
            elif order.shipped_quantity > 0:
                order.status = "PARTIALLY_FULFILLED"
            return order

        fulfillment.order_mgmt.update_order_fulfillment = mock_update_order
        fulfillment.order_mgmt.create_transfer_order = AsyncMock(
            return_value=_make_to(quantity=100.0)
        )
        fulfillment.update_inventory_level = AsyncMock()
        fulfillment.order_mgmt.get_backlog_for_site = AsyncMock(return_value=50.0)

        result = await fulfillment.fulfill_customer_orders_fifo(
            site_id=1,
            product_id="BEER-CASE",
            scenario_id=1,
            config_id=1,
            current_round=1,
        )

        assert result['quantity_shipped'] == 100.0
        assert result['backlog_remaining'] == 50.0
        assert result['orders_fulfilled'] == 0  # Not fully fulfilled


class TestFulfillPurchaseOrders:
    """Test PO fulfillment as sales orders."""

    @pytest.mark.asyncio
    async def test_fulfill_purchase_orders(self):
        db = _mock_db_session()
        fulfillment = FulfillmentService(db)

        # PO for 80 units from Wholesaler (200 available)
        po = _make_po(
            id=1, po_number="PO-001",
            supplier_site_id=2, destination_site_id=1,
            product_id="BEER-CASE", quantity=80.0,
        )

        fulfillment.order_mgmt.get_unfulfilled_purchase_orders = AsyncMock(
            return_value=[po]
        )
        fulfillment.calculate_available_to_ship = AsyncMock(return_value=200.0)

        async def mock_update_po_shipment(po_id, line_number, shipped_quantity, promised_delivery_date=None):
            po_line = po.line_items[0]
            po_line.shipped_quantity += shipped_quantity
            if po_line.shipped_quantity >= po_line.quantity:
                po.status = "SHIPPED"
            elif po_line.shipped_quantity > 0:
                po.status = "PARTIALLY_SHIPPED"
            return po

        fulfillment.order_mgmt.update_po_shipment = mock_update_po_shipment
        fulfillment.order_mgmt.create_transfer_order = AsyncMock(
            return_value=_make_to(id=1, quantity=80.0, source_po_id=1)
        )
        fulfillment.update_inventory_level = AsyncMock()

        result = await fulfillment.fulfill_purchase_orders(
            supplier_site_id=2,
            product_id="BEER-CASE",
            scenario_id=1,
            config_id=1,
            current_round=1,
        )

        assert result['pos_fulfilled'] == 1
        assert result['quantity_shipped'] == 80.0
        assert len(result['transfer_orders_created']) == 1

        # Check PO status updated
        assert po.status == "SHIPPED"


class TestReceiveShipments:
    """Test shipment receipt and inventory update."""

    @pytest.mark.asyncio
    async def test_receive_shipments(self):
        db = _mock_db_session()
        fulfillment = FulfillmentService(db)

        # TO arriving at Retailer (site_id=1) for 50 units
        to = _make_to(
            id=1, destination_site_id=1, quantity=50.0,
            arrival_round=2,
        )

        fulfillment.order_mgmt.get_arriving_transfer_orders = AsyncMock(
            return_value=[to]
        )
        fulfillment.update_inventory_level = AsyncMock()

        async def mock_receive_to(to_id):
            to.status = "RECEIVED"
            to.actual_delivery_date = date.today()
            return to

        fulfillment.order_mgmt.receive_transfer_order = mock_receive_to

        result = await fulfillment.receive_shipments(
            scenario_id=1,
            arrival_round=2,
            config_id=1,
        )

        assert result['transfer_orders_received'] == 1
        assert result['total_quantity_received'] == 50.0
        assert 1 in result['receipts_by_site']
        assert result['receipts_by_site'][1] == 50.0


class TestGetInventoryLevel:
    """Test inventory level retrieval."""

    @pytest.mark.asyncio
    async def test_get_inventory_level(self):
        db = _mock_db_session()
        fulfillment = FulfillmentService(db)

        inv = _make_inv_level(100.0)
        db.execute = AsyncMock(return_value=_mock_scalar_result(inv))

        level = await fulfillment.get_inventory_level(
            site_id=1,
            product_id="BEER-CASE",
            config_id=1,
            scenario_id=1,
        )

        assert level == 100.0

    @pytest.mark.asyncio
    async def test_get_inventory_level_not_found(self):
        db = _mock_db_session()
        fulfillment = FulfillmentService(db)

        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        level = await fulfillment.get_inventory_level(
            site_id=1,
            product_id="BEER-CASE",
            config_id=1,
            scenario_id=1,
        )

        assert level == 0.0


# ============================================================================
# ATPCalculationService Tests
# ============================================================================

class TestATPWithComponents:
    """Test ATP calculation with all components."""

    @pytest.mark.asyncio
    async def test_calculate_atp_with_components(self):
        db = _mock_db_session()
        atp_service = ATPCalculationService(db)

        # Mock the internal helper methods
        atp_service._get_on_hand_inventory = AsyncMock(return_value=100.0)
        atp_service._get_in_transit_quantity = AsyncMock(return_value=20.0)
        atp_service._get_committed_quantity = AsyncMock(return_value=30.0)
        atp_service._get_backlog_quantity = AsyncMock(return_value=30.0)
        atp_service._project_future_receipts = AsyncMock(return_value=[])

        atp_data = await atp_service.calculate_atp(
            site_id=1,
            product_id="BEER-CASE",
            config_id=1,
            scenario_id=1,
            current_round=1,
            horizon_rounds=4,
        )

        # ATP = On-hand (100) + In-transit (20) - Committed (30) - Backlog (30) = 60
        assert atp_data['current_atp'] == 60.0
        assert atp_data['on_hand'] == 100.0
        assert atp_data['in_transit'] == 20.0
        assert atp_data['committed'] == 30.0
        assert atp_data['backlog'] == 30.0


class TestPromiseDateCalculation:
    """Test promise date calculations."""

    @pytest.mark.asyncio
    async def test_calculate_promise_date_immediate(self):
        """Test promise date when ATP is sufficient."""
        db = _mock_db_session()
        atp_service = ATPCalculationService(db)

        # Mock calculate_atp to return sufficient ATP
        atp_service.calculate_atp = AsyncMock(return_value={
            'current_atp': 100.0,
            'on_hand': 100.0,
            'in_transit': 0.0,
            'committed': 0.0,
            'backlog': 0.0,
            'future_receipts': [],
            'projected_atp': [],
        })

        promise = await atp_service.calculate_promise_date(
            site_id=1,
            product_id="BEER-CASE",
            requested_quantity=50.0,
            requested_date=_date(7),
            config_id=1,
            scenario_id=1,
            current_round=1,
        )

        assert promise['can_promise'] is True
        assert promise['promised_quantity'] == 50.0
        assert promise['shortfall_quantity'] == 0.0
        assert promise['confidence'] == 1.0

    @pytest.mark.asyncio
    async def test_calculate_promise_date_insufficient(self):
        """Test promise date when ATP is insufficient."""
        db = _mock_db_session()
        atp_service = ATPCalculationService(db)

        # Mock calculate_atp with insufficient ATP and no future receipts
        atp_service.calculate_atp = AsyncMock(return_value={
            'current_atp': 100.0,
            'on_hand': 100.0,
            'in_transit': 0.0,
            'committed': 0.0,
            'backlog': 0.0,
            'future_receipts': [],
            'projected_atp': [],
        })

        promise = await atp_service.calculate_promise_date(
            site_id=1,
            product_id="BEER-CASE",
            requested_quantity=150.0,  # > 100 available
            requested_date=_date(7),
            config_id=1,
            scenario_id=1,
            current_round=1,
        )

        assert promise['can_promise'] is False
        assert promise['promised_quantity'] == 100.0
        assert promise['shortfall_quantity'] == 50.0


class TestFulfillmentFeasibility:
    """Test quick fulfillment feasibility check."""

    @pytest.mark.asyncio
    async def test_check_fulfillment_feasibility_sufficient(self):
        db = _mock_db_session()
        atp_service = ATPCalculationService(db)

        atp_service.calculate_atp = AsyncMock(return_value={
            'current_atp': 100.0,
            'on_hand': 100.0,
            'in_transit': 0.0,
            'committed': 0.0,
            'backlog': 0.0,
            'future_receipts': [],
            'projected_atp': [],
        })

        feasible = await atp_service.check_fulfillment_feasibility(
            site_id=1,
            product_id="BEER-CASE",
            required_quantity=80.0,
            config_id=1,
            scenario_id=1,
        )
        assert feasible is True

    @pytest.mark.asyncio
    async def test_check_fulfillment_feasibility_insufficient(self):
        db = _mock_db_session()
        atp_service = ATPCalculationService(db)

        atp_service.calculate_atp = AsyncMock(return_value={
            'current_atp': 100.0,
            'on_hand': 100.0,
            'in_transit': 0.0,
            'committed': 0.0,
            'backlog': 0.0,
            'future_receipts': [],
            'projected_atp': [],
        })

        not_feasible = await atp_service.check_fulfillment_feasibility(
            site_id=1,
            product_id="BEER-CASE",
            required_quantity=150.0,
            config_id=1,
            scenario_id=1,
        )
        assert not_feasible is False


# ============================================================================
# End-to-End Integration Test (Mocked)
# ============================================================================

class TestEndToEndOrderFulfillmentCycle:
    """
    End-to-end test of complete order fulfillment cycle:
    1. Customer places order
    2. ATP check and promise
    3. Fulfill order and create TO
    4. Receive TO at destination
    5. Update inventory
    """

    @pytest.mark.asyncio
    async def test_end_to_end_order_fulfillment_cycle(self):
        db = _mock_db_session()

        order_mgmt = OrderManagementService(db)
        fulfillment = FulfillmentService(db)
        atp_service = ATPCalculationService(db)

        # ---- Step 1: Customer places order ----
        order = _make_order(
            id=1, order_id="ORDER-E2E-001",
            ordered_quantity=40.0, shipped_quantity=0.0,
            backlog_quantity=0.0, status="DRAFT",
            product_id="BEER-CASE", site_id=1,
            market_demand_site_id=3, config_id=1, scenario_id=1,
        )

        # ---- Step 2: Check ATP and promise ----
        atp_service.calculate_atp = AsyncMock(return_value={
            'current_atp': 100.0,
            'on_hand': 100.0,
            'in_transit': 0.0,
            'committed': 0.0,
            'backlog': 0.0,
            'future_receipts': [],
            'projected_atp': [],
        })

        promise = await atp_service.calculate_promise_date(
            site_id=1,
            product_id="BEER-CASE",
            requested_quantity=40.0,
            requested_date=_date(7),
            config_id=1,
            scenario_id=1,
            current_round=1,
        )

        assert promise['can_promise'] is True

        # Confirm order
        order.status = "CONFIRMED"
        order.promised_quantity = 40.0
        order.backlog_quantity = 40.0

        # ---- Step 3: Fulfill order ----
        fulfillment.order_mgmt.get_unfulfilled_customer_orders = AsyncMock(
            return_value=[order]
        )
        fulfillment.calculate_available_to_ship = AsyncMock(return_value=100.0)

        created_to = _make_to(id=1, quantity=40.0, destination_site_id=3, arrival_round=2)

        async def mock_update_order(order_id, shipped_quantity, promised_delivery_date=None, customer_id=None):
            order.shipped_quantity += shipped_quantity
            order.backlog_quantity = max(0, order.ordered_quantity - order.shipped_quantity)
            if order.shipped_quantity >= order.ordered_quantity:
                order.status = "FULFILLED"
            elif order.shipped_quantity > 0:
                order.status = "PARTIALLY_FULFILLED"
            return order

        fulfillment.order_mgmt.update_order_fulfillment = mock_update_order
        fulfillment.order_mgmt.create_transfer_order = AsyncMock(return_value=created_to)
        fulfillment.update_inventory_level = AsyncMock()
        fulfillment.order_mgmt.get_backlog_for_site = AsyncMock(return_value=0.0)

        result = await fulfillment.fulfill_customer_orders_fifo(
            site_id=1,
            product_id="BEER-CASE",
            scenario_id=1,
            config_id=1,
            current_round=1,
        )

        assert result['orders_fulfilled'] == 1
        assert result['quantity_shipped'] == 40.0
        assert len(result['transfer_orders_created']) == 1

        # Check order status
        assert order.status == "FULFILLED"
        assert order.shipped_quantity == 40.0
        assert order.backlog_quantity == 0.0

        # ---- Step 4: Receive TO at customer site ----
        to = result['transfer_orders_created'][0]

        fulfillment.order_mgmt.get_arriving_transfer_orders = AsyncMock(
            return_value=[to]
        )

        async def mock_receive_to(to_id):
            to.status = "RECEIVED"
            to.actual_delivery_date = date.today()
            return to

        fulfillment.order_mgmt.receive_transfer_order = mock_receive_to

        receipt_result = await fulfillment.receive_shipments(
            scenario_id=1,
            arrival_round=to.arrival_round,
            config_id=1,
        )

        assert receipt_result['transfer_orders_received'] == 1
        assert receipt_result['total_quantity_received'] == 40.0

        # Check TO status
        assert to.status == "RECEIVED"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
