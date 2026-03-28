"""
Generate SAP Business One demo data in Service Layer JSON format.

Creates realistic OEC Computers data matching B1 Service Layer entity schemas.
Output: JSON files in the target directory, one per entity.

Usage:
    python scripts/generate_b1_demo_data.py /tmp/b1_export
    python scripts/generate_b1_demo_data.py /tmp/b1_export --items 200
"""

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/b1_export")
NUM_ITEMS = int(sys.argv[2]) if len(sys.argv) > 2 else 150

# ---------------------------------------------------------------------------
# Warehouses
# ---------------------------------------------------------------------------

WAREHOUSES = [
    {"WarehouseCode": "01", "WarehouseName": "General Warehouse", "Street": "1901 Maynesboro Drive", "City": "New York", "State": "NY", "Country": "US", "ZipCode": "19065", "Inactive": "tNO", "DefaultBin": None},
    {"WarehouseCode": "02", "WarehouseName": "West Coast Warehouse", "Street": "5th Avenue 203", "City": "Los Angeles", "State": "CA", "Country": "US", "ZipCode": "509303", "Inactive": "tNO", "DefaultBin": None},
    {"WarehouseCode": "03", "WarehouseName": "Dropship Warehouse", "Street": "Arenas Street 450", "City": "New York", "State": "NY", "Country": "US", "ZipCode": "", "Inactive": "tNO", "DefaultBin": None},
    {"WarehouseCode": "04", "WarehouseName": "Consignment Warehouse", "Street": "1901 Maynesboro Drive", "City": "New York", "State": "NY", "Country": "US", "ZipCode": "19065", "Inactive": "tNO", "DefaultBin": None},
    {"WarehouseCode": "05", "WarehouseName": "Assembly Floor", "Street": "800 Industrial Pkwy", "City": "Chicago", "State": "IL", "Country": "US", "ZipCode": "60601", "Inactive": "tNO", "DefaultBin": None},
]

# ---------------------------------------------------------------------------
# Business Partners
# ---------------------------------------------------------------------------

VENDORS = [
    {"CardCode": "V10000", "CardName": "Maxi-Teq", "CardType": "cSupplier", "GroupCode": 1, "Address": "110 Main St", "City": "San Jose", "Country": "US", "ZipCode": "95101", "Phone1": "408-555-0100", "EmailAddress": "orders@maxiteq.com", "Currency": "$", "Valid": "tYES"},
    {"CardCode": "V1010", "CardName": "Panorama Studios", "CardType": "cSupplier", "GroupCode": 1, "Address": "200 Elm Rd", "City": "Austin", "Country": "US", "ZipCode": "73301", "Phone1": "512-555-0200", "EmailAddress": "sales@panorama.com", "Currency": "$", "Valid": "tYES"},
    {"CardCode": "V20000", "CardName": "Park Systems", "CardType": "cSupplier", "GroupCode": 1, "Address": "300 Oak Ave", "City": "Seattle", "Country": "US", "ZipCode": "98101", "Phone1": "206-555-0300", "EmailAddress": "supply@parksys.com", "Currency": "$", "Valid": "tYES"},
    {"CardCode": "V30000", "CardName": "Earthshaker Corp", "CardType": "cSupplier", "GroupCode": 1, "Address": "400 Pine Blvd", "City": "Portland", "Country": "US", "ZipCode": "97201", "Phone1": "503-555-0400", "EmailAddress": "info@earthshaker.com", "Currency": "$", "Valid": "tYES"},
    {"CardCode": "V40000", "CardName": "Micro Chips", "CardType": "cSupplier", "GroupCode": 1, "Address": "500 Circuit Dr", "City": "San Diego", "Country": "US", "ZipCode": "92101", "Phone1": "619-555-0500", "EmailAddress": "orders@microchips.com", "Currency": "$", "Valid": "tYES"},
    {"CardCode": "V50000", "CardName": "SB Electronics", "CardType": "cSupplier", "GroupCode": 1, "Address": "600 Volt Way", "City": "Denver", "Country": "US", "ZipCode": "80201", "Phone1": "303-555-0600", "EmailAddress": "sales@sbelectronics.com", "Currency": "$", "Valid": "tYES"},
]

CUSTOMERS = [
    {"CardCode": "C10000", "CardName": "Microchips", "CardType": "cCustomer", "GroupCode": 2, "Address": "1 Market St", "City": "San Francisco", "Country": "US", "ZipCode": "94105", "Phone1": "415-555-1000", "EmailAddress": "purchasing@microchips.com", "Currency": "$", "Valid": "tYES"},
    {"CardCode": "C20000", "CardName": "Norm Thompson", "CardType": "cCustomer", "GroupCode": 2, "Address": "2 Broadway", "City": "New York", "Country": "US", "ZipCode": "10001", "Phone1": "212-555-2000", "EmailAddress": "orders@normthompson.com", "Currency": "$", "Valid": "tYES"},
    {"CardCode": "C23900", "CardName": "One Time Customer", "CardType": "cCustomer", "GroupCode": 2, "Address": "3 Oak Lane", "City": "Boston", "Country": "US", "ZipCode": "02101", "Phone1": "617-555-2390", "EmailAddress": "info@onetime.com", "Currency": "$", "Valid": "tYES"},
    {"CardCode": "C30000", "CardName": "Maxi-Teq", "CardType": "cCustomer", "GroupCode": 2, "Address": "4 Tech Blvd", "City": "Dallas", "Country": "US", "ZipCode": "75201", "Phone1": "214-555-3000", "EmailAddress": "buy@maxiteq-retail.com", "Currency": "$", "Valid": "tYES"},
    {"CardCode": "C40000", "CardName": "Precision Computers", "CardType": "cCustomer", "GroupCode": 2, "Address": "5 Gear Ave", "City": "Atlanta", "Country": "US", "ZipCode": "30301", "Phone1": "404-555-4000", "EmailAddress": "orders@precisioncomp.com", "Currency": "$", "Valid": "tYES"},
    {"CardCode": "C50000", "CardName": "Sandra & Co", "CardType": "cCustomer", "GroupCode": 2, "Address": "6 River Rd", "City": "Miami", "Country": "US", "ZipCode": "33101", "Phone1": "305-555-5000", "EmailAddress": "purchasing@sandraandco.com", "Currency": "$", "Valid": "tYES"},
    {"CardCode": "C60000", "CardName": "Johnson Electronics", "CardType": "cCustomer", "GroupCode": 2, "Address": "7 Park Way", "City": "Phoenix", "Country": "US", "ZipCode": "85001", "Phone1": "602-555-6000", "EmailAddress": "orders@johnsonelec.com", "Currency": "$", "Valid": "tYES"},
    {"CardCode": "C70000", "CardName": "TechMart Retail", "CardType": "cCustomer", "GroupCode": 2, "Address": "8 Mall Dr", "City": "Minneapolis", "Country": "US", "ZipCode": "55401", "Phone1": "612-555-7000", "EmailAddress": "buying@techmart.com", "Currency": "$", "Valid": "tYES"},
]

