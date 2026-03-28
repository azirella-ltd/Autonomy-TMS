"""
Generate Infor M3 demo data in MI API JSON format.

Creates realistic Midwest Industrial Supply data matching M3 MI field naming.
Output: JSON files in the target directory, one per entity.

Midwest Industrial Supply is a fictional industrial equipment manufacturer
producing pumps, valves, actuators, and control systems — a typical Infor M3
manufacturing vertical (process/discrete hybrid).

Usage:
    python scripts/generate_infor_demo_data.py /tmp/infor_export
    python scripts/generate_infor_demo_data.py /tmp/infor_export --items 200
"""

import json
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

random.seed(42)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/infor_export")
NUM_EXTRA_ITEMS = int(sys.argv[2]) if len(sys.argv) > 2 else 0
TODAY = date(2026, 3, 28)

# ---------------------------------------------------------------------------
# Warehouses (M3 WHLO)
# ---------------------------------------------------------------------------

WAREHOUSES = [
    {"WHLO": "100", "WHNM": "Main Plant", "WHDC": "Primary manufacturing facility", "WHTY": "3", "TOWN": "Indianapolis", "PNOD": "IN", "CSCD": "US", "Inactive": "0"},
    {"WHLO": "200", "WHNM": "Central Distribution", "WHDC": "Central distribution center", "WHTY": "2", "TOWN": "Columbus", "PNOD": "OH", "CSCD": "US", "Inactive": "0"},
    {"WHLO": "300", "WHNM": "West Coast DC", "WHDC": "West coast distribution hub", "WHTY": "2", "TOWN": "Reno", "PNOD": "NV", "CSCD": "US", "Inactive": "0"},
    {"WHLO": "400", "WHNM": "Assembly Plant South", "WHDC": "Southern assembly and finishing", "WHTY": "3", "TOWN": "Nashville", "PNOD": "TN", "CSCD": "US", "Inactive": "0"},
    {"WHLO": "500", "WHNM": "Raw Material Store", "WHDC": "Raw material and component storage", "WHTY": "1", "TOWN": "Indianapolis", "PNOD": "IN", "CSCD": "US", "Inactive": "0"},
    {"WHLO": "600", "WHNM": "Spare Parts Depot", "WHDC": "Aftermarket spare parts", "WHTY": "1", "TOWN": "Louisville", "PNOD": "KY", "CSCD": "US", "Inactive": "0"},
]

# ---------------------------------------------------------------------------
# Suppliers (M3 SUNO)
# ---------------------------------------------------------------------------

SUPPLIERS = [
    {"SUNO": "S10001", "SUNM": "Cascade Foundry", "CSCD": "US", "TOWN": "Pittsburgh", "PHNO": "412-555-0101", "STAT": "20"},
    {"SUNO": "S10002", "SUNM": "Precision Castings Inc", "CSCD": "US", "TOWN": "Cleveland", "PHNO": "216-555-0202", "STAT": "20"},
    {"SUNO": "S10003", "SUNM": "Midwest Steel Supply", "CSCD": "US", "TOWN": "Gary", "PHNO": "219-555-0303", "STAT": "20"},
    {"SUNO": "S10004", "SUNM": "Polymeric Seals Corp", "CSCD": "US", "TOWN": "Akron", "PHNO": "330-555-0404", "STAT": "20"},
    {"SUNO": "S10005", "SUNM": "Allied Bearings", "CSCD": "US", "TOWN": "Detroit", "PHNO": "313-555-0505", "STAT": "20"},
    {"SUNO": "S10006", "SUNM": "Eurofluid Components", "CSCD": "DE", "TOWN": "Stuttgart", "PHNO": "+49-711-5550606", "STAT": "20"},
    {"SUNO": "S10007", "SUNM": "Nippon Actuator Systems", "CSCD": "JP", "TOWN": "Osaka", "PHNO": "+81-6-555-0707", "STAT": "20"},
    {"SUNO": "S10008", "SUNM": "Southern Copper Tubing", "CSCD": "US", "TOWN": "Birmingham", "PHNO": "205-555-0808", "STAT": "20"},
]

# ---------------------------------------------------------------------------
# Customers (M3 CUNO)
# ---------------------------------------------------------------------------

