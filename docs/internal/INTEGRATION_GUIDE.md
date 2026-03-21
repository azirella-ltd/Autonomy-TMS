# Integration Guide

**Last Updated**: 2026-02-25

---

## Overview

Autonomy provides comprehensive integration capabilities for both reading data from external systems (import) and writing data to external systems (export). This guide covers data import/export, API usage, authentication, and integration patterns.

---

## Table of Contents

1. [Data Import (Read Capabilities)](#data-import-read-capabilities)
2. [Data Export (Write Capabilities)](#data-export-write-capabilities)
3. [REST API Integration](#rest-api-integration)
4. [WebSocket API](#websocket-api)
5. [Authentication & Authorization](#authentication--authorization)
6. [Integration Patterns](#integration-patterns)
7. [Code Examples](#code-examples)

---

## Data Import (Read Capabilities)

### Supported Formats

**1. CSV/Excel (Bulk Upload)**
- **Use Case**: Import master data (items, sites, BOMs, forecasts)
- **Format**: CSV (UTF-8) or Excel (.xlsx)
- **Size Limit**: 10,000 rows per file (configurable)
- **Validation**: Schema validation, duplicate detection, referential integrity

**2. JSON (REST API)**
- **Use Case**: Real-time data integration, API-to-API
- **Format**: JSON
- **Batch Size**: 1,000 records per request (configurable)
- **Validation**: Pydantic schema validation

**3. Database Direct Connection**
- **Use Case**: ETL pipelines, scheduled imports
- **Supported DBs**: PostgreSQL, MySQL, MariaDB, SQL Server
- **Method**: SQLAlchemy connections
- **Frequency**: Configurable (hourly, daily, on-demand)

**4. AWS S3 Integration** (Planned)
- **Use Case**: Large file imports, data lake integration
- **Format**: CSV, Parquet, JSON
- **Trigger**: S3 event notifications
- **Processing**: Async batch processing

### Import Entities

**Supply Chain Network**:
- **Sites**: Distribution centers, factories, warehouses, retailers
- **Transportation Lanes**: Routes between sites
- **Products**: SKUs, finished goods, components, raw materials
- **Markets**: Market demand/supply sites

**Demand & Forecasts**:
- **Forecasts**: Statistical forecasts with P10/P50/P90 percentiles
- **Historical Demand**: Actual demand history for training
- **Supplementary Time Series**: Promotional events, economic indicators

**Inventory**:
- **Inventory Levels**: Current on-hand, available, reserved quantities
- **Inventory Policies**: Safety stock rules (4 policy types)
- **Lot Tracking**: Batch/lot information for traceability

**Bill of Materials**:
- **ProductBom**: Component requirements for manufactured items
- **Scrap Rates**: Expected waste/yield loss
- **Substitutions**: Alternate components

**Vendor Data**:
- **Vendors**: Supplier information
- **VendorProduct**: Supplier-specific product attributes
- **VendorLeadTime**: Lead times by vendor and product

**Capacity**:
- **CapacityResource**: Available capacity by site and resource
- **ProductionProcess**: Manufacturing process definitions

**Sourcing Rules**:
- **SourcingRules**: Buy/transfer/manufacture rules with priorities
- **Multi-sourcing**: Multiple sources with allocation logic

### Import Process

**Step 1: Data Preparation**

Example CSV format for **Items** (Products):
```csv
item_name,item_type,unit_cost,unit_price,lead_time_days,min_order_qty,lot_size
Beer Case,finished_good,10.00,15.00,7,50,100
Wine Case,finished_good,20.00,30.00,14,25,50
Component A,component,2.50,0,5,100,500
```

Example CSV format for **Nodes** (Sites):
```csv
node_name,sc_node_type,master_type,address,city,state,country
DC East,DC,INVENTORY,123 Main St,Boston,MA,USA
DC West,DC,INVENTORY,456 Oak Ave,Seattle,WA,USA
Factory Central,Factory,MANUFACTURER,789 Industrial Pkwy,Chicago,IL,USA
```

Example CSV format for **Forecasts**:
```csv
product_name,site_name,forecast_date,forecast_quantity,forecast_p50,forecast_p10,forecast_p90
Beer Case,DC East,2026-01-22,1000,1000,800,1200
Beer Case,DC East,2026-01-29,1050,1050,840,1260
Wine Case,DC West,2026-01-22,500,500,400,600
```

**Step 2: Upload via UI**

1. Navigate to http://localhost:8088/admin/import
2. Select entity type (Items, Nodes, Forecasts, etc.)
3. Upload CSV/Excel file
4. Preview data (first 10 rows)
5. Map columns to fields (if headers don't match exactly)
6. Validate:
   - Schema validation
   - Duplicate detection
   - Foreign key checks
7. Review errors (if any)
8. Commit or cancel

**Step 3: Upload via API**

```bash
# Upload items
POST /api/v1/import/items
Content-Type: multipart/form-data

# Form data:
# - file: items.csv
# - config_id: 1
# - overwrite_existing: false

# Response
{
  "task_id": "import-abc-123",
  "status": "PENDING",
  "total_rows": 150
}

# Check status
GET /api/v1/import/status/import-abc-123

# Response
{
  "task_id": "import-abc-123",
  "status": "COMPLETED",
  "total_rows": 150,
  "success_rows": 148,
  "error_rows": 2,
  "errors": [
    {
      "row": 5,
      "field": "unit_cost",
      "error": "Must be positive"
    },
    {
      "row": 12,
      "field": "item_name",
      "error": "Duplicate item name"
    }
  ]
}
```

### Validation & Mapping

**Automatic Validations**:
- **Type Validation**: Ensure fields match expected types (int, float, date, enum)
- **Required Fields**: Check that mandatory fields are present
- **Foreign Keys**: Verify referenced entities exist (e.g., product_id exists in items table)
- **Duplicates**: Detect duplicate primary keys or unique constraints
- **Range Checks**: Ensure values are within reasonable ranges (e.g., unit_cost > 0)

**Field Mapping** (if CSV headers don't match):
```python
# Example: User CSV has "Product Name" but system expects "item_name"
field_mapping = {
    "Product Name": "item_name",
    "SKU": "item_id",
    "Cost ($)": "unit_cost"
}

# Apply mapping during import
POST /api/v1/import/items
{
  "file": "items.csv",
  "field_mapping": field_mapping
}
```

**Preview Before Commit**:
```bash
# Preview import (does not commit to database)
POST /api/v1/import/items/preview
{
  "file": "items.csv"
}

# Response: First 10 rows with validation results
{
  "preview_rows": [
    {"item_name": "Beer Case", "unit_cost": 10.0, "status": "valid"},
    {"item_name": "Wine Case", "unit_cost": -5.0, "status": "error", "error": "unit_cost must be positive"},
    ...
  ],
  "summary": {
    "total_rows": 150,
    "valid_rows": 148,
    "error_rows": 2
  }
}
```

---

## Data Export (Write Capabilities)

### Supported Formats

**1. CSV/Excel (Formatted Reports)**
- **Use Case**: Export data for analysis in Excel/Google Sheets
- **Format**: CSV (UTF-8) or Excel (.xlsx)
- **Customization**: Select columns, apply filters, sort order

**2. JSON (API Responses)**
- **Use Case**: API-to-API integration, programmatic access
- **Format**: JSON
- **Pagination**: Limit/offset or cursor-based
- **Filtering**: Query parameters for field filtering

**3. PDF (Executive Summaries)**
- **Use Case**: Reports for non-technical stakeholders
- **Format**: PDF with charts and tables
- **Templates**: Customizable report templates

**4. Database Views** (Planned)
- **Use Case**: Read-only access for BI tools (Tableau, Power BI)
- **Method**: SQL views or REST API
- **Refresh**: Real-time or scheduled

### Export Entities

**Supply Plans**:
- **Supply Plan Recommendations**: PO/TO/MO requests from planning engine
- **Sourcing Schedules**: When to order, from whom, how much
- **Exception Alerts**: Stockout warnings, overstock alerts

**Inventory Projections**:
- **Multi-Period Projections**: Week-by-week inventory forecast (52 weeks)
- **Target vs. Actual**: Compare projected inventory to targets
- **ATP Projections**: Available-to-Promise over time

**Capacity Requirements**:
- **Resource Utilization**: Capacity consumption by period
- **Bottleneck Analysis**: Resources at risk of over-capacity
- **Capacity Gaps**: Shortfall vs. requirements

**KPI Dashboards**:
- **Financial Metrics**: Total cost, cost breakdown, budget variance
- **Customer Metrics**: OTIF, fill rate, service level
- **Operational Metrics**: Inventory turns, days of supply, bullwhip ratio
- **Strategic Metrics**: CO2 emissions, supplier reliability

**Probabilistic Balanced Scorecards** (Stochastic Planning):
- **Distribution Metrics**: P10/P50/P90 for all KPIs
- **Risk Metrics**: P(Cost < Budget), P(Service Level > Target)
- **Scenario Outcomes**: Monte Carlo simulation results

**Game Analytics**:
- **Leaderboards**: Player rankings by total cost
- **Round History**: Round-by-round game state
- **Bullwhip Analysis**: Order variance by echelon
- **Performance Benchmarks**: Human vs. AI comparisons

### Export Process

**Method 1: UI Export**

1. Navigate to report page (e.g., Supply Plan, Inventory Projection)
2. Apply filters (date range, sites, items, etc.)
3. Click "Export" button
4. Select format (CSV, Excel, PDF)
5. Download file

**Method 2: API Export**

```bash
# Export supply plan to CSV
GET /api/v1/supply-plan/{task_id}/export?format=csv

# Response: CSV file download
# Content-Type: text/csv
# Content-Disposition: attachment; filename="supply_plan_abc-123.csv"

# Export to JSON
GET /api/v1/supply-plan/{task_id}/export?format=json

# Response: JSON payload
{
  "supply_plan_id": "abc-123",
  "config_id": 1,
  "generated_date": "2026-01-22",
  "recommendations": [
    {
      "type": "purchase_order",
      "vendor_id": 10,
      "product_id": 5,
      "quantity": 1000,
      "requested_delivery_date": "2026-02-05",
      "estimated_cost": 10000
    },
    {
      "type": "transfer_order",
      "origin_site_id": 2,
      "destination_site_id": 5,
      "product_id": 5,
      "quantity": 500,
      "expected_arrival_date": "2026-02-01"
    },
    ...
  ]
}
```

### Automation

**Scheduled Exports**:
```python
# Configure scheduled export (via API or admin UI)
POST /api/v1/export/schedule
{
  "name": "Weekly Supply Plan Export",
  "entity_type": "supply_plan",
  "format": "excel",
  "schedule": "0 8 * * 1",  # Cron: Every Monday at 8am
  "filters": {
    "config_id": 1,
    "planning_horizon": 52
  },
  "delivery": {
    "method": "email",
    "recipients": ["planner@company.com", "manager@company.com"],
    "subject": "Weekly Supply Plan - {date}"
  }
}
```

**Event-Triggered Exports**:
```python
# Export when supply plan is approved
POST /api/v1/export/trigger
{
  "trigger_event": "supply_plan_approved",
  "entity_type": "supply_plan",
  "format": "pdf",
  "delivery": {
    "method": "webhook",
    "url": "https://external-system.com/api/receive-supply-plan"
  }
}
```

**Webhook Integration**:
```python
# Autonomy sends HTTP POST to external system when export is ready
POST https://external-system.com/api/receive-supply-plan
Content-Type: application/json

{
  "event": "supply_plan_exported",
  "export_id": "export-xyz-789",
  "download_url": "https://autonomy.ai/api/v1/exports/export-xyz-789/download",
  "expires_at": "2026-01-29T00:00:00Z"
}
```

---

## REST API Integration

### Base URL

**Local Development**: `http://localhost:8088/api`
**Production**: `https://your-domain.com/api`

**API Version**: `/api/v1/`

### Authentication

**Method**: JWT tokens via HTTP-only cookies + CSRF tokens

**Login**:
```bash
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@company.com",
  "password": "SecurePassword123!"
}

# Response
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 5,
    "email": "user@company.com",
    "role": "TENANT_ADMIN",
    "customer_id": 1
  }
}

# Token is also set as HTTP-only cookie (automatic for browser clients)
# Set-Cookie: access_token=eyJhbG...; HttpOnly; Secure; SameSite=Lax
```

**Using Token** (for non-browser clients):
```bash
# Include token in Authorization header
GET /api/v1/supply-chain-configs
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**CSRF Protection** (for browser clients):
```bash
# Get CSRF token
GET /api/v1/auth/csrf-token

# Response
{
  "csrf_token": "abc123xyz..."
}

# Include CSRF token in requests
POST /api/v1/supply-plan/generate
X-CSRF-Token: abc123xyz...
Content-Type: application/json

{...}
```

### Common Endpoints

**Supply Chain Configuration**:
```bash
# List all configs
GET /api/v1/supply-chain-configs

# Get specific config
GET /api/v1/supply-chain-configs/{config_id}

# Create config
POST /api/v1/supply-chain-configs
{
  "config_name": "My Network",
  "customer_id": 1,
  "sites": [...],
  "transportation_lanes": [...],
  "products": [...]
}

# Update config
PUT /api/v1/supply-chain-configs/{config_id}

# Delete config
DELETE /api/v1/supply-chain-configs/{config_id}
```

**Supply Planning**:
```bash
# Generate supply plan
POST /api/v1/supply-plan/generate
{
  "config_id": 1,
  "planning_horizon": 52,
  "start_date": "2026-01-22",
  "stochastic_params": {...},
  "objectives": {...}
}

# Response
{
  "task_id": "plan-abc-123",
  "status": "PENDING"
}

# Check status
GET /api/v1/supply-plan/status/plan-abc-123

# Get results
GET /api/v1/supply-plan/result/plan-abc-123

# Approve plan
POST /api/v1/supply-plan/approve/plan-abc-123
{
  "approved_by": "user@company.com",
  "comments": "Approved for execution"
}
```

**Inventory Management**:
```bash
# Get inventory levels
GET /api/v1/inventory/levels?site_id=5&product_id=10

# Adjust inventory
POST /api/v1/inventory/adjust
{
  "site_id": 5,
  "product_id": 10,
  "adjustment_qty": 100,
  "reason": "cycle_count_correction"
}

# Get inventory projection
GET /api/v1/inventory/projection?site_id=5&product_id=10&horizon_weeks=12
```

**Order Promising**:
```bash
# Calculate ATP
POST /api/v1/order-promising/atp
{
  "site_id": 5,
  "item_id": 10,
  "requested_quantity": 100,
  "requested_date": "2026-01-25"
}

# Response
{
  "available_quantity": 100,
  "promise_date": "2026-01-25",
  "source_sites": [5],
  "split_required": false
}
```

**Transfer Orders**:
```bash
# Create transfer order
POST /api/v1/transfer-orders
{
  "origin_site_id": 2,
  "destination_site_id": 5,
  "config_id": 1,
  "expected_arrival_date": "2026-02-01",
  "lines": [
    {"product_id": 10, "ordered_quantity": 500}
  ]
}

# Ship transfer order
POST /api/v1/transfer-orders/{id}/ship
{
  "ship_date": "2026-01-25",
  "shipped_quantities": {"1": 500}
}

# Receive transfer order
POST /api/v1/transfer-orders/{id}/receive
{
  "receive_date": "2026-02-01",
  "received_quantities": {"1": 495}
}
```

**Beer Game**:
```bash
# Create mixed game
POST /api/v1/mixed-games
{
  "name": "Training Game",
  "config_id": 1,
  "max_rounds": 52,
  "players": [...]
}

# Start game
POST /api/v1/mixed-games/{game_id}/start

# Play round (human decision)
POST /api/v1/mixed-games/{game_id}/play-round
{
  "player_id": 5,
  "order_quantity": 120
}

# Get game state
GET /api/v1/mixed-games/{game_id}/state

# Get analytics
GET /api/v1/mixed-games/{game_id}/analytics
```

### Pagination

**Method**: Limit/Offset

```bash
# Get first page (50 items)
GET /api/v1/supply-chain-configs?limit=50&offset=0

# Get second page
GET /api/v1/supply-chain-configs?limit=50&offset=50

# Response includes pagination metadata
{
  "items": [...],
  "pagination": {
    "total": 237,
    "limit": 50,
    "offset": 0,
    "has_next": true,
    "has_prev": false
  }
}
```

### Filtering & Sorting

**Filtering**:
```bash
# Filter by field values
GET /api/v1/items?item_type=finished_good&unit_cost__gte=10.0

# Filter operators:
# - __eq: equal (default)
# - __ne: not equal
# - __gt: greater than
# - __gte: greater than or equal
# - __lt: less than
# - __lte: less than or equal
# - __in: in list
# - __like: SQL LIKE (substring match)
```

**Sorting**:
```bash
# Sort by field (ascending)
GET /api/v1/items?sort=unit_cost

# Sort descending
GET /api/v1/items?sort=-unit_cost

# Multiple sort fields
GET /api/v1/items?sort=item_type,-unit_cost
```

### Error Handling

**HTTP Status Codes**:
- `200 OK`: Success
- `201 Created`: Resource created
- `400 Bad Request`: Validation error
- `401 Unauthorized`: Missing or invalid token
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Resource not found
- `422 Unprocessable Entity`: Business logic error
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error

**Error Response Format**:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input data",
    "details": [
      {
        "field": "unit_cost",
        "message": "Must be a positive number"
      }
    ]
  }
}
```

### Rate Limiting

**Limits**:
- **Anonymous**: 100 requests/hour
- **Authenticated**: 1000 requests/hour
- **System Admin**: Unlimited

**Headers**:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 995
X-RateLimit-Reset: 1640000000
```

**Exceeded**:
```
HTTP/1.1 429 Too Many Requests
Retry-After: 3600

{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests. Please try again in 3600 seconds."
  }
}
```

---

## WebSocket API

### Connection

**URL**: `ws://localhost:8088/api/ws` (or `wss://` for secure)

**Authentication**: Include JWT token in connection query params
```javascript
const socket = io('http://localhost:8088/api/ws', {
  query: { token: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...' }
});
```

### Game Events

**Join Game Room**:
```javascript
socket.emit('join_game', { game_id: 123 });
```

**Listen for Round Completion**:
```javascript
socket.on('round_completed', (data) => {
  console.log('Round', data.round_number, 'completed');
  console.log('Game state:', data.game_state);
  updateUI(data);
});
```

**Listen for Player Actions**:
```javascript
socket.on('player_action', (data) => {
  console.log('Player', data.player_name, 'ordered', data.order_quantity);
  updatePlayerStatus(data.player_id, 'ready');
});
```

**Listen for Game Completion**:
```javascript
socket.on('game_completed', (data) => {
  console.log('Game completed!');
  console.log('Final results:', data.summary);
  showFinalScorecard(data);
});
```

### Planning Events (Planned)

**Subscribe to Planning Updates**:
```javascript
socket.emit('subscribe_planning', { config_id: 1 });

socket.on('supply_plan_update', (data) => {
  console.log('Supply plan status:', data.status);
  if (data.status === 'COMPLETED') {
    console.log('Results:', data.result);
  }
});
```

---

## Authentication & Authorization

### User Roles

**Role Hierarchy**:
1. **SYSTEM_ADMIN**: Full access to all features and all customers
2. **TENANT_ADMIN**: Admin access within their customer org
3. **PLANNER**: Can create/approve supply plans within their customer org
4. **PLAYER**: Can play scenarios, view dashboards (read-only planning)

### Permissions (RBAC)

**Capability-Based Permissions**:
- **view_mps**: View MPS plans
- **manage_mps**: Create/edit MPS plans
- **approve_mps**: Approve MPS plans for execution
- **view_supply_plan**: View supply plans
- **manage_supply_plan**: Generate supply plans
- **approve_supply_plan**: Approve supply plans
- **view_inventory**: View inventory levels
- **manage_inventory**: Adjust inventory
- **view_games**: View games
- **manage_games**: Create/manage games
- **view_analytics**: View dashboards
- **manage_users**: User management (TENANT_ADMIN+)
- **manage_configs**: Supply chain configuration (TENANT_ADMIN+)

**Permission Checks**:
```python
# Backend permission decorator
from app.core.rbac import require_permission

@router.post("/supply-plan/approve/{task_id}")
@require_permission("approve_supply_plan")
async def approve_supply_plan(task_id: str, current_user: User = Depends(get_current_user)):
    # Only users with approve_supply_plan permission can access
    ...
```

### Multi-Tenancy (Customers)

**Customer Isolation**:
- Each customer represents a company/organization
- Users belong to one customer
- Data is scoped to customer (supply chain configs, scenarios, plans)
- TENANT_ADMIN can only see their customer's data
- SYSTEM_ADMIN can see all customers

**API Scoping**:
```bash
# User in Customer 1 can only see Customer 1 configs
GET /api/v1/supply-chain-configs
# Returns configs where customer_id = current_user.customer_id

# SYSTEM_ADMIN sees all
GET /api/v1/supply-chain-configs?customer_id=1  # Filter by customer
```

---

## Integration Patterns

### Pattern 1: ERP Integration (Read & Write)

**Scenario**: Sync master data from ERP (SAP, Oracle) to Autonomy, export supply plans back to ERP.

**Architecture**:
```
ERP (SAP) ←→ ETL Layer ←→ Autonomy API
```

**Step 1: Import Master Data from ERP** (Daily)
```python
import requests

# Extract from ERP (example: SAP)
items = sap_client.get_items()
sites = sap_client.get_sites()
boms = sap_client.get_boms()

# Transform to Autonomy format
autonomy_items = [
    {
        "item_name": item["MATNR"],
        "item_type": "finished_good",
        "unit_cost": item["COST"],
        ...
    }
    for item in items
]

# Load to Autonomy
response = requests.post(
    "http://autonomy.ai/api/v1/import/items",
    headers={"Authorization": f"Bearer {token}"},
    json={"items": autonomy_items}
)
```

**Step 2: Generate Supply Plan in Autonomy**
```python
# Trigger planning
response = requests.post(
    "http://autonomy.ai/api/v1/supply-plan/generate",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "config_id": 1,
        "planning_horizon": 52,
        "stochastic_params": {...}
    }
)

task_id = response.json()["task_id"]

# Poll for completion
while True:
    status_response = requests.get(
        f"http://autonomy.ai/api/v1/supply-plan/status/{task_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    status = status_response.json()["status"]
    if status == "COMPLETED":
        break
    time.sleep(5)

# Get results
result_response = requests.get(
    f"http://autonomy.ai/api/v1/supply-plan/result/{task_id}",
    headers={"Authorization": f"Bearer {token}"}
)
supply_plan = result_response.json()
```

**Step 3: Export Supply Plan to ERP** (Write Back)
```python
# Extract PO recommendations from Autonomy supply plan
pos = [rec for rec in supply_plan["recommendations"] if rec["type"] == "purchase_order"]

# Transform to ERP format
sap_pos = [
    {
        "EBELN": None,  # Will be generated by SAP
        "LIFNR": rec["vendor_id"],
        "MATNR": rec["product_id"],
        "MENGE": rec["quantity"],
        "EINDT": rec["requested_delivery_date"],
        ...
    }
    for rec in pos
]

# Load to ERP
for po in sap_pos:
    sap_client.create_purchase_order(po)
```

### Pattern 2: BI Tool Integration (Read-Only)

**Scenario**: Connect Tableau/Power BI to Autonomy for dashboards.

**Architecture**:
```
Autonomy Database ←→ SQL Views ←→ Tableau/Power BI
```

**Option A: Direct Database Connection**
```sql
-- Create read-only user
CREATE USER 'tableau_user'@'%' IDENTIFIED BY 'secure_password';

-- Grant SELECT on relevant views
GRANT SELECT ON autonomy.v_inventory_levels TO 'tableau_user'@'%';
GRANT SELECT ON autonomy.v_supply_plan_summary TO 'tableau_user'@'%';
GRANT SELECT ON autonomy.v_game_analytics TO 'tableau_user'@'%';

-- Create views for BI tools
CREATE VIEW v_inventory_levels AS
SELECT
    s.site_name AS site_name,
    p.product_name AS product_name,
    inv.on_hand_quantity,
    inv.available_quantity,
    inv.reserved_quantity,
    inv.in_transit_quantity,
    inv.last_updated
FROM inv_level inv
JOIN site s ON inv.site_id = s.id
JOIN product p ON inv.product_id = p.id;
```

**Option B: REST API Connection** (via Tableau Web Data Connector)
```javascript
// Tableau WDC to fetch data from Autonomy API
const connector = tableau.makeConnector();

connector.getSchema = function(schemaCallback) {
  const schema = {
    id: "inventory_levels",
    columns: [
      { id: "site_name", dataType: tableau.dataTypeEnum.string },
      { id: "product_name", dataType: tableau.dataTypeEnum.string },
      { id: "on_hand_quantity", dataType: tableau.dataTypeEnum.float },
      ...
    ]
  };
  schemaCallback([schema]);
};

connector.getData = function(table, doneCallback) {
  fetch('http://autonomy.ai/api/v1/inventory/levels', {
    headers: { 'Authorization': 'Bearer ' + token }
  })
  .then(response => response.json())
  .then(data => {
    table.appendRows(data.items);
    doneCallback();
  });
};
```

### Pattern 3: Event-Driven Integration (Webhooks)

**Scenario**: Notify external system when supply plan is approved.

**Setup Webhook**:
```bash
POST /api/v1/webhooks
{
  "name": "Supply Plan Approved Notification",
  "event": "supply_plan_approved",
  "url": "https://external-system.com/api/webhooks/autonomy",
  "secret": "shared_secret_for_signature",
  "active": true
}
```

**Autonomy Sends**:
```bash
POST https://external-system.com/api/webhooks/autonomy
Content-Type: application/json
X-Autonomy-Signature: sha256=abc123...

{
  "event": "supply_plan_approved",
  "task_id": "plan-abc-123",
  "config_id": 1,
  "approved_by": "user@company.com",
  "approved_at": "2026-01-22T14:30:00Z",
  "download_url": "https://autonomy.ai/api/v1/supply-plan/result/plan-abc-123"
}
```

**External System Receives**:
```python
from flask import Flask, request
import hmac, hashlib

app = Flask(__name__)

@app.route('/api/webhooks/autonomy', methods=['POST'])
def receive_autonomy_webhook():
    # Verify signature
    signature = request.headers.get('X-Autonomy-Signature')
    expected_signature = 'sha256=' + hmac.new(
        'shared_secret_for_signature'.encode(),
        request.data,
        hashlib.sha256
    ).hexdigest()

    if signature != expected_signature:
        return 'Unauthorized', 401

    # Process event
    event_data = request.json
    if event_data['event'] == 'supply_plan_approved':
        # Download supply plan
        plan = requests.get(
            event_data['download_url'],
            headers={'Authorization': f'Bearer {token}'}
        ).json()

        # Process plan (e.g., create POs in ERP)
        process_supply_plan(plan)

    return 'OK', 200
```

---

## Code Examples

### Python Client Example

```python
import requests
from typing import Dict, List

class AutonomyClient:
    def __init__(self, base_url: str, email: str, password: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.login(email, password)

    def login(self, email: str, password: str):
        """Authenticate and store token."""
        response = self.session.post(
            f"{self.base_url}/auth/login",
            json={"email": email, "password": password}
        )
        response.raise_for_status()
        data = response.json()
        self.session.headers.update({
            "Authorization": f"Bearer {data['access_token']}"
        })

    def get_supply_chain_configs(self) -> List[Dict]:
        """Get all supply chain configurations."""
        response = self.session.get(f"{self.base_url}/supply-chain-configs")
        response.raise_for_status()
        return response.json()["items"]

    def generate_supply_plan(self, config_id: int, horizon: int = 52) -> str:
        """Generate supply plan and return task ID."""
        response = self.session.post(
            f"{self.base_url}/supply-plan/generate",
            json={
                "config_id": config_id,
                "planning_horizon": horizon,
                "start_date": "2026-01-22"
            }
        )
        response.raise_for_status()
        return response.json()["task_id"]

    def get_supply_plan_status(self, task_id: str) -> Dict:
        """Check supply plan generation status."""
        response = self.session.get(
            f"{self.base_url}/supply-plan/status/{task_id}"
        )
        response.raise_for_status()
        return response.json()

    def get_supply_plan_result(self, task_id: str) -> Dict:
        """Get completed supply plan results."""
        response = self.session.get(
            f"{self.base_url}/supply-plan/result/{task_id}"
        )
        response.raise_for_status()
        return response.json()

# Usage
client = AutonomyClient(
    base_url="http://localhost:8088/api/v1",
    email="user@company.com",
    password="SecurePassword123!"
)

# Get configs
configs = client.get_supply_chain_configs()
print(f"Found {len(configs)} configs")

# Generate plan
task_id = client.generate_supply_plan(config_id=1, horizon=52)
print(f"Supply plan task ID: {task_id}")

# Poll for completion
import time
while True:
    status = client.get_supply_plan_status(task_id)
    print(f"Status: {status['status']}")
    if status["status"] == "COMPLETED":
        break
    time.sleep(5)

# Get results
result = client.get_supply_plan_result(task_id)
print(f"Total cost: ${result['financial']['total_cost']['E']:,.0f}")
print(f"Service level: {result['customer']['service_level']['E']:.1%}")
```

### JavaScript Client Example

```javascript
class AutonomyClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
    this.token = null;
  }

  async login(email, password) {
    const response = await fetch(`${this.baseUrl}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });

    if (!response.ok) throw new Error('Login failed');

    const data = await response.json();
    this.token = data.access_token;
  }

  async getSupplyChainConfigs() {
    const response = await fetch(`${this.baseUrl}/supply-chain-configs`, {
      headers: { 'Authorization': `Bearer ${this.token}` }
    });

    if (!response.ok) throw new Error('Failed to fetch configs');
    return (await response.json()).items;
  }

  async generateSupplyPlan(configId, horizon = 52) {
    const response = await fetch(`${this.baseUrl}/supply-plan/generate`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        config_id: configId,
        planning_horizon: horizon,
        start_date: '2026-01-22'
      })
    });

    if (!response.ok) throw new Error('Failed to generate plan');
    return (await response.json()).task_id;
  }

  async waitForSupplyPlan(taskId) {
    while (true) {
      const response = await fetch(
        `${this.baseUrl}/supply-plan/status/${taskId}`,
        { headers: { 'Authorization': `Bearer ${this.token}` } }
      );

      const status = await response.json();
      if (status.status === 'COMPLETED') {
        return this.getSupplyPlanResult(taskId);
      } else if (status.status === 'FAILED') {
        throw new Error('Supply plan generation failed');
      }

      await new Promise(resolve => setTimeout(resolve, 5000));
    }
  }

  async getSupplyPlanResult(taskId) {
    const response = await fetch(
      `${this.baseUrl}/supply-plan/result/${taskId}`,
      { headers: { 'Authorization': `Bearer ${this.token}` } }
    );

    if (!response.ok) throw new Error('Failed to get result');
    return response.json();
  }
}

// Usage
const client = new AutonomyClient('http://localhost:8088/api/v1');

async function main() {
  await client.login('user@company.com', 'SecurePassword123!');

  const configs = await client.getSupplyChainConfigs();
  console.log(`Found ${configs.length} configs`);

  const taskId = await client.generateSupplyPlan(1, 52);
  console.log(`Supply plan task ID: ${taskId}`);

  const result = await client.waitForSupplyPlan(taskId);
  console.log(`Total cost: $${result.financial.total_cost.E.toLocaleString()}`);
  console.log(`Service level: ${(result.customer.service_level.E * 100).toFixed(1)}%`);
}

main().catch(console.error);
```

---

## Claude Skills — TRM Exception Handler

**Last Updated**: 2026-03-01

> **Note**: PicoClaw and OpenClaw external agent runtimes were removed in Feb 2026 and replaced by the Claude Skills ecosystem. See [docs/CLAUDE_SKILLS_STRATEGY.md](docs/CLAUDE_SKILLS_STRATEGY.md) for migration rationale.

The platform uses a **hybrid TRM + Claude Skills** architecture. TRMs (7M-parameter neural networks) handle ~95% of execution decisions at <10ms latency. Claude Skills serve as the **exception handler** for the ~5% of novel situations where conformal prediction indicates low TRM confidence.

### Architecture

```
Deterministic Engine (always runs first)
    ↓
TRM Exception Head (fast, <10ms, learned adjustments)
    ↓
Conformal Prediction Router:
    ├── High confidence (tight intervals) → Accept TRM result ✓
    └── Low confidence (wide intervals) → Escalate to Claude Skills
        ↓
    Claude Skills Exception Handler
        ├── RAG Decision Memory (find similar past decisions)
        ├── Claude API (Haiku for calculation, Sonnet for judgment)
        └── Proposal validated against engine constraints
    ↓
Skills decisions recorded for TRM meta-learning (shift 95/5 boundary)
```

### 11 Skills by Routing Tier

| Tier | Skills | Cost/Call | Notes |
|------|--------|-----------|-------|
| Deterministic | `atp_executor`, `order_tracking` | $0 | No LLM needed |
| Haiku | `po_creation`, `inventory_rebalancing`, `inventory_buffer`, `to_execution` | ~$0.0018 | Calculation-heavy |
| Sonnet | `mo_execution`, `quality_disposition`, `maintenance_scheduling`, `subcontracting`, `forecast_adjustment` | ~$0.0054 | Requires judgment |

### Conformal Prediction Routing

The TRM → Skills boundary is governed by conformal prediction:
- `skill_escalation_threshold` (default: 0.6): TRM confidence below this triggers escalation
- CDT `risk_bound` > (1 - threshold): High uncertainty triggers escalation
- Conformal `interval_width` > 0.5: Wide prediction intervals trigger escalation

### RAG Decision Memory (Cost Reduction Flywheel)

| Scenario | Action | Cost |
|----------|--------|------|
| Cache hit (similarity > 0.95) | Skip LLM entirely | $0 |
| Few-shot hit (similarity > 0.70) | Inject as context, Haiku model | ~$0.0012 |
| Novel situation | Full skill prompt to Sonnet | ~$0.0054 |

Expected cost: ~$130/mo initially → ~$34/mo as decision corpus grows.

### Key Files

- `backend/app/services/skills/base_skill.py` — `SkillDefinition`, `SkillResult`, registry
- `backend/app/services/skills/claude_client.py` — Claude API client with vLLM/Qwen fallback
- `backend/app/services/skills/skill_orchestrator.py` — Exception handler and meta-learner
- `backend/app/services/skills/*/SKILL.md` — 11 heuristic rule files (one per TRM type)
- `backend/app/models/decision_embeddings.py` — pgvector 768-dim embeddings for RAG decision memory
- `backend/app/services/decision_memory_service.py` — Embed/retrieve past decisions for few-shot context

### Ask Why API Endpoints (Context-Aware Explainability)

All TRM and GNN agent decisions support context-aware explanations via the planning cascade API:

**TRM Decision Explanation**:
```
GET /api/v1/planning-cascade/trm-decision/{decision_id}/ask-why?level=NORMAL
```
Returns `ContextAwareExplanation` JSON:
```json
{
  "summary": "Reorder point breach: Order 500 units from Supplier-A (confidence 87%, UNILATERAL).",
  "explanation": "Full text at requested verbosity...",
  "confidence": 0.87,
  "authority": {
    "agent_type": "trm_po", "authority_level": "OPERATOR",
    "decision_classification": "UNILATERAL",
    "authority_statement": "Standard PO within $10K threshold — unilateral authority."
  },
  "guardrails": [
    {"name": "demand_deviation", "threshold": 0.15, "actual": 0.08, "status": "WITHIN", "margin": 0.47}
  ],
  "attribution": {
    "method": "gradient_saliency",
    "features": {"inventory_dos": 0.42, "demand_forecast": 0.28, "pipeline_qty": 0.15}
  },
  "prediction_interval": {"lower": 380, "estimate": 500, "upper": 620, "coverage": 0.9},
  "counterfactuals": ["If inventory were 15% lower, PO would trigger at CRITICAL urgency."]
}
```

**GNN Node Explanation**:
```
GET /api/v1/planning-cascade/gnn-analysis/{config_id}/node/{node_id}/ask-why?model_type=sop&level=NORMAL
```

**ExplainabilityLevel Query Parameter**: `VERBOSE` | `NORMAL` | `SUCCINCT`

### Further Reading

- [CLAUDE_SKILLS_STRATEGY.md](docs/CLAUDE_SKILLS_STRATEGY.md) - Strategy for replacing PicoClaw/OpenClaw with Claude Skills
- [AGENTIC_AUTHORIZATION_PROTOCOL.md](docs/AGENTIC_AUTHORIZATION_PROTOCOL.md) - Authorization protocol specification
- [POWELL_APPROACH.md](POWELL_APPROACH.md) - Powell framework (computation layer)

---

## Azirella — Directive API

Natural language directive capture via the TopNavbar prompt bar.

### Endpoints

```bash
POST /api/v1/directives/analyze    # Parse + gap detect (no persist)
POST /api/v1/directives/submit     # Persist + route (with clarifications)
GET  /api/v1/directives/           # List recent directives for tenant
GET  /api/v1/directives/{id}       # Get single directive by ID
```

### Analyze Request

```json
POST /api/v1/directives/analyze
{
  "text": "I want to increase revenue by 10% in the SW region next quarter because customer feedback indicates growing demand",
  "config_id": 22
}
```

### Submit Request (with clarifications)

```json
POST /api/v1/directives/submit
{
  "text": "I want to increase revenue by 10% in the SW region next quarter because customer feedback indicates growing demand",
  "config_id": 22,
  "clarifications": {
    "products": "Beverages, Dry Goods"
  }
}
```

See [TALK_TO_ME.md](TALK_TO_ME.md) for full documentation.

---

## Email Signal Intelligence — API

GDPR-safe email ingestion for supply chain signal extraction.

### Connection Management

```bash
POST   /api/v1/email-signals/connections                # Create IMAP/Gmail connection
GET    /api/v1/email-signals/connections                # List connections
PUT    /api/v1/email-signals/connections/{id}           # Update connection
DELETE /api/v1/email-signals/connections/{id}           # Delete connection
POST   /api/v1/email-signals/connections/{id}/test      # Test connectivity
POST   /api/v1/email-signals/connections/{id}/poll      # Manual poll
```

### Signal Management

```bash
GET  /api/v1/email-signals/signals                     # List (filterable by config_id, status, signal_type, partner_type)
GET  /api/v1/email-signals/signals/{id}                # Detail
POST /api/v1/email-signals/signals/{id}/dismiss        # Dismiss with reason
POST /api/v1/email-signals/signals/{id}/reclassify     # Re-run LLM classification
```

### Dashboard & Testing

```bash
GET  /api/v1/email-signals/dashboard                   # Summary stats
POST /api/v1/email-signals/ingest-manual               # Manual email paste for testing
```

### Manual Ingestion Example

```json
POST /api/v1/email-signals/ingest-manual
{
  "config_id": 22,
  "from_header": "Sarah Johnson <sarah@acme-supplies.com>",
  "subject": "Lead Time Extension Notice",
  "body": "Due to raw material constraints, lead times for Widget-A and Widget-B will be extended by 3 weeks starting March 15."
}
```

The from_header is used only for domain extraction (acme-supplies.com → ACME Supplies trading partner). Personal identity is stripped before storage.

See [EMAIL_SIGNAL_INTELLIGENCE.md](EMAIL_SIGNAL_INTELLIGENCE.md) for full documentation.

---

## Self-Hosted LLM Configuration

**Last Updated**: 2026-02-19

For data sovereignty and cost control, Autonomy supports self-hosted LLM inference as an alternative to Claude API or OpenAI API calls. This is particularly relevant for air-gapped customers where business data (orders, inventory levels, pricing) cannot be sent to external providers.

### Recommended Model: Qwen 3 8B

**Why Qwen 3**: Autonomy agents need tool calling (REST API calls), structured JSON output (order quantities, dates, priorities), and reasoning (authorization protocol, what-if evaluation). Qwen 3 leads on all three among self-hostable models.

| Requirement | Qwen 3 8B | DeepSeek V3.2 | Llama 4 Maverick |
|---|---|---|---|
| **Tool calling accuracy** | **96.5%** | 81.5% | Good but not accuracy-first |
| **Structured JSON** | Native via Qwen-Agent | Requires prompt engineering | Supported but less reliable |
| **Reasoning** | Hybrid thinking/non-thinking in one pass | **Best** but needs multi-GPU | Adequate |
| **VRAM required** | **~8GB** | 200GB+ (4-8x A100) | 100GB+ |
| **OpenAI API compat** | Yes via vLLM | Yes via vLLM | Yes via vLLM |

Qwen 3's architecture produces tool calls and chain-of-thought reasoning in a single inference pass with the reasoning block segregated — agents can reason about an authorization request while formatting the API call.

### Sizing Guide

With the tiered intelligence model (deterministic heartbeats, ConditionMonitor for agent-to-agent), LLM handles only human interaction — keeping call volumes low even at enterprise scale.

| Scale | Sites | SKUs | LLM Calls/Day | Model | VRAM | Hardware |
|---|---|---|---|---|---|---|
| **Pilot** | 4-8 | 100-500 | 200-800 | Qwen 3 8B | 8GB | RTX 3070/4060 (shared) |
| **Department** | 20-50 | 5K-20K | 800-3,000 | Qwen 3 8B | 8GB | RTX 3070/4060 (shared) |
| **Division** | 50-100 | 50K-100K | 1,500-5,000 | Qwen 3 14B | 16GB | RTX 4080/A5000 (dedicated) |
| **Enterprise** | 200+ | 300K+ | 2,000-7,000 | Qwen 3 14B | 16GB | RTX 4080/A5000 (dedicated) |
| **Enterprise + disruption** | 200+ | 300K+ | 5,000-20,000 | Qwen 3 32B or 2x 14B | 24GB | RTX 4090/A6000 |

**Key insight**: Even at 223 sites and 300K SKUs, the tiered model keeps LLM calls under 7K/day normal — well within a single dedicated GPU. The tiered architecture is what makes this tractable, not bigger hardware.

**Upgrade Path**: Start with 8B → validate tool calling → upgrade to 14B/32B for production chat. If hardware allows (4x A100), DeepSeek V3.2 becomes the strongest option for complex reasoning.

### Recommended Serving: vLLM

**Why vLLM over Ollama**: Autonomy runs a multi-agent system, not a single chatbot.

- **Concurrent serving**: Multiple Claude Skills escalations + scheduled jobs hitting the same endpoint
- **Constrained JSON generation**: Define Pydantic schemas → vLLM guarantees valid JSON matching `ATPResponse`, `PORecommendation`, `AuthorizationRequest` schemas
- **OpenAI-compatible API**: Claude Skills fallback client and LLM agents expect `/v1/chat/completions` — vLLM provides this natively
- **GPU memory efficiency**: PagedAttention reduces VRAM waste under concurrent load

### Docker Compose Deployment

Add a `docker-compose.llm.yml` overlay (layered like `docker-compose.gpu.yml`):

```yaml
services:
  llm:
    image: vllm/vllm-openai:latest
    container_name: autonomy-llm
    runtime: nvidia
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      - NVIDIA_VISIBLE_DEVICES=0
    command: >
      --model Qwen/Qwen3-8B
      --served-model-name qwen3-8b
      --max-model-len 8192
      --enable-auto-tool-choice
      --tool-call-parser hermes
      --gpu-memory-utilization 0.85
    ports:
      - "8100:8000"
    networks:
      - autonomy-network
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
```

**Environment Variables** (`.env`):
```bash
# Replace external OpenAI with local vLLM
AUTONOMY_LLM_MODEL=qwen3-8b
AUTONOMY_LLM_BASE_URL=http://llm:8000/v1
AUTONOMY_LLM_API_KEY=not-needed
```

**Usage**:
```bash
# Start with self-hosted LLM
docker compose -f docker-compose.yml -f docker-compose.llm.yml up

# Or with GPU backend + LLM
docker compose -f docker-compose.gpu.yml -f docker-compose.llm.yml up
```

### GPU Sharing Strategy

TRM inference uses <10ms bursts; vLLM serving is longer but intermittent. They can share a GPU:

- **Single GPU**: vLLM at `--gpu-memory-utilization 0.60` (60%), TRM/GNN gets remaining 40%
- **Dual GPU**: GPU 0 → vLLM (dedicated), GPU 1 → TRM/GNN training + inference

### References

- [Qwen 3 Tool Calling Documentation](https://qwen.readthedocs.io/en/latest/framework/function_call.html)
- [Qwen-Agent Framework](https://github.com/QwenLM/Qwen-Agent)
- [vLLM Structured Outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/)
- [vLLM Docker Deployment](https://docs.vllm.ai/en/stable/cli/serve/)

---

## Physical Two-Machine Deployment

**Last Updated**: 2026-02-25

For development and small-scale production, Autonomy can run across two physical machines — separating LLM inference from ML training/inference. This eliminates GPU contention between the memory-hungry LLM and the latency-sensitive TRM agents.

### Architecture

```
┌───────────────────────────────┐       LAN / Tailscale       ┌───────────────────────────────┐
│  Machine A — Language         │◄────────────────────────────►│  Machine B — Neural           │
│  (Mac Mini M4 Pro, 24GB)      │                              │  (Linux, RTX 4060 8GB)        │
│                               │                              │                               │
│  Ollama :11434                │                              │  FastAPI Backend :8000         │
│   ├─ Qwen 3 8B (Q8, ~8.5GB)  │                              │  PostgreSQL :5432              │
│   └─ nomic-embed-text (~0.8GB)│                              │  pgAdmin :5050                 │
│                               │                              │                               │
│  Claude Skills client          │                              │  PyTorch / CUDA                │
│                               │                              │   ├─ 11 TRM agents (<10ms)     │
│  Frontend :3000               │                              │   ├─ Execution tGNN (daily)    │
│  Nginx proxy :8088            │                              │   └─ S&OP GraphSAGE (weekly)   │
│                               │                              │                               │
│  Serves: chat, NL interaction,│                              │  TRM Decision API :8001        │
│  signal ingestion, alerts     │                              │                               │
└───────────────────────────────┘                              └───────────────────────────────┘
```

### Why this split works

| Concern | Benefit |
|---|---|
| **No GPU contention** | LLM generation (variable KV cache) can't starve TRMs of their <10ms latency budget |
| **Right-sized hardware** | Machine A needs VRAM for LLM weights; Machine B needs CUDA for PyTorch training |
| **Powell layer alignment** | Machine A = orchestration/NL (AAP Layer 3-4); Machine B = execution/decisions (Layer 1-2) |
| **Independent scaling** | More users → upgrade Machine A; more sites/products → upgrade Machine B |
| **Unified memory advantage** | Apple Silicon's unified memory makes the full 24GB available to models (unlike discrete GPUs) |

### Hardware recommendations

#### Machine A — Language (Mac Mini)

| Model | Memory | LLM Capacity | Verdict |
|---|---|---|---|
| M4 16GB | 16GB unified | Qwen 3 8B Q4 + embeddings | Functional but tight |
| **M4 Pro 24GB** | **24GB unified** | **Qwen 3 8B Q8 + embeddings + headroom** | **Recommended** |
| M4 Pro 48GB | 48GB unified | Qwen 3 14B+ or multiple models | Future-proof |

Ollama has first-class Apple Silicon / Metal support. The M4 Pro 24GB runs Qwen 3 8B at Q8 quantization (~8.5GB) plus nomic-embed-text (~0.8GB) with ample headroom for Claude Skills fallback inference.

#### Machine B — Neural (existing Linux box)

- **GPU**: NVIDIA RTX 4060 (8GB VRAM) — freed entirely for ML workloads
- **TRM inference**: All 11 TRMs total ~308MB of weights (11 × 7M params × 4 bytes)
- **Training**: Full CUDA availability for TRM curriculum, GNN training, behavioral cloning
- **Note**: With no LLM competing for VRAM, the RTX 4060 has ample capacity for all ML workloads

### Networking

#### Option 1: Tailscale (recommended)

Tailscale provides encrypted WireGuard tunnels with stable hostnames. Free for personal use. Works across networks — the Mac Mini can sit anywhere.

```bash
# Install on both machines
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Machines become reachable as:
#   mac-mini (100.x.x.x)
#   linux-box (100.x.x.x)
```

#### Option 2: LAN static IPs

If both machines are on the same network, assign static IPs and reference them directly. Simpler but less portable.

### Docker Compose configuration

#### Machine B — Neural (Linux box)

Use the existing `docker-compose.yml` with the LLM endpoint pointed at Machine A:

```bash
# .env on Machine B
LLM_API_BASE=http://mac-mini:11434/v1    # Tailscale hostname
LLM_API_KEY=not-needed
LLM_MODEL_NAME=qwen3-8b
EMBEDDING_API_BASE=http://mac-mini:11434/v1
```

No `docker-compose.llm.yml` overlay needed — the LLM runs on Machine A.

#### Machine A — Language (Mac Mini)

Create `docker-compose.language.yml`:

```yaml
version: "3.8"

services:
  ollama:
    image: ollama/ollama
    container_name: autonomy-ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:11434/api/tags || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3

  openclaw:
    image: openclaw/openclaw:latest
    container_name: autonomy-openclaw
    ports:
      - "3001:3001"
    environment:
      - AUTONOMY_API_BASE=http://linux-box:8000/api   # Tailscale hostname
      - LLM_PROVIDER_URL=http://ollama:11434/v1
      - LLM_MODEL=qwen3-8b
    volumes:
      - ./deploy/openclaw/workspace:/workspace:ro
    depends_on:
      ollama:
        condition: service_healthy
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
    container_name: autonomy-frontend
    ports:
      - "3000:3000"
    restart: unless-stopped

  proxy:
    image: nginx:alpine
    container_name: autonomy-proxy
    ports:
      - "8088:80"
    volumes:
      - ./proxy/nginx.conf:/etc/nginx/conf.d/default.conf:ro
    restart: unless-stopped

volumes:
  ollama_data:
```

**Nginx config** — The proxy on Machine A forwards `/api/*` to Machine B:

```nginx
# proxy/nginx.language.conf
upstream backend {
    server linux-box:8000;  # Tailscale hostname for Machine B
}

server {
    listen 80;

    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        proxy_pass http://frontend:3000;
        proxy_set_header Host $host;
    }

    location /ws/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Model setup on Machine A

```bash
# One-time: pull models
ollama pull qwen3:8b
ollama pull nomic-embed-text

# Verify
ollama list
```

### Makefile targets

Add to the project `Makefile` for cross-machine orchestration:

```makefile
# --- Physical Two-Machine Deployment ---
MACHINE_A_HOST ?= mac-mini          # Tailscale hostname or IP
MACHINE_A_PATH ?= ~/autonomy       # Project path on Machine A

deploy-language:
	ssh $(MACHINE_A_HOST) "cd $(MACHINE_A_PATH) && docker compose -f docker-compose.language.yml up -d"

deploy-neural:
	docker compose up -d

deploy-all: deploy-neural deploy-language

stop-language:
	ssh $(MACHINE_A_HOST) "cd $(MACHINE_A_PATH) && docker compose -f docker-compose.language.yml down"

stop-all: stop-language
	docker compose down

status-all:
	@echo "=== Machine B — Neural (local) ==="
	@docker compose ps
	@echo ""
	@echo "=== Machine A — Language ($(MACHINE_A_HOST)) ==="
	@ssh $(MACHINE_A_HOST) "cd $(MACHINE_A_PATH) && docker compose -f docker-compose.language.yml ps"

logs-language:
	ssh $(MACHINE_A_HOST) "cd $(MACHINE_A_PATH) && docker compose -f docker-compose.language.yml logs -f"

logs-ollama:
	ssh $(MACHINE_A_HOST) "cd $(MACHINE_A_PATH) && docker compose -f docker-compose.language.yml logs -f ollama"
```

### Component placement summary

| Component | Machine A (Language) | Machine B (Neural) | Communication |
|---|---|---|---|
| PostgreSQL | | X | Direct (local) |
| FastAPI backend | | X | LLM calls → Machine A |
| Frontend + Nginx | X | | Proxies `/api/*` → Machine B |
| Ollama (LLM + embeddings) | X | | `:11434` over Tailscale |
| Claude Skills client | X | | Calls Claude API or Machine A Ollama |
| TRM inference (11 agents) | | X | Local, <10ms |
| tGNN / GraphSAGE | | X | Local |
| TRM/GNN training | | X | CUDA, local |
| pgAdmin | | X | Browser access |

### Key design constraint

**All cross-machine communication goes through the REST API** — the frontend on Machine A proxies `/api/*` to Machine B, and LLM inference calls go from Machine B to Machine A's Ollama endpoint. No direct database connections across machines. This is already how the architecture works; the two-machine split doesn't change any application code.

### Day-to-day workflow

```bash
# Start everything
make deploy-all

# Check both machines
make status-all

# Develop backend/ML on Machine B (local)
cd backend && uvicorn main:app --reload

# Mac Mini runs headless — SSH when needed
ssh mac-mini

# Retrain TRMs on Machine B (full GPU available)
make train-gnn

# Tail LLM logs from Machine B
make logs-ollama

# Stop everything
make stop-all
```

### Migration path to production

This two-machine physical setup maps directly to cloud deployment:

| Physical | Cloud equivalent |
|---|---|
| Mac Mini (Language) | `g5.xlarge` (A10G 24GB) or CPU instance + managed LLM endpoint |
| Linux box (Neural) | `g4dn.xlarge` (T4 16GB) for training+inference |
| Tailscale | VPC peering or private subnet |
| `docker-compose.language.yml` | ECS task definition or EC2 user data |

The same Docker Compose files, environment variables, and Makefile targets work in both environments — only hostnames and hardware change.

---

## Further Reading

- [API_REFERENCE.md](API_REFERENCE.md) - Complete API documentation (coming soon)
- [PLANNING_CAPABILITIES.md](PLANNING_CAPABILITIES.md) - Planning endpoints
- [EXECUTION_CAPABILITIES.md](EXECUTION_CAPABILITIES.md) - Execution endpoints
- [BEER_GAME_GUIDE.md](BEER_GAME_GUIDE.md) - Game API usage
- [CLAUDE_SKILLS_STRATEGY.md](docs/CLAUDE_SKILLS_STRATEGY.md) - Claude Skills strategy and migration from PicoClaw/OpenClaw
- [AI_AGENTS.md](AI_AGENTS.md) - AI agent types and self-hosted LLM provider options

---

## Support

**Issues**: GitHub Issues
**Email**: support@autonomy.ai
**Documentation**: https://docs.autonomy.ai
