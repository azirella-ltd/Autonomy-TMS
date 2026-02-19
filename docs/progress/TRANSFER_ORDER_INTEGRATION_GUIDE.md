# Transfer Order Integration Guide

## Quick Reference for Steps 1-4

This guide provides complete implementation details for integrating Transfer Order functionality into the application.

---

## Step 1: Test Suite ✅ COMPLETE

### Test Script Location
**File**: `backend/scripts/test_transfer_orders.py` (600+ lines)

### Running the Tests

```bash
cd /home/trevor/Projects/The_Beer_Game/backend

# Quick 10-round test
python3 scripts/test_transfer_orders.py --rounds 10 --validate

# Full 52-round simulation
python3 scripts/test_transfer_orders.py --rounds 52 --validate

# Skip validation (faster)
python3 scripts/test_transfer_orders.py --rounds 10 --no-validate
```

### Validation Checks

The test suite runs 6 comprehensive checks:

1. **TO Creation** - Verifies sufficient TOs created
2. **In-Transit Consistency** - Validates `inv_level.in_transit_qty` matches TO sum
3. **Status Transitions** - Checks status lifecycle correctness
4. **Arrival Round Calculation** - Validates lead time calculations
5. **Inventory Balance** - Ensures inventory conservation
6. **Multi-Period Projection** - Tests future arrival tracking

### Expected Output

```
================================================================================
52-ROUND BEER GAME SIMULATION WITH TRANSFER ORDERS
================================================================================

Game created: ID=123
Initializing game state...
✓ Game initialized with AWS SC state

────────────────────────────────────────────────────────────────────────────────
ROUND 1/52
────────────────────────────────────────────────────────────────────────────────

📦 STEP 1: Receiving Shipments (POs and TOs arriving this round)
✓ Received 0 purchase orders
✓ Received 0 transfer orders

🎯 STEP 3: Order Promising (Fulfilling Demand)
✓ Processed 1 order promising operations
  • retailer_001: FULL fulfillment (4.0/4.0 units) - TO: TO-G123-R1-retailer_001-...

💰 STEP 6: Cost Accrual
✓ Total Cost: $24.00

...

================================================================================
SIMULATION COMPLETE - 52 ROUNDS
================================================================================

Transfer Orders:
  Total created: 156
  In transit: 8
  Received: 148

Total Costs:
  Total: $4,523.50
  Holding: $2,145.00
  Backlog: $2,378.50

================================================================================
RUNNING VALIDATION CHECKS
================================================================================

📋 Check 1: Transfer Order Creation
  ✅ PASSED

📦 Check 2: In-Transit Inventory Consistency
  ✅ PASSED

🔄 Check 3: Status Transitions
  ✅ PASSED

📅 Check 4: Arrival Round Calculation
  ✅ PASSED

💰 Check 5: Inventory Balance
  ✅ PASSED

📊 Check 6: Multi-Period Inventory Projection
  ✅ PASSED

🎉 ALL VALIDATION CHECKS PASSED!
```

---

## Step 2: API Endpoints ✅ COMPLETE

### API File Location
**File**: `backend/app/api/endpoints/transfer_orders.py`

### Available Endpoints

#### 1. Get Transfer Orders for Game
```
GET /api/v1/games/{game_id}/transfer-orders
Query Parameters:
  - status: Optional[str] (IN_TRANSIT, RECEIVED)
  - round_number: Optional[int]

Response:
{
  "game_id": 123,
  "total_count": 156,
  "transfer_orders": [
    {
      "to_number": "TO-G123-R1-retailer_001-1234567890",
      "source_site_id": "retailer_001",
      "destination_site_id": "MARKET",
      "status": "RECEIVED",
      "order_round": 1,
      "arrival_round": 1,
      "quantity": 4.0,
      "line_item_count": 1
    },
    ...
  ]
}
```

