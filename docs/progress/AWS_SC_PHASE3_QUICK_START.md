# AWS SC Phase 3: Quick Start Guide

**For Developers**: Quick reference for using Phase 3 features

---

## TL;DR

Phase 3 adds three optional features to AWS SC execution mode:
1. **Sprint 1**: 187.5x performance boost (always enabled)
2. **Sprint 2**: Capacity constraints (opt-in per game)
3. **Sprint 3**: Order aggregation (opt-in per game)

All features are backward compatible and work independently or together.

---

## Quick Examples

### 1. Standard Game (Sprint 1 only)
```python
game = Game(
    name="Standard Game",
    use_aws_sc_planning=True,
    config={}  # Sprint 1 cache is always enabled
)
# Result: 187.5x speedup, no constraints
```

### 2. Add Capacity Constraints (Sprint 2)
```python
from app.models.aws_sc_planning import ProductionCapacity

# Enable in game config
game = Game(
    name="Capacity Game",
    use_aws_sc_planning=True,
    config={
        'use_capacity_constraints': True,
        'capacity_reset_period': 1  # Reset every round
    }
)

# Create capacity constraint
capacity = ProductionCapacity(
    site_id=factory_node.id,
    product_id=item.id,
    max_capacity_per_period=100.0,
    capacity_type='production',
    capacity_period='week',
    allow_overflow=False,
    group_id=game.group_id,
    config_id=game.supply_chain_config_id
)
db.add(capacity)
await db.commit()
```

### 3. Add Order Aggregation (Sprint 3)
```python
from app.models.aws_sc_planning import OrderAggregationPolicy

# Enable in game config
game = Game(
    name="Aggregation Game",
    use_aws_sc_planning=True,
    config={
        'use_order_aggregation': True
    }
)

# Create aggregation policy
policy = OrderAggregationPolicy(
    from_site_id=distributor_node.id,
    to_site_id=factory_node.id,
    product_id=item.id,
    min_order_quantity=50.0,
    order_multiple=10.0,
    fixed_order_cost=100.0,
    group_id=game.group_id,
    config_id=game.supply_chain_config_id
)
db.add(policy)
await db.commit()
```

### 4. Full Featured Game (All Sprints)
```python
game = Game(
    name="Full Featured Game",
    use_aws_sc_planning=True,
    config={
        'use_capacity_constraints': True,
        'capacity_reset_period': 1,
        'use_order_aggregation': True
    }
)

# Then create both ProductionCapacity and OrderAggregationPolicy records
```

---

## Configuration Reference

### Game Config Fields

```python
game.config = {
    # Sprint 2: Capacity Constraints
    'use_capacity_constraints': True,    # Enable capacity enforcement
    'capacity_reset_period': 1,          # Reset every N rounds (1 = weekly)

    # Sprint 3: Order Aggregation
    'use_order_aggregation': True        # Enable order aggregation
}
```

### ProductionCapacity Model (Sprint 2)

```python
ProductionCapacity(
    site_id=node_id,                     # Required: Site with capacity
    product_id=item_id,                  # Optional: Product-specific (None = all products)
    max_capacity_per_period=100.0,      # Required: Maximum capacity
    current_capacity_used=0.0,           # Auto-updated by system
    capacity_type='production',          # 'production', 'transfer', or 'storage'
    capacity_period='week',              # 'week', 'month', etc.
    allow_overflow=False,                # Allow exceeding capacity?
    overflow_cost_multiplier=1.5,        # Cost penalty for overflow (e.g., 1.5x)
    group_id=game.group_id,              # Required: Multi-tenancy
    config_id=game.supply_chain_config_id # Required: Config association
)
```

### OrderAggregationPolicy Model (Sprint 3)

```python
OrderAggregationPolicy(
    from_site_id=distributor_id,         # Required: Ordering site
    to_site_id=factory_id,               # Required: Supplier site
    product_id=item_id,                  # Optional: Product-specific (None = all products)
    min_order_quantity=50.0,             # Optional: Minimum order size
    max_order_quantity=200.0,            # Optional: Maximum order size
    order_multiple=10.0,                 # Optional: Order in multiples (e.g., pallet size)
    fixed_order_cost=100.0,              # Optional: Fixed cost per order
    variable_cost_per_unit=5.0,          # Optional: Variable cost per unit
    is_active=True,                      # Required: Enable policy
    group_id=game.group_id,              # Required: Multi-tenancy
    config_id=game.supply_chain_config_id # Required: Config association
)
```

---