BUSINESS_PARTNERS = VENDORS + CUSTOMERS

# ---------------------------------------------------------------------------
# Items — OEC Computers product line
# ---------------------------------------------------------------------------

ITEM_GROUPS = {
    101: "Printers",
    102: "Color Printers",
    103: "Scanners",
    104: "Monitors",
    105: "Keyboards & Mice",
    106: "Cables & Accessories",
    107: "Ink & Toner",
    108: "Paper & Media",
    109: "Desktops",
    110: "Laptops",
    111: "Components",
    112: "Networking",
    113: "Storage",
    114: "Software",
}

# Finished goods (sold to customers, sometimes manufactured)
FINISHED_GOODS = [
    ("A00001", "J.B. Officeprint 1420", 101, 210.00, 350.00, "V10000"),
    ("A00002", "J.B. Officeprint 1111", 101, 155.00, 280.00, "V1010"),
    ("A00003", "J.B. Officeprint 1186", 101, 217.00, 395.00, "V20000"),
    ("A00004", "Rainbow Color Printer 5.0", 102, 340.00, 599.00, "V10000"),
    ("A00005", "Rainbow Color Printer 7.5", 102, 284.00, 499.00, "V1010"),
    ("A00006", "Rainbow 1200 Laser Series", 102, 493.00, 849.00, "V20000"),
    ("A00007", "High-End Laser Printer Z80", 102, 520.00, 899.00, "V10000"),
    ("A00008", "EcoJet Inkjet Printer", 101, 85.00, 149.00, "V1010"),
    ("A00009", "PowerScan Pro 3000", 103, 190.00, 329.00, "V20000"),
    ("A00010", "PowerScan Home 1500", 103, 95.00, 169.00, "V30000"),
    ("A10001", "HD Monitor 24-inch", 104, 180.00, 319.00, "V40000"),
    ("A10002", "HD Monitor 27-inch", 104, 250.00, 449.00, "V40000"),
    ("A10003", "UltraWide Monitor 34-inch", 104, 420.00, 749.00, "V40000"),
    ("A10004", "Gaming Monitor 32-inch 144Hz", 104, 380.00, 679.00, "V40000"),
    ("A20001", "Wireless Keyboard Pro", 105, 25.00, 59.00, "V50000"),
    ("A20002", "Wireless Mouse Ergo", 105, 15.00, 39.00, "V50000"),
    ("A20003", "Mechanical Keyboard RGB", 105, 55.00, 119.00, "V50000"),
    ("A20004", "Keyboard & Mouse Combo", 105, 30.00, 69.00, "V50000"),
    ("A30001", "Laptop UltraBook 14-inch", 110, 650.00, 1199.00, "V10000"),
    ("A30002", "Laptop ProBook 15-inch", 110, 520.00, 949.00, "V10000"),
    ("A30003", "Laptop Budget 14-inch", 110, 320.00, 599.00, "V1010"),
    ("A40001", "Desktop WorkStation Pro", 109, 780.00, 1399.00, "V10000"),
    ("A40002", "Desktop HomePC", 109, 380.00, 699.00, "V1010"),
    ("A40003", "Desktop MiniPC", 109, 280.00, 499.00, "V20000"),
    ("A50001", "NAS Storage 4-Bay", 113, 320.00, 569.00, "V30000"),
    ("A50002", "External SSD 1TB", 113, 65.00, 119.00, "V30000"),
    ("A50003", "USB Flash Drive 64GB", 113, 8.00, 19.00, "V50000"),
    ("A60001", "Network Switch 24-Port", 112, 180.00, 329.00, "V40000"),
    ("A60002", "WiFi Router AC3000", 112, 95.00, 179.00, "V40000"),
    ("A60003", "Network Cable Cat6 50ft", 106, 12.00, 24.00, "V50000"),
]