CUSTOMERS = [
    {"CUNO": "C20001", "CUNM": "Chevron Process Solutions", "CSCD": "US", "TOWN": "Houston", "PHNO": "713-555-2001", "STAT": "20"},
    {"CUNO": "C20002", "CUNM": "DuPont Engineering", "CSCD": "US", "TOWN": "Wilmington", "PHNO": "302-555-2002", "STAT": "20"},
    {"CUNO": "C20003", "CUNM": "Siemens Energy Services", "CSCD": "DE", "TOWN": "Munich", "PHNO": "+49-89-555-2003", "STAT": "20"},
    {"CUNO": "C20004", "CUNM": "BASF Chemical", "CSCD": "DE", "TOWN": "Ludwigshafen", "PHNO": "+49-621-555-2004", "STAT": "20"},
    {"CUNO": "C20005", "CUNM": "Georgia-Pacific Industrial", "CSCD": "US", "TOWN": "Atlanta", "PHNO": "404-555-2005", "STAT": "20"},
    {"CUNO": "C20006", "CUNM": "Archer Daniels Midland", "CSCD": "US", "TOWN": "Chicago", "PHNO": "312-555-2006", "STAT": "20"},
    {"CUNO": "C20007", "CUNM": "Dow Water & Process", "CSCD": "US", "TOWN": "Midland", "PHNO": "989-555-2007", "STAT": "20"},
    {"CUNO": "C20008", "CUNM": "Kimberly-Clark Industrial", "CSCD": "US", "TOWN": "Dallas", "PHNO": "214-555-2008", "STAT": "20"},
    {"CUNO": "C20009", "CUNM": "Marathon Petroleum", "CSCD": "US", "TOWN": "Findlay", "PHNO": "419-555-2009", "STAT": "20"},
    {"CUNO": "C20010", "CUNM": "Cargill Process Systems", "CSCD": "US", "TOWN": "Minneapolis", "PHNO": "612-555-2010", "STAT": "20"},
]

# ---------------------------------------------------------------------------
# Item Groups (M3 ITGR)
# ---------------------------------------------------------------------------

ITEM_GROUPS = {
    "PMP": "Pumps",
    "VLV": "Valves",
    "ACT": "Actuators",
    "CTL": "Control Systems",
    "CST": "Castings",
    "SEL": "Seals & Gaskets",
    "BRG": "Bearings",
    "MTR": "Motors & Drives",
    "PIP": "Piping & Fittings",
    "ELC": "Electrical Components",
    "FAS": "Fasteners",
    "LBR": "Labor",
}

# ---------------------------------------------------------------------------
# Items — Midwest Industrial Supply product line
# ---------------------------------------------------------------------------

# Finished Goods (FG) — Products with BOMs
FINISHED_GOODS = [
    {"ITNO": "PMP-1000", "ITDS": "Centrifugal Pump CP-100 (2\" inlet)", "ITGR": "PMP", "ITTY": "FG", "UNMS": "EA", "UCOS": 850.00, "SAPR": 2100.00, "GRWE": 45.0},
    {"ITNO": "PMP-1010", "ITDS": "Centrifugal Pump CP-200 (4\" inlet)", "ITGR": "PMP", "ITTY": "FG", "UNMS": "EA", "UCOS": 1450.00, "SAPR": 3500.00, "GRWE": 78.0},
    {"ITNO": "PMP-1020", "ITDS": "Centrifugal Pump CP-300 (6\" inlet)", "ITGR": "PMP", "ITTY": "FG", "UNMS": "EA", "UCOS": 2200.00, "SAPR": 5200.00, "GRWE": 125.0},
    {"ITNO": "PMP-2000", "ITDS": "Positive Displacement Pump PD-100", "ITGR": "PMP", "ITTY": "FG", "UNMS": "EA", "UCOS": 1100.00, "SAPR": 2800.00, "GRWE": 55.0},
    {"ITNO": "PMP-2010", "ITDS": "Positive Displacement Pump PD-200 (high pressure)", "ITGR": "PMP", "ITTY": "FG", "UNMS": "EA", "UCOS": 1800.00, "SAPR": 4200.00, "GRWE": 85.0},
    {"ITNO": "PMP-3000", "ITDS": "Submersible Pump SP-100", "ITGR": "PMP", "ITTY": "FG", "UNMS": "EA", "UCOS": 950.00, "SAPR": 2400.00, "GRWE": 38.0},
    {"ITNO": "VLV-1000", "ITDS": "Gate Valve GV-200 (2\" ANSI 150)", "ITGR": "VLV", "ITTY": "FG", "UNMS": "EA", "UCOS": 280.00, "SAPR": 680.00, "GRWE": 12.0},
    {"ITNO": "VLV-1010", "ITDS": "Gate Valve GV-400 (4\" ANSI 150)", "ITGR": "VLV", "ITTY": "FG", "UNMS": "EA", "UCOS": 520.00, "SAPR": 1250.00, "GRWE": 28.0},
    {"ITNO": "VLV-1020", "ITDS": "Gate Valve GV-600 (6\" ANSI 300)", "ITGR": "VLV", "ITTY": "FG", "UNMS": "EA", "UCOS": 980.00, "SAPR": 2400.00, "GRWE": 55.0},
    {"ITNO": "VLV-2000", "ITDS": "Ball Valve BV-200 (2\" full bore)", "ITGR": "VLV", "ITTY": "FG", "UNMS": "EA", "UCOS": 180.00, "SAPR": 450.00, "GRWE": 8.0},
    {"ITNO": "VLV-2010", "ITDS": "Ball Valve BV-400 (4\" full bore)", "ITGR": "VLV", "ITTY": "FG", "UNMS": "EA", "UCOS": 380.00, "SAPR": 920.00, "GRWE": 18.0},
    {"ITNO": "VLV-3000", "ITDS": "Butterfly Valve BF-300 (3\" wafer)", "ITGR": "VLV", "ITTY": "FG", "UNMS": "EA", "UCOS": 150.00, "SAPR": 380.00, "GRWE": 6.0},
    {"ITNO": "VLV-3010", "ITDS": "Butterfly Valve BF-600 (6\" wafer)", "ITGR": "VLV", "ITTY": "FG", "UNMS": "EA", "UCOS": 320.00, "SAPR": 780.00, "GRWE": 14.0},
    {"ITNO": "VLV-4000", "ITDS": "Control Valve CV-200 (2\" globe, pneumatic)", "ITGR": "VLV", "ITTY": "FG", "UNMS": "EA", "UCOS": 1200.00, "SAPR": 2900.00, "GRWE": 22.0},
    {"ITNO": "VLV-4010", "ITDS": "Control Valve CV-400 (4\" globe, pneumatic)", "ITGR": "VLV", "ITTY": "FG", "UNMS": "EA", "UCOS": 1800.00, "SAPR": 4300.00, "GRWE": 38.0},
    {"ITNO": "ACT-1000", "ITDS": "Pneumatic Actuator PA-100 (spring return)", "ITGR": "ACT", "ITTY": "FG", "UNMS": "EA", "UCOS": 450.00, "SAPR": 1100.00, "GRWE": 15.0},
    {"ITNO": "ACT-1010", "ITDS": "Pneumatic Actuator PA-200 (double acting)", "ITGR": "ACT", "ITTY": "FG", "UNMS": "EA", "UCOS": 650.00, "SAPR": 1600.00, "GRWE": 22.0},
    {"ITNO": "ACT-2000", "ITDS": "Electric Actuator EA-100 (multi-turn)", "ITGR": "ACT", "ITTY": "FG", "UNMS": "EA", "UCOS": 800.00, "SAPR": 1950.00, "GRWE": 28.0},
    {"ITNO": "ACT-2010", "ITDS": "Electric Actuator EA-200 (quarter-turn)", "ITGR": "ACT", "ITTY": "FG", "UNMS": "EA", "UCOS": 950.00, "SAPR": 2300.00, "GRWE": 32.0},
    {"ITNO": "CTL-1000", "ITDS": "Flow Control Panel FCP-100", "ITGR": "CTL", "ITTY": "FG", "UNMS": "EA", "UCOS": 3200.00, "SAPR": 7800.00, "GRWE": 65.0},
    {"ITNO": "CTL-1010", "ITDS": "Pressure Control Panel PCP-100", "ITGR": "CTL", "ITTY": "FG", "UNMS": "EA", "UCOS": 2800.00, "SAPR": 6800.00, "GRWE": 55.0},
]

