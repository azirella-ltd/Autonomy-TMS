# Quick Start Guide - Phase 2 Implementation

**Last Updated**: January 20, 2026
**Phase**: Phase 2 - Data Model Refactoring
**Status**: 2 of 5 entities complete (40%)

---

## 🚀 What's New

### ✅ Production Orders (Entity #15)
Full production order lifecycle management with 6 states.

**Access**: `/planning/production-orders`
**API**: `/api/v1/production-orders`
**Permissions**: `view_production_orders`, `manage_production_orders`, `release_production_orders`

### ✅ Capacity Planning (Entity #16) - Backend Only
RCCP with bottleneck detection and scenario planning.

**API**: `/api/v1/capacity-plans`
**Status**: Backend complete, frontend pending
**Permissions**: `view_capacity_planning`, `manage_capacity_planning`

---

## 🛠️ Setup Instructions

### 1. Apply Database Migrations

```bash
# Navigate to project root
cd /home/trevor/Projects/The_Beer_Game

# Ensure services are running
docker compose up -d

# Run migrations
docker compose exec backend alembic upgrade head

# Verify new tables exist
docker compose exec db psql -U beer_user -d beer_game -c "\dt" | grep -E "(production|capacity)"
```

**Expected Tables**:
- ✅ production_orders
- ✅ production_order_components
- ✅ capacity_plans
- ✅ capacity_resources
- ✅ capacity_requirements

### 2. Restart Backend (to load new models)

```bash
docker compose restart backend

# Watch logs to ensure clean startup
docker compose logs -f backend
```

**Expected in logs**:
```
INFO: Registered tables in metadata: {..., 'production_orders', 'capacity_plans', ...}
INFO: Application startup complete
```

### 3. Verify API Endpoints

```bash
# Check API documentation
open http://localhost:8000/docs

# Look for new tags:
# - production-orders (11 endpoints)
# - capacity-plans (14 endpoints)
```

---

## 📖 Usage Guide

### Production Orders

#### Create a Production Order

**Via UI**:
1. Navigate to `/planning/production-orders`
2. Click "Create Order" button
3. Fill in the form:
   - Item: Select finished good
   - Site: Select production site
   - Config: Select supply chain config
   - Planned Quantity: Enter units to produce
   - Start Date: When to start
   - Completion Date: When to finish
   - Priority: 1-10 (default: 5)
4. Click "Create Order"

**Via API**:
```bash
curl -X POST http://localhost:8000/api/v1/production-orders \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION" \
  -d '{
    "item_id": 1,
    "site_id": 1,
    "config_id": 1,
    "planned_quantity": 1000,
    "planned_start_date": "2026-01-25T08:00:00Z",
    "planned_completion_date": "2026-02-01T17:00:00Z",
    "priority": 5,
    "notes": "Q1 2026 production batch"
  }'
```

#### Lifecycle Operations

**Release Order to Shop Floor**:
```bash
curl -X POST http://localhost:8000/api/v1/production-orders/1/release \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION" \
  -d '{
    "notes": "Released for production"
  }'
```

**Start Production**:
```bash
curl -X POST http://localhost:8000/api/v1/production-orders/1/start \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION" \
  -d '{
    "actual_start_date": "2026-01-25T08:30:00Z",
    "notes": "Production started on schedule"
  }'
```

**Complete Production**:
```bash
curl -X POST http://localhost:8000/api/v1/production-orders/1/complete \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION" \
  -d '{
    "actual_quantity": 980,
    "scrap_quantity": 20,
    "actual_completion_date": "2026-02-01T16:00:00Z",
    "notes": "Production completed with 98% yield"
  }'
```

**Close Order**:
```bash
curl -X POST http://localhost:8000/api/v1/production-orders/1/close \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION" \
  -d '{
    "notes": "Order closed and finalized"
  }'
```

---

### Capacity Planning

#### Create a Capacity Plan