# Raw materials / components (purchased, used in BOMs)
RAW_MATERIALS = [
    ("R10001", "Printer Drum Unit", 107, 45.00, "V10000"),
    ("R10002", "Toner Cartridge Black", 107, 28.00, "V10000"),
    ("R10003", "Toner Cartridge Color Set", 107, 65.00, "V20000"),
    ("R10004", "Ink Cartridge Black", 107, 12.00, "V30000"),
    ("R10005", "Ink Cartridge Color", 107, 18.00, "V30000"),
    ("R10006", "Fuser Assembly", 111, 35.00, "V10000"),
    ("R10007", "Paper Feed Roller", 111, 8.00, "V20000"),
    ("R10008", "Scanner Glass Panel", 111, 22.00, "V20000"),
    ("R10009", "LCD Panel 24-inch", 111, 95.00, "V40000"),
    ("R10010", "LCD Panel 27-inch", 111, 130.00, "V40000"),
    ("R10011", "LCD Panel 34-inch UW", 111, 220.00, "V40000"),
    ("R10012", "Power Supply Unit 500W", 111, 38.00, "V50000"),
    ("R10013", "Motherboard ATX", 111, 85.00, "V10000"),
    ("R10014", "CPU Intel i5", 111, 180.00, "V10000"),
    ("R10015", "CPU Intel i7", 111, 310.00, "V10000"),
    ("R10016", "RAM 16GB DDR4", 111, 42.00, "V40000"),
    ("R10017", "RAM 32GB DDR4", 111, 75.00, "V40000"),
    ("R10018", "SSD 512GB NVMe", 111, 45.00, "V30000"),
    ("R10019", "SSD 1TB NVMe", 111, 80.00, "V30000"),
    ("R10020", "HDD 2TB SATA", 111, 55.00, "V30000"),
    ("R10021", "Desktop Chassis Mid-Tower", 111, 45.00, "V50000"),
    ("R10022", "Laptop Shell 14-inch", 111, 65.00, "V1010"),
    ("R10023", "Laptop Battery 72Wh", 111, 35.00, "V1010"),
    ("R10024", "WiFi Module AC", 111, 12.00, "V40000"),
    ("R10025", "Keyboard Mechanism", 111, 8.00, "V50000"),
    ("R000011", "Printer Paper A4 White", 108, 3.50, "V30000"),
    ("R000012", "Photo Paper A4 Glossy", 108, 12.00, "V30000"),
    ("R000013", "USB Cable Type-C 6ft", 106, 4.00, "V50000"),
    ("R000014", "HDMI Cable 6ft", 106, 5.00, "V50000"),
    ("R000015", "Power Cord Standard", 106, 3.00, "V50000"),
]

# Labor items (non-stock)
LABOR_ITEMS = [
    ("L10001", "Labor Hours Production", 100, 5.00),
    ("LB0001", "Daily Service Labor Charge", 100, 200.00),
    ("LB0002", "Hourly Service Labor Charge", 100, 50.00),
]


def build_items():
    items = []
    for code, name, grp, cost, price, vendor in FINISHED_GOODS:
        items.append({
            "ItemCode": code, "ItemName": name, "ItemType": "itItems",
            "ItemsGroupCode": grp, "InventoryItem": "tYES",
            "SalesItem": "tYES", "PurchaseItem": "tYES",
            "AvgStdPrice": cost, "QuantityOnStock": random.randint(50, 800),
            "QuantityOrderedByCustomers": random.randint(10, 200),
            "QuantityOrderedFromVendors": random.randint(5, 150),
            "DefaultWarehouse": random.choice(["01", "02"]),
            "PreferredVendor": vendor,
            "ManageBatchNumbers": "tNO", "ManageSerialNumbers": "tNO",
            "Valid": "tYES",
            "PurchaseUnit": "Each", "PurchaseItemsPerUnit": 1,
            "SalesUnit": "Each", "SalesItemsPerUnit": 1,
            "PurchaseUnitPrice": cost, "SalesUnitPrice": price,
        })
    for code, name, grp, cost, vendor in RAW_MATERIALS:
        items.append({
            "ItemCode": code, "ItemName": name, "ItemType": "itItems",
            "ItemsGroupCode": grp, "InventoryItem": "tYES",
            "SalesItem": "tNO", "PurchaseItem": "tYES",
            "AvgStdPrice": cost, "QuantityOnStock": random.randint(100, 2000),
            "QuantityOrderedByCustomers": 0,
            "QuantityOrderedFromVendors": random.randint(20, 500),
            "DefaultWarehouse": "01",
            "PreferredVendor": vendor,
            "ManageBatchNumbers": "tNO", "ManageSerialNumbers": "tNO",
            "Valid": "tYES",
            "PurchaseUnit": "Each", "PurchaseItemsPerUnit": 1,
            "PurchaseUnitPrice": cost,
        })
    for code, name, grp, cost in LABOR_ITEMS:
        items.append({
            "ItemCode": code, "ItemName": name, "ItemType": "itItems",
            "ItemsGroupCode": grp, "InventoryItem": "tNO",
            "SalesItem": "tYES", "PurchaseItem": "tNO",
            "AvgStdPrice": cost, "QuantityOnStock": 0,
            "Valid": "tYES",
        })
    return items


# ---------------------------------------------------------------------------
# Product Trees (BOMs)
# ---------------------------------------------------------------------------