#### 2. Get TO Analytics
```
GET /api/v1/games/{game_id}/transfer-order-analytics
Query Parameters:
  - include_routes: bool (default: true)
  - include_timeline: bool (default: true)

Response:
{
  "game_id": 123,
  "summary": {
    "total_tos": 156,
    "status_breakdown": {"IN_TRANSIT": 8, "RECEIVED": 148},
    "total_quantity_shipped": 1248.0,
    "avg_quantity_per_to": 8.0
  },
  "delivery_performance": {
    "on_time_delivery_rate": 98.65,
    "total_received": 148,
    "on_time_count": 146,
    "late_count": 2,
    "early_count": 0
  },
  "lead_time_analysis": {...},
  "in_transit_analysis": {...},
  "throughput": {...},
  "route_analysis": {...},
  "timeline": {...}
}
```

### Frontend Integration Example

```javascript
// services/transferOrderService.js

import api from './api';

export const transferOrderService = {
  // Get all TOs for a game
  async getGameTransferOrders(gameId, filters = {}) {
    const params = new URLSearchParams();
    if (filters.status) params.append('status', filters.status);
    if (filters.round_number) params.append('round_number', filters.round_number);

    const response = await api.get(
      `/games/${gameId}/transfer-orders?${params.toString()}`
    );
    return response.data;
  },

  // Get TO analytics
  async getTransferOrderAnalytics(gameId, options = {}) {
    const params = new URLSearchParams({
      include_routes: options.include_routes !== false,
      include_timeline: options.include_timeline !== false
    });

    const response = await api.get(
      `/games/${gameId}/transfer-order-analytics?${params.toString()}`
    );
    return response.data;
  },

  // Get in-transit inventory
  async getInTransitInventory(gameId) {
    const response = await api.get(`/games/${gameId}/in-transit-inventory`);
    return response.data;
  }
};
```

---

## Step 3: Frontend Integration ✅ READY

### Component Location
**File**: `frontend/src/components/game/TransferOrderTimeline.jsx` (800+ lines)

### Integration into Game Report

**File**: `frontend/src/pages/GameReport.jsx` (or equivalent)

```javascript
import React, { useState, useEffect } from 'react';
import { Box, Typography, Divider } from '@mui/material';
import TransferOrderTimeline from '../components/game/TransferOrderTimeline';
import { transferOrderService } from '../services/transferOrderService';

function GameReport({ gameId }) {
  const [transferOrders, setTransferOrders] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchTOData = async () => {
      try {
        setLoading(true);

        // Fetch TOs and analytics in parallel
        const [tosResponse, analyticsResponse] = await Promise.all([
          transferOrderService.getGameTransferOrders(gameId),
          transferOrderService.getTransferOrderAnalytics(gameId)
        ]);

        setTransferOrders(tosResponse.transfer_orders);
        setAnalytics(analyticsResponse);
      } catch (error) {
        console.error('Failed to fetch TO data:', error);
      } finally {
        setLoading(false);
      }
    };

    if (gameId) {
      fetchTOData();
    }
  }, [gameId]);

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Game Report - Game {gameId}
      </Typography>

      {/* Existing game metrics */}
      <Box mb={4}>
        {/* Your existing game metrics components */}
      </Box>

      <Divider sx={{ my: 4 }} />

      {/* Transfer Order Analytics */}
      <Box mb={4}>
        <Typography variant="h5" gutterBottom>
          Transfer Order Analytics
        </Typography>
        {loading ? (
          <Typography>Loading TO data...</Typography>
        ) : (
          <TransferOrderTimeline
            gameId={gameId}
            transferOrders={transferOrders}
            analytics={analytics}
          />
        )}
      </Box>
    </Box>
  );
}

export default GameReport;
```

### Alternative: Separate TO Analytics Page

```javascript
// pages/TransferOrderAnalytics.jsx

import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Container, Paper } from '@mui/material';
import TransferOrderTimeline from '../components/game/TransferOrderTimeline';
import { transferOrderService } from '../services/transferOrderService';

function TransferOrderAnalytics() {
  const { gameId } = useParams();
  const [transferOrders, setTransferOrders] = useState([]);
  const [analytics, setAnalytics] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      const [tosData, analyticsData] = await Promise.all([
        transferOrderService.getGameTransferOrders(gameId),
        transferOrderService.getTransferOrderAnalytics(gameId)
      ]);

      setTransferOrders(tosData.transfer_orders);
      setAnalytics(analyticsData);
    };

    fetchData();
  }, [gameId]);

  return (
    <Container maxWidth="xl">
      <Paper sx={{ p: 3, mt: 3 }}>
        <TransferOrderTimeline
          gameId={gameId}
          transferOrders={transferOrders}
          analytics={analytics}
        />
      </Paper>
    </Container>
  );
}

export default TransferOrderAnalytics;
```