# Raw Materials (RM)
RAW_MATERIALS = [
    {"ITNO": "CST-0100", "ITDS": "Pump Casing (2\" centrifugal, cast iron)", "ITGR": "CST", "ITTY": "RM", "UNMS": "EA", "UCOS": 120.00, "SAPR": 0, "GRWE": 15.0},
    {"ITNO": "CST-0200", "ITDS": "Pump Casing (4\" centrifugal, cast iron)", "ITGR": "CST", "ITTY": "RM", "UNMS": "EA", "UCOS": 220.00, "SAPR": 0, "GRWE": 28.0},
    {"ITNO": "CST-0300", "ITDS": "Pump Casing (6\" centrifugal, ductile iron)", "ITGR": "CST", "ITTY": "RM", "UNMS": "EA", "UCOS": 380.00, "SAPR": 0, "GRWE": 45.0},
    {"ITNO": "CST-0400", "ITDS": "Valve Body (2\" gate, CF8M stainless)", "ITGR": "CST", "ITTY": "RM", "UNMS": "EA", "UCOS": 65.00, "SAPR": 0, "GRWE": 4.0},
    {"ITNO": "CST-0500", "ITDS": "Valve Body (4\" gate, CF8M stainless)", "ITGR": "CST", "ITTY": "RM", "UNMS": "EA", "UCOS": 135.00, "SAPR": 0, "GRWE": 10.0},
    {"ITNO": "CST-0600", "ITDS": "Valve Body (6\" gate, CF8M stainless)", "ITGR": "CST", "ITTY": "RM", "UNMS": "EA", "UCOS": 250.00, "SAPR": 0, "GRWE": 20.0},
    {"ITNO": "CST-0700", "ITDS": "Impeller (2\" closed, 316SS)", "ITGR": "CST", "ITTY": "RM", "UNMS": "EA", "UCOS": 95.00, "SAPR": 0, "GRWE": 3.0},
    {"ITNO": "CST-0800", "ITDS": "Impeller (4\" closed, 316SS)", "ITGR": "CST", "ITTY": "RM", "UNMS": "EA", "UCOS": 165.00, "SAPR": 0, "GRWE": 6.0},
    {"ITNO": "CST-0900", "ITDS": "Impeller (6\" closed, duplex SS)", "ITGR": "CST", "ITTY": "RM", "UNMS": "EA", "UCOS": 310.00, "SAPR": 0, "GRWE": 12.0},
    {"ITNO": "SEL-0100", "ITDS": "Mechanical Seal (2\" cartridge, SiC/SiC)", "ITGR": "SEL", "ITTY": "RM", "UNMS": "EA", "UCOS": 85.00, "SAPR": 0, "GRWE": 0.8},
    {"ITNO": "SEL-0200", "ITDS": "Mechanical Seal (4\" cartridge, SiC/SiC)", "ITGR": "SEL", "ITTY": "RM", "UNMS": "EA", "UCOS": 140.00, "SAPR": 0, "GRWE": 1.2},
    {"ITNO": "SEL-0300", "ITDS": "Mechanical Seal (6\" cartridge, TC/TC)", "ITGR": "SEL", "ITTY": "RM", "UNMS": "EA", "UCOS": 220.00, "SAPR": 0, "GRWE": 1.8},
    {"ITNO": "SEL-0400", "ITDS": "O-Ring Kit (Viton, assorted)", "ITGR": "SEL", "ITTY": "RM", "UNMS": "KIT", "UCOS": 12.00, "SAPR": 0, "GRWE": 0.1},
    {"ITNO": "SEL-0500", "ITDS": "Packing Set (graphite PTFE, 2\")", "ITGR": "SEL", "ITTY": "RM", "UNMS": "SET", "UCOS": 35.00, "SAPR": 0, "GRWE": 0.3},
    {"ITNO": "BRG-0100", "ITDS": "Ball Bearing 6205-2RS (25mm)", "ITGR": "BRG", "ITTY": "RM", "UNMS": "EA", "UCOS": 8.50, "SAPR": 0, "GRWE": 0.12},
    {"ITNO": "BRG-0200", "ITDS": "Ball Bearing 6210-2RS (50mm)", "ITGR": "BRG", "ITTY": "RM", "UNMS": "EA", "UCOS": 16.00, "SAPR": 0, "GRWE": 0.35},
    {"ITNO": "BRG-0300", "ITDS": "Thrust Bearing 51110 (50mm)", "ITGR": "BRG", "ITTY": "RM", "UNMS": "EA", "UCOS": 22.00, "SAPR": 0, "GRWE": 0.28},
    {"ITNO": "MTR-0100", "ITDS": "Electric Motor (3HP, TEFC, 1750RPM)", "ITGR": "MTR", "ITTY": "RM", "UNMS": "EA", "UCOS": 280.00, "SAPR": 0, "GRWE": 18.0},
    {"ITNO": "MTR-0200", "ITDS": "Electric Motor (7.5HP, TEFC, 1750RPM)", "ITGR": "MTR", "ITTY": "RM", "UNMS": "EA", "UCOS": 520.00, "SAPR": 0, "GRWE": 35.0},
    {"ITNO": "MTR-0300", "ITDS": "Electric Motor (15HP, TEFC, 3500RPM)", "ITGR": "MTR", "ITTY": "RM", "UNMS": "EA", "UCOS": 850.00, "SAPR": 0, "GRWE": 55.0},
    {"ITNO": "PIP-0100", "ITDS": "Coupling (2\" flexible jaw)", "ITGR": "PIP", "ITTY": "RM", "UNMS": "EA", "UCOS": 45.00, "SAPR": 0, "GRWE": 1.5},
    {"ITNO": "PIP-0200", "ITDS": "Coupling (4\" flexible jaw)", "ITGR": "PIP", "ITTY": "RM", "UNMS": "EA", "UCOS": 85.00, "SAPR": 0, "GRWE": 3.0},
    {"ITNO": "PIP-0300", "ITDS": "Baseplate (welded steel, pump mount)", "ITGR": "PIP", "ITTY": "RM", "UNMS": "EA", "UCOS": 110.00, "SAPR": 0, "GRWE": 22.0},
    {"ITNO": "ELC-0100", "ITDS": "Positioner (I/P, 4-20mA input)", "ITGR": "ELC", "ITTY": "RM", "UNMS": "EA", "UCOS": 350.00, "SAPR": 0, "GRWE": 2.5},
    {"ITNO": "ELC-0200", "ITDS": "Solenoid Valve (3-way, 24VDC)", "ITGR": "ELC", "ITTY": "RM", "UNMS": "EA", "UCOS": 65.00, "SAPR": 0, "GRWE": 0.8},
    {"ITNO": "ELC-0300", "ITDS": "Limit Switch (NAMUR, explosion proof)", "ITGR": "ELC", "ITTY": "RM", "UNMS": "EA", "UCOS": 120.00, "SAPR": 0, "GRWE": 1.0},
    {"ITNO": "ELC-0400", "ITDS": "PLC Module (8 analog I/O)", "ITGR": "ELC", "ITTY": "RM", "UNMS": "EA", "UCOS": 450.00, "SAPR": 0, "GRWE": 0.5},
    {"ITNO": "ELC-0500", "ITDS": "Flow Transmitter (vortex, 4-20mA)", "ITGR": "ELC", "ITTY": "RM", "UNMS": "EA", "UCOS": 680.00, "SAPR": 0, "GRWE": 3.5},
    {"ITNO": "ELC-0600", "ITDS": "Pressure Transmitter (gauge, 4-20mA)", "ITGR": "ELC", "ITTY": "RM", "UNMS": "EA", "UCOS": 320.00, "SAPR": 0, "GRWE": 1.2},
    {"ITNO": "FAS-0100", "ITDS": "Stud Bolt Set (B7/2H, 5/8\" × 4\")", "ITGR": "FAS", "ITTY": "RM", "UNMS": "SET", "UCOS": 8.00, "SAPR": 0, "GRWE": 0.5},
    {"ITNO": "FAS-0200", "ITDS": "Stud Bolt Set (B7/2H, 3/4\" × 5\")", "ITGR": "FAS", "ITTY": "RM", "UNMS": "SET", "UCOS": 12.00, "SAPR": 0, "GRWE": 0.8},
    {"ITNO": "FAS-0300", "ITDS": "Gasket (spiral wound, 2\" 150#)", "ITGR": "FAS", "ITTY": "RM", "UNMS": "EA", "UCOS": 6.00, "SAPR": 0, "GRWE": 0.1},
    {"ITNO": "FAS-0400", "ITDS": "Gasket (spiral wound, 4\" 150#)", "ITGR": "FAS", "ITTY": "RM", "UNMS": "EA", "UCOS": 10.00, "SAPR": 0, "GRWE": 0.2},
]

