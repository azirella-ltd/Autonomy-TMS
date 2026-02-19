"""
Integration Tests for Simulation Execution Services

Tests the integration of OrderManagementService, FulfillmentService,
and ATPCalculationService for simulation execution refactoring.

Tests cover:
- Order lifecycle (DRAFT → CONFIRMED → FULFILLED)
- FIFO + priority fulfillment
- ATP calculation accuracy
- Inventory updates
- TransferOrder creation and receipt
- PurchaseOrder fulfillment
- Round-based receipt processing
"""

import pytest
from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sc_entities import OutboundOrderLine, InventoryLevel
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem
from app.models.transfer_order import TransferOrder, TransferOrderLineItem
from app.models.supply_chain_config import Node, SupplyChainConfig, Item
from app.models.scenario import Scenario
from app.services.order_management_service import OrderManagementService
from app.services.fulfillment_service import FulfillmentService
from app.services.atp_calculation_service import ATPCalculationService


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
async def test_config(db_session: AsyncSession):
    """Create test supply chain configuration."""
    config = SupplyChainConfig(
        name="Test Beer Scenario Config",
        description="Test configuration for Beer Scenario execution tests",
    )
    db_session.add(config)
    await db_session.flush()
    await db_session.refresh(config)
    return config


@pytest.fixture
async def test_sites(db_session: AsyncSession, test_config):
    """Create test sites (Retailer, Wholesaler, Market Demand)."""
    retailer = Node(
        name="Test Retailer",
        sc_node_type="Retailer",
        master_type="INVENTORY",
        config_id=test_config.id,
    )
    wholesaler = Node(
        name="Test Wholesaler",
        sc_node_type="Wholesaler",
        master_type="INVENTORY",
        config_id=test_config.id,
    )
    market_demand = Node(
        name="Test Customer",
        sc_node_type="Market Demand",
        master_type="MARKET_DEMAND",
        config_id=test_config.id,
    )

    db_session.add_all([retailer, wholesaler, market_demand])
    await db_session.flush()
    await db_session.refresh(retailer)
    await db_session.refresh(wholesaler)
    await db_session.refresh(market_demand)

    return {
        'retailer': retailer,
        'wholesaler': wholesaler,
        'market_demand': market_demand,
    }


@pytest.fixture
async def test_product(db_session: AsyncSession, test_config):
    """Create test product."""
    product = Item(
        product_id="BEER-CASE",
        name="Beer Case",
        config_id=test_config.id,
    )
    db_session.add(product)
    await db_session.flush()
    return product


@pytest.fixture
async def test_scenario(db_session: AsyncSession, test_config):
    """Create test scenario."""
    scenario = Scenario(
        name="Test Scenario",
        config_id=test_config.id,
        current_round=1,
        status="IN_PROGRESS",
    )
    db_session.add(scenario)
    await db_session.flush()
    await db_session.refresh(scenario)
    return scenario


@pytest.fixture
async def test_inventory(db_session: AsyncSession, test_sites, test_product, test_config, test_scenario):
    """Create initial inventory levels."""
    retailer_inv = InventoryLevel(
        site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        quantity=100.0,
        config_id=test_config.id,
        scenario_id=test_scenario.id,
        as_of_date=date.today(),
    )
    wholesaler_inv = InventoryLevel(
        site_id=test_sites['wholesaler'].id,
        product_id=test_product.product_id,
        quantity=200.0,
        config_id=test_config.id,
        scenario_id=test_scenario.id,
        as_of_date=date.today(),
    )

    db_session.add_all([retailer_inv, wholesaler_inv])
    await db_session.commit()

    return {
        'retailer': retailer_inv,
        'wholesaler': wholesaler_inv,
    }


# ============================================================================
# OrderManagementService Tests
# ============================================================================

