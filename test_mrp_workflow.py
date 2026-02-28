#!/usr/bin/env python3
"""
End-to-end MRP workflow test script
Tests:
1. Login authentication
2. Run MRP on approved MPS plan
3. Verify PO/TO generation
4. Check AWS SC compliance fields
"""

import requests
import json
from pprint import pprint

BASE_URL = "http://localhost:8000/api"

def login():
    """Login and get JWT token"""
    print("=" * 80)
    print("STEP 1: Login Authentication")
    print("=" * 80)

    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={
            "username": "systemadmin@autonomy.ai",
            "password": "Autonomy@2026"
        }
    )

    if response.status_code != 200:
        print(f"❌ Login failed: {response.status_code}")
        print(response.text)
        return None

    cookies = response.cookies
    print("✅ Login successful")
    print(f"Session cookies: {dict(cookies)}")
    return cookies


def run_mrp(cookies, mps_plan_id=2):
    """Run MRP on approved MPS plan"""
    print("\n" + "=" * 80)
    print(f"STEP 2: Run MRP on MPS Plan {mps_plan_id}")
    print("=" * 80)

    payload = {
        "mps_plan_id": mps_plan_id,
        "planning_horizon_weeks": None,  # Use MPS plan horizon
        "explode_bom_levels": None,  # Explode all levels
        "generate_orders": True,  # Auto-generate PO/TO orders
        "run_async": False  # Synchronous execution
    }

    print(f"\nRequest payload:")
    pprint(payload)

    response = requests.post(
        f"{BASE_URL}/mrp/run",
        json=payload,
        cookies=cookies
    )

    if response.status_code != 200:
        print(f"\n❌ MRP run failed: {response.status_code}")
        print(response.text)
        return None

    result = response.json()
    print(f"\n✅ MRP run completed successfully")
    print(f"\nRun ID: {result['run_id']}")
    print(f"Status: {result['status']}")
    print(f"\nSummary:")
    pprint(result['summary'])

    print(f"\nRequirements: {len(result['requirements'])} items")
    for req in result['requirements'][:3]:  # Show first 3
        print(f"  - {req['component_name']}: Net Req = {req['net_requirement']}")

    print(f"\nGenerated Orders: {len(result['generated_orders'])} orders")
    for order in result['generated_orders'][:5]:  # Show first 5
        print(f"  - {order['order_type']}: {order['component_name']} x {order['quantity']}")

    if result['exceptions']:
        print(f"\n⚠️  Exceptions: {len(result['exceptions'])} issues")
        for exc in result['exceptions'][:3]:
            print(f"  - [{exc['severity']}] {exc['message']}")
    else:
        print(f"\n✅ No exceptions")

    return result


def check_purchase_orders(cookies):
    """Check generated purchase orders"""
    print("\n" + "=" * 80)
    print("STEP 3: Check Generated Purchase Orders")
    print("=" * 80)

    response = requests.get(
        f"{BASE_URL}/purchase-orders/",
        cookies=cookies
    )

    if response.status_code != 200:
        print(f"❌ Failed to fetch purchase orders: {response.status_code}")
        print(response.text)
        return None

    pos = response.json()
    print(f"\n✅ Found {len(pos)} purchase orders")

    for po in pos[:3]:  # Show first 3
        print(f"\nPO Number: {po['po_number']}")
        print(f"  Status: {po['status']}")
        print(f"  Vendor ID: {po.get('vendor_id', 'N/A')}")
        print(f"  Total Amount: ${po.get('total_amount', 0):.2f}")
        print(f"  Line Items: {po.get('line_items_count', 0)}")

        # Check AWS SC compliance fields
        print(f"  AWS SC Fields:")
        print(f"    company_id: {po.get('company_id', 'N/A')}")
        print(f"    order_type: {po.get('order_type', 'N/A')}")
        print(f"    source: {po.get('source', 'N/A')}")

    return pos


def check_transfer_orders(cookies):
    """Check generated transfer orders"""
    print("\n" + "=" * 80)
    print("STEP 4: Check Generated Transfer Orders")
    print("=" * 80)

    response = requests.get(
        f"{BASE_URL}/transfer-orders/",
        cookies=cookies
    )

    if response.status_code != 200:
        print(f"❌ Failed to fetch transfer orders: {response.status_code}")
        print(response.text)
        return None

    tos = response.json()
    print(f"\n✅ Found {len(tos)} transfer orders")

    for to in tos[:3]:  # Show first 3
        print(f"\nTO Number: {to['to_number']}")
        print(f"  Status: {to['status']}")
        print(f"  Source Site: {to.get('source_site_name', 'N/A')}")
        print(f"  Destination Site: {to.get('destination_site_name', 'N/A')}")
        print(f"  Line Items: {to.get('line_items_count', 0)}")

        # Check AWS SC compliance fields
        print(f"  AWS SC Fields:")
        print(f"    company_id: {to.get('company_id', 'N/A')}")
        print(f"    order_type: {to.get('order_type', 'N/A')}")
        print(f"    from_tpartner_id: {to.get('from_tpartner_id', 'N/A')}")
        print(f"    to_tpartner_id: {to.get('to_tpartner_id', 'N/A')}")

    return tos


def main():
    print("\n" + "=" * 80)
    print("MRP WORKFLOW END-TO-END TEST")
    print("=" * 80)

    # Step 1: Login
    cookies = login()
    if not cookies:
        print("\n❌ Test failed: Could not authenticate")
        return

    # Step 2: Run MRP
    mrp_result = run_mrp(cookies)
    if not mrp_result:
        print("\n❌ Test failed: MRP run failed")
        return

    # Step 3: Check POs
    pos = check_purchase_orders(cookies)

    # Step 4: Check TOs
    tos = check_transfer_orders(cookies)

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"✅ MRP Run: {mrp_result['status']}")
    print(f"✅ Components: {mrp_result['summary']['total_components']}")
    print(f"✅ Planned Orders: {mrp_result['summary']['total_planned_orders']}")
    print(f"✅ Exceptions: {mrp_result['summary']['total_exceptions']}")

    if pos is not None:
        print(f"✅ Purchase Orders: {len(pos)} generated")

    if tos is not None:
        print(f"✅ Transfer Orders: {len(tos)} generated")

    print("\n" + "=" * 80)
    print("END-TO-END TEST COMPLETED SUCCESSFULLY")
    print("=" * 80)


if __name__ == "__main__":
    main()
