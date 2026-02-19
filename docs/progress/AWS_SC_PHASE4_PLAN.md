# AWS SC Phase 4: Analytics & Reporting - Planning

**Date**: 2026-01-12
**Status**: 📋 **PLANNING**

---

## Phase 4 Overview

Phase 4 focuses on analytics and reporting for the advanced AWS SC features delivered in Phase 3. This includes visualizations, metrics, and insights for:

1. Order aggregation effectiveness
2. Capacity utilization
3. Cost savings tracking
4. Policy performance analysis

---

## Goals

### Primary Objectives

1. **Aggregation Analytics**: Track and visualize order aggregation metrics
2. **Capacity Monitoring**: Display capacity utilization and constraints
3. **Cost Analysis**: Show cost savings from aggregation
4. **Policy Effectiveness**: Analyze which policies provide most value
5. **Comparative Analytics**: Compare performance with/without features

### Secondary Objectives

1. Dashboard UI for real-time metrics
2. Historical trend analysis
3. Export capabilities (CSV, JSON)
4. Alert system for capacity thresholds

---

## Sprints Breakdown

### Sprint 1: Backend Analytics Endpoints ✅ (Next)
**Estimated**: 400-500 lines

**Deliverables**:
1. Aggregation metrics endpoint
   - Cost savings by round
   - Orders aggregated count
   - Quantity adjustments

2. Capacity metrics endpoint
   - Utilization by site
   - Queue statistics
   - Overflow events

3. Policy effectiveness endpoint
   - Policy usage counts
   - Cost savings per policy
   - Constraint violations

4. Historical trends endpoint
   - Time series data
   - Comparative analysis

**Files**:
- New: `backend/app/api/endpoints/analytics.py` (~300 lines)
- New: `backend/app/services/analytics_service.py` (~200 lines)

### Sprint 2: Dashboard UI
**Estimated**: 500-600 lines

**Deliverables**:
1. Analytics dashboard page
2. Aggregation metrics charts
3. Capacity utilization visualizations
4. Cost savings trends
5. Policy comparison tables

**Files**:
- New: `frontend/src/pages/admin/AnalyticsDashboard.jsx` (~200 lines)
- New: `frontend/src/components/analytics/AggregationMetrics.jsx` (~150 lines)
- New: `frontend/src/components/analytics/CapacityCharts.jsx` (~150 lines)
- New: `frontend/src/components/analytics/CostSavings.jsx` (~100 lines)

### Sprint 3: Export & Reporting
**Estimated**: 300-400 lines

**Deliverables**:
1. CSV export for all metrics
2. JSON export for raw data
3. PDF report generation (optional)
4. Scheduled reports (optional)

**Files**:
- New: `backend/app/services/export_service.py` (~200 lines)
- Modified: `backend/app/api/endpoints/analytics.py` (+100 lines)

---

## Sprint 1 Detailed Plan: Backend Analytics

### 1. Aggregation Metrics Endpoint

**Route**: `GET /api/v1/analytics/aggregation/{game_id}`

**Response**:
```json
{
  "game_id": 1024,
  "total_rounds": 10,
  "aggregation_summary": {
    "total_orders_aggregated": 45,
    "total_groups_created": 15,
    "total_cost_savings": 1500.00,
    "avg_cost_savings_per_round": 150.00
  },
  "by_round": [
    {
      "round": 1,
      "orders_aggregated": 3,
      "groups_created": 1,
      "cost_savings": 200.00,
      "quantity_adjustments": [
        {
          "from_site": "Distributor",
          "to_site": "Factory",
          "total_quantity": 55.0,
          "adjusted_quantity": 60.0,
          "reason": "multiple_of_10"
        }
      ]
    }
  ],
  "by_site_pair": [
    {
      "from_site": "Distributor",
      "to_site": "Factory",
      "total_aggregated": 25,
      "total_savings": 800.00,
      "avg_quantity_adjustment": 5.2
    }
  ]
}
```

### 2. Capacity Metrics Endpoint

**Route**: `GET /api/v1/analytics/capacity/{game_id}`

**Response**:
```json
{
  "game_id": 1024,
  "capacity_summary": {
    "sites_with_capacity": 3,
    "total_capacity": 300.0,
    "avg_utilization": 75.5,
    "orders_queued": 12,
    "overflow_events": 3
  },
  "by_site": [
    {
      "site_id": 74,
      "site_name": "Factory",
      "capacity": 100.0,
      "avg_utilization": 85.0,
      "peak_utilization": 100.0,
      "rounds_at_capacity": 4,
      "orders_queued": 8
    }
  ],
  "by_round": [
    {
      "round": 1,
      "total_used": 225.0,
      "total_capacity": 300.0,
      "utilization_pct": 75.0,
      "queued": 2
    }
  ]
}
```

### 3. Policy Effectiveness Endpoint

**Route**: `GET /api/v1/analytics/policies/{config_id}`

**Response**:
```json
{
  "config_id": 2,
  "group_id": 2,
  "policies": [
    {
      "policy_id": 1,
      "type": "aggregation",
      "from_site": "Distributor",
      "to_site": "Factory",
      "usage_count": 25,
      "total_savings": 800.00,
      "avg_savings_per_use": 32.00,
      "effectiveness_score": 85.0
    },
    {
      "policy_id": 2,
      "type": "capacity",
      "site": "Factory",
      "capacity": 100.0,
      "avg_utilization": 85.0,
      "bottleneck_severity": "moderate"
    }
  ]
}
```

### 4. Comparative Analytics Endpoint

**Route**: `GET /api/v1/analytics/comparison/{game_id}`