@pytest.mark.asyncio
async def test_create_customer_order(db_session: AsyncSession, test_sites, test_product, test_config, test_scenario):
    """Test customer order creation."""
    order_mgmt = OrderManagementService(db_session)

    order = await order_mgmt.create_customer_order(
        order_id="ORDER-001",
        line_number=1,
        product_id=test_product.product_id,
        site_id=test_sites['retailer'].id,
        ordered_quantity=50.0,
        requested_delivery_date=date.today() + timedelta(weeks=1),
        market_demand_site_id=test_sites['market_demand'].id,
        priority_code="HIGH",
        config_id=test_config.id,
        scenario_id=test_scenario.id,
    )

    assert order is not None
    assert order.order_id == "ORDER-001"
    assert order.ordered_quantity == 50.0
    assert order.status == "DRAFT"
    assert order.priority_code == "HIGH"
    assert order.shipped_quantity == 0.0
    assert order.backlog_quantity == 0.0


@pytest.mark.asyncio
async def test_get_unfulfilled_orders_fifo_priority(db_session: AsyncSession, test_sites, test_product, test_config, test_scenario):
    """Test FIFO + priority order retrieval."""
    order_mgmt = OrderManagementService(db_session)

    # Create orders with different priorities and dates
    orders_data = [
        ("ORDER-001", "LOW", date.today() - timedelta(days=3)),
        ("ORDER-002", "HIGH", date.today() - timedelta(days=2)),
        ("ORDER-003", "STANDARD", date.today() - timedelta(days=1)),
        ("ORDER-004", "VIP", date.today()),
    ]

    for order_id, priority, order_date in orders_data:
        order = OutboundOrderLine(
            order_id=order_id,
            line_number=1,
            product_id=test_product.product_id,
            site_id=test_sites['retailer'].id,
            ordered_quantity=10.0,
            requested_delivery_date=date.today() + timedelta(weeks=1),
            order_date=order_date,
            market_demand_site_id=test_sites['market_demand'].id,
            priority_code=priority,
            status="CONFIRMED",
            backlog_quantity=10.0,
            config_id=test_config.id,
            scenario_id=test_scenario.id,
        )
        db_session.add(order)

    await db_session.commit()

    # Retrieve orders with FIFO + priority
    unfulfilled = await order_mgmt.get_unfulfilled_customer_orders(
        site_id=test_sites['retailer'].id,
        scenario_id=test_scenario.id,
        priority_order=True,
    )

    # Should be sorted: oldest first, then by priority (VIP > HIGH > STANDARD > LOW)
    assert len(unfulfilled) == 4
    # First: ORDER-001 (oldest)
    assert unfulfilled[0].order_id == "ORDER-001"
    # Within same date, priority should be highest first
    # But since ORDER-002 is newer than ORDER-001, FIFO takes precedence


@pytest.mark.asyncio
async def test_update_order_fulfillment(db_session: AsyncSession, test_sites, test_product, test_config, test_scenario):
    """Test order fulfillment status updates."""
    order_mgmt = OrderManagementService(db_session)

    # Create order
    order = await order_mgmt.create_customer_order(
        order_id="ORDER-001",
        line_number=1,
        product_id=test_product.product_id,
        site_id=test_sites['retailer'].id,
        ordered_quantity=100.0,
        requested_delivery_date=date.today() + timedelta(weeks=1),
        config_id=test_config.id,
        scenario_id=test_scenario.id,
    )

    # Partial fulfillment
    updated_order = await order_mgmt.update_order_fulfillment(
        order_id=order.id,
        shipped_quantity=60.0,
    )

    assert updated_order.shipped_quantity == 60.0
    assert updated_order.backlog_quantity == 40.0
    assert updated_order.status == "PARTIALLY_FULFILLED"

    # Complete fulfillment
    final_order = await order_mgmt.update_order_fulfillment(
        order_id=order.id,
        shipped_quantity=40.0,
    )

    assert final_order.shipped_quantity == 100.0
    assert final_order.backlog_quantity == 0.0
    assert final_order.status == "FULFILLED"