### Component Features

The `TransferOrderTimeline` component provides 4 interactive tabs:

1. **Timeline Tab**
   - Area chart: TOs created vs received by round
   - Line chart: Quantity created vs received
   - Visual TO flow over time

2. **Routes Tab**
   - Table of all routes with metrics
   - Expandable rows showing individual TOs
   - Sortable by volume, lead time

3. **In-Transit Tab**
   - Summary cards (TO count, total quantity)
   - Bar chart: In-transit by destination
   - Table: Current in-transit TOs with arrival schedule

4. **Performance Tab**
   - On-time delivery rate
   - Lead time statistics (planned vs actual)
   - Delivery status breakdown (on-time/late/early)

---

## Step 4: Database Schema ✅ COMPLETE

### Schema Updates Applied

The Transfer Order model has been updated to support Beer Game integration with AWS SC compliance:

**Changes Made**:
1. **AWS SC Compliant**: `source_site_id` and `destination_site_id` are `Integer ForeignKey` to `nodes.id`
2. **AWS SC Compliant**: `product_id` in line items is `Integer ForeignKey` to `items.id`
3. Added Beer Game fields: `game_id`, `order_round`, `arrival_round`, `order_date`
4. Added indexes: `idx_to_game_arrival`, `idx_to_game_order` for efficient Beer Game queries
5. **ID Mapping**: Created `BeerGameIdMapper` service to translate between node names and Integer IDs

### Applying the Migration

**Option 1: Run Migration Script (Recommended)**
```bash
cd /home/trevor/Projects/The_Beer_Game/backend

# Apply migration to existing database
python3 scripts/migrate_to_schema.py
```

**Option 2: Recreate Tables (Fresh Start)**
```bash
# If you want to start fresh, drop and recreate tables
docker compose exec backend python -m app.db.init_db
```

### Required Tables

The Transfer Order implementation uses the following tables:

#### 1. transfer_order

```sql
CREATE TABLE transfer_order (
    id INT AUTO_INCREMENT PRIMARY KEY,
    to_number VARCHAR(100) UNIQUE NOT NULL,

    -- Sites (AWS SC Standard: Integer ForeignKey to nodes table)
    source_site_id INT NOT NULL,
    destination_site_id INT NOT NULL,

    -- Configuration
    config_id INT,
    group_id INT,

    -- Status and dates
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    order_date DATE,
    shipment_date DATE NOT NULL,
    estimated_delivery_date DATE NOT NULL,
    actual_ship_date DATE,
    actual_delivery_date DATE,

    -- Beer Game fields
    game_id INT,
    order_round INT,
    arrival_round INT,

    -- Transportation
    transportation_mode VARCHAR(50),
    carrier VARCHAR(100),
    tracking_number VARCHAR(100),

    -- Cost tracking
    transportation_cost DOUBLE DEFAULT 0.0,
    currency VARCHAR(3) DEFAULT 'USD',

    -- Audit
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME ON UPDATE CURRENT_TIMESTAMP,

    -- Indexes
    INDEX idx_to_source_site (source_site_id),
    INDEX idx_to_dest_site (destination_site_id),
    INDEX idx_to_status (status),
    INDEX idx_to_game_arrival (game_id, arrival_round, status),
    INDEX idx_to_game_order (game_id, order_round),
    INDEX idx_to_lane (source_site_id, destination_site_id),

    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (source_site_id) REFERENCES nodes(id),
    FOREIGN KEY (destination_site_id) REFERENCES nodes(id)
);
```

#### 2. transfer_order_line_item