# Labor items
LABOR_ITEMS = [
    {"ITNO": "LBR-0100", "ITDS": "Assembly Labor — Skilled", "ITGR": "LBR", "ITTY": "RM", "UNMS": "HR", "UCOS": 55.00, "SAPR": 0, "GRWE": 0},
    {"ITNO": "LBR-0200", "ITDS": "Test & Inspection Labor", "ITGR": "LBR", "ITTY": "RM", "UNMS": "HR", "UCOS": 65.00, "SAPR": 0, "GRWE": 0},
    {"ITNO": "LBR-0300", "ITDS": "Painting & Finishing Labor", "ITGR": "LBR", "ITTY": "RM", "UNMS": "HR", "UCOS": 45.00, "SAPR": 0, "GRWE": 0},
]

ALL_ITEMS = FINISHED_GOODS + RAW_MATERIALS + LABOR_ITEMS
ITEM_MAP = {item["ITNO"]: item for item in ALL_ITEMS}
FG_CODES = [item["ITNO"] for item in FINISHED_GOODS]
RM_CODES = [item["ITNO"] for item in RAW_MATERIALS]

# Add STAT field
for item in ALL_ITEMS:
    item["STAT"] = "20"

# ---------------------------------------------------------------------------
# Bills of Material
# ---------------------------------------------------------------------------