## How It Works

### Execution Flow

```python
# In mixed_game_service.py (automatically handled)
use_capacity = game.config.get('use_capacity_constraints', False)
use_aggregation = game.config.get('use_order_aggregation', False)

if use_aggregation:
    # Sprint 3: Aggregation (+ optional capacity)
    result = await adapter.create_work_orders_with_aggregation(
        player_orders, round_number, use_capacity=use_capacity
    )

elif use_capacity:
    # Sprint 2: Capacity only
    result = await adapter.create_work_orders_with_capacity(
        player_orders, round_number
    )

else:
    # Sprint 1: Batch operations
    work_orders = await adapter.create_work_orders_batch(
        player_orders, round_number
    )
```

### What Happens When

**Sprint 1 (Always On)**:
- ExecutionCache loads policies, nodes, items at game start
- O(1) dictionary lookups during execution
- Batch database inserts for work orders
- 187.5x performance improvement

**Sprint 2 (When `use_capacity_constraints=True`)**:
- Cache loads ProductionCapacity records
- Each work order checks available capacity
- Orders queue or overflow if capacity exceeded
- Capacity resets every N rounds

**Sprint 3 (When `use_order_aggregation=True`)**:
- Cache loads OrderAggregationPolicy records
- Orders to same upstream site are grouped
- Quantity constraints applied (min/max/multiple)
- Cost savings calculated and tracked
- Works with or without capacity constraints

---

## Common Use Cases

### Use Case 1: Simple Capacity Limit

**Goal**: Factory can only produce 100 units per week

```python
capacity = ProductionCapacity(
    site_id=factory_id,
    max_capacity_per_period=100.0,
    capacity_type='production',
    capacity_period='week',
    allow_overflow=False,
    group_id=game.group_id,
    config_id=config_id
)
```

**Result**: Orders exceeding 100 units are queued for next period

### Use Case 2: Flexible Capacity with Overflow

**Goal**: Warehouse can handle 200 units normally, but allows overflow at 1.5x cost

```python
capacity = ProductionCapacity(
    site_id=warehouse_id,
    max_capacity_per_period=200.0,
    capacity_type='storage',
    capacity_period='week',
    allow_overflow=True,
    overflow_cost_multiplier=1.5,
    group_id=game.group_id,
    config_id=config_id
)
```

**Result**: Orders up to 200 units are normal cost, excess orders cost 1.5x

### Use Case 3: Minimum Order Quantity

**Goal**: Supplier requires minimum 50 unit orders

```python
policy = OrderAggregationPolicy(
    from_site_id=distributor_id,
    to_site_id=supplier_id,
    min_order_quantity=50.0,
    group_id=game.group_id,
    config_id=config_id
)
```

**Result**: Orders below 50 units are increased to 50

### Use Case 4: Pallet Quantities

**Goal**: Orders must be in multiples of 24 (pallet size)

```python
policy = OrderAggregationPolicy(
    from_site_id=distributor_id,
    to_site_id=factory_id,
    order_multiple=24.0,
    fixed_order_cost=150.0,
    group_id=game.group_id,
    config_id=config_id
)
```

**Result**: Order of 50 units becomes 48 (2 pallets), saves $150 per aggregated order

### Use Case 5: Full Featured Supply Chain

**Goal**: Factory has capacity limit + orders in pallets + minimum quantities

```python
# Enable both features
game.config = {
    'use_capacity_constraints': True,
    'use_order_aggregation': True
}

# Capacity constraint
capacity = ProductionCapacity(
    site_id=factory_id,
    max_capacity_per_period=120.0,
    allow_overflow=False,
    group_id=game.group_id,
    config_id=config_id
)

# Aggregation policy
policy = OrderAggregationPolicy(
    from_site_id=distributor_id,
    to_site_id=factory_id,
    min_order_quantity=48.0,
    order_multiple=24.0,
    fixed_order_cost=100.0,
    group_id=game.group_id,
    config_id=config_id
)
```

**Result**:
- Orders adjusted to pallet quantities (multiples of 24)
- Minimum 48 units enforced
- Capacity limit of 120 units enforced
- Cost savings tracked

---

## Querying Data

### Check Capacity Usage

```python
from app.models.aws_sc_planning import ProductionCapacity

result = await db.execute(
    select(ProductionCapacity).filter(
        ProductionCapacity.site_id == factory_id,
        ProductionCapacity.group_id == group_id
    )
)
capacity = result.scalar_one_or_none()

if capacity:
    print(f"Used: {capacity.current_capacity_used}/{capacity.max_capacity_per_period}")
    print(f"Available: {capacity.max_capacity_per_period - capacity.current_capacity_used}")
```

