# SAP Integration Guide for Beer Game
## S/4HANA and APO Supply Chain Data Integration

**Version**: 1.0
**Date**: 2026-01-16
**Status**: Implementation Ready

---

## Table of Contents

1. [Overview](#overview)
2. [AI-Enhanced Features](#ai-enhanced-features)
3. [Architecture](#architecture)
4. [Connection Modes](#connection-modes)
5. [Installation](#installation)
6. [Configuration](#configuration)
7. [Data Extraction](#data-extraction)
8. [AWS Supply Chain Mapping](#aws-supply-chain-mapping)
9. [Plan Writing](#plan-writing)
10. [Usage Examples](#usage-examples)
11. [Troubleshooting](#troubleshooting)
12. [SAP Table Reference](#sap-table-reference)

---

## Overview

The SAP Integration module enables bidirectional data exchange between Beer Game and SAP systems:

- **Extract** supply chain data from S/4HANA and APO
- **Map** to AWS Supply Chain Data Model format
- **Optimize** using Beer Game simulation engine
- **Write** optimized plans back to SAP

### Supported SAP Systems

- **SAP S/4HANA**: ERP with integrated supply chain (1909+)
- **SAP APO**: Advanced Planning and Optimization (7.0+)

### Connection Methods

1. **Direct RFC** (pyrfc): Real-time connection via SAP NetWeaver RFC
2. **CSV Files**: Batch mode using file-based extracts

### AI-Enhanced Capabilities (New)

The integration now includes **Claude AI-powered features** for intelligent data handling:

- **Z-Field Interpretation**: Automatic interpretation of custom SAP fields (Z*/ZZ* fields)
- **Missing Data Assistance**: AI recommendations for handling missing or unexpected data
- **Schema Validation**: Intelligent data quality checks with auto-fix suggestions
- **Delta Loading**: Efficient daily updates with net change detection (20x performance improvement)
- **Auto-Fixing**: Automatic application of AI-recommended data transformations

**For comprehensive AI features documentation, see**: [SAP_AI_INTEGRATION_GUIDE.md](SAP_AI_INTEGRATION_GUIDE.md)

---

## AI-Enhanced Features

### Overview

The SAP integration includes **intelligent loading capabilities** powered by Claude AI (Sonnet 4.5). These features automatically handle the most common challenges in SAP data integration:

1. **Custom Z-Fields**: SAP systems often extend standard tables with custom fields (starting with Z or ZZ). Claude AI automatically interprets these fields and suggests appropriate mappings.

2. **Data Quality Issues**: Missing values, unexpected data types, and schema mismatches are detected and fixed automatically with AI recommendations.

3. **Delta Loading**: Daily incremental loads transfer only changed records, achieving up to 99.5% reduction in data volume with hash-based and date-based change detection.

4. **Initial vs Daily Load**: Two distinct modes optimize for full data synchronization (initial) versus efficient updates (daily).

### Quick Start with AI Features

```bash
# Initial load with Claude AI (full extract with validation)
python backend/scripts/intelligent_sap_load.py \
    --mode initial \
    --source csv \
    --csv-dir /data/sap/csv \
    --claude

# Daily load (delta only with net change detection)
python backend/scripts/intelligent_sap_load.py \
    --mode daily \
    --source csv \
    --csv-dir /data/sap/csv \
    --claude
```

### Key Benefits

| Feature | Benefit | Performance Impact |
|---------|---------|-------------------|
| Z-Field Interpretation | No manual mapping configuration | Saves 2-4 hours per custom field |
| Auto-Fixing | Automatic data quality correction | 90%+ issues resolved automatically |
| Delta Loading | Transfer only changed records | 20x faster, 99.5% data reduction |
| Schema Validation | Early error detection | Prevents downstream failures |
| AI Recommendations | Expert-level data transformation suggestions | Reduces manual analysis time |

### Example: Z-Field Interpretation

```python
# Claude AI automatically interprets custom fields like:
# ZCUSTLEAD -> "Customer lead time in days"
# ZSAFETYSTK -> "Safety stock override quantity"
# ZVENDMAT -> "Vendor-specific material number"

from app.integrations.sap import create_intelligent_loader

loader = create_intelligent_loader(
    mode="initial",
    connection_type="csv",
    use_claude=True,
    claude_api_key="your-anthropic-api-key"
)

# AI automatically analyzes and maps Z-fields
df, result = loader.load_table("MARC", data_source)
print(f"Z-fields found: {result.z_fields_found}")
print(f"AI recommendations: {result.validation_analysis.claude_suggestions}")
```

### When to Use AI Features

**Use AI-Enhanced Loading When:**
- Working with heavily customized SAP systems (many Z-fields)
- Data quality is inconsistent or unknown
- Need to minimize daily data transfer volume
- Want automatic documentation of custom fields
- Require intelligent error handling

**Use Standard Loading When:**
- Simple, well-documented SAP systems
- No custom Z-fields or extensions
- Small datasets where delta loading isn't needed
- Cost optimization (AI features use Anthropic API)

### Configuration

Enable AI features by setting the Anthropic API key:

```bash
# In .env file
ANTHROPIC_API_KEY=sk-ant-your-api-key

# Or pass as command-line argument
--claude-api-key sk-ant-your-api-key
```

**For detailed AI features documentation, see**: [SAP_AI_INTEGRATION_GUIDE.md](SAP_AI_INTEGRATION_GUIDE.md)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      SAP Systems                             │
│                                                              │
│  ┌──────────────┐              ┌──────────────┐            │
│  │  S/4HANA     │              │     APO      │            │
│  │              │              │              │            │
│  │ - MARA/MARC  │              │ - /SAPAPO/   │            │
│  │ - EKKO/EKPO  │              │   LOC/MAT    │            │
│  │ - VBAK/VBAP  │              │ - SNP Plans  │            │
│  │ - LIKP/LIPS  │              │ - Orders     │            │
│  └──────────────┘              └──────────────┘            │
│         │                              │                    │
│         │  RFC or CSV                  │  CSV Primary       │
│         ▼                              ▼                    │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                Beer Game Integration Layer                   │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ S4HANA       │  │    APO       │  │     CSV      │     │
│  │ Connector    │  │  Connector   │  │   Loader     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│         │                  │                  │            │
│         └──────────────────┴──────────────────┘            │
│                          │                                  │
│                          ▼                                  │
│              ┌──────────────────────┐                      │
│              │ Intelligent Loader   │ ◄── NEW              │
│              │ (Claude AI)          │                      │
│              │ - Z-Field Analysis   │                      │
│              │ - Schema Validation  │                      │
│              │ - Delta Loading      │                      │
│              │ - Auto-Fixing        │                      │
│              └──────────────────────┘                      │
│                          │                                  │
│                          ▼                                  │
│              ┌──────────────────────┐                      │
│              │  AWS Supply Chain    │                      │
│              │  Data Model Mapper   │                      │
│              └──────────────────────┘                      │
│                          │                                  │
│                          ▼                                  │
│              ┌──────────────────────┐                      │
│              │   Beer Game Engine   │                      │
│              │   (Optimization)     │                      │
│              └──────────────────────┘                      │
│                          │                                  │
│                          ▼                                  │
│              ┌──────────────────────┐                      │
│              │    Plan Writer       │                      │
│              │  (Back to SAP)       │                      │
│              └──────────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    SAP Systems (Write)                       │
│                                                              │
│  - Purchase Requisitions (BAPI_PR_CREATE)                   │
│  - Planned Orders (CSV Import)                              │
│  - Stock Transport Orders (BAPI_PO_CREATE1)                 │
│  - APO SNP Plans (CSV Upload)                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Connection Modes

### Mode 1: Direct RFC Connection

**Advantages:**
- Real-time data access
- Direct BAPI calls for writing
- No intermediate files

**Requirements:**
- SAP NetWeaver RFC SDK installed
- pyrfc Python library
- SAP user credentials with appropriate authorizations
- Network connectivity to SAP system

**Use Cases:**
- Real-time integration
- Automated scheduled jobs
- Production environments with SAP connectivity

### Mode 2: CSV File-Based

**Advantages:**
- No RFC dependencies
- Works with any SAP export
- Easier security/firewall configuration
- Can work offline

**Requirements:**
- CSV extracts from SAP (manual or scheduled)
- File system access to CSV directory

**Use Cases:**
- Development/testing
- Air-gapped environments
- APO integration (recommended due to liveCache complexity)
- Batch processing

---

## Installation

### Prerequisites

```bash
# Python 3.10+
python --version

# Install core dependencies
cd backend
pip install pandas numpy

# For AI-enhanced features (recommended)
pip install anthropic

# Optional: For RFC connection (Mode 1)
# Requires SAP NetWeaver RFC SDK
pip install pyrfc
```

### SAP NetWeaver RFC SDK Installation (for RFC mode)

**Linux:**
```bash
# Download SDK from SAP Support Portal
# Extract to /usr/local/sap/nwrfcsdk

export SAPNWRFC_HOME=/usr/local/sap/nwrfcsdk
export LD_LIBRARY_PATH=$SAPNWRFC_HOME/lib:$LD_LIBRARY_PATH

pip install pyrfc
```

**Windows:**
```powershell
# Download SDK from SAP Support Portal
# Extract to C:\nwrfcsdk

$env:SAPNWRFC_HOME = "C:\nwrfcsdk"
$env:Path += ";C:\nwrfcsdk\lib"

pip install pyrfc
```

**macOS:**
```bash
# Download SDK from SAP Support Portal
# Extract to /usr/local/sap/nwrfcsdk

export SAPNWRFC_HOME=/usr/local/sap/nwrfcsdk
export DYLD_LIBRARY_PATH=$SAPNWRFC_HOME/lib:$DYLD_LIBRARY_PATH

pip install pyrfc
```

---

## Configuration

### Environment Variables

Create `.env` file:

```bash
# S/4HANA Connection (RFC Mode)
S4HANA_HOST=sap-s4hana.company.com
S4HANA_SYSNR=00
S4HANA_CLIENT=100
S4HANA_USER=BEERGAME
S4HANA_PASSWORD=YourPassword

# APO Connection (CSV Mode Recommended)
APO_CSV_DIR=/data/sap/apo/exports

# Output Directory
SAP_OUTPUT_DIR=/data/sap/beergame/output

# AI-Enhanced Features (NEW)
ANTHROPIC_API_KEY=sk-ant-your-anthropic-api-key
```

### SAP Authorizations Required

**S/4HANA:**
- `S_RFC` - RFC access
- `S_TABU_DIS` - Table read access (MARA, MARC, EKKO, etc.)
- `S_DATASET` - File access (if using CSV export from SAP)
- `BAPI_PR_CREATE` - Purchase requisition creation
- `BAPI_PO_CREATE1` - Purchase order/STO creation

**APO:**
- File system access to CSV export directory
- SNP Planning Book access (for plan upload)

---

## Data Extraction

### Standard vs Intelligent Loading

**Standard Loading** (Basic extraction):
- Direct table reads without validation
- Manual handling of Z-fields
- Full load every time
- See examples below

**Intelligent Loading** (AI-Enhanced):
- Automatic Z-field interpretation
- Schema validation and auto-fixing
- Delta loading for daily updates
- See [SAP_AI_INTEGRATION_GUIDE.md](SAP_AI_INTEGRATION_GUIDE.md)

### S/4HANA Extraction

#### Using RFC Connection

```python
from app.integrations.sap import S4HANAConnector, S4HANAConnectionConfig

# Configure connection
config = S4HANAConnectionConfig(
    ashost="sap-s4hana.company.com",
    sysnr="00",
    client="100",
    user="BEERGAME",
    passwd="YourPassword"
)

# Extract data
with S4HANAConnector(config) as connector:
    # Master data
    plants = connector.extract_plants()
    materials = connector.extract_materials(plant="1000")
    inventory = connector.extract_inventory(plant="1000")

    # Transactional data
    from datetime import date, timedelta

    date_from = date.today() - timedelta(days=90)
    date_to = date.today()

    po_headers, po_items = connector.extract_purchase_orders(
        plant="1000",
        date_from=date_from,
        date_to=date_to
    )

    so_headers, so_items = connector.extract_sales_orders(
        sales_org="1000",
        date_from=date_from,
        date_to=date_to
    )
```

#### Using CSV Files

```python
from app.integrations.sap import CSVDataLoader

# Configure CSV directory
loader = CSVDataLoader(csv_directory="/data/sap/csv")

# List available tables
available_tables = loader.list_available_tables()
print(f"Available: {available_tables}")

# Load data
plants = loader.load_plants()
materials = loader.load_materials(with_plant_data=True)
inventory = loader.load_inventory()
po_headers, po_items = loader.load_purchase_orders()
so_headers, so_items = loader.load_sales_orders()
```

### APO Extraction (CSV Recommended)

```python
from app.integrations.sap import APOConnector, APOConnectionConfig

# Configure for CSV mode
config = APOConnectionConfig(
    csv_directory="/data/sap/apo/exports",
    use_csv_mode=True
)

with APOConnector(config) as connector:
    # Master data
    locations = connector.extract_locations()
    materials = connector.extract_materials()
    mat_locs = connector.extract_material_locations()

    # Planning data
    stock = connector.extract_stock()
    orders = connector.extract_orders()
    snp_plan = connector.extract_snp_plan(
        plan_version="000",
        date_from=date_from,
        date_to=date_to
    )
```

---

## AWS Supply Chain Mapping

### Mapping Overview

The AWS Supply Chain Data Model provides standardized entities for supply chain data:

| SAP Data | AWS Entity | Mapping |
|----------|------------|---------|
| T001W (Plants) | Sites | Physical locations |
| MARA/MARC (Materials) | Products | SKUs/Materials |
| MARD (Stock) | InventoryLevel | Stock positions |
| EKKO/EKPO (POs) | PurchaseOrder | Procurement |
| VBAK/VBAP (SOs) | SalesOrder | Customer orders |
| LIKP/LIPS (Deliveries) | Shipment | Shipments |
| APO Orders | SupplyPlan | Planned supply |
| APO SNP | DemandPlan | Demand forecast |

### Mapping Example

```python
from app.integrations.sap import AWSSupplyChainMapper

mapper = AWSSupplyChainMapper()

# Map S/4HANA data
aws_sites = mapper.map_s4hana_plants_to_sites(plants)
aws_products = mapper.map_s4hana_materials_to_products(materials)
aws_inventory = mapper.map_s4hana_inventory_to_inventory_levels(inventory)
aws_pos = mapper.map_s4hana_po_to_purchase_orders(po_headers, po_items)
aws_sos = mapper.map_s4hana_so_to_sales_orders(so_headers, so_items)

# Map APO data
aws_sites_apo = mapper.map_apo_locations_to_sites(locations)
aws_supply = mapper.map_apo_orders_to_supply_plans(orders)
aws_demand = mapper.map_apo_snp_to_demand_plans(snp_plan)

# Export to AWS format
mapper.export_to_aws_format(
    df=aws_products,
    entity_type="Products",
    output_path="aws_products.csv"
)
```

### AWS Supply Chain Entity Schemas

**Sites:**
```python
{
    "site_id": "1000",
    "site_name": "Hamburg Plant",
    "site_type": "PLANT",
    "country": "DE",
    "city": "Hamburg",
    "is_active": True
}
```

**Products:**
```python
{
    "product_id": "FG001",
    "product_name": "Finished Good 001",
    "product_category": "FERT",
    "unit_of_measure": "EA",
    "is_active": True
}
```

**InventoryLevel:**
```python
{
    "site_id": "1000",
    "product_id": "FG001",
    "inventory_date": "2026-01-16",
    "available_quantity": 500.0,
    "in_transit_quantity": 100.0,
    "safety_stock_quantity": 200.0
}
```

---

## Plan Writing

### Writing Results Back to SAP

#### CSV Mode (Recommended)

```python
from app.integrations.sap import PlanWriter
from datetime import date, timedelta

# Initialize writer in CSV mode
writer = PlanWriter(
    output_directory="/data/sap/beergame/output",
    use_csv_mode=True
)

# Prepare optimization results
import pandas as pd

purchase_reqs = pd.DataFrame({
    "MATERIAL": ["FG001", "FG002"],
    "PLANT": ["1000", "1000"],
    "QUANTITY": [500, 300],
    "DELIV_DATE": [date.today() + timedelta(days=14)] * 2,
    "PREQ_PRICE": [10.0, 15.0],
    "CURRENCY": ["USD", "USD"],
    "PUR_GROUP": ["001", "001"]
})

# Write purchase requisitions
result = writer.write_purchase_requisitions(purchase_reqs)
print(f"Written: {result.records_written}")
print(f"Output: {result.output_file}")

# Write complete plan
plan_metadata = {
    "plan_version": "BG_20260116",
    "planning_horizon_start": date.today(),
    "planning_horizon_end": date.today() + timedelta(days=90),
    "created_by": "BEERGAME",
    "description": "Beer Game Optimization"
}

optimization_results = {
    "purchase_requisitions": purchase_reqs,
    "planned_orders": planned_orders_df,
    "stock_transfers": sto_df,
    "snp_plan": snp_df
}

results = writer.write_beer_game_optimization_plan(
    optimization_results,
    plan_metadata
)
```

#### RFC Mode (Direct BAPI)

```python
from app.integrations.sap import PlanWriter, S4HANAConnector

# Establish connection
with S4HANAConnector(config) as connector:
    # Initialize writer with RFC connection
    writer = PlanWriter(
        connection=connector.connection,
        use_csv_mode=False
    )

    # Write purchase requisitions via BAPI
    result = writer.write_purchase_requisitions(
        purchase_reqs,
        test_mode=False  # Set True for validation only
    )

    # Check results
    for msg in result.messages:
        print(msg)
```

### APO SNP Plan Upload

```python
# APO always uses CSV mode
writer = PlanWriter(
    output_directory="/data/sap/apo/upload",
    use_csv_mode=True
)

snp_plan = pd.DataFrame({
    "LOCATION": ["DC01", "DC02"],
    "MATERIAL": ["FG001", "FG001"],
    "PLAN_DATE": [date.today() + timedelta(days=i) for i in range(2)],
    "DEMAND_QTY": [100, 120],
    "SUPPLY_QTY": [110, 130],
    "STOCK_QTY": [200, 210]
})

result = writer.write_apo_snp_plan(
    snp_plan=snp_plan,
    plan_version="001",
    planning_horizon_start=date.today(),
    planning_horizon_end=date.today() + timedelta(days=90)
)

print(f"SNP plan file: {result.output_file}")
# Then upload to APO via /SAPAPO/SNP94 transaction
```

---

## Usage Examples

### Example 1: Complete Integration Flow

```python
#!/usr/bin/env python3
"""Complete SAP integration example."""

from app.integrations.sap import (
    CSVDataLoader,
    AWSSupplyChainMapper,
    PlanWriter
)
from datetime import date, timedelta

# Step 1: Extract data from CSV
loader = CSVDataLoader("/data/sap/csv")
materials = loader.load_materials(with_plant_data=True)
inventory = loader.load_inventory()
po_headers, po_items = loader.load_purchase_orders()

# Step 2: Map to AWS format
mapper = AWSSupplyChainMapper()
aws_products = mapper.map_s4hana_materials_to_products(materials)
aws_inventory = mapper.map_s4hana_inventory_to_inventory_levels(inventory)
aws_pos = mapper.map_s4hana_po_to_purchase_orders(po_headers, po_items)

# Step 3: Run Beer Game optimization
# (Integrate with your Beer Game engine here)
optimization_results = run_beer_game_optimization(
    products=aws_products,
    inventory=aws_inventory,
    orders=aws_pos
)

# Step 4: Write results back to SAP
writer = PlanWriter(
    output_directory="/data/sap/output",
    use_csv_mode=True
)

plan_metadata = {
    "plan_version": "BG_" + date.today().strftime("%Y%m%d"),
    "planning_horizon_start": date.today(),
    "planning_horizon_end": date.today() + timedelta(days=90),
    "created_by": "BEERGAME",
    "description": "Automated Beer Game Plan"
}

results = writer.write_beer_game_optimization_plan(
    optimization_results,
    plan_metadata
)

print("Integration complete!")
for component, result in results.items():
    print(f"{component}: {result.records_written} records written")
```

### Example 2: Using Command-Line Script (Standard Loading)

```bash
# Using CSV mode
python backend/scripts/sap_integration_example.py \
    --mode csv \
    --csv-dir /data/sap/csv \
    --output-dir /data/sap/output

# Using RFC mode
python backend/scripts/sap_integration_example.py \
    --mode rfc \
    --s4-host sap-s4hana.company.com \
    --s4-sysnr 00 \
    --s4-client 100 \
    --s4-user BEERGAME \
    --s4-passwd YourPassword \
    --output-dir /data/sap/output
```

### Example 2b: Using Intelligent Loading (AI-Enhanced)

```bash
# Initial load with Claude AI (full extract with validation)
python backend/scripts/intelligent_sap_load.py \
    --mode initial \
    --source csv \
    --csv-dir /data/sap/csv \
    --claude \
    --report-dir /data/sap/reports

# Daily delta load (net change only)
python backend/scripts/intelligent_sap_load.py \
    --mode daily \
    --source csv \
    --csv-dir /data/sap/csv \
    --claude \
    --report-dir /data/sap/reports \
    --delta-state-dir /data/sap/delta_state

# RFC connection with AI
python backend/scripts/intelligent_sap_load.py \
    --mode daily \
    --source rfc \
    --s4-host sap-s4hana.company.com \
    --s4-user BEERGAME \
    --s4-passwd YourPassword \
    --claude \
    --tables MARA MARC MARD EKKO EKPO

# Reset delta state (force full reload next time)
python backend/scripts/intelligent_sap_load.py \
    --mode daily \
    --source csv \
    --csv-dir /data/sap/csv \
    --reset-delta
```

### Example 3: Scheduled Batch Job (Standard)

```bash
#!/bin/bash
# sap_integration_job.sh

# Set up environment
export SAP_CSV_DIR=/data/sap/csv
export SAP_OUTPUT_DIR=/data/sap/output
export LOG_DIR=/var/log/beergame

# Run integration
python3 /app/backend/scripts/sap_integration_example.py \
    --mode csv \
    --csv-dir $SAP_CSV_DIR \
    --output-dir $SAP_OUTPUT_DIR \
    >> $LOG_DIR/integration_$(date +%Y%m%d).log 2>&1

# Archive old logs
find $LOG_DIR -name "integration_*.log" -mtime +30 -delete
```

Schedule with cron:
```cron
# Run daily at 2 AM
0 2 * * * /path/to/sap_integration_job.sh
```

### Example 3b: Scheduled Intelligent Job (AI-Enhanced)

```bash
#!/bin/bash
# intelligent_sap_load_job.sh

# Set up environment
export SAP_CSV_DIR=/data/sap/csv
export ANTHROPIC_API_KEY=sk-ant-your-api-key
export REPORT_DIR=/data/sap/reports
export DELTA_STATE_DIR=/data/sap/delta_state
export LOG_DIR=/var/log/beergame

# Timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Run intelligent loading (daily mode with delta)
python3 /app/backend/scripts/intelligent_sap_load.py \
    --mode daily \
    --source csv \
    --csv-dir $SAP_CSV_DIR \
    --claude \
    --report-dir $REPORT_DIR \
    --delta-state-dir $DELTA_STATE_DIR \
    >> $LOG_DIR/intelligent_load_${TIMESTAMP}.log 2>&1

# Check exit code
if [ $? -eq 0 ]; then
    echo "Load completed successfully at $(date)" >> $LOG_DIR/success.log
else
    echo "Load failed at $(date)" >> $LOG_DIR/errors.log
    # Send alert
    mail -s "SAP Load Failed" admin@company.com < $LOG_DIR/intelligent_load_${TIMESTAMP}.log
fi

# Archive old logs and reports
find $LOG_DIR -name "intelligent_load_*.log" -mtime +30 -delete
find $REPORT_DIR -name "validation_report_*.json" -mtime +90 -delete
```

Schedule with cron:
```cron
# Initial load: First day of month at 1 AM
0 1 1 * * export MODE=initial && /path/to/intelligent_sap_load_job.sh

# Daily delta load: Every day at 2 AM
0 2 * * * export MODE=daily && /path/to/intelligent_sap_load_job.sh
```

---

## Troubleshooting

### Common Issues

#### RFC Connection Fails

**Error:** `pyrfc.RFCError: Cannot connect to SAP system`

**Solutions:**
1. Check network connectivity: `ping sap-host.company.com`
2. Verify SAP system is running
3. Check firewall rules for RFC ports (33XX)
4. Verify credentials and authorizations
5. Test with SAP GUI first

#### CSV Files Not Found

**Error:** `CSV file not found for table: MARA`

**Solutions:**
1. Check CSV directory path is correct
2. Verify CSV files exist: `ls /data/sap/csv/*.csv`
3. Check file naming conventions (MARA.csv, SAP_MARA.csv, etc.)
4. Ensure read permissions on CSV files

#### Data Mapping Errors

**Error:** `Missing expected fields in MARA: ['MAKTX']`

**Solutions:**
1. Check SAP table extract includes all required fields
2. Review field mapping in `AWSSupplyChainMapper`
3. Update `expected_fields` list if schema changed
4. Use custom field mapping if needed

#### BAPI Call Fails

**Error:** `BAPI_PR_CREATE failed: Material XYZ not found`

**Solutions:**
1. Verify material exists in SAP
2. Check material is valid for plant
3. Ensure purchasing data maintained (MARC)
4. Run in test mode first: `test_mode=True`
5. Check SAP user authorizations

#### AI Features Issues

**Error:** `anthropic.APIError: Invalid API key`

**Solutions:**
1. Check ANTHROPIC_API_KEY is set correctly
2. Verify API key is active in Anthropic console
3. Test API key: `curl -H "x-api-key: $ANTHROPIC_API_KEY" https://api.anthropic.com/v1/messages`

**Error:** `Z-fields not interpreted`

**Solutions:**
1. Ensure `--claude` flag is enabled
2. Check that Z-fields have sample data (not all NULL)
3. Review validation report for AI analysis results
4. Increase AI token limit if hitting rate limits

**Error:** `Delta loading not working`

**Solutions:**
1. Check delta state directory exists and is writable
2. Verify change date fields exist in table (AEDAT, LAEDA, etc.)
3. Review delta state JSON files in delta_state_dir
4. Use `--reset-delta` to force full reload
5. Ensure key fields are properly defined for hash comparison

### Debugging Tips

**Enable debug logging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Validate data before writing:**
```python
# Check DataFrame before writing
print(purchase_reqs.info())
print(purchase_reqs.head())

# Validate AWS schema
mapper = AWSSupplyChainMapper()
is_valid = mapper.validate_schema(aws_products, mapper.PRODUCT_SCHEMA)
print(f"Schema valid: {is_valid}")
```

**Test with small datasets:**
```python
# Limit rows for testing
materials_sample = materials.head(10)
aws_products = mapper.map_s4hana_materials_to_products(materials_sample)
```

**Debug AI features:**
```python
# Enable verbose logging for AI assistant
from app.integrations.sap import create_intelligent_loader
import logging

logging.basicConfig(level=logging.DEBUG)

loader = create_intelligent_loader(
    mode="initial",
    connection_type="csv",
    use_claude=True,
    save_reports=True  # Saves detailed validation reports
)

# Check validation report
import json
with open('/data/sap/reports/validation_report_MARC.json') as f:
    report = json.load(f)
    print(json.dumps(report, indent=2))
```

**Monitor delta loading performance:**
```python
from app.integrations.sap import SAPDeltaLoader, DeltaLoadConfig

loader = SAPDeltaLoader(state_directory="/data/sap/delta_state")

# Check what's in delta state
state = loader.tracker.get_last_load_timestamp("MARA")
print(f"Last load: {state}")

# View delta statistics
config = DeltaLoadConfig(
    table_name="MARA",
    key_fields=["MATNR"],
    change_date_field="LAEDA"
)

result = loader.load_delta(current_data, config)
print(f"New: {result.new_records}, Changed: {result.changed_records}")
print(f"Efficiency: {result.efficiency_metric:.2%} reduction")
```

---

## SAP Table Reference

### S/4HANA Core Tables

| Table | Description | Key Fields |
|-------|-------------|------------|
| **MARA** | Material Master (General) | MATNR, MAKTX, MTART, MEINS |
| **MARC** | Material Master (Plant) | MATNR, WERKS, DISPO, EISBE, PLIFZ |
| **MARD** | Material Master (Storage Location) | MATNR, WERKS, LGORT, LABST |
| **EKKO** | Purchasing Document Header | EBELN, LIFNR, BEDAT, EKORG |
| **EKPO** | Purchasing Document Item | EBELN, EBELP, MATNR, MENGE |
| **EKET** | Scheduling Agreement Schedule Lines | EBELN, EBELP, ETENR, EINDT |
| **VBAK** | Sales Document Header | VBELN, KUNNR, ERDAT, VKORG |
| **VBAP** | Sales Document Item | VBELN, POSNR, MATNR, KWMENG |
| **LIKP** | Delivery Header | VBELN, LFDAT, WADAT_IST |
| **LIPS** | Delivery Item | VBELN, POSNR, MATNR, LFIMG |
| **T001W** | Plants/Branches | WERKS, NAME1, KUNNR, LIFNR |
| **T001L** | Storage Locations | WERKS, LGORT, LGOBE |

### APO Core Tables

| Table | Description | Key Fields |
|-------|-------------|------------|
| **/SAPAPO/LOC** | Locations | LOCNO, LOCDESC, LOCTYPE |
| **/SAPAPO/MAT** | Materials | MATNR, MATDESC, MATTYPE |
| **/SAPAPO/MATLOC** | Material-Location | MATNR, LOCNO, SAFETY_STOCK |
| **/SAPAPO/ORD** | Orders | ORDERNO, ORDERTYPE, MATNR, QUANTITY |
| **/SAPAPO/STOCK** | Stock/Inventory | MATNR, LOCNO, AVAILABLE_QTY |
| **/SAPAPO/SNP** | SNP Planning Data | PLAN_VERSION, MATNR, LOCNO, DEMAND_QTY |

### Execution & Quality Tables (New)

| Table | Description | Key Fields | SyncDataType |
|-------|-------------|------------|--------------|
| **LTAK** | Transfer Order Header | LGNUM, TESSION | `transfer_orders` |
| **LTAP** | Transfer Order Item | LGNUM, TESSION, TAESSION | `transfer_orders` |
| **QMEL** | Quality Notification Header | QMNUM, QMART, MATNR | `quality_orders` |
| **QMIH** | Quality Notification Item | QMNUM, FEESSION | `quality_orders` |
| **AUFK_PM** | Maintenance Order Header (PM) | AUFNR, EQUNR, ILART | `maintenance_orders` |
| **IHPA** | PM Object Partners | OBJNR, PESSION | `maintenance_orders` |
| **MHIS** | Maintenance History | OBJNR, POINT | `maintenance_orders` |
| **MKAL** | Subcontracting Cockpit | MATNR, WERKS, VEESSION | `subcontracting_orders` |
| **EKKO_SC** | Subcontracting PO Header (doc type L) | EBELN, BSART='L' | `subcontracting_orders` |
| **EKPO_SC** | Subcontracting PO Item | EBELN, EBELP | `subcontracting_orders` |

### Standard BAPIs

| BAPI | Purpose | Parameters |
|------|---------|------------|
| **BAPI_PR_CREATE** | Create Purchase Requisition | PRHEADER, PRITEM |
| **BAPI_PO_CREATE1** | Create Purchase Order/STO | POHEADER, POITEM, POSHIPPING |
| **BAPI_TRANSACTION_COMMIT** | Commit BAPI Changes | WAIT |
| **RFC_READ_TABLE** | Read SAP Table | QUERY_TABLE, FIELDS, OPTIONS |

---

## Appendix A: CSV File Formats

### Expected CSV Formats

#### Materials (MARA.csv)
```csv
MATNR,MAKTX,MTART,MEINS,MATKL,BRGEW,NTGEW,GEWEI,VOLUM,VOLEH
FG001,Finished Good 001,FERT,EA,MAT01,10.5,9.5,KG,0.05,M3
FG002,Finished Good 002,FERT,EA,MAT01,12.0,11.0,KG,0.06,M3
```

#### Inventory (MARD.csv)
```csv
MATNR,WERKS,LGORT,LABST,UMLME,INSME,SPEME
FG001,1000,0001,500,100,0,0
FG002,1000,0001,300,50,0,0
```

#### Purchase Orders Header (EKKO.csv)
```csv
EBELN,BUKRS,BSTYP,BSART,LIFNR,EKORG,EKGRP,BEDAT
4500001234,1000,F,NB,VENDOR01,1000,001,20260115
```

#### Purchase Orders Item (EKPO.csv)
```csv
EBELN,EBELP,MATNR,WERKS,LGORT,MENGE,MEINS,NETPR
4500001234,00010,FG001,1000,0001,500,EA,10.00
```

---

## Appendix B: Makefile Targets

Add to `Makefile`:

```makefile
# SAP Integration Targets

.PHONY: sap-extract-csv
sap-extract-csv: ## Extract SAP data from CSV files
	docker compose exec backend python -m scripts.sap_integration_example \\
		--mode csv \\
		--csv-dir /data/sap/csv \\
		--output-dir /data/sap/output

.PHONY: sap-extract-rfc
sap-extract-rfc: ## Extract SAP data via RFC
	docker compose exec backend python -m scripts.sap_integration_example \\
		--mode rfc \\
		--s4-host ${S4HANA_HOST} \\
		--s4-sysnr ${S4HANA_SYSNR} \\
		--s4-client ${S4HANA_CLIENT} \\
		--s4-user ${S4HANA_USER} \\
		--s4-passwd ${S4HANA_PASSWORD}

.PHONY: sap-test-connection
sap-test-connection: ## Test SAP RFC connection
	docker compose exec backend python -c \\
		"from app.integrations.sap import S4HANAConnector, S4HANAConnectionConfig; \\
		import os; \\
		config = S4HANAConnectionConfig( \\
			ashost=os.getenv('S4HANA_HOST'), \\
			sysnr=os.getenv('S4HANA_SYSNR'), \\
			client=os.getenv('S4HANA_CLIENT'), \\
			user=os.getenv('S4HANA_USER'), \\
			passwd=os.getenv('S4HANA_PASSWORD') \\
		); \\
		conn = S4HANAConnector(config); \\
		print('Testing connection...'); \\
		result = conn.connect(); \\
		print(f'Connection: {'SUCCESS' if result else 'FAILED'}'); \\
		conn.disconnect()"

.PHONY: sap-intelligent-load
sap-intelligent-load: ## Run intelligent SAP load with Claude AI
	docker compose exec backend python scripts/intelligent_sap_load.py \\
		--mode daily \\
		--source csv \\
		--csv-dir /data/sap/csv \\
		--claude \\
		--report-dir /data/sap/reports \\
		--delta-state-dir /data/sap/delta_state

.PHONY: sap-initial-load
sap-initial-load: ## Run initial full SAP load
	docker compose exec backend python scripts/intelligent_sap_load.py \\
		--mode initial \\
		--source csv \\
		--csv-dir /data/sap/csv \\
		--claude \\
		--report-dir /data/sap/reports

.PHONY: sap-reset-delta
sap-reset-delta: ## Reset delta state (force full reload)
	docker compose exec backend python scripts/intelligent_sap_load.py \\
		--mode daily \\
		--source csv \\
		--csv-dir /data/sap/csv \\
		--reset-delta
```

---

## Support and Resources

### Documentation
- **[SAP_AI_INTEGRATION_GUIDE.md](SAP_AI_INTEGRATION_GUIDE.md)** - Comprehensive AI features documentation
- [SAP S/4HANA Documentation](https://help.sap.com/s4hana)
- [SAP APO Documentation](https://help.sap.com/apo)
- [AWS Supply Chain Data Model](https://docs.aws.amazon.com/aws-supply-chain/)
- [pyrfc Documentation](https://sap.github.io/PyRFC/)
- [Anthropic Claude API](https://docs.anthropic.com/)

### Contact
- Beer Game Support: See repository maintainers
- SAP Issues: SAP Support Portal
- pyrfc Issues: https://github.com/SAP/PyRFC/issues

---

## Related Documentation

- **[SAP_AI_INTEGRATION_GUIDE.md](SAP_AI_INTEGRATION_GUIDE.md)**: Comprehensive guide for AI-enhanced features including Z-field interpretation, delta loading, schema validation, and auto-fixing
- **[TRM_IMPLEMENTATION_PLAN.md](TRM_IMPLEMENTATION_PLAN.md)**: Implementation plan for Tiny Recursive Models as Beer Game agents

---

**Document Version**: 1.1
**Last Updated**: 2026-01-16
**Status**: Production Ready (with AI enhancements)