BOMS = {
    # Centrifugal Pump CP-100 (2")
    "PMP-1000": [
        ("CST-0100", 1, "EA"),   # Casing
        ("CST-0700", 1, "EA"),   # Impeller
        ("SEL-0100", 1, "EA"),   # Mechanical seal
        ("SEL-0400", 2, "KIT"),  # O-rings
        ("BRG-0100", 2, "EA"),   # Bearings
        ("MTR-0100", 1, "EA"),   # Motor
        ("PIP-0100", 1, "EA"),   # Coupling
        ("PIP-0300", 1, "EA"),   # Baseplate
        ("FAS-0100", 8, "SET"),  # Bolts
        ("FAS-0300", 2, "EA"),   # Gaskets
        ("LBR-0100", 6, "HR"),   # Assembly
        ("LBR-0200", 2, "HR"),   # Test
    ],
    # Centrifugal Pump CP-200 (4")
    "PMP-1010": [
        ("CST-0200", 1, "EA"),
        ("CST-0800", 1, "EA"),
        ("SEL-0200", 1, "EA"),
        ("SEL-0400", 3, "KIT"),
        ("BRG-0200", 2, "EA"),
        ("MTR-0200", 1, "EA"),
        ("PIP-0200", 1, "EA"),
        ("PIP-0300", 1, "EA"),
        ("FAS-0200", 12, "SET"),
        ("FAS-0400", 2, "EA"),
        ("LBR-0100", 8, "HR"),
        ("LBR-0200", 3, "HR"),
    ],
    # Centrifugal Pump CP-300 (6")
    "PMP-1020": [
        ("CST-0300", 1, "EA"),
        ("CST-0900", 1, "EA"),
        ("SEL-0300", 1, "EA"),
        ("SEL-0400", 4, "KIT"),
        ("BRG-0300", 2, "EA"),
        ("MTR-0300", 1, "EA"),
        ("PIP-0200", 1, "EA"),
        ("PIP-0300", 1, "EA"),
        ("FAS-0200", 16, "SET"),
        ("LBR-0100", 12, "HR"),
        ("LBR-0200", 4, "HR"),
        ("LBR-0300", 2, "HR"),
    ],
    # Gate Valve GV-200 (2")
    "VLV-1000": [
        ("CST-0400", 1, "EA"),
        ("SEL-0500", 1, "SET"),
        ("FAS-0100", 4, "SET"),
        ("FAS-0300", 1, "EA"),
        ("LBR-0100", 2, "HR"),
        ("LBR-0200", 1, "HR"),
    ],
    # Gate Valve GV-400 (4")
    "VLV-1010": [
        ("CST-0500", 1, "EA"),
        ("SEL-0500", 1, "SET"),
        ("FAS-0200", 8, "SET"),
        ("FAS-0400", 1, "EA"),
        ("LBR-0100", 3, "HR"),
        ("LBR-0200", 1.5, "HR"),
    ],
    # Control Valve CV-200 (2")
    "VLV-4000": [
        ("CST-0400", 1, "EA"),
        ("SEL-0500", 1, "SET"),
        ("ELC-0100", 1, "EA"),
        ("ELC-0200", 1, "EA"),
        ("FAS-0100", 4, "SET"),
        ("FAS-0300", 1, "EA"),
        ("LBR-0100", 4, "HR"),
        ("LBR-0200", 2, "HR"),
    ],
    # Pneumatic Actuator PA-100
    "ACT-1000": [
        ("SEL-0400", 2, "KIT"),
        ("ELC-0200", 1, "EA"),
        ("ELC-0300", 2, "EA"),
        ("FAS-0100", 4, "SET"),
        ("LBR-0100", 3, "HR"),
        ("LBR-0200", 1, "HR"),
    ],
    # Electric Actuator EA-100
    "ACT-2000": [
        ("MTR-0100", 1, "EA"),
        ("BRG-0100", 2, "EA"),
        ("ELC-0300", 2, "EA"),
        ("SEL-0400", 1, "KIT"),
        ("FAS-0100", 6, "SET"),
        ("LBR-0100", 5, "HR"),
        ("LBR-0200", 2, "HR"),
    ],
    # Flow Control Panel FCP-100
    "CTL-1000": [
        ("ELC-0400", 2, "EA"),
        ("ELC-0500", 2, "EA"),
        ("ELC-0600", 2, "EA"),
        ("ELC-0100", 4, "EA"),
        ("ELC-0200", 4, "EA"),
        ("LBR-0100", 16, "HR"),
        ("LBR-0200", 8, "HR"),
    ],
}

