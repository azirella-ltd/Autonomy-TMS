# Phase 2 Quick Reference Guide

**Last Updated**: January 19, 2026
**Status**: ✅ Production Ready

---

## 🚀 Quick Start

### 1. Access the New Features

**Production Orders**:
```
URL: http://localhost:8088/planning/production-orders
Navigation: Sidebar → Planning → Production Orders
```

**Capacity Planning**:
```
URL: http://localhost:8088/planning/capacity
Navigation: Sidebar → Planning → Capacity Planning
```

### 2. System Status Check

```bash
# Check backend health
docker compose ps backend
# Expected: Up (healthy)

# Check database tables
docker compose exec db psql -U beer_user -d beer_game -c "\dt" | grep -E "production|capacity"
# Expected: 6 tables (production_orders, production_order_components, capacity_plans, capacity_resources, capacity_requirements)

# Test API endpoints
curl -L "http://localhost:8000/api/v1/production-orders"
# Expected: {"detail":"Not authenticated"} (working, requires login)
```

---

## 📖 Quick Usage Guide

### Production Orders

**Create a Production Order**:
1. Login to the platform
2. Navigate to Planning → Production Orders
3. Click "Create Order" button
4. Fill in:
   - Item to produce
   - Production site
   - Supply chain config
   - Planned quantity
   - Start/completion dates
   - Priority (1-10)
5. Click "Create Order"

**Lifecycle States**:
```
PLANNED → RELEASED → IN_PROGRESS → COMPLETED → CLOSED
```

**Key Actions**:
- **Release**: Makes order available to shop floor
- **Start**: Records actual production start
- **Complete**: Records actual quantity and scrap
- **Close**: Finalizes the order
- **Cancel**: Cancels the order (from any pre-completed state)

### Capacity Planning

**Create a Capacity Plan**:
1. Navigate to Planning → Capacity Planning
2. Click "Create Plan" button
3. Fill in:
   - Plan name
   - Supply chain configuration
   - Planning horizon (weeks)
   - Start/end dates
   - Optional: Mark as scenario
4. Click "Create"

**Add Resources**:
1. Select a plan
2. Go to "Resources" tab
3. Click "Add Resource"
4. Define:
   - Resource name (e.g., "Assembly Line 1")
   - Resource type (LABOR, MACHINE, FACILITY, UTILITY, TOOL)
   - Available capacity (hours/week)
   - Efficiency percentage
   - Target utilization percentage

**Calculate Requirements**:
1. Go to plan details
2. Click "Calculate Requirements"
3. System automatically:
   - Analyzes production orders
   - Calculates resource needs
   - Identifies bottlenecks (>95% utilization)
   - Detects overloads (>100% capacity)

**What-If Scenarios**:
1. Create new plan
2. Check "This is a what-if scenario"
3. Select base plan for comparison
4. Modify resources (e.g., add third shift)
5. Calculate and compare results

---

## 🔑 API Quick Reference

### Production Orders API

**Base URL**: `/api/v1/production-orders`

**Common Endpoints**:
```bash
# List all orders (with filters)
GET /api/v1/production-orders?status=PLANNED&page=1&page_size=20

# Get summary statistics
GET /api/v1/production-orders/summary

# Get specific order
GET /api/v1/production-orders/{id}

# Create order
POST /api/v1/production-orders
{
  "item_id": 1,
  "site_id": 1,
  "config_id": 1,
  "planned_quantity": 1000,
  "planned_start_date": "2026-01-25T08:00:00Z",
  "planned_completion_date": "2026-02-01T17:00:00Z",
  "priority": 5
}

# Release order
POST /api/v1/production-orders/{id}/release
{ "notes": "Released for production" }

# Start production
POST /api/v1/production-orders/{id}/start
{
  "actual_start_date": "2026-01-25T08:30:00Z",
  "notes": "Started on time"
}

# Complete production
POST /api/v1/production-orders/{id}/complete
{
  "actual_quantity": 980,
  "scrap_quantity": 20,
  "actual_completion_date": "2026-02-01T16:00:00Z"
}
```

### Capacity Plans API

**Base URL**: `/api/v1/capacity-plans`

**Common Endpoints**:
```bash
# List all plans
GET /api/v1/capacity-plans?status=ACTIVE&page=1

# Get summary statistics
GET /api/v1/capacity-plans/summary

# Create plan
POST /api/v1/capacity-plans
{
  "name": "Q1 2026 Capacity Plan",
  "supply_chain_config_id": 1,
  "planning_horizon_weeks": 13,
  "start_date": "2026-01-20T00:00:00Z",
  "end_date": "2026-04-20T00:00:00Z"
}

# Add resource
POST /api/v1/capacity-plans/{plan_id}/resources
{
  "resource_name": "Assembly Line 1",
  "resource_type": "MACHINE",
  "site_id": 1,
  "available_capacity": 160,
  "capacity_unit": "hours",
  "efficiency_percent": 85.0
}

# Calculate requirements
POST /api/v1/capacity-plans/{id}/calculate
{
  "source_type": "PRODUCTION_ORDER",
  "recalculate": true
}

# Get analysis
GET /api/v1/capacity-plans/{id}/analysis

# Get bottlenecks
GET /api/v1/capacity-plans/{id}/bottlenecks
```

---