@pytest.mark.asyncio
async def test_create_and_fulfill_purchase_order(db_session: AsyncSession, test_sites, test_product, test_config, test_scenario):
    """Test PO creation and fulfillment."""
    order_mgmt = OrderManagementService(db_session)

    # Create PO
    po = await order_mgmt.create_purchase_order(
        po_number="PO-001",
        supplier_site_id=test_sites['wholesaler'].id,
        destination_site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        quantity=75.0,
        requested_delivery_date=date.today() + timedelta(weeks=1),
        config_id=test_config.id,
        scenario_id=test_scenario.id,
        order_round=1,
    )

    assert po is not None
    assert po.po_number == "PO-001"
    assert po.status == "APPROVED"
    assert len(po.line_items) == 1
    assert po.line_items[0].quantity == 75.0

    # Update shipment
    updated_po = await order_mgmt.update_po_shipment(
        po_id=po.id,
        line_number=1,
        shipped_quantity=75.0,
    )

    assert updated_po.status == "SHIPPED"


@pytest.mark.asyncio
async def test_transfer_order_lifecycle(db_session: AsyncSession, test_sites, test_product, test_config, test_scenario):
    """Test TO creation, arrival, and receipt."""
    order_mgmt = OrderManagementService(db_session)

    # Create TO
    to = await order_mgmt.create_transfer_order(
        to_number="TO-001",
        source_site_id=test_sites['wholesaler'].id,
        destination_site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        quantity=50.0,
        estimated_delivery_date=date.today() + timedelta(weeks=1),
        config_id=test_config.id,
        scenario_id=test_scenario.id,
        order_round=1,
        arrival_round=2,
    )

    assert to is not None
    assert to.status == "IN_TRANSIT"
    assert to.arrival_round == 2

    # Get arriving TOs for round 2
    arriving = await order_mgmt.get_arriving_transfer_orders(
        scenario_id=test_scenario.id,
        arrival_round=2,
    )

    assert len(arriving) == 1
    assert arriving[0].id == to.id

    # Receive TO
    received_to = await order_mgmt.receive_transfer_order(to_id=to.id)

    assert received_to.status == "RECEIVED"
    assert received_to.actual_delivery_date is not None


# ============================================================================
# FulfillmentService Tests
# ============================================================================

@pytest.mark.asyncio
async def test_atp_calculation(db_session: AsyncSession, test_sites, test_product, test_config, test_scenario, test_inventory):
    """Test ATP calculation."""
    fulfillment = FulfillmentService(db_session)

    atp = await fulfillment.calculate_available_to_ship(
        site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        config_id=test_config.id,
        scenario_id=test_scenario.id,
    )

    # Initial inventory is 100.0, no committed orders
    assert atp == 100.0


@pytest.mark.asyncio
async def test_fulfill_customer_orders_fifo(db_session: AsyncSession, test_sites, test_product, test_config, test_scenario, test_inventory):
    """Test FIFO customer order fulfillment."""
    order_mgmt = OrderManagementService(db_session)
    fulfillment = FulfillmentService(db_session)

    # Create 3 customer orders
    for i in range(3):
        await order_mgmt.create_customer_order(
            order_id=f"ORDER-00{i+1}",
            line_number=1,
            product_id=test_product.product_id,
            site_id=test_sites['retailer'].id,
            ordered_quantity=30.0,
            requested_delivery_date=date.today() + timedelta(weeks=1),
            market_demand_site_id=test_sites['market_demand'].id,
            config_id=test_config.id,
            scenario_id=test_scenario.id,
        )

    # Mark orders as CONFIRMED (set status and backlog)
    orders = await order_mgmt.get_unfulfilled_customer_orders(
        site_id=test_sites['retailer'].id,
        scenario_id=test_scenario.id,
    )

    for order in orders:
        order.status = "CONFIRMED"
        order.backlog_quantity = order.ordered_quantity

    await db_session.commit()

    # Fulfill orders (ATP = 100, total demand = 90)
    result = await fulfillment.fulfill_customer_orders_fifo(
        site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        scenario_id=test_scenario.id,
        config_id=test_config.id,
        current_round=1,
    )

    # All 3 orders should be fulfilled
    assert result['orders_fulfilled'] == 3
    assert result['quantity_shipped'] == 90.0
    assert result['backlog_remaining'] == 0.0
    assert len(result['transfer_orders_created']) == 3

    # Check inventory reduced
    inv = await fulfillment.get_inventory_level(
        site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        config_id=test_config.id,
        scenario_id=test_scenario.id,
    )
    assert inv == 10.0  # 100 - 90


