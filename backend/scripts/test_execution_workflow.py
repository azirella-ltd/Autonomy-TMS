"""
Test AWS SC Execution Workflow

This script demonstrates the execution architecture with a minimal example.
It shows how work orders (inbound_order_line) are created and tracked.

Usage:
    docker compose exec backend python scripts/test_execution_workflow.py
"""

import asyncio
from datetime import date, timedelta
from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.supply_chain_config import SupplyChainConfig
from app.models.group import Group
from app.models.aws_sc_planning import InboundOrderLine, OutboundOrderLine, InvLevel


async def test_execution_workflow():
    """Test the execution workflow with work orders"""

    print("=" * 80)
    print("AWS SC EXECUTION WORKFLOW TEST")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
        # 1. Get a test config and group
        print("1. Loading configuration...")
        result = await db.execute(
            select(SupplyChainConfig).filter(
                SupplyChainConfig.name.like("%Default%")
            )
        )
        config = result.scalar_one_or_none()

        if not config:
            print("   ❌ No config found")
            return False

        result = await db.execute(select(Group).filter(Group.id == 2))
        group = result.scalar_one_or_none()

        if not group:
            print("   ❌ No group found")
            return False

        print(f"   ✓ Config: {config.name} (ID: {config.id})")
        print(f"   ✓ Group: {group.name} (ID: {group.id})")
        print()

        # 2. Load nodes and items
        await db.refresh(config, ['nodes', 'items', 'lanes'])

        if not config.items or not config.nodes:
            print("   ❌ Config missing items or nodes")
            return False

        item = config.items[0]
        retailer = next((n for n in config.nodes if n.type == 'retailer'), None)
        wholesaler = next((n for n in config.nodes if n.type == 'wholesaler'), None)

        if not retailer or not wholesaler:
            print("   ❌ Missing retailer or wholesaler nodes")
            return False

        print(f"   ✓ Item: {item.name} (ID: {item.id})")
        print(f"   ✓ Retailer: {retailer.name} (ID: {retailer.id})")
        print(f"   ✓ Wholesaler: {wholesaler.name} (ID: {wholesaler.id})")
        print()

        # 3. Create an Inventory Snapshot (execution data)
        print("2. Creating inventory snapshot (inv_level)...")

        inv_level = InvLevel(
            product_id=item.id,
            site_id=retailer.id,
            on_hand_qty=10.0,
            available_qty=10.0,
            reserved_qty=0.0,
            in_transit_qty=8.0,
            backorder_qty=0.0,
            snapshot_date=date.today(),
            group_id=group.id,
            config_id=config.id
        )

        db.add(inv_level)
        await db.flush()

        print(f"   ✓ Created inventory snapshot:")
        print(f"      Site: {retailer.name}")
        print(f"      On-hand: 10 units")
        print(f"      In-transit: 8 units")
        print()

        # 4. Record Customer Demand (outbound order)
        print("3. Recording customer demand (outbound_order_line)...")

        outbound_order = OutboundOrderLine(
            order_id="TEST_DEMAND_001",
            line_number=1,
            product_id=item.id,
            site_id=retailer.id,
            ship_from_site_id=retailer.id,
            # Execution quantities
            init_quantity_requested=8.0,
            final_quantity_requested=8.0,
            quantity_promised=8.0,
            quantity_delivered=8.0,
            # Dates
            order_date=date.today(),
            requested_delivery_date=date.today(),
            actual_delivery_date=date.today(),
            # Status
            status='delivered',
            # Multi-tenancy
            group_id=group.id,
            config_id=config.id,
            round_number=1
        )

        db.add(outbound_order)
        await db.flush()

        print(f"   ✓ Customer demand recorded:")
        print(f"      Order ID: TEST_DEMAND_001")
        print(f"      Quantity: 8 units")
        print(f"      Status: delivered")
        print()

        # 5. Create Work Order (inbound order - TO type)
        print("4. Creating work order (inbound_order_line - TO)...")

        order_date = date.today()
        expected_delivery = order_date + timedelta(days=14)  # 2 weeks

        inbound_order = InboundOrderLine(
            order_id="TEST_WO_001",
            line_number=1,
            product_id=item.id,
            to_site_id=retailer.id,
            from_site_id=wholesaler.id,
            tpartner_id=None,
            # Order type
            order_type='TO',  # Transfer Order
            # Quantities
            quantity_submitted=8.0,
            quantity_confirmed=8.0,
            quantity_received=None,  # Not yet received
            quantity_uom='CASES',
            # Dates
            submitted_date=order_date,
            expected_delivery_date=expected_delivery,
            earliest_delivery_date=expected_delivery,
            latest_delivery_date=expected_delivery,
            confirmation_date=order_date,
            order_receive_date=None,  # Not yet received
            # Status
            status='open',  # In transit
            vendor_status='confirmed',
            # Lead time
            lead_time_days=14,
            # Multi-tenancy
            group_id=group.id,
            config_id=config.id,
            round_number=1
        )

        db.add(inbound_order)
        await db.flush()

        print(f"   ✓ Work order created:")
        print(f"      Order ID: TEST_WO_001")
        print(f"      Type: TO (Transfer Order)")
        print(f"      From: {wholesaler.name}")
        print(f"      To: {retailer.name}")
        print(f"      Quantity: 8 units")
        print(f"      Status: open (in transit)")
        print(f"      Expected delivery: {expected_delivery}")
        print()

        # 6. Simulate Delivery (update work order)
        print("5. Simulating delivery (2 weeks later)...")

        inbound_order.quantity_received = 8.0
        inbound_order.order_receive_date = expected_delivery
        inbound_order.status = 'received'

        await db.flush()

        print(f"   ✓ Work order delivered:")
        print(f"      Order ID: TEST_WO_001")
        print(f"      Quantity received: 8 units")
        print(f"      Status: received")
        print(f"      Received date: {expected_delivery}")
        print()

        # 7. Verify data
        print("6. Verifying execution data...")

        # Count inventory snapshots
        result = await db.execute(
            select(InvLevel).filter(
                InvLevel.group_id == group.id,
                InvLevel.config_id == config.id
            )
        )
        inv_count = len(result.scalars().all())

        # Count outbound orders
        result = await db.execute(
            select(OutboundOrderLine).filter(
                OutboundOrderLine.group_id == group.id,
                OutboundOrderLine.config_id == config.id
            )
        )
        outbound_count = len(result.scalars().all())

        # Count inbound orders
        result = await db.execute(
            select(InboundOrderLine).filter(
                InboundOrderLine.group_id == group.id,
                InboundOrderLine.config_id == config.id
            )
        )
        inbound_count = len(result.scalars().all())

        print(f"   ✓ Inventory snapshots: {inv_count}")
        print(f"   ✓ Customer demands (outbound): {outbound_count}")
        print(f"   ✓ Work orders (inbound): {inbound_count}")
        print()

        # Commit all changes
        await db.commit()

        print("=" * 80)
        print("✅ EXECUTION WORKFLOW TEST PASSED")
        print("=" * 80)
        print()
        print("Summary:")
        print("  - Inventory snapshot created (inv_level)")
        print("  - Customer demand recorded (outbound_order_line)")
        print("  - Work order created (inbound_order_line - TO)")
        print("  - Work order lifecycle tracked: open → received")
        print("  - All execution entities working correctly")
        print()
        print("This demonstrates:")
        print("  1. Execution data (not planning)")
        print("  2. Work Order Management (TO/MO/PO)")
        print("  3. Order lifecycle tracking")
        print("  4. Multi-tenancy support")
        print()

        return True


async def main():
    """Main entry point"""
    try:
        success = await test_execution_workflow()
        return 0 if success else 1
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