## 🎯 Common Workflows

### Workflow 1: Create and Execute Production Order

1. Create production order (PLANNED state)
2. Review order details
3. Release to shop floor (→ RELEASED)
4. Start production (→ IN_PROGRESS)
5. Complete with actual quantities (→ COMPLETED)
6. Close order (→ CLOSED)

### Workflow 2: Validate Production Capacity

1. Create capacity plan
2. Add resources (machines, labor, facilities)
3. Calculate requirements from production orders
4. Review utilization by resource
5. Identify bottlenecks (>95% utilization)
6. If overloaded:
   - Add capacity (new resources)
   - Reschedule orders
   - Create what-if scenario

### Workflow 3: MPS → Production → Capacity Flow

1. Create MPS plan with weekly quantities
2. Generate production orders from MPS
3. Create capacity plan
4. Calculate requirements from production orders
5. Validate capacity is sufficient
6. If issues found:
   - Adjust MPS quantities
   - Add resources
   - Modify production schedules

---

## 🔍 Troubleshooting

### Issue: Can't see Production Orders/Capacity Planning in menu

**Solution**:
- Check user has required capabilities
- Login as systemadmin@autonomy.ai (full access)
- Refresh browser cache (Ctrl+Shift+R)

### Issue: API returns 404

**Solution**:
```bash
# Verify backend is running
docker compose ps backend

# Check logs for errors
docker compose logs backend --tail 50

# Restart backend if needed
docker compose restart backend
```

### Issue: Database tables missing

**Solution**:
```bash
# Check current migration version
docker compose exec backend alembic current

# Run migrations
docker compose exec backend alembic upgrade head

# Or target specific migration
docker compose exec backend alembic upgrade 20260120_add_capacity_plans
```

### Issue: Frontend shows blank page

**Solution**:
1. Open browser DevTools (F12)
2. Check Console tab for errors
3. Check Network tab for failed API calls
4. Verify route is added in App.js
5. Clear browser cache and reload

---

## 📊 Key Metrics & Thresholds

### Production Orders

**Yield Calculation**:
```
Yield % = (Actual Quantity / Planned Quantity) × 100
Good Yield: >95%
Warning: 90-95%
Poor: <90%
```

**On-Time Delivery**:
```
On-Time: Actual completion ≤ Planned completion
Late: Actual completion > Planned completion
```

### Capacity Planning

**Utilization Levels**:
```
Green (<80%):    Healthy - room for growth
Yellow (80-95%): Good - near optimal
Orange (95-100%): Bottleneck - watch closely
Red (>100%):     Overloaded - action required
```

**Target Utilization**: 80-85% (sweet spot)

---

## 🎓 Best Practices

### Production Order Management

1. **Plan First**: Create orders in PLANNED state, review before releasing
2. **Batch Release**: Release multiple orders together for efficiency
3. **Track Actuals**: Always record actual quantities and scrap for yield analysis
4. **Close Promptly**: Close completed orders to keep data clean
5. **Use Notes**: Document important decisions and issues

### Capacity Planning

1. **Resource Accuracy**: Ensure available_capacity reflects reality
2. **Set Realistic Targets**: Use 80-85% utilization targets, not 100%
3. **Account for Efficiency**: Set efficiency_percent based on historical data
4. **Regular Updates**: Recalculate requirements when orders change
5. **Scenario Planning**: Always test "what-if" before major decisions
6. **Monitor Bottlenecks**: Review bottleneck report weekly

---

## 📞 Support & Documentation

**Full Documentation**:
- [PHASE2_COMPLETION_SUMMARY.md](PHASE2_COMPLETION_SUMMARY.md) - Complete implementation details
- [QUICK_START_PHASE2.md](QUICK_START_PHASE2.md) - Comprehensive user guide with examples
- [SESSION_SUMMARY_20260119.md](SESSION_SUMMARY_20260119.md) - Technical implementation notes
- [ACTION_ITEMS_WEEK5.md](ACTION_ITEMS_WEEK5.md) - Task completion status

**API Documentation**:
- Interactive docs: http://localhost:8000/docs
- OpenAPI schema: http://localhost:8000/openapi.json

**Database Schema**:
```sql
-- View table structure
\d production_orders
\d capacity_plans
\d capacity_resources
\d capacity_requirements
```

---

## ✅ Pre-Flight Checklist

Before using in production:

- [x] Database migrations applied
- [x] Backend running and healthy
- [x] Frontend accessible
- [x] API endpoints responding
- [x] Navigation working
- [ ] Test with real data
- [ ] Verify permissions for different user roles
- [ ] Review capacity thresholds
- [ ] Configure notification preferences

---

## 🎉 Quick Wins

**Immediate Value**:
1. Create first production order and track through lifecycle
2. Set up capacity plan for current quarter
3. Identify existing bottlenecks in production
4. Run what-if scenario for capacity expansion
5. Generate yield reports for quality improvement

**Week 1 Goals**:
- 10+ production orders created and tracked
- 1 capacity plan with all resources defined
- Bottleneck report reviewed and addressed
- First what-if scenario completed

---

**Quick Reference Version**: 1.0
**Last Updated**: January 19, 2026
**Phase 2 Status**: 40% Complete (2 of 5 entities)

🚀 **You're ready to start using Production Orders and Capacity Planning!**