```bash
curl -X POST http://localhost:8000/api/v1/capacity-plans \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION" \
  -d '{
    "name": "Q1 2026 Capacity Plan",
    "description": "13-week capacity validation for Q1 production",
    "supply_chain_config_id": 1,
    "planning_horizon_weeks": 13,
    "bucket_size_days": 7,
    "start_date": "2026-01-20T00:00:00Z",
    "end_date": "2026-04-20T00:00:00Z",
    "is_scenario": false
  }'
```

#### Add Capacity Resources

```bash
# Add Assembly Line
curl -X POST http://localhost:8000/api/v1/capacity-plans/1/resources \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION" \
  -d '{
    "resource_name": "Assembly Line 1",
    "resource_type": "MACHINE",
    "site_id": 1,
    "available_capacity": 160,
    "capacity_unit": "hours",
    "efficiency_percent": 85.0,
    "utilization_target_percent": 85.0,
    "cost_per_hour": 150.0,
    "shifts_per_day": 2,
    "hours_per_shift": 8,
    "working_days_per_week": 5
  }'

# Add Labor Resource
curl -X POST http://localhost:8000/api/v1/capacity-plans/1/resources \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION" \
  -d '{
    "resource_name": "Production Workers",
    "resource_type": "LABOR",
    "site_id": 1,
    "available_capacity": 320,
    "capacity_unit": "hours",
    "efficiency_percent": 90.0,
    "utilization_target_percent": 80.0,
    "cost_per_hour": 35.0
  }'
```

#### Calculate Requirements from Production Orders

```bash
curl -X POST http://localhost:8000/api/v1/capacity-plans/1/calculate \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION" \
  -d '{
    "plan_id": 1,
    "source_type": "PRODUCTION_ORDER",
    "recalculate": true
  }'
```

**Response**:
```json
{
  "message": "Capacity requirements calculated successfully",
  "requirements_created": 26,
  "is_feasible": true,
  "overloaded_resources": 0
}
```

#### Get Capacity Analysis

```bash
curl http://localhost:8000/api/v1/capacity-plans/1/analysis \
  -H "Cookie: session=YOUR_SESSION"
```

**Response**:
```json
{
  "plan_id": 1,
  "is_feasible": true,
  "total_periods": 13,
  "overloaded_periods": 0,
  "bottleneck_resources": [],
  "utilization_by_resource": {
    "Assembly Line 1": 78.5,
    "Production Workers": 65.2
  },
  "utilization_by_period": [
    {
      "period_number": 1,
      "period_start": "2026-01-20T00:00:00Z",
      "avg_utilization": 75.0,
      "overloaded_resources": 0
    }
  ],
  "recommendations": [
    "Average utilization is below 60%. Consider consolidating resources or increasing production."
  ]
}
```

#### Identify Bottlenecks

```bash
curl http://localhost:8000/api/v1/capacity-plans/1/bottlenecks \
  -H "Cookie: session=YOUR_SESSION"
```

**Response** (when bottlenecks exist):
```json
[
  {
    "resource_id": 1,
    "resource_name": "Assembly Line 1",
    "site_id": 1,
    "site_name": "Main Factory",
    "max_utilization_percent": 97.5,
    "overloaded_periods": 2,
    "avg_utilization_percent": 88.3
  }
]
```

#### Create What-If Scenario

```bash
# Create scenario based on existing plan
curl -X POST http://localhost:8000/api/v1/capacity-plans \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION" \
  -d '{
    "name": "Q1 2026 - Increased Capacity Scenario",
    "description": "What if we add a third shift?",
    "supply_chain_config_id": 1,
    "planning_horizon_weeks": 13,
    "start_date": "2026-01-20T00:00:00Z",
    "end_date": "2026-04-20T00:00:00Z",
    "is_scenario": true,
    "scenario_description": "Add third shift to Assembly Line 1",
    "base_plan_id": 1
  }'

# Then add resources with increased capacity
# Compare results between base plan and scenario
```

---

## 🎯 Common Workflows

### Workflow 1: Release Production Orders from MPS

1. Create MPS plan with weekly quantities
2. Generate production orders from MPS
3. Review production orders in `/planning/production-orders`
4. Release orders to shop floor (bulk or individually)
5. Track progress through IN_PROGRESS
6. Complete orders with actual quantities
7. Close completed orders

