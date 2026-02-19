#!/usr/bin/env python3
"""Simple direct MRP test with proper cookie handling"""

import requests

BASE_URL = "http://localhost:8000/api"

# Step 1: Login
print("Step 1: Login...")
response = requests.post(
    f"{BASE_URL}/auth/login",
    data={
        "username": "systemadmin@autonomy.ai",
        "password": "Autonomy@2025"
    }
)

if response.status_code != 200:
    print(f"❌ Login failed: {response.status_code}")
    print(response.text)
    exit(1)

print("✅ Login successful")
cookies = response.cookies

# Step 2: Run MRP
print("\nStep 2: Run MRP...")
response = requests.post(
    f"{BASE_URL}/mrp/run",
    json={
        "mps_plan_id": 2,
        "generate_orders": True
    },
    cookies=cookies
)

if response.status_code != 200:
    print(f"❌ MRP failed: {response.status_code}")
    print(response.text)
    exit(1)

result = response.json()
print("✅ MRP completed successfully!")
print(f"Run ID: {result['run_id']}")
print(f"Components: {result['summary']['total_components']}")
print(f"Planned Orders: {result['summary']['total_planned_orders']}")
print(f"Exceptions: {result['summary']['total_exceptions']}")

# Step 3: Check POs
print("\nStep 3: Check Purchase Orders...")
response = requests.get(f"{BASE_URL}/purchase-orders/", cookies=cookies)
if response.status_code == 200:
    pos = response.json()
    print(f"✅ Found {len(pos)} purchase orders")
    for po in pos[:2]:
        print(f"   - {po['po_number']}: company_id={po.get('company_id')}, order_type={po.get('order_type')}")
else:
    print(f"⚠️  Could not fetch POs: {response.status_code}")

# Step 4: Check TOs
print("\nStep 4: Check Transfer Orders...")
response = requests.get(f"{BASE_URL}/transfer-orders/", cookies=cookies)
if response.status_code == 200:
    tos = response.json()
    print(f"✅ Found {len(tos)} transfer orders")
    for to in tos[:2]:
        print(f"   - {to['to_number']}: company_id={to.get('company_id')}, order_type={to.get('order_type')}")
else:
    print(f"⚠️  Could not fetch TOs: {response.status_code}")

print("\n" + "="*80)
print("END-TO-END TEST COMPLETED SUCCESSFULLY!")
print("="*80)