# ---------------------------------------------------------------------------
# Work Centers
# ---------------------------------------------------------------------------

WORK_CENTERS = [
    {"PLGR": "WC-CAST", "PLNM": "Casting Inspection", "WHLO": "100", "PCAP": 16.0},
    {"PLGR": "WC-MACH", "PLNM": "CNC Machining", "WHLO": "100", "PCAP": 24.0},
    {"PLGR": "WC-ASSY", "PLNM": "Assembly Line 1", "WHLO": "100", "PCAP": 16.0},
    {"PLGR": "WC-ASY2", "PLNM": "Assembly Line 2", "WHLO": "400", "PCAP": 16.0},
    {"PLGR": "WC-TEST", "PLNM": "Hydrostatic Test Bay", "WHLO": "100", "PCAP": 8.0},
    {"PLGR": "WC-PNTU", "PLNM": "Paint & Finish", "WHLO": "100", "PCAP": 16.0},
    {"PLGR": "WC-ELEC", "PLNM": "Electrical Assembly", "WHLO": "100", "PCAP": 16.0},
    {"PLGR": "WC-PACK", "PLNM": "Packing & Shipping", "WHLO": "200", "PCAP": 24.0},
]

# ---------------------------------------------------------------------------
# Generate Transaction Data
# ---------------------------------------------------------------------------

def random_date(days_back_min=7, days_back_max=180):
    """Random date between days_back_max and days_back_min ago."""
    delta = random.randint(days_back_min, days_back_max)
    return (TODAY - timedelta(days=delta)).strftime("%Y%m%d")


def future_date(days_ahead_min=5, days_ahead_max=60):
    """Random future date."""
    delta = random.randint(days_ahead_min, days_ahead_max)
    return (TODAY + timedelta(days=delta)).strftime("%Y%m%d")


def generate_purchase_orders(count=60):
    """Generate PO headers and lines."""
    headers = []
    lines = []
    statuses = ["15", "15", "15", "20", "20", "35", "45", "45", "75"]

    for i in range(1, count + 1):
        puno = f"{3000000 + i}"
        suno = random.choice(SUPPLIERS)["SUNO"]
        status = random.choice(statuses)
        order_date = random_date(14, 120)
        delivery_date = (datetime.strptime(order_date, "%Y%m%d") + timedelta(days=random.randint(14, 45))).strftime("%Y%m%d")

        headers.append({
            "PUNO": puno,
            "SUNO": suno,
            "PUDT": order_date,
            "DWDT": delivery_date,
            "PUSL": status,
            "LNAM": 0,  # calculated from lines
        })

        num_lines = random.randint(1, 5)
        total = 0
        for ln in range(1, num_lines + 1):
            itno = random.choice(RM_CODES)
            item = ITEM_MAP[itno]
            qty = random.randint(5, 200)
            price = item["UCOS"] * random.uniform(0.9, 1.1)
            rcv_qty = qty if status in ("45", "75") else (random.randint(0, qty) if status == "35" else 0)
            total += qty * price

            lines.append({
                "PUNO": puno,
                "PNLI": ln,
                "PNLS": 0,
                "ITNO": itno,
                "ORQA": qty,
                "RVQA": rcv_qty,
                "WHLO": random.choice(["100", "400", "500"]),
                "PUPR": round(price, 2),
                "DWDT": delivery_date,
                "PUSL": status,
            })

        headers[-1]["LNAM"] = round(total, 2)

    return headers, lines