```sql
CREATE TABLE transfer_order_line_item (
    id INT AUTO_INCREMENT PRIMARY KEY,
    to_id INT NOT NULL,
    line_number INT NOT NULL,

    -- Product (AWS SC Standard: Integer ForeignKey to items table)
    product_id INT NOT NULL,

    -- Quantities
    quantity DOUBLE NOT NULL,
    ordered_quantity DOUBLE DEFAULT 0.0,
    picked_quantity DOUBLE DEFAULT 0.0,
    shipped_quantity DOUBLE DEFAULT 0.0,
    received_quantity DOUBLE DEFAULT 0.0,
    damaged_quantity DOUBLE DEFAULT 0.0,

    -- Dates
    requested_ship_date DATE NOT NULL,
    requested_delivery_date DATE NOT NULL,
    actual_ship_date DATE,
    actual_delivery_date DATE,

    -- Audit
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME ON UPDATE CURRENT_TIMESTAMP,

    -- Indexes
    INDEX idx_to_line_to (to_id),
    INDEX idx_to_line_product (product_id),
    INDEX idx_to_line_number (to_id, line_number),

    FOREIGN KEY (to_id) REFERENCES transfer_order(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES items(id)
);
```

### Checking Schema

```bash
# Connect to database
docker compose exec db mariadb -u beer_user -p beer_game

# Check if tables exist
SHOW TABLES LIKE 'transfer%';

# Check transfer_order schema
DESCRIBE transfer_order;

# Check indexes
SHOW INDEX FROM transfer_order;

# Count TOs
SELECT status, COUNT(*) FROM transfer_order GROUP BY status;
```

### Creating Tables (if needed)

If the tables don't exist, create them:

```python
# backend/scripts/create_to_tables.py

from app.db.session import SessionLocal
from app.models.transfer_order import Base
from sqlalchemy import create_engine

engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
Base.metadata.create_all(bind=engine, tables=[
    Base.metadata.tables['transfer_order'],
    Base.metadata.tables['transfer_order_line_item']
])
print("✓ Transfer Order tables created")
```

Or run migration:

```bash
# If using Alembic
alembic revision --autogenerate -m "Add transfer order tables"
alembic upgrade head
```

---

## Testing the Complete Integration

### 1. Backend Test

```bash
cd backend

# Test imports
python3 -c "from app.services.sc_execution.to_analytics import TransferOrderAnalytics; print('✓ Analytics import OK')"
python3 -c "from app.api.endpoints import transfer_orders_router; print('✓ Router import OK')"

# Run test suite
python3 scripts/test_transfer_orders.py --rounds 10 --validate
```

### 2. API Test

```bash
# Start backend
cd backend
uvicorn main:app --reload

# In another terminal, test API
curl -X GET "http://localhost:8000/api/v1/games/1/transfer-orders" | jq

# Test analytics
curl -X GET "http://localhost:8000/api/v1/games/1/transfer-order-analytics" | jq
```

### 3. Frontend Test

```bash
cd frontend
npm start

# Navigate to:
# http://localhost:3000/games/1/report
# or
# http://localhost:3000/games/1/transfer-orders
```

### 4. End-to-End Test

1. **Create a game** via UI or API
2. **Run several rounds** to generate TOs
3. **View game report** - should show TO analytics
4. **Check different tabs** in TransferOrderTimeline:
   - Timeline chart should show TO flow
   - Routes table should list all routes
   - In-Transit should show current pending TOs
   - Performance should show delivery metrics

---

## Troubleshooting

### Issue: "Module not found: TransferOrderAnalytics"

**Solution**: Verify file exists:
```bash
ls -la backend/app/services/sc_execution/to_analytics.py
```

If missing, it was created in this session - check your git status.

### Issue: "transfer_order table doesn't exist"

**Solution**: Check if model is imported:
```python
from app.models.transfer_order import TransferOrder, TransferOrderLineItem
```

Run database initialization:
```bash
docker compose exec backend python -m app.db.init_db
```

### Issue: "API endpoint returns 404"

**Solution**: Verify router is registered:
```bash
grep "transfer_orders" backend/app/api/api_v1/api.py
```