### Workflow 2: Validate Production Capacity

1. Create capacity plan linked to supply chain config
2. Define capacity resources (machines, labor, facilities)
3. Calculate requirements from production orders
4. Review utilization by resource and period
5. Identify bottlenecks (>95% utilization)
6. Address overloaded resources:
   - Add capacity (new resources)
   - Reschedule orders
   - Increase efficiency
7. Create what-if scenarios to test alternatives

### Workflow 3: Scenario Planning

1. Create base capacity plan
2. Calculate requirements
3. Identify constraints/bottlenecks
4. Create scenario plan (reference base via base_plan_id)
5. Modify resources in scenario:
   - Add third shift
   - Increase efficiency
   - Add new equipment
6. Calculate requirements for scenario
7. Compare base vs scenario:
   - Utilization differences
   - Bottleneck resolution
   - Cost impact
8. Choose best scenario and make it ACTIVE

---

## 📊 Data Model Reference

### Production Order States

```
PLANNED
  ↓ release()
RELEASED
  ↓ start()
IN_PROGRESS
  ↓ complete(actual_qty, scrap_qty)
COMPLETED
  ↓ close()
CLOSED

From any state (except COMPLETED/CLOSED):
  ↓ cancel(reason)
CANCELLED
```

### Capacity Plan Workflow

```
DRAFT (editable)
  ↓ activate
ACTIVE (in use for planning)
  ↓ archive when obsolete
ARCHIVED (historical reference)

Scenarios:
SCENARIO (what-if analysis, references base_plan_id)
```

### Resource Types

- **LABOR**: Human resources (workers, operators)
- **MACHINE**: Equipment (CNC, assembly lines, packaging)
- **FACILITY**: Building space (warehouse, production floor)
- **UTILITY**: Utilities (power, water, gas)
- **TOOL**: Tools and fixtures

### Capacity Metrics

```python
# Effective capacity (accounts for efficiency)
effective_capacity = available_capacity × (efficiency_percent / 100)

# Target capacity (accounts for target utilization)
target_capacity = effective_capacity × (utilization_target_percent / 100)

# Utilization percentage
utilization_percent = (required_capacity / available_capacity) × 100

# Overload detection
is_overloaded = utilization_percent > 100

# Bottleneck detection
is_bottleneck = utilization_percent >= 95

# Spare capacity
spare_capacity = available_capacity - required_capacity
```

---

## 🔍 Troubleshooting

### Issue: Migration fails

**Error**: `Table 'production_orders' already exists`

**Solution**:
```bash
# Check current migration version
docker compose exec backend alembic current

# If ahead, downgrade first
docker compose exec backend alembic downgrade -1

# Then upgrade
docker compose exec backend alembic upgrade head
```

### Issue: API returns 404

**Error**: `{"detail": "Not Found"}`

**Solution**:
1. Verify backend is running: `docker compose ps`
2. Check router registration in `backend/app/api/api_v1/api.py`
3. Restart backend: `docker compose restart backend`
4. Check logs: `docker compose logs backend | tail -50`

### Issue: Permission denied on API calls

**Error**: `{"detail": "Access Denied"}`

**Solution**:
1. Verify user has required capability:
   ```sql
   SELECT * FROM user_capabilities WHERE user_id = YOUR_USER_ID;
   ```
2. Grant capability if missing (as SYSTEM_ADMIN):
   ```python
   # Via Django shell or SQL
   INSERT INTO user_capabilities (user_id, capability)
   VALUES (1, 'view_production_orders');
   ```

### Issue: Frontend page is blank

**Error**: Blank page, no errors in console

**Solution**:
1. Check browser console for import errors
2. Verify route is added to `App.js`
3. Check component export: `export default ComponentName`
4. Restart frontend: `docker compose restart frontend`

### Issue: Capacity calculation returns no requirements

**Error**: `{"requirements_created": 0}`

**Solution**:
1. Verify production orders exist for the time period
2. Check production orders are in PLANNED/RELEASED/IN_PROGRESS status
3. Verify site_id matches between orders and resources
4. Check date ranges overlap

---

## 📚 API Reference