def generate_sales_orders(count=80):
    """Generate SO headers and lines."""
    headers = []
    lines = []
    statuses = ["15", "15", "22", "33", "44", "55", "66", "77"]

    for i in range(1, count + 1):
        orno = f"{5000000 + i}"
        cuno = random.choice(CUSTOMERS)["CUNO"]
        status = random.choice(statuses)
        order_date = random_date(7, 150)
        delivery_date = (datetime.strptime(order_date, "%Y%m%d") + timedelta(days=random.randint(7, 30))).strftime("%Y%m%d")

        headers.append({
            "ORNO": orno,
            "CUNO": cuno,
            "ORDT": order_date,
            "DWDT": delivery_date,
            "ORSL": status,
            "LNAM": 0,
        })

        num_lines = random.randint(1, 4)
        total = 0
        for ln in range(1, num_lines + 1):
            itno = random.choice(FG_CODES)
            item = ITEM_MAP[itno]
            qty = random.randint(1, 20)
            shipped = qty if status in ("55", "66", "77") else (random.randint(0, qty) if status == "44" else 0)
            total += qty * item["SAPR"]

            lines.append({
                "ORNO": orno,
                "PONR": ln,
                "POSX": 0,
                "ITNO": itno,
                "ORQA": qty,
                "DLQA": shipped,
                "WHLO": random.choice(["100", "200", "300", "400"]),
                "SAPR": item["SAPR"],
                "DWDT": delivery_date,
                "ORSL": status,
            })

        headers[-1]["LNAM"] = round(total, 2)

    return headers, lines


def generate_production_orders(count=30):
    """Generate manufacturing orders."""
    orders = []
    statuses = ["10", "20", "30", "40", "50", "60", "70", "80"]

    bom_items = list(BOMS.keys())
    for i in range(1, count + 1):
        mfno = f"{7000000 + i}"
        prno = random.choice(bom_items)
        status = random.choice(statuses)
        start_date = random_date(7, 90)
        due_date = (datetime.strptime(start_date, "%Y%m%d") + timedelta(days=random.randint(5, 21))).strftime("%Y%m%d")

        orders.append({
            "MFNO": mfno,
            "PRNO": prno,
            "ORQA": random.randint(5, 50),
            "STDT": start_date,
            "FIDT": due_date,
            "WHST": status,
            "WHLO": random.choice(["100", "400"]),
        })

    return orders


def generate_deliveries(count=40):
    """Generate outbound shipments."""
    deliveries = []
    for i in range(1, count + 1):
        conn = f"{9000000 + i}"
        deliveries.append({
            "CONN": conn,
            "ORNO": f"{5000000 + random.randint(1, 80)}",
            "DSDT": random_date(3, 60),
            "DWDT": future_date(1, 14),
            "STAT": random.choice(["30", "50", "70", "90"]),
        })
    return deliveries


def generate_goods_receipts(count=30):
    """Generate goods receipt records."""
    receipts = []
    for i in range(1, count + 1):
        receipts.append({
            "REPN": f"{8000000 + i}",
            "PUNO": f"{3000000 + random.randint(1, 60)}",
            "TRDT": random_date(3, 45),
        })
    return receipts


def generate_transfer_orders(count=15):
    """Generate inter-warehouse stock transfers."""
    transfers = []
    wh_pairs = [("100", "200"), ("100", "300"), ("200", "300"),
                ("400", "200"), ("500", "100"), ("100", "600")]

    for i in range(1, count + 1):
        twlo, whlo = random.choice(wh_pairs)
        itno = random.choice(RM_CODES + FG_CODES[:6])
        transfers.append({
            "RIDN": f"{6000000 + i}",
            "ITNO": itno,
            "TRQA": random.randint(10, 100),
            "TWLO": twlo,
            "WHLO": whlo,
            "TRDT": random_date(3, 30),
            "TTYP": "1",
        })
    return transfers


def generate_forecasts():
    """Generate demand forecasts for FG items."""
    forecasts = []
    for itno in FG_CODES:
        for whlo in ["100", "200", "300"]:
            for week_offset in range(0, 12):
                fc_date = (TODAY + timedelta(weeks=week_offset)).strftime("%Y%m%d")
                base_qty = random.randint(5, 40)
                forecasts.append({
                    "ITNO": itno,
                    "WHLO": whlo,
                    "FRDT": fc_date,
                    "FOQA": base_qty,
                    "FOTY": "statistical",
                })
    return forecasts