@pytest.mark.asyncio
async def test_fulfill_with_insufficient_inventory(db_session: AsyncSession, test_sites, test_product, test_config, test_scenario, test_inventory):
    """Test partial fulfillment with insufficient inventory."""
    order_mgmt = OrderManagementService(db_session)
    fulfillment = FulfillmentService(db_session)

    # Create order larger than available inventory
    await order_mgmt.create_customer_order(
        order_id="ORDER-001",
        line_number=1,
        product_id=test_product.product_id,
        site_id=test_sites['retailer'].id,
        ordered_quantity=150.0,  # > 100 available
        requested_delivery_date=date.today() + timedelta(weeks=1),
        market_demand_site_id=test_sites['market_demand'].id,
        config_id=test_config.id,
        scenario_id=test_scenario.id,
    )

    # Mark as CONFIRMED
    orders = await order_mgmt.get_unfulfilled_customer_orders(
        site_id=test_sites['retailer'].id,
        scenario_id=test_scenario.id,
    )
    orders[0].status = "CONFIRMED"
    orders[0].backlog_quantity = 150.0
    await db_session.commit()

    # Fulfill (should only ship 100)
    result = await fulfillment.fulfill_customer_orders_fifo(
        site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        scenario_id=test_scenario.id,
        config_id=test_config.id,
        current_round=1,
    )

    assert result['quantity_shipped'] == 100.0
    assert result['backlog_remaining'] == 50.0
    assert result['orders_fulfilled'] == 0  # Not fully fulfilled


@pytest.mark.asyncio
async def test_fulfill_purchase_orders(db_session: AsyncSession, test_sites, test_product, test_config, test_scenario, test_inventory):
    """Test PO fulfillment as sales orders."""
    order_mgmt = OrderManagementService(db_session)
    fulfillment = FulfillmentService(db_session)

    # Create PO from Retailer to Wholesaler
    po = await order_mgmt.create_purchase_order(
        po_number="PO-001",
        supplier_site_id=test_sites['wholesaler'].id,
        destination_site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        quantity=80.0,
        requested_delivery_date=date.today() + timedelta(weeks=1),
        config_id=test_config.id,
        scenario_id=test_scenario.id,
        order_round=1,
    )

    # Fulfill PO from Wholesaler's inventory
    result = await fulfillment.fulfill_purchase_orders(
        supplier_site_id=test_sites['wholesaler'].id,
        product_id=test_product.product_id,
        scenario_id=test_scenario.id,
        config_id=test_config.id,
        current_round=1,
    )

    assert result['pos_fulfilled'] == 1
    assert result['quantity_shipped'] == 80.0
    assert len(result['transfer_orders_created']) == 1

    # Check PO status updated
    await db_session.refresh(po)
    assert po.status == "SHIPPED"

    # Check Wholesaler inventory reduced
    inv = await fulfillment.get_inventory_level(
        site_id=test_sites['wholesaler'].id,
        product_id=test_product.product_id,
        config_id=test_config.id,
        scenario_id=test_scenario.id,
    )
    assert inv == 120.0  # 200 - 80