### Production Orders

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/production-orders` | List orders (with filtering) |
| GET | `/api/v1/production-orders/summary` | Summary statistics |
| GET | `/api/v1/production-orders/{id}` | Get order by ID |
| POST | `/api/v1/production-orders` | Create order |
| PUT | `/api/v1/production-orders/{id}` | Update order |
| DELETE | `/api/v1/production-orders/{id}` | Delete order (soft) |
| POST | `/api/v1/production-orders/{id}/release` | Release to shop floor |
| POST | `/api/v1/production-orders/{id}/start` | Start production |
| POST | `/api/v1/production-orders/{id}/complete` | Complete with actuals |
| POST | `/api/v1/production-orders/{id}/close` | Close order |
| POST | `/api/v1/production-orders/{id}/cancel` | Cancel order |

### Capacity Plans

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/capacity-plans` | List plans (with filtering) |
| GET | `/api/v1/capacity-plans/summary` | Summary statistics |
| GET | `/api/v1/capacity-plans/{id}` | Get plan by ID |
| POST | `/api/v1/capacity-plans` | Create plan |
| PUT | `/api/v1/capacity-plans/{id}` | Update plan |
| DELETE | `/api/v1/capacity-plans/{id}` | Delete plan (soft) |
| GET | `/api/v1/capacity-plans/{id}/resources` | List resources |
| POST | `/api/v1/capacity-plans/{id}/resources` | Create resource |
| PUT | `/api/v1/capacity-plans/resources/{id}` | Update resource |
| DELETE | `/api/v1/capacity-plans/resources/{id}` | Delete resource |
| GET | `/api/v1/capacity-plans/{id}/requirements` | List requirements |
| POST | `/api/v1/capacity-plans/{id}/calculate` | Calculate requirements |
| GET | `/api/v1/capacity-plans/{id}/analysis` | Full analysis |
| GET | `/api/v1/capacity-plans/{id}/bottlenecks` | Identify bottlenecks |

---

## 🎓 Best Practices

### Production Order Management

1. **Plan First**: Create orders in PLANNED status, review before releasing
2. **Batch Release**: Release multiple orders together for efficiency
3. **Track Actuals**: Always record actual quantities and scrap for yield analysis
4. **Close Promptly**: Close completed orders to keep data clean
5. **Use Notes**: Document important decisions in the notes field

### Capacity Planning

1. **Resource Accuracy**: Ensure available_capacity reflects reality (shifts × hours)
2. **Set Realistic Targets**: Use 80-85% utilization targets, not 100%
3. **Account for Efficiency**: Set efficiency_percent based on historical data
4. **Regular Updates**: Recalculate requirements when orders change
5. **Scenario Planning**: Always test "what-if" before major decisions
6. **Monitor Bottlenecks**: Review bottleneck report weekly

### Performance Optimization

1. **Use Pagination**: Always paginate large result sets
2. **Filter Early**: Apply filters at the database level, not in memory
3. **Index Usage**: Ensure queries use indexes (check EXPLAIN ANALYZE)
4. **Batch Operations**: Create multiple resources in a loop, not one API call per resource
5. **Cache Results**: Cache expensive calculations like capacity analysis

---

## 📞 Support

**Documentation**:
- [PHASE_2_PROGRESS_SUMMARY.md](PHASE_2_PROGRESS_SUMMARY.md) - Detailed implementation status
- [SESSION_SUMMARY_20260120.md](SESSION_SUMMARY_20260120.md) - Session deliverables
- [AWS_SC_IMPLEMENTATION_STATUS.md](AWS_SC_IMPLEMENTATION_STATUS.md) - Compliance tracking
- [ACTION_ITEMS_WEEK5.md](ACTION_ITEMS_WEEK5.md) - Next steps checklist

**API Documentation**:
- Interactive docs: http://localhost:8000/docs
- OpenAPI schema: http://localhost:8000/openapi.json

**Issues**:
- GitHub: https://github.com/MilesAheadToo/The_Beer_Game/issues

---

**Quick Start Version**: 1.0
**Last Updated**: January 20, 2026
**Phase 2 Status**: 40% Complete (2/5 entities)