def generate_inventory_balances():
    """Generate current inventory snapshot."""
    balances = []
    for item in ALL_ITEMS:
        itno = item["ITNO"]
        if item["ITTY"] == "RM":
            warehouses = ["100", "400", "500"]
        else:
            warehouses = ["100", "200", "300", "400"]

        for whlo in warehouses:
            on_hand = random.randint(0, 500) if item["ITGR"] != "LBR" else 0
            balances.append({
                "ITNO": itno,
                "WHLO": whlo,
                "STQT": on_hand,
                "APTS": max(0, on_hand - random.randint(0, 50)),
                "REQT": random.randint(0, 30),
                "TRQT": random.randint(0, 20),
            })
    return balances


def generate_item_warehouse():
    """Generate item-warehouse planning parameters."""
    records = []
    for item in ALL_ITEMS:
        itno = item["ITNO"]
        if item["ITGR"] == "LBR":
            continue

        warehouses = ["100", "200", "300", "400", "500"] if item["ITTY"] == "RM" else ["100", "200", "300", "400"]
        for whlo in warehouses:
            ss = random.randint(10, 100)
            records.append({
                "ITNO": itno,
                "WHLO": whlo,
                "SSQT": ss,
                "REOP": ss + random.randint(20, 80),
                "MXST": ss * 5,
                "LOQT": random.choice([1, 5, 10, 25, 50]),
                "EOQT": random.choice([0, 50, 100, 200]),
                "PLCD": random.choice(["1", "1", "2", "3"]),
            })
    return records


def generate_bom_records():
    """Convert BOM dict to M3 MI format."""
    records = []
    for prno, components in BOMS.items():
        for seq, (mtno, qty, uom) in enumerate(components, 1):
            records.append({
                "PRNO": prno,
                "MTNO": mtno,
                "MSEQ": seq * 10,
                "CNQT": qty,
                "PEUN": uom,
                "WAPC": 0,
                "FDAT": "20250101",
                "TDAT": "20991231",
            })
    return records


def generate_purchase_agreements(count=8):
    """Generate blanket purchase agreements."""
    agreements = []
    for i in range(1, count + 1):
        suno = random.choice(SUPPLIERS)["SUNO"]
        itno = random.choice(RM_CODES)
        agreements.append({
            "AGNB": f"AGR-{1000 + i}",
            "SUNO": suno,
            "ITNO": itno,
            "VFDT": "20260101",
            "VTDT": "20261231",
            "AGQT": random.randint(500, 5000),
        })
    return agreements


def generate_planned_orders(count=20):
    """Generate MRP planned orders."""
    planned = []
    for i in range(1, count + 1):
        itno = random.choice(RM_CODES + FG_CODES[:6])
        poty = random.choice(["10", "20", "30"])  # PO, MO, TO
        planned.append({
            "PLPN": f"PLN-{2000 + i}",
            "ITNO": itno,
            "POTY": poty,
            "PPQT": random.randint(10, 200),
            "PLDT": future_date(3, 21),
            "DLDT": future_date(14, 45),
            "WHLO": random.choice(["100", "200", "400"]),
        })
    return planned


# ---------------------------------------------------------------------------
# Main: Write all entity files
# ---------------------------------------------------------------------------

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Master Data
    entities = {
        "Warehouse": WAREHOUSES,
        "Supplier": SUPPLIERS,
        "Customer": CUSTOMERS,
        "ItemMaster": ALL_ITEMS,
        "BillOfMaterial": generate_bom_records(),
        "WorkCenter": WORK_CENTERS,
        "ItemWarehouse": generate_item_warehouse(),
        "PurchaseAgreement": generate_purchase_agreements(),
    }

    # Transaction Data
    po_headers, po_lines = generate_purchase_orders()
    so_headers, so_lines = generate_sales_orders()

    entities["PurchaseOrder"] = po_headers
    entities["PurchaseOrderLine"] = po_lines
    entities["SalesOrder"] = so_headers
    entities["SalesOrderLine"] = so_lines
    entities["ProductionOrder"] = generate_production_orders()
    entities["Delivery"] = generate_deliveries()
    entities["GoodsReceipt"] = generate_goods_receipts()
    entities["TransferOrder"] = generate_transfer_orders()
    entities["Forecast"] = generate_forecasts()
    entities["PlannedOrder"] = generate_planned_orders()

    # CDC Data
    entities["InventoryBalance"] = generate_inventory_balances()

    # Write files
    total_records = 0
    print(f"\nGenerating Infor M3 demo data → {OUTPUT_DIR}/\n")
    print(f"{'Entity':<30} {'Records':>8}")
    print("-" * 42)

    for entity_name, records in sorted(entities.items()):
        filepath = OUTPUT_DIR / f"{entity_name}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, default=str)
        total_records += len(records)
        print(f"{entity_name:<30} {len(records):>8}")

    print("-" * 42)
    print(f"{'TOTAL':<30} {total_records:>8}")
    print(f"\nDemo company: Midwest Industrial Supply")
    print(f"Products: {len(FINISHED_GOODS)} finished goods, {len(RAW_MATERIALS)} raw materials, {len(LABOR_ITEMS)} labor")
    print(f"BOMs: {len(BOMS)} product structures")
    print(f"Files saved to: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