**Response**:
```json
{
  "game_id": 1024,
  "features_enabled": {
    "capacity_constraints": true,
    "order_aggregation": true
  },
  "comparison": {
    "theoretical_without_aggregation": {
      "total_orders": 60,
      "total_cost": 6000.00
    },
    "actual_with_aggregation": {
      "total_orders": 15,
      "total_cost": 4500.00
    },
    "savings": {
      "orders_reduced": 45,
      "cost_saved": 1500.00,
      "efficiency_gain_pct": 25.0
    }
  },
  "capacity_impact": {
    "orders_fulfilled": 48,
    "orders_queued": 12,
    "fulfillment_rate_pct": 80.0
  }
}
```

---

## Implementation Steps

### Step 1: Analytics Service (Backend)

**File**: `backend/app/services/analytics_service.py`

**Classes**:
```python
class AnalyticsService:
    """Service for computing analytics metrics"""

    async def get_aggregation_metrics(game_id: int) -> Dict
    async def get_capacity_metrics(game_id: int) -> Dict
    async def get_policy_effectiveness(config_id: int, group_id: int) -> Dict
    async def get_comparative_analytics(game_id: int) -> Dict

    # Helper methods
    async def _calculate_cost_savings(game_id: int) -> float
    async def _calculate_capacity_utilization(game_id: int) -> Dict
    async def _calculate_policy_usage(config_id: int) -> Dict
```

### Step 2: Analytics Endpoints (Backend)

**File**: `backend/app/api/endpoints/analytics.py`

**Routes**:
```python
router = APIRouter()

@router.get("/aggregation/{game_id}")
async def get_aggregation_metrics(game_id: int, db: AsyncSession)

@router.get("/capacity/{game_id}")
async def get_capacity_metrics(game_id: int, db: AsyncSession)

@router.get("/policies/{config_id}")
async def get_policy_effectiveness(config_id: int, group_id: int, db: AsyncSession)

@router.get("/comparison/{game_id}")
async def get_comparative_analytics(game_id: int, db: AsyncSession)
```

### Step 3: Database Queries

**Aggregation Queries**:
```python
# Get all aggregated orders for a game
result = await db.execute(
    select(AggregatedOrder)
    .filter(AggregatedOrder.game_id == game_id)
    .order_by(AggregatedOrder.round_number)
)

# Calculate total savings
total_savings = await db.execute(
    select(func.sum(AggregatedOrder.fixed_cost_saved))
    .filter(AggregatedOrder.game_id == game_id)
)
```

**Capacity Queries**:
```python
# Get capacity usage by round
result = await db.execute(
    select(
        InboundOrderLine.round_number,
        ProductionCapacity.site_id,
        func.sum(InboundOrderLine.quantity_submitted)
    )
    .join(ProductionCapacity, ...)
    .group_by(InboundOrderLine.round_number, ProductionCapacity.site_id)
)
```

---

## Database Schema Additions (Optional)

### Analytics Cache Table (Optional)

For performance, we may want to cache computed metrics:

```sql
CREATE TABLE analytics_cache (
    id INT PRIMARY KEY AUTO_INCREMENT,
    game_id INT,
    metric_type VARCHAR(50),  -- 'aggregation', 'capacity', etc.
    round_number INT,
    metric_data JSON,
    computed_at DATETIME,
    expires_at DATETIME,
    INDEX idx_game_metric (game_id, metric_type),
    INDEX idx_expires (expires_at)
);
```

**Benefits**:
- Faster dashboard loads
- Reduced database query load
- Supports real-time updates

**Implementation**: Optional for Sprint 1, recommended for production

---

## Testing Strategy

### Unit Tests
- Test each analytics calculation independently
- Mock database queries
- Verify metric accuracy

### Integration Tests
- Test endpoints with real game data
- Verify JSON response format
- Test query performance

### Test Data
- Use existing test games from Phase 3
- Create additional test data for edge cases
- Test with 0 aggregations, 0 capacity constraints

---

## Success Criteria

### Sprint 1 (Backend)
- ✅ All 4 endpoints implemented
- ✅ Response times < 500ms for typical games
- ✅ Accurate calculations verified
- ✅ Integration tests passing
- ✅ Documentation complete

### Sprint 2 (UI)
- ✅ Dashboard displays all metrics
- ✅ Charts render correctly
- ✅ Real-time updates work
- ✅ Mobile responsive
- ✅ User testing feedback positive

### Sprint 3 (Export)
- ✅ CSV export works
- ✅ JSON export works
- ✅ Exports contain all necessary data
- ✅ File downloads work in browser

---

## Timeline Estimate

**Sprint 1**: 2-3 hours (Backend analytics)
**Sprint 2**: 3-4 hours (Dashboard UI)
**Sprint 3**: 1-2 hours (Export functionality)

**Total Phase 4**: 6-9 hours of development time

---

## Next Steps

1. ✅ Complete this planning document
2. ⏳ Implement analytics_service.py
3. ⏳ Implement analytics API endpoints
4. ⏳ Write integration tests
5. ⏳ Build dashboard UI (Sprint 2)
6. ⏳ Add export functionality (Sprint 3)

---

## Questions to Resolve

1. **Caching Strategy**: Cache metrics or compute on-demand?
   - Recommendation: Compute on-demand for Sprint 1, add caching in Sprint 2 if needed

2. **Real-time Updates**: WebSocket or polling for dashboard?
   - Recommendation: Polling for Sprint 1, WebSocket for Sprint 2 if needed

3. **Historical Data**: How far back to show trends?
   - Recommendation: All rounds for current game, last 30 days for multi-game

4. **Permissions**: Who can view analytics?
   - Recommendation: Game participants + admins, filterable by group_id

---

**Status**: Planning complete, ready to start Sprint 1 implementation
**Next**: Implement `analytics_service.py`