### View Aggregated Orders

```python
from app.models.aws_sc_planning import AggregatedOrder

result = await db.execute(
    select(AggregatedOrder).filter(
        AggregatedOrder.game_id == game_id,
        AggregatedOrder.round_number == round_number
    )
)
agg_orders = result.scalars().all()

for order in agg_orders:
    print(f"Site: {order.from_site_id} → {order.to_site_id}")
    print(f"Quantity: {order.total_quantity} → {order.adjusted_quantity}")
    print(f"Orders combined: {order.num_orders_aggregated}")
    print(f"Cost saved: ${order.fixed_cost_saved}")
```

### Calculate Total Savings

```python
result = await db.execute(
    select(AggregatedOrder).filter(
        AggregatedOrder.game_id == game_id
    )
)
agg_orders = result.scalars().all()

total_savings = sum(order.fixed_cost_saved for order in agg_orders)
print(f"Total cost savings: ${total_savings:.2f}")
```

---

## Testing

### Run All Tests

```bash
# Sprint 2: Capacity integration tests
docker compose exec backend python scripts/test_capacity_integration.py

# Sprint 3: Aggregation adapter tests
docker compose exec backend python scripts/test_aggregation_integration.py

# Sprint 3: Aggregation game service tests
docker compose exec backend python scripts/test_aggregation_game_service.py
```

### Expected Output

```
✅ ALL TESTS PASSED

Sprint 2: 4/4 tests passing
Sprint 3: 9/9 tests passing (5 adapter + 4 game service)
Total: 13/13 tests passing
```

---

## Troubleshooting

### Orders Not Being Aggregated

**Check**:
1. Is `use_order_aggregation=True` in game config?
2. Does an OrderAggregationPolicy exist for this site pair?
3. Is the policy `is_active=True`?
4. Are `group_id` and `config_id` correct?

```python
# Check if policy exists
policy = cache.get_aggregation_policy(
    from_site_id=distributor_id,
    to_site_id=factory_id,
    product_id=item_id
)
print(f"Policy found: {policy is not None}")
```

### Capacity Not Being Enforced

**Check**:
1. Is `use_capacity_constraints=True` in game config?
2. Does a ProductionCapacity exist for this site?
3. Is `current_capacity_used` being reset each period?

```python
# Check capacity
capacity = cache.get_production_capacity(factory_id, item_id)
print(f"Capacity: {capacity.current_capacity_used}/{capacity.max_capacity_per_period}")
```

### Cache Not Loading

**Check**:
1. Is cache being initialized with `use_cache=True`?
2. Is `await cache.load()` being called?

```python
adapter = BeerGameExecutionAdapter(game, db, use_cache=True)
cache_counts = await adapter.cache.load()
print(f"Loaded: {cache_counts}")
```

---

## Performance Tips

1. **Always Use Cache**: Initialize adapter with `use_cache=True`
2. **Batch Operations**: Create multiple policies before game starts
3. **Reset Capacity**: Set appropriate `capacity_reset_period`
4. **Index Queries**: Use indexed fields (site_id, product_id, group_id)

---

## Migration Path

### Existing Games

Existing games continue working without changes:
- Sprint 1 performance boost is automatic
- Sprint 2/3 features are disabled by default
- No breaking changes

### Enable New Features

```python
# Update game config
game = await db.get(Game, game_id)
if not game.config:
    game.config = {}

game.config['use_capacity_constraints'] = True
game.config['use_order_aggregation'] = True
await db.commit()

# Create constraints/policies as needed
```

---

## Additional Resources

- **Full Documentation**: See `AWS_SC_PHASE3_COMPLETE.md`
- **Sprint 2 Details**: See `AWS_SC_PHASE3_SPRINT2_INTEGRATION_COMPLETE.md`
- **Sprint 3 Details**: See `AWS_SC_PHASE3_SPRINT3_INTEGRATION_COMPLETE.md`
- **Test Scripts**: See `backend/scripts/test_*_integration.py`

---

## Summary

Phase 3 delivers:
- ✅ 187.5x performance improvement (always on)
- ✅ Optional capacity constraints (per-game opt-in)
- ✅ Optional order aggregation (per-game opt-in)
- ✅ All features work independently or together
- ✅ Zero breaking changes
- ✅ Production-ready and fully tested

**Start using**: Just add config flags to your game and create policies!