BOMS = {
    "A00004": [  # Rainbow Color Printer 5.0
        ("R10001", 1, "01"), ("R10003", 1, "01"), ("R10006", 1, "01"),
        ("R10007", 2, "01"), ("R000015", 1, "01"), ("L10001", 0.5, "01"),
    ],
    "A00006": [  # Rainbow 1200 Laser Series
        ("R10001", 1, "01"), ("R10002", 2, "01"), ("R10003", 1, "01"),
        ("R10006", 1, "01"), ("R10007", 3, "01"), ("R000015", 1, "01"),
        ("L10001", 1.0, "01"),
    ],
    "A00007": [  # High-End Laser Printer Z80
        ("R10001", 2, "01"), ("R10002", 2, "01"), ("R10003", 2, "01"),
        ("R10006", 2, "01"), ("R10007", 4, "01"), ("R000015", 1, "01"),
        ("L10001", 1.5, "01"),
    ],
    "A10001": [  # HD Monitor 24-inch
        ("R10009", 1, "05"), ("R10012", 1, "05"), ("R000014", 1, "05"),
        ("R000015", 1, "05"), ("L10001", 0.5, "05"),
    ],
    "A10002": [  # HD Monitor 27-inch
        ("R10010", 1, "05"), ("R10012", 1, "05"), ("R000014", 1, "05"),
        ("R000015", 1, "05"), ("L10001", 0.5, "05"),
    ],
    "A10003": [  # UltraWide Monitor 34-inch
        ("R10011", 1, "05"), ("R10012", 1, "05"), ("R000014", 2, "05"),
        ("R000015", 1, "05"), ("L10001", 1.0, "05"),
    ],
    "A40001": [  # Desktop WorkStation Pro
        ("R10013", 1, "05"), ("R10015", 1, "05"), ("R10017", 2, "05"),
        ("R10019", 1, "05"), ("R10012", 1, "05"), ("R10021", 1, "05"),
        ("R10024", 1, "05"), ("R000015", 1, "05"), ("L10001", 2.0, "05"),
    ],
    "A40002": [  # Desktop HomePC
        ("R10013", 1, "05"), ("R10014", 1, "05"), ("R10016", 1, "05"),
        ("R10018", 1, "05"), ("R10012", 1, "05"), ("R10021", 1, "05"),
        ("R10024", 1, "05"), ("R000015", 1, "05"), ("L10001", 1.5, "05"),
    ],
    "A30001": [  # Laptop UltraBook 14-inch
        ("R10014", 1, "05"), ("R10016", 1, "05"), ("R10018", 1, "05"),
        ("R10022", 1, "05"), ("R10023", 1, "05"), ("R10024", 1, "05"),
        ("R10025", 1, "05"), ("L10001", 2.0, "05"),
    ],
    "A30002": [  # Laptop ProBook 15-inch
        ("R10015", 1, "05"), ("R10017", 1, "05"), ("R10019", 1, "05"),
        ("R10022", 1, "05"), ("R10023", 1, "05"), ("R10024", 1, "05"),
        ("R10025", 1, "05"), ("L10001", 2.5, "05"),
    ],
}


def build_product_trees():
    trees = []
    tree_lines = []
    for tree_code, components in BOMS.items():
        trees.append({
            "TreeCode": tree_code,
            "TreeType": "iProductionTree",
            "Quantity": 1.0,
        })
        for i, (item_code, qty, whs) in enumerate(components):
            tree_lines.append({
                "TreeCode": tree_code,
                "LineNumber": i,
                "ItemCode": item_code,
                "Quantity": qty,
                "Warehouse": whs,
                "IssueMethod": "im_Manual",
            })
    return trees, tree_lines


# ---------------------------------------------------------------------------
# Item Warehouse Info
# ---------------------------------------------------------------------------