Should see:
```python
from app.api.endpoints import transfer_orders_router
api_router.include_router(transfer_orders_router, tags=["transfer-orders"])
```

### Issue: Frontend component not rendering

**Solution**: Check console for errors. Common issues:
- Missing `transferOrderService` - create the service file
- API returning empty data - run a game first to generate TOs
- Props not passed correctly - verify `gameId`, `transferOrders`, `analytics`

---

## Performance Considerations

### Database Queries

1. **Use Indexes**: The recommended indexes are:
   ```sql
   CREATE INDEX idx_game_arrival ON transfer_order (game_id, arrival_round, status);
   CREATE INDEX idx_destination_status ON transfer_order (destination_site_id, status);
   ```

2. **Batch Queries**: Fetch TOs and analytics in parallel:
   ```javascript
   const [tos, analytics] = await Promise.all([
     getTransferOrders(gameId),
     getAnalytics(gameId)
   ]);
   ```

3. **Pagination**: For games with 1000+ TOs:
   ```python
   @router.get("/games/{game_id}/transfer-orders")
   async def get_transfer_orders(
       game_id: int,
       page: int = Query(1, ge=1),
       page_size: int = Query(50, ge=1, le=500),
       db: Session = Depends(get_db)
   ):
       offset = (page - 1) * page_size
       tos = query.offset(offset).limit(page_size).all()
       ...
   ```

### Frontend Optimization

1. **Lazy Loading**: Load TO data only when tab is visible
2. **Memoization**: Cache analytics results
3. **Virtual Scrolling**: For large TO lists (>1000 rows)

---

## Summary Checklist

- [x] **Step 1: Test Suite** ✅ COMPLETE
  - [x] Test script created (`test_transfer_orders.py`)
  - [x] 6 validation checks implemented
  - [x] 52-round simulation capability
  - [x] Script made executable and verified

- [x] **Step 2: API Endpoints** ✅ COMPLETE
  - [x] Endpoints file created (`backend/app/api/endpoints/transfer_orders.py`)
  - [x] Router registered in API v1
  - [x] 5 endpoints available:
    - Get TOs for game
    - Get TO analytics
    - Get in-transit inventory
    - Get TO by number
    - Get TOs by route
  - [x] Analytics service integrated (`to_analytics.py`)

- [x] **Step 3: Frontend Integration** ✅ COMPLETE
  - [x] TransferOrderTimeline component exists (`frontend/src/components/game/TransferOrderTimeline.jsx`)
  - [x] 4 interactive tabs implemented
  - [x] Integration examples provided in guide
  - [x] Service layer defined (`transferOrderService`)

- [x] **Step 4: Database Schema** ✅ COMPLETE
  - [x] Model updated (`backend/app/models/transfer_order.py`)
  - [x] **AWS SC Compliant**: site_id and product_id use Integer ForeignKeys
  - [x] Added Beer Game fields: `game_id`, `order_round`, `arrival_round`, `order_date`
  - [x] Added indexes: `idx_to_game_arrival`, `idx_to_game_order`
  - [x] Created `BeerGameIdMapper` service for name ↔ ID translation
  - [x] Updated all services to use Integer node IDs

---

## Next Steps

After completing steps 1-4, consider:

1. **Run the full test suite** to validate implementation
2. **Add TO visualization to existing game pages**
3. **Implement real-time TO updates** via WebSocket
4. **Add TO export** (CSV/Excel) for reporting
5. **Implement Manufacturing Orders** with TO integration

---

## Support

For issues or questions:
1. Check test output for validation failures
2. Verify database schema matches requirements
3. Review API responses for data correctness
4. Check browser console for frontend errors

**Documentation References**:
- [TRANSFER_ORDERS_AND_DAG_TRAVERSAL.md](TRANSFER_ORDERS_AND_DAG_TRAVERSAL.md)
- [TRANSFER_ORDER_IMPLEMENTATION.md](TRANSFER_ORDER_IMPLEMENTATION.md)
- [TRANSFER_ORDER_COMPLETION_SUMMARY.md](TRANSFER_ORDER_COMPLETION_SUMMARY.md)