@pytest.mark.asyncio
async def test_receive_shipments(db_session: AsyncSession, test_sites, test_product, test_config, test_scenario, test_inventory):
    """Test shipment receipt and inventory update."""
    order_mgmt = OrderManagementService(db_session)
    fulfillment = FulfillmentService(db_session)

    # Create TO
    to = await order_mgmt.create_transfer_order(
        to_number="TO-001",
        source_site_id=test_sites['wholesaler'].id,
        destination_site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        quantity=50.0,
        estimated_delivery_date=date.today() + timedelta(weeks=1),
        config_id=test_config.id,
        scenario_id=test_scenario.id,
        order_round=1,
        arrival_round=2,
    )

    # Initial Retailer inventory
    initial_inv = await fulfillment.get_inventory_level(
        site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        config_id=test_config.id,
        scenario_id=test_scenario.id,
    )

    # Receive shipments for round 2
    result = await fulfillment.receive_shipments(
        scenario_id=test_scenario.id,
        arrival_round=2,
        config_id=test_config.id,
    )

    assert result['transfer_orders_received'] == 1
    assert result['total_quantity_received'] == 50.0
    assert test_sites['retailer'].id in result['receipts_by_site']
    assert result['receipts_by_site'][test_sites['retailer'].id] == 50.0

    # Check inventory increased
    final_inv = await fulfillment.get_inventory_level(
        site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        config_id=test_config.id,
        scenario_id=test_scenario.id,
    )
    assert final_inv == initial_inv + 50.0


# ============================================================================
# ATPCalculationService Tests
# ============================================================================

@pytest.mark.asyncio
async def test_calculate_atp_with_components(db_session: AsyncSession, test_sites, test_product, test_config, test_scenario, test_inventory):
    """Test ATP calculation with all components."""
    order_mgmt = OrderManagementService(db_session)
    atp_service = ATPCalculationService(db_session)

    # Create committed order
    order = await order_mgmt.create_customer_order(
        order_id="ORDER-001",
        line_number=1,
        product_id=test_product.product_id,
        site_id=test_sites['retailer'].id,
        ordered_quantity=30.0,
        requested_delivery_date=date.today() + timedelta(weeks=1),
        config_id=test_config.id,
        scenario_id=test_scenario.id,
    )
    order.status = "CONFIRMED"
    order.promised_quantity = 30.0
    order.backlog_quantity = 30.0

    # Create in-transit TO
    await order_mgmt.create_transfer_order(
        to_number="TO-001",
        source_site_id=test_sites['wholesaler'].id,
        destination_site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        quantity=20.0,
        estimated_delivery_date=date.today() + timedelta(weeks=1),
        config_id=test_config.id,
        scenario_id=test_scenario.id,
        order_round=1,
        arrival_round=1,
    )

    await db_session.commit()

    # Calculate ATP
    atp_data = await atp_service.calculate_atp(
        site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        config_id=test_config.id,
        scenario_id=test_scenario.id,
        current_round=1,
        horizon_rounds=4,
    )

    # ATP = On-hand (100) + In-transit (20) - Committed (30) - Backlog (30) = 60
    assert atp_data['current_atp'] == 60.0
    assert atp_data['on_hand'] == 100.0
    assert atp_data['in_transit'] == 20.0
    assert atp_data['committed'] == 30.0
    assert atp_data['backlog'] == 30.0


@pytest.mark.asyncio
async def test_calculate_promise_date_immediate(db_session: AsyncSession, test_sites, test_product, test_config, test_scenario, test_inventory):
    """Test promise date calculation when ATP is sufficient."""
    atp_service = ATPCalculationService(db_session)

    promise = await atp_service.calculate_promise_date(
        site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        requested_quantity=50.0,
        requested_date=date.today() + timedelta(weeks=1),
        config_id=test_config.id,
        scenario_id=test_scenario.id,
        current_round=1,
    )

    assert promise['can_promise'] is True
    assert promise['promised_quantity'] == 50.0
    assert promise['shortfall_quantity'] == 0.0
    assert promise['confidence'] == 1.0


@pytest.mark.asyncio
async def test_calculate_promise_date_insufficient(db_session: AsyncSession, test_sites, test_product, test_config, test_scenario, test_inventory):
    """Test promise date calculation when ATP is insufficient."""
    atp_service = ATPCalculationService(db_session)

    promise = await atp_service.calculate_promise_date(
        site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        requested_quantity=150.0,  # > 100 available
        requested_date=date.today() + timedelta(weeks=1),
        config_id=test_config.id,
        scenario_id=test_scenario.id,
        current_round=1,
    )

    assert promise['can_promise'] is False
    assert promise['promised_quantity'] == 100.0
    assert promise['shortfall_quantity'] == 50.0