def build_item_warehouse_info():
    rows = []
    all_items = [(c, n) for c, n, *_ in FINISHED_GOODS] + [(c, n) for c, n, *_ in RAW_MATERIALS]
    for code, name in all_items:
        for whs in ["01", "02"]:
            on_hand = random.randint(0, 500) if whs == "01" else random.randint(0, 200)
            rows.append({
                "ItemCode": code,
                "WarehouseCode": whs,
                "InStock": float(on_hand),
                "Committed": float(random.randint(0, on_hand // 3)) if on_hand > 0 else 0.0,
                "Ordered": float(random.randint(0, 100)),
                "MinimalStock": float(random.randint(10, 50)),
                "MaximalStock": float(random.randint(200, 800)),
                "MinimalOrder": float(random.randint(5, 25)),
                "StandardAveragePrice": 0.0,
                "Locked": "tNO",
            })
    return rows


# ---------------------------------------------------------------------------
# Transaction generators
# ---------------------------------------------------------------------------

TODAY = date(2026, 3, 27)


def _random_date(days_back_min=7, days_back_max=180):
    delta = random.randint(days_back_min, days_back_max)
    return (TODAY - timedelta(days=delta)).isoformat()


def build_orders(count=80):
    """Sales Orders (ORDR + RDR1)."""
    orders = []
    for doc_entry in range(1, count + 1):
        customer = random.choice(CUSTOMERS)
        doc_date = _random_date(7, 120)
        due_date = (date.fromisoformat(doc_date) + timedelta(days=random.randint(7, 30))).isoformat()
        num_lines = random.randint(1, 5)
        items_chosen = random.sample(FINISHED_GOODS, min(num_lines, len(FINISHED_GOODS)))
        lines = []
        doc_total = 0.0
        for line_num, (item_code, item_name, grp, cost, price, vendor) in enumerate(items_chosen):
            qty = random.randint(1, 20)
            line_total = round(qty * price, 2)
            doc_total += line_total
            lines.append({
                "LineNum": line_num,
                "ItemCode": item_code,
                "ItemDescription": item_name,
                "Quantity": qty,
                "Price": price,
                "LineTotal": line_total,
                "WarehouseCode": random.choice(["01", "02"]),
                "Currency": "$",
            })
        status = random.choice(["bost_Open", "bost_Open", "bost_Open", "bost_Close"])
        orders.append({
            "DocEntry": doc_entry,
            "DocNum": 10000 + doc_entry,
            "CardCode": customer["CardCode"],
            "CardName": customer["CardName"],
            "DocDate": doc_date,
            "DocDueDate": due_date,
            "DocTotal": round(doc_total, 2),
            "DocumentStatus": status,
            "DocCurrency": "$",
            "DocumentLines": lines,
        })
    return orders


def build_purchase_orders(count=60):
    """Purchase Orders (OPOR + POR1)."""
    pos = []
    all_purchasable = FINISHED_GOODS + [(c, n, g, cost, v) for c, n, g, cost, v in RAW_MATERIALS]
    for doc_entry in range(1, count + 1):
        vendor = random.choice(VENDORS)
        doc_date = _random_date(14, 150)
        due_date = (date.fromisoformat(doc_date) + timedelta(days=random.randint(14, 45))).isoformat()
        num_lines = random.randint(1, 6)
        # Pick items from this vendor preferably
        vendor_items = [i for i in all_purchasable if (i[5] if len(i) == 6 else i[4]) == vendor["CardCode"]]
        if len(vendor_items) < num_lines:
            vendor_items = all_purchasable
        items_chosen = random.sample(vendor_items, min(num_lines, len(vendor_items)))
        lines = []
        doc_total = 0.0
        for line_num, item_tuple in enumerate(items_chosen):
            item_code = item_tuple[0]
            item_name = item_tuple[1]
            cost = item_tuple[3]
            qty = random.randint(10, 100)
            line_total = round(qty * cost, 2)
            doc_total += line_total
            lines.append({
                "LineNum": line_num,
                "ItemCode": item_code,
                "ItemDescription": item_name,
                "Quantity": qty,
                "Price": cost,
                "LineTotal": line_total,
                "WarehouseCode": random.choice(["01", "02", "05"]),
                "Currency": "$",
            })
        status = random.choice(["bost_Open", "bost_Open", "bost_Close"])
        pos.append({
            "DocEntry": doc_entry,
            "DocNum": 20000 + doc_entry,
            "CardCode": vendor["CardCode"],
            "CardName": vendor["CardName"],
            "DocDate": doc_date,
            "DocDueDate": due_date,
            "DocTotal": round(doc_total, 2),
            "DocumentStatus": status,
            "DocCurrency": "$",
            "DocumentLines": lines,
        })
    return pos


def build_production_orders(count=25):
    """Production Orders (OWOR)."""
    prod_orders = []
    bom_items = list(BOMS.keys())
    for abs_entry in range(1, count + 1):
        item_code = random.choice(bom_items)
        item_name = next(n for c, n, *_ in FINISHED_GOODS if c == item_code)
        qty = random.randint(5, 50)
        start = _random_date(30, 120)
        due = (date.fromisoformat(start) + timedelta(days=random.randint(3, 14))).isoformat()
        status = random.choice(["boposPlanned", "boposReleased", "boposReleased", "boposClosed"])
        prod_orders.append({
            "AbsoluteEntry": abs_entry,
            "DocumentNumber": 30000 + abs_entry,
            "ItemNo": item_code,
            "ProductDescription": item_name,
            "PlannedQuantity": qty,
            "CompletedQuantity": qty if status == "boposClosed" else 0,
            "ProductionOrderStatus": status,
            "PostingDate": start,
            "DueDate": due,
            "Warehouse": "05",
            "ProductionOrderType": "bopotStandard",
        })
    return prod_orders


def build_delivery_notes(orders, count=40):
    """Deliveries / Shipments (ODLN)."""
    deliveries = []
    closed_orders = [o for o in orders if o["DocumentStatus"] == "bost_Close"]
    for doc_entry in range(1, min(count + 1, len(closed_orders) + 1)):
        order = closed_orders[doc_entry - 1] if doc_entry <= len(closed_orders) else random.choice(orders)
        ship_date = (date.fromisoformat(order["DocDate"]) + timedelta(days=random.randint(3, 14))).isoformat()
        lines = []
        for line in order["DocumentLines"]:
            lines.append({
                "LineNum": line["LineNum"],
                "ItemCode": line["ItemCode"],
                "ItemDescription": line["ItemDescription"],
                "Quantity": line["Quantity"],
                "WarehouseCode": line["WarehouseCode"],
            })
        deliveries.append({
            "DocEntry": doc_entry,
            "DocNum": 40000 + doc_entry,
            "CardCode": order["CardCode"],
            "CardName": order["CardName"],
            "DocDate": ship_date,
            "DocumentStatus": "bost_Close",
            "DocumentLines": lines,
        })
    return deliveries


def build_purchase_delivery_notes(purchase_orders, count=30):
    """Goods Receipt POs (OPDN)."""
    grpos = []
    closed_pos = [p for p in purchase_orders if p["DocumentStatus"] == "bost_Close"]
    for doc_entry in range(1, min(count + 1, len(closed_pos) + 1)):
        po = closed_pos[doc_entry - 1] if doc_entry <= len(closed_pos) else random.choice(purchase_orders)
        recv_date = (date.fromisoformat(po["DocDate"]) + timedelta(days=random.randint(7, 21))).isoformat()
        lines = []
        for line in po["DocumentLines"]:
            lines.append({
                "LineNum": line["LineNum"],
                "ItemCode": line["ItemCode"],
                "ItemDescription": line["ItemDescription"],
                "Quantity": line["Quantity"],
                "Price": line["Price"],
                "WarehouseCode": line["WarehouseCode"],
            })
        grpos.append({
            "DocEntry": doc_entry,
            "DocNum": 50000 + doc_entry,
            "CardCode": po["CardCode"],
            "CardName": po["CardName"],
            "DocDate": recv_date,
            "DocumentStatus": "bost_Close",
            "DocumentLines": lines,
        })
    return grpos


def build_stock_transfers(count=15):
    """Inventory Transfers (OWTR)."""
    transfers = []
    fg_items = [(c, n) for c, n, *_ in FINISHED_GOODS]
    for doc_entry in range(1, count + 1):
        item_code, item_name = random.choice(fg_items)
        from_whs, to_whs = random.sample(["01", "02", "05"], 2)
        qty = random.randint(5, 50)
        transfers.append({
            "DocEntry": doc_entry,
            "DocNum": 60000 + doc_entry,
            "DocDate": _random_date(7, 90),
            "FromWarehouse": from_whs,
            "ToWarehouse": to_whs,
            "StockTransferLines": [{
                "LineNum": 0,
                "ItemCode": item_code,
                "ItemDescription": item_name,
                "Quantity": qty,
                "FromWarehouseCode": from_whs,
                "WarehouseCode": to_whs,
            }],
        })
    return transfers


def build_companies():
    return [{
        "DbName": "SBODemoUS",
        "CompanyName": "OEC Computers US",
        "LocalCurrency": "$",
        "SystemCurrency": "$",
        "AddressLine1": "1901 Maynesboro Drive",
        "City": "New York",
        "State": "NY",
        "Country": "US",
        "ZipCode": "19065",
    }]


def build_item_groups():
    return [{"Number": k, "GroupName": v} for k, v in ITEM_GROUPS.items()]


def build_invoices(orders, count=35):
    """A/R Invoices (OINV) — from closed sales orders."""
    invoices = []
    closed = [o for o in orders if o["DocumentStatus"] == "bost_Close"]
    for doc_entry in range(1, min(count + 1, len(closed) + 1)):
        order = closed[doc_entry - 1]
        inv_date = (date.fromisoformat(order["DocDate"]) + timedelta(days=random.randint(5, 20))).isoformat()
        lines = []
        for line in order["DocumentLines"]:
            lines.append({
                "LineNum": line["LineNum"], "ItemCode": line["ItemCode"],
                "ItemDescription": line["ItemDescription"], "Quantity": line["Quantity"],
                "Price": line["Price"], "LineTotal": line["LineTotal"],
                "WarehouseCode": line["WarehouseCode"],
            })
        invoices.append({
            "DocEntry": doc_entry, "DocNum": 70000 + doc_entry,
            "CardCode": order["CardCode"], "CardName": order["CardName"],
            "DocDate": inv_date, "DocDueDate": (date.fromisoformat(inv_date) + timedelta(days=30)).isoformat(),
            "DocTotal": order["DocTotal"], "DocumentStatus": "bost_Close",
            "DocCurrency": "$", "DocumentLines": lines,
        })
    return invoices


def build_returns(orders, count=8):
    """Sales Returns (ORDN)."""
    returns = []
    closed = [o for o in orders if o["DocumentStatus"] == "bost_Close"]
    for doc_entry in range(1, min(count + 1, len(closed) + 1)):
        order = closed[doc_entry - 1]
        ret_date = (date.fromisoformat(order["DocDate"]) + timedelta(days=random.randint(15, 45))).isoformat()
        line = order["DocumentLines"][0]
        ret_qty = max(1, line["Quantity"] // 3)
        returns.append({
            "DocEntry": doc_entry, "DocNum": 75000 + doc_entry,
            "CardCode": order["CardCode"], "CardName": order["CardName"],
            "DocDate": ret_date, "DocumentStatus": "bost_Close",
            "DocTotal": round(ret_qty * line["Price"], 2), "DocCurrency": "$",
            "DocumentLines": [{
                "LineNum": 0, "ItemCode": line["ItemCode"],
                "ItemDescription": line["ItemDescription"],
                "Quantity": ret_qty, "Price": line["Price"],
                "LineTotal": round(ret_qty * line["Price"], 2),
                "WarehouseCode": line["WarehouseCode"],
            }],
        })
    return returns


def build_purchase_invoices(purchase_orders, count=25):
    """A/P Invoices (OPCH)."""
    invoices = []
    closed = [p for p in purchase_orders if p["DocumentStatus"] == "bost_Close"]
    for doc_entry in range(1, min(count + 1, len(closed) + 1)):
        po = closed[doc_entry - 1]
        inv_date = (date.fromisoformat(po["DocDate"]) + timedelta(days=random.randint(10, 30))).isoformat()
        lines = []
        for line in po["DocumentLines"]:
            lines.append({
                "LineNum": line["LineNum"], "ItemCode": line["ItemCode"],
                "ItemDescription": line["ItemDescription"], "Quantity": line["Quantity"],
                "Price": line["Price"], "LineTotal": line["LineTotal"],
                "WarehouseCode": line["WarehouseCode"],
            })
        invoices.append({
            "DocEntry": doc_entry, "DocNum": 80000 + doc_entry,
            "CardCode": po["CardCode"], "CardName": po["CardName"],
            "DocDate": inv_date, "DocTotal": po["DocTotal"],
            "DocumentStatus": "bost_Close", "DocCurrency": "$",
            "DocumentLines": lines,
        })
    return invoices


def build_purchase_requests(count=20):
    """Purchase Requests (OPRQ)."""
    reqs = []
    rm_items = [(c, n, g, cost, v) for c, n, g, cost, v in RAW_MATERIALS]
    for doc_entry in range(1, count + 1):
        item = random.choice(rm_items)
        qty = random.randint(50, 300)
        reqs.append({
            "DocEntry": doc_entry, "DocNum": 85000 + doc_entry,
            "RequriedDate": _random_date(1, 30),
            "DocumentStatus": random.choice(["bost_Open", "bost_Close"]),
            "DocumentLines": [{
                "LineNum": 0, "ItemCode": item[0], "ItemDescription": item[1],
                "Quantity": qty, "Price": item[3],
                "LineTotal": round(qty * item[3], 2), "WarehouseCode": "01",
            }],
        })
    return reqs


def build_inventory_transfer_requests(count=10):
    """Inventory Transfer Requests (OWTQ)."""
    reqs = []
    fg_items = [(c, n) for c, n, *_ in FINISHED_GOODS]
    for doc_entry in range(1, count + 1):
        item_code, item_name = random.choice(fg_items)
        from_whs, to_whs = random.sample(["01", "02", "05"], 2)
        qty = random.randint(10, 60)
        reqs.append({
            "DocEntry": doc_entry, "DocNum": 87000 + doc_entry,
            "DocDate": _random_date(3, 45),
            "FromWarehouse": from_whs, "ToWarehouse": to_whs,
            "DocumentStatus": random.choice(["bost_Open", "bost_Close"]),
            "StockTransferLines": [{
                "LineNum": 0, "ItemCode": item_code, "ItemDescription": item_name,
                "Quantity": qty, "FromWarehouseCode": from_whs, "WarehouseCode": to_whs,
            }],
        })
    return reqs


def build_goods_returns(count=5):
    """Purchase Returns / Goods Returns (ORPD)."""
    returns = []
    rm_items = [(c, n, g, cost, v) for c, n, g, cost, v in RAW_MATERIALS]
    for doc_entry in range(1, count + 1):
        vendor = random.choice(VENDORS)
        item = random.choice(rm_items)
        qty = random.randint(5, 30)
        returns.append({
            "DocEntry": doc_entry, "DocNum": 88000 + doc_entry,
            "CardCode": vendor["CardCode"], "CardName": vendor["CardName"],
            "DocDate": _random_date(10, 60), "DocumentStatus": "bost_Close",
            "DocTotal": round(qty * item[3], 2), "DocCurrency": "$",
            "DocumentLines": [{
                "LineNum": 0, "ItemCode": item[0], "ItemDescription": item[1],
                "Quantity": qty, "Price": item[3],
                "LineTotal": round(qty * item[3], 2), "WarehouseCode": "01",
            }],
        })
    return returns


def build_blanket_agreements(count=6):
    """Blanket/Framework Agreements (OAGL)."""
    agreements = []
    for i in range(1, count + 1):
        vendor = VENDORS[i % len(VENDORS)]
        start = _random_date(60, 365)
        end = (date.fromisoformat(start) + timedelta(days=365)).isoformat()
        agreements.append({
            "AgreementNo": i,
            "BPCode": vendor["CardCode"],
            "BPName": vendor["CardName"],
            "AgreementType": "atBuyAll" if i % 2 == 0 else "atBuyAll",
            "Status": "asApproved",
            "StartDate": start, "EndDate": end,
            "AgreementMethod": "amItemMethod",
            "Description": f"Annual supply agreement with {vendor['CardName']}",
        })
    return agreements


def build_resources():
    """Resources / Work Centers (ORES + ORSC)."""
    resources = [
        {"ResCode": "MFG-01", "ResName": "Assembly Line 1", "ResType": "rtMachine",
         "UnitOfMeasure": "Hours", "CostPerHour": 45.0, "Warehouse": "05"},
        {"ResCode": "MFG-02", "ResName": "Assembly Line 2", "ResType": "rtMachine",
         "UnitOfMeasure": "Hours", "CostPerHour": 45.0, "Warehouse": "05"},
        {"ResCode": "QC-01", "ResName": "Quality Control Station", "ResType": "rtMachine",
         "UnitOfMeasure": "Hours", "CostPerHour": 35.0, "Warehouse": "05"},
        {"ResCode": "LABOR-01", "ResName": "Production Labor", "ResType": "rtLabor",
         "UnitOfMeasure": "Hours", "CostPerHour": 25.0, "Warehouse": "05"},
    ]
    capacities = []
    for res in resources:
        for week_offset in range(12):
            cap_date = (TODAY - timedelta(weeks=week_offset)).isoformat()
            capacities.append({
                "AbsEntry": len(capacities) + 1,
                "ResourceCode": res["ResCode"],
                "Date": cap_date,
                "Capacity": 40.0 if res["ResType"] == "rtMachine" else 80.0,
                "SourceType": "rcstNone",
            })
    return resources, capacities


def build_service_calls(count=8):
    """Service Calls (OSCL) → MaintenanceOrder."""
    calls = []
    for i in range(1, count + 1):
        customer = random.choice(CUSTOMERS)
        item = random.choice(FINISHED_GOODS)
        calls.append({
            "ServiceCallID": i,
            "CustomerCode": customer["CardCode"],
            "CustomerName": customer["CardName"],
            "ItemCode": item[0], "ItemDescription": item[1],
            "Subject": f"Maintenance request for {item[1]}",
            "Status": random.choice([-1, -2, -3]),  # -1=open, -2=pending, -3=closed
            "Priority": random.choice(["scp_Low", "scp_Medium", "scp_High"]),
            "CallType": random.choice([1, 2, 3]),
            "CreationDate": _random_date(5, 60),
        })
    return calls


def build_inventory_gen_entries(count=20):
    """Inventory Postings — Goods Receipts (OIGE)."""
    entries = []
    all_items = [(c, n) for c, n, *_ in FINISHED_GOODS] + [(c, n) for c, n, *_ in RAW_MATERIALS]
    for doc_entry in range(1, count + 1):
        item_code, item_name = random.choice(all_items)
        qty = float(random.randint(10, 200))
        entries.append({
            "DocEntry": doc_entry, "DocNum": 90000 + doc_entry,
            "DocDate": _random_date(3, 90),
            "DocumentLines": [{
                "LineNum": 0, "ItemCode": item_code, "ItemDescription": item_name,
                "Quantity": qty, "WarehouseCode": random.choice(["01", "02", "05"]),
            }],
        })
    return entries


def build_inventory_gen_exits(count=15):
    """Inventory Exits — Goods Issues (OIGE)."""
    exits = []
    all_items = [(c, n) for c, n, *_ in FINISHED_GOODS] + [(c, n) for c, n, *_ in RAW_MATERIALS]
    for doc_entry in range(1, count + 1):
        item_code, item_name = random.choice(all_items)
        qty = float(random.randint(5, 80))
        exits.append({
            "DocEntry": 1000 + doc_entry, "DocNum": 91000 + doc_entry,
            "DocDate": _random_date(3, 90),
            "DocumentLines": [{
                "LineNum": 0, "ItemCode": item_code, "ItemDescription": item_name,
                "Quantity": qty, "WarehouseCode": random.choice(["01", "02"]),
            }],
        })
    return exits


def build_price_lists():
    """Price Lists (OPLN)."""
    return [
        {"PriceListNo": 1, "PriceListName": "Base Price", "IsGrossPrice": "tNO", "Active": "tYES"},
        {"PriceListNo": 2, "PriceListName": "Wholesale", "IsGrossPrice": "tNO", "Active": "tYES", "BasePriceList": 1, "Factor": 0.85},
        {"PriceListNo": 3, "PriceListName": "Retail", "IsGrossPrice": "tNO", "Active": "tYES", "BasePriceList": 1, "Factor": 1.15},
    ]


def build_special_prices():
    """BP-specific special prices (OSPP)."""
    specials = []
    for vendor in VENDORS[:3]:
        items = [i for i in FINISHED_GOODS if i[5] == vendor["CardCode"]]
        for item in items[:3]:
            specials.append({
                "CardCode": vendor["CardCode"],
                "ItemCode": item[0],
                "Price": round(item[3] * 0.9, 2),
                "Currency": "$",
            })
    return specials


def build_unit_of_measurements():
    """Units of Measurement (OUOM)."""
    return [
        {"AbsEntry": 1, "Code": "Each", "Name": "Each"},
        {"AbsEntry": 2, "Code": "cm", "Name": "Centimeter"},
        {"AbsEntry": 3, "Code": "kg", "Name": "Kilogram"},
        {"AbsEntry": 4, "Code": "lb", "Name": "Pound"},
        {"AbsEntry": 5, "Code": "N/A", "Name": "Not Applicable"},
        {"AbsEntry": 6, "Code": "Box", "Name": "Box"},
        {"AbsEntry": 7, "Code": "Pallet", "Name": "Pallet"},
        {"AbsEntry": 8, "Code": "Meter", "Name": "Meter"},
        {"AbsEntry": 9, "Code": "Pack", "Name": "Pack"},
        {"AbsEntry": 10, "Code": "Hours", "Name": "Hours"},
    ]


def build_batch_number_details():
    """Batch number details (OBTN)."""
    batches = []
    batch_items = [i for i in FINISHED_GOODS if i[2] in (101, 102)][:5]
    for idx, item in enumerate(batch_items):
        for b in range(3):
            batches.append({
                "AbsEntry": idx * 3 + b + 1,
                "ItemCode": item[0], "ItemDescription": item[1],
                "BatchNumber": f"BATCH-{item[0]}-{b+1:03d}",
                "Status": "bdsStatus_Released",
                "Quantity": float(random.randint(20, 100)),
                "ManufacturingDate": _random_date(30, 180),
                "ExpirationDate": (TODAY + timedelta(days=random.randint(90, 365))).isoformat(),
            })
    return batches


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    items = build_items()
    product_trees, product_tree_lines = build_product_trees()
    item_whs = build_item_warehouse_info()
    orders = build_orders(80)
    purchase_orders = build_purchase_orders(60)
    production_orders = build_production_orders(25)
    deliveries = build_delivery_notes(orders, 40)
    grpos = build_purchase_delivery_notes(purchase_orders, 30)
    transfers = build_stock_transfers(15)
    invoices = build_invoices(orders, 35)
    returns = build_returns(orders, 8)
    purchase_invoices = build_purchase_invoices(purchase_orders, 25)
    purchase_requests = build_purchase_requests(20)
    transfer_requests = build_inventory_transfer_requests(10)
    goods_returns = build_goods_returns(5)
    blanket_agreements = build_blanket_agreements(6)
    resources, resource_capacities = build_resources()
    service_calls = build_service_calls(8)
    inv_entries = build_inventory_gen_entries(20)
    inv_exits = build_inventory_gen_exits(15)

    entities = {
        "Companies": build_companies(),
        "Warehouses": WAREHOUSES,
        "BusinessPartners": BUSINESS_PARTNERS,
        "BusinessPartnerGroups": [
            {"Code": 1, "Name": "Vendors", "Type": "bbpgt_VendorGroup"},
            {"Code": 2, "Name": "Customers", "Type": "bbpgt_CustomerGroup"},
        ],
        "Items": items,
        "ItemGroups": build_item_groups(),
        "ProductTrees": product_trees,
        "ProductTreeLines": product_tree_lines,
        "ItemWarehouseInfoCollection": item_whs,
        "UnitOfMeasurements": build_unit_of_measurements(),
        "PriceLists": build_price_lists(),
        "SpecialPrices": build_special_prices(),
        "Resources": resources,
        "ResourceCapacities": resource_capacities,
        "Orders": orders,
        "PurchaseOrders": purchase_orders,
        "ProductionOrders": production_orders,
        "DeliveryNotes": deliveries,
        "PurchaseDeliveryNotes": grpos,
        "Invoices": invoices,
        "Returns": returns,
        "PurchaseInvoices": purchase_invoices,
        "PurchaseRequests": purchase_requests,
        "InventoryTransferRequests": transfer_requests,
        "StockTransfers": transfers,
        "GoodsReturns": goods_returns,
        "BlanketAgreements": blanket_agreements,
        "ServiceCalls": service_calls,
        "InventoryGenEntries": inv_entries,
        "InventoryGenExits": inv_exits,
        "BatchNumberDetails": build_batch_number_details(),
    }

    total = 0
    for entity_name, data in entities.items():
        path = OUTPUT_DIR / f"{entity_name}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        total += len(data)
        print(f"  {entity_name}: {len(data)} records → {path.name}")

    print(f"\nTotal: {total} records across {len(entities)} entities")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