@pytest.mark.asyncio
async def test_check_fulfillment_feasibility(db_session: AsyncSession, test_sites, test_product, test_config, test_scenario, test_inventory):
    """Test quick fulfillment feasibility check."""
    atp_service = ATPCalculationService(db_session)

    # Should be feasible
    feasible = await atp_service.check_fulfillment_feasibility(
        site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        required_quantity=80.0,
        config_id=test_config.id,
        scenario_id=test_scenario.id,
    )
    assert feasible is True

    # Should not be feasible
    not_feasible = await atp_service.check_fulfillment_feasibility(
        site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        required_quantity=150.0,
        config_id=test_config.id,
        scenario_id=test_scenario.id,
    )
    assert not_feasible is False


# ============================================================================
# End-to-End Integration Test
# ============================================================================

@pytest.mark.asyncio
async def test_end_to_end_order_fulfillment_cycle(db_session: AsyncSession, test_sites, test_product, test_config, test_scenario, test_inventory):
    """
    End-to-end test of complete order fulfillment cycle:
    1. Customer places order
    2. ATP check and promise
    3. Fulfill order and create TO
    4. Receive TO at destination
    5. Update inventory
    """
    order_mgmt = OrderManagementService(db_session)
    fulfillment = FulfillmentService(db_session)
    atp_service = ATPCalculationService(db_session)

    # Step 1: Customer places order
    order = await order_mgmt.create_customer_order(
        order_id="ORDER-E2E-001",
        line_number=1,
        product_id=test_product.product_id,
        site_id=test_sites['retailer'].id,
        ordered_quantity=40.0,
        requested_delivery_date=date.today() + timedelta(weeks=1),
        market_demand_site_id=test_sites['market_demand'].id,
        config_id=test_config.id,
        scenario_id=test_scenario.id,
    )

    # Step 2: Check ATP and promise
    promise = await atp_service.calculate_promise_date(
        site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        requested_quantity=40.0,
        requested_date=date.today() + timedelta(weeks=1),
        config_id=test_config.id,
        scenario_id=test_scenario.id,
        current_round=1,
    )

    assert promise['can_promise'] is True

    # Confirm order
    order.status = "CONFIRMED"
    order.promised_quantity = 40.0
    order.backlog_quantity = 40.0
    await db_session.commit()

    # Step 3: Fulfill order
    result = await fulfillment.fulfill_customer_orders_fifo(
        site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        scenario_id=test_scenario.id,
        config_id=test_config.id,
        current_round=1,
    )

    assert result['orders_fulfilled'] == 1
    assert result['quantity_shipped'] == 40.0
    assert len(result['transfer_orders_created']) == 1

    # Check order status
    await db_session.refresh(order)
    assert order.status == "FULFILLED"
    assert order.shipped_quantity == 40.0
    assert order.backlog_quantity == 0.0

    # Check inventory reduced
    inv = await fulfillment.get_inventory_level(
        site_id=test_sites['retailer'].id,
        product_id=test_product.product_id,
        config_id=test_config.id,
        scenario_id=test_scenario.id,
    )
    assert inv == 60.0  # 100 - 40

    # Step 4: Receive TO at customer site (arrival_round = 2)
    to = result['transfer_orders_created'][0]
    await db_session.refresh(to)

    # Simulate round advance to round 2
    receipt_result = await fulfillment.receive_shipments(
        scenario_id=test_scenario.id,
        arrival_round=to.arrival_round,
        config_id=test_config.id,
    )

    assert receipt_result['transfer_orders_received'] == 1
    assert receipt_result['total_quantity_received'] == 40.0

    # Check TO status
    await db_session.refresh(to)
    assert to.status == "RECEIVED"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
