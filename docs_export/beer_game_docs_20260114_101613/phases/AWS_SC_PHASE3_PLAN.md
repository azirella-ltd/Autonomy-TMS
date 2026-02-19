# AWS SC Phase 3: Advanced Features - Implementation Plan

**Date**: 2026-01-12
**Status**: 🚧 **IN PROGRESS**
**Phase**: Phase 3 - Advanced Execution Features
**Dependencies**: Phase 2 Complete ✅

---

## Executive Summary

Phase 3 builds on the execution foundation from Phase 2 by adding advanced features that make AWS SC execution mode production-ready and feature-complete. These enhancements focus on realism, performance, and analytics.

**Goal**: Transform AWS SC execution from "working prototype" to "production-ready system"

---

## Implementation Strategy

### Approach: Incremental Enhancement
- Build on existing `BeerGameExecutionAdapter`
- Add new methods without breaking Phase 2 functionality
- Each feature is independently testable
- Maintain backward compatibility with legacy mode

### Priority Order
1. **Performance Optimization** (High impact, foundational)
2. **Capacity Constraints** (Realism, builds on performance)
3. **Order Aggregation** (Efficiency, uses capacity system)
4. **Advanced Scheduling** (Sophistication, uses aggregation)
5. **Analytics & Reporting** (Observability, uses all above)
6. **Integration Testing** (Validation, final verification)

---

## Feature 1: Performance Optimization

### Problem
Current execution mode is 10-20x slower than legacy mode:
- Legacy: 50-100ms per round
- Execution: 500-2000ms per round

### Root Causes
1. **Repeated DB queries**: Fetching `inv_policy` and `sourcing_rules` every round
2. **Individual inserts**: Creating work orders one-by-one
3. **Full synchronization**: Syncing all inventory every round
4. **No caching**: Config data re-fetched repeatedly

### Solution: Multi-Layer Caching

#### A. In-Memory Cache Layer
```python
class ExecutionCache:
    """Cache for frequently accessed AWS SC data"""

    def __init__(self, db: AsyncSession, config_id: int, group_id: int):
        self.db = db
        self.config_id = config_id
        self.group_id = group_id

        # Caches
        self._inv_policies: Dict[Tuple[int, int], InvPolicy] = {}
        self._sourcing_rules: Dict[Tuple[int, int], List[SourcingRules]] = {}
        self._nodes: Dict[int, Node] = {}
        self._items: Dict[int, Item] = {}
        self._lanes: Dict[Tuple[int, int], Lane] = {}

        # Cache status
        self._loaded = False

    async def load(self):
        """Preload all reference data (called once at game start)"""
        if self._loaded:
            return

        # Load inventory policies
        result = await self.db.execute(
            select(InvPolicy).filter(
                InvPolicy.config_id == self.config_id,
                InvPolicy.group_id == self.group_id
            )
        )
        for policy in result.scalars():
            key = (policy.product_id, policy.site_id)
            self._inv_policies[key] = policy

        # Load sourcing rules
        result = await self.db.execute(
            select(SourcingRules).filter(
                SourcingRules.config_id == self.config_id,
                SourcingRules.group_id == self.group_id
            )
        )
        for rule in result.scalars():
            key = (rule.product_id, rule.site_id)
            if key not in self._sourcing_rules:
                self._sourcing_rules[key] = []
            self._sourcing_rules[key].append(rule)

        # Load nodes, items, lanes
        # ... (similar pattern)

        self._loaded = True

    def get_inv_policy(self, product_id: int, site_id: int) -> Optional[InvPolicy]:
        """Get cached inventory policy"""
        return self._inv_policies.get((product_id, site_id))

    def get_sourcing_rules(self, product_id: int, site_id: int) -> List[SourcingRules]:
        """Get cached sourcing rules"""
        return self._sourcing_rules.get((product_id, site_id), [])
```

#### B. Batch Operations
```python
async def create_work_orders_batch(
    self,
    player_orders: Dict[str, float],
    round_number: int
) -> int:
    """
    Create multiple work orders in a single batch insert

    Performance: 10-20x faster than individual inserts
    """
    order_date = self.game.start_date + timedelta(days=round_number * 7)

    # Prepare all work orders
    work_orders = []
    for role, order_qty in player_orders.items():
        if order_qty <= 0:
            continue

        node, item, upstream, order_type = await self._get_order_metadata(role)
        lead_time = await self.cache.get_lead_time(item.id, node.id, upstream.id)

        work_order = InboundOrderLine(
            order_id=f"WO_G{self.game.id}_R{round_number}_{role}",
            line_number=1,
            product_id=item.id,
            to_site_id=node.id,
            from_site_id=upstream.id,
            order_type=order_type,
            quantity_submitted=order_qty,
            quantity_confirmed=order_qty,
            expected_delivery_date=order_date + timedelta(days=lead_time),
            submitted_date=order_date,
            status='open',
            group_id=self.group_id,
            config_id=self.config_id,
            game_id=self.game.id,
            round_number=round_number,
            lead_time_days=lead_time
        )
        work_orders.append(work_order)

    # Batch insert
    self.db.add_all(work_orders)
    await self.db.commit()

    return len(work_orders)
```

#### C. Lazy Synchronization
```python
async def sync_inventory_levels_delta(
    self,
    round_number: int,
    changed_players: List[str]
) -> int:
    """
    Only sync inventory for players whose state changed

    Performance: 4x faster for typical rounds (25% of players change)
    """
    # Only update changed players
    records_updated = 0
    for role in changed_players:
        inv_level = await self._get_or_create_inv_level(role, round_number)
        new_qty, new_backlog = self._get_player_inventory_and_backlog(
            player, round_number
        )

        # Update if changed
        if inv_level.on_hand_qty != new_qty or inv_level.backorder_qty != new_backlog:
            inv_level.on_hand_qty = new_qty
            inv_level.backorder_qty = new_backlog
            records_updated += 1

    await self.db.commit()
    return records_updated
```

#### D. Query Optimization
```python
# Add composite indexes for common queries
Index('idx_inbound_order_game_round_status', 'game_id', 'round_number', 'status')
Index('idx_inv_level_game_round_site', 'group_id', 'config_id', 'site_id', 'snapshot_date')

# Use select-in loading for relationships
result = await db.execute(
    select(InboundOrderLine)
    .filter(InboundOrderLine.game_id == game_id)
    .options(selectinload(InboundOrderLine.to_site))
    .options(selectinload(InboundOrderLine.from_site))
)
```

### Performance Targets
| Metric | Current | Target | Improvement |
|--------|---------|--------|-------------|
| Round processing | 500-2000ms | 100-300ms | 5-10x faster |
| Cache hit rate | 0% | >95% | Infinite |
| DB queries/round | 20-50 | 3-8 | 4-10x fewer |
| Batch insert speedup | 1x | 10-20x | 10-20x |

### Files to Modify
- `backend/app/services/aws_sc_planning/execution_cache.py` (NEW)
- `backend/app/services/aws_sc_planning/beer_game_execution_adapter.py` (enhance)
- `backend/app/models/aws_sc_planning.py` (add indexes)

---

## Feature 2: Capacity Constraints

### Problem
Current system allows unlimited production/transfer:
- Factory can produce infinite units
- No queue management
- Unrealistic for supply chain scenarios

### Solution: Capacity Management System

#### A. Capacity Configuration
```python
class ProductionCapacity(Base):
    """Per-site production/transfer capacity limits"""
    __tablename__ = "production_capacity"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("items.id"), nullable=False)

    # Capacity per time bucket (week)
    max_capacity_per_period = Column(Double, nullable=False)  # Max units/week
    current_capacity_used = Column(Double, default=0)  # Currently allocated

    # Capacity type
    capacity_type = Column(String(20))  # 'production', 'transfer', 'storage'

    # Multi-tenancy
    group_id = Column(Integer, ForeignKey("groups.id"))
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))

    __table_args__ = (
        Index('idx_capacity_site_product', 'site_id', 'product_id'),
        Index('idx_capacity_group_config', 'group_id', 'config_id'),
    )
```

#### B. Capacity Check & Allocation
```python
async def create_work_orders_with_capacity(
    self,
    player_orders: Dict[str, float],
    round_number: int
) -> Dict[str, Any]:
    """
    Create work orders respecting capacity constraints

    Returns:
        {
            'created': List[InboundOrderLine],  # Orders that fit
            'queued': List[Dict],  # Orders waiting for capacity
            'rejected': List[Dict],  # Orders that can't be fulfilled
            'capacity_used': Dict[str, float]  # Capacity consumed per site
        }
    """
    created = []
    queued = []
    rejected = []
    capacity_used = {}

    for role, order_qty in player_orders.items():
        node, item, upstream = await self._get_order_metadata(role)

        # Check capacity at upstream site (supplier)
        capacity = await self.cache.get_capacity(upstream.id, item.id)
        if not capacity:
            # No capacity constraint - create order
            work_order = await self._create_single_work_order(
                role, order_qty, round_number
            )
            created.append(work_order)
            continue

        available = capacity.max_capacity_per_period - capacity.current_capacity_used

        if order_qty <= available:
            # Fits in capacity
            work_order = await self._create_single_work_order(
                role, order_qty, round_number
            )
            capacity.current_capacity_used += order_qty
            capacity_used[upstream.name] = capacity.current_capacity_used
            created.append(work_order)
        else:
            # Exceeds capacity
            if available > 0:
                # Partial fulfillment
                partial_order = await self._create_single_work_order(
                    role, available, round_number
                )
                capacity.current_capacity_used = capacity.max_capacity_per_period
                created.append(partial_order)

                # Queue remainder
                queued.append({
                    'role': role,
                    'quantity': order_qty - available,
                    'round': round_number + 1  # Next period
                })
            else:
                # No capacity - queue entire order
                queued.append({
                    'role': role,
                    'quantity': order_qty,
                    'round': round_number + 1
                })

    await self.db.commit()

    return {
        'created': created,
        'queued': queued,
        'rejected': rejected,
        'capacity_used': capacity_used
    }
```

#### C. Capacity Reset
```python
async def reset_period_capacity(self, round_number: int):
    """Reset capacity counters at start of new period"""
    await self.db.execute(
        update(ProductionCapacity)
        .filter(
            ProductionCapacity.group_id == self.group_id,
            ProductionCapacity.config_id == self.config_id
        )
        .values(current_capacity_used=0)
    )
    await self.db.commit()
```

### Files to Create/Modify
- `backend/app/models/aws_sc_planning.py` (add ProductionCapacity model)
- `backend/migrations/versions/20260112_capacity_constraints.py` (NEW)
- `backend/app/services/aws_sc_planning/beer_game_execution_adapter.py` (enhance)

---

## Feature 3: Order Aggregation

### Problem
Creating separate work orders for every player action:
- High transaction overhead
- Unrealistic (real supply chains batch orders)
- Increases database size

### Solution: Order Batching System

#### A. Aggregation Configuration
```python
class OrderAggregationPolicy(Base):
    """Policy for batching orders"""
    __tablename__ = "order_aggregation_policy"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("nodes.id"))
    product_id = Column(Integer, ForeignKey("items.id"))

    # Aggregation rules
    aggregation_window_days = Column(Integer, default=7)  # Batch orders within 7 days
    min_order_quantity = Column(Double, default=0)  # Minimum batch size
    max_order_quantity = Column(Double)  # Maximum batch size

    # Cost savings
    fixed_order_cost = Column(Double, default=100)  # Cost per order
    unit_cost_discount = Column(Double, default=0.05)  # 5% discount for batching

    # Multi-tenancy
    group_id = Column(Integer, ForeignKey("groups.id"))
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
```

#### B. Order Batching Logic
```python
async def aggregate_work_orders(
    self,
    player_orders: Dict[str, float],
    round_number: int
) -> Dict[str, Any]:
    """
    Batch orders to same upstream site

    Example: Retailer orders 8, Wholesaler orders 12 from same Factory
    Result: Single MO work order for 20 units to Factory
    """
    # Group orders by (to_site, from_site, product)
    batches: Dict[Tuple, List] = {}

    for role, order_qty in player_orders.items():
        node, item, upstream, order_type = await self._get_order_metadata(role)

        # Get aggregation policy
        policy = await self.cache.get_aggregation_policy(node.id, item.id)
        if not policy:
            # No aggregation - create individual order
            await self._create_single_work_order(role, order_qty, round_number)
            continue

        # Add to batch
        batch_key = (upstream.id, item.id, order_type)
        if batch_key not in batches:
            batches[batch_key] = []

        batches[batch_key].append({
            'role': role,
            'node_id': node.id,
            'quantity': order_qty
        })

    # Create aggregated orders
    aggregated_orders = []
    for (upstream_id, item_id, order_type), orders in batches.items():
        total_qty = sum(o['quantity'] for o in orders)

        # Create single batched work order
        work_order = InboundOrderLine(
            order_id=f"AGG_G{self.game.id}_R{round_number}_U{upstream_id}",
            line_number=1,
            product_id=item_id,
            to_site_id=None,  # Multiple destinations
            from_site_id=upstream_id,
            order_type=order_type,
            quantity_submitted=total_qty,
            quantity_confirmed=total_qty,
            status='open',
            # Metadata: track constituent orders
            metadata={'constituent_orders': orders},
            group_id=self.group_id,
            config_id=self.config_id,
            game_id=self.game.id,
            round_number=round_number
        )

        self.db.add(work_order)
        aggregated_orders.append(work_order)

    await self.db.commit()

    return {
        'aggregated_orders': aggregated_orders,
        'batches': len(batches),
        'total_orders': sum(len(o) for o in batches.values()),
        'reduction': 1 - (len(batches) / sum(len(o) for o in batches.values()))
    }
```

### Benefits
- **Cost Savings**: Reduce fixed order costs (1 order vs. N orders)
- **Performance**: Fewer DB inserts (1 vs. N)
- **Realism**: Mirrors real supply chain practices

---

## Feature 4: Advanced Scheduling

### Problem
Current system uses simple fixed lead times:
- No periodic ordering policies (e.g., order every 2 weeks)
- No delivery time windows
- Can't model JIT or VMI strategies

### Solution: Scheduling System

#### A. Sourcing Schedules
```python
async def apply_sourcing_schedules(
    self,
    round_number: int
) -> List[InboundOrderLine]:
    """
    Generate orders based on periodic schedules

    Example: "Order from Factory every 2 weeks, quantity = forecast + safety stock"
    """
    scheduled_orders = []

    # Get all sourcing schedules for this config
    schedules = await self.cache.get_sourcing_schedules()

    for schedule in schedules:
        # Check if this round matches schedule frequency
        if round_number % schedule.frequency_weeks != 0:
            continue  # Not time to order yet

        # Calculate order quantity based on schedule logic
        order_qty = await self._calculate_scheduled_quantity(
            schedule, round_number
        )

        if order_qty > 0:
            work_order = InboundOrderLine(
                order_id=f"SCHED_{schedule.id}_R{round_number}",
                product_id=schedule.product_id,
                to_site_id=schedule.site_id,
                from_site_id=schedule.supplier_site_id,
                order_type='TO',
                quantity_submitted=order_qty,
                status='open',
                # Schedule metadata
                source='sourcing_schedule',
                source_id=schedule.id,
                group_id=self.group_id,
                config_id=self.config_id,
                game_id=self.game.id,
                round_number=round_number
            )
            scheduled_orders.append(work_order)

    self.db.add_all(scheduled_orders)
    await self.db.commit()

    return scheduled_orders
```

#### B. Time Window Constraints
```python
async def validate_delivery_windows(
    self,
    work_orders: List[InboundOrderLine]
) -> Dict[str, Any]:
    """
    Ensure orders respect delivery time windows

    Example: "Retailer only accepts deliveries Mon-Fri 8am-5pm"
    """
    valid = []
    rescheduled = []

    for order in work_orders:
        delivery_date = order.expected_delivery_date

        # Check time window constraint
        constraint = await self.cache.get_delivery_window(order.to_site_id)
        if not constraint:
            valid.append(order)
            continue

        # Check if delivery date falls in allowed window
        if self._is_in_delivery_window(delivery_date, constraint):
            valid.append(order)
        else:
            # Reschedule to next available window
            next_available = self._find_next_delivery_window(
                delivery_date, constraint
            )
            order.expected_delivery_date = next_available
            order.earliest_delivery_date = next_available
            rescheduled.append(order)

    await self.db.commit()

    return {
        'valid': valid,
        'rescheduled': rescheduled
    }
```

---

## Feature 5: Analytics & Reporting

### Problem
No visibility into execution performance:
- Can't see order fill rates
- No lead time analysis
- Can't compare execution vs. plan

### Solution: Execution Analytics System

#### A. Order Metrics
```python
class ExecutionMetrics:
    """Calculate execution performance metrics"""

    async def calculate_fill_rate(
        self,
        game_id: int,
        round_start: int,
        round_end: int
    ) -> Dict[str, float]:
        """
        Calculate order fill rate by node

        Fill rate = (quantity delivered) / (quantity requested)
        """
        result = await self.db.execute(
            select(
                OutboundOrderLine.site_id,
                func.sum(OutboundOrderLine.final_quantity_requested).label('requested'),
                func.sum(OutboundOrderLine.quantity_delivered).label('delivered')
            )
            .filter(
                OutboundOrderLine.game_id == game_id,
                OutboundOrderLine.round_number.between(round_start, round_end)
            )
            .group_by(OutboundOrderLine.site_id)
        )

        fill_rates = {}
        for row in result:
            fill_rate = row.delivered / row.requested if row.requested > 0 else 0
            fill_rates[row.site_id] = fill_rate

        return fill_rates

    async def calculate_on_time_delivery(
        self,
        game_id: int,
        round_start: int,
        round_end: int
    ) -> Dict[str, float]:
        """
        Calculate on-time delivery rate

        On-time = orders where actual_date <= expected_date
        """
        result = await self.db.execute(
            select(
                InboundOrderLine.to_site_id,
                func.count().label('total'),
                func.sum(
                    case(
                        (InboundOrderLine.order_receive_date <= InboundOrderLine.expected_delivery_date, 1),
                        else_=0
                    )
                ).label('on_time')
            )
            .filter(
                InboundOrderLine.game_id == game_id,
                InboundOrderLine.round_number.between(round_start, round_end),
                InboundOrderLine.status == 'received'
            )
            .group_by(InboundOrderLine.to_site_id)
        )

        otd_rates = {}
        for row in result:
            otd_rate = row.on_time / row.total if row.total > 0 else 0
            otd_rates[row.to_site_id] = otd_rate

        return otd_rates

    async def calculate_lead_time_stats(
        self,
        game_id: int
    ) -> Dict[str, Dict[str, float]]:
        """
        Analyze lead time performance

        Returns: {site_id: {avg, min, max, std_dev}}
        """
        result = await self.db.execute(
            select(
                InboundOrderLine.to_site_id,
                func.avg(
                    func.datediff(
                        InboundOrderLine.order_receive_date,
                        InboundOrderLine.submitted_date
                    )
                ).label('avg_lead_time'),
                func.min(
                    func.datediff(
                        InboundOrderLine.order_receive_date,
                        InboundOrderLine.submitted_date
                    )
                ).label('min_lead_time'),
                func.max(
                    func.datediff(
                        InboundOrderLine.order_receive_date,
                        InboundOrderLine.submitted_date
                    )
                ).label('max_lead_time'),
                func.stddev(
                    func.datediff(
                        InboundOrderLine.order_receive_date,
                        InboundOrderLine.submitted_date
                    )
                ).label('std_dev')
            )
            .filter(
                InboundOrderLine.game_id == game_id,
                InboundOrderLine.status == 'received'
            )
            .group_by(InboundOrderLine.to_site_id)
        )

        stats = {}
        for row in result:
            stats[row.to_site_id] = {
                'avg': row.avg_lead_time,
                'min': row.min_lead_time,
                'max': row.max_lead_time,
                'std_dev': row.std_dev
            }

        return stats
```

#### B. Execution Dashboard API
```python
# backend/app/api/endpoints/aws_sc_analytics.py

@router.get("/games/{game_id}/execution-metrics")
async def get_execution_metrics(
    game_id: int,
    round_start: Optional[int] = 1,
    round_end: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive execution metrics for a game

    Returns:
        - Fill rates by node
        - On-time delivery rates
        - Lead time statistics
        - Capacity utilization
        - Order aggregation efficiency
    """
    metrics_service = ExecutionMetrics(db)

    fill_rates = await metrics_service.calculate_fill_rate(
        game_id, round_start, round_end or 999
    )

    otd_rates = await metrics_service.calculate_on_time_delivery(
        game_id, round_start, round_end or 999
    )

    lead_time_stats = await metrics_service.calculate_lead_time_stats(game_id)

    return {
        "game_id": game_id,
        "rounds": {
            "start": round_start,
            "end": round_end
        },
        "fill_rates": fill_rates,
        "on_time_delivery": otd_rates,
        "lead_time_stats": lead_time_stats
    }
```

#### C. Frontend Visualization
```javascript
// frontend/src/components/aws-sc/ExecutionDashboard.jsx

export function ExecutionDashboard({ gameId }) {
  const [metrics, setMetrics] = useState(null);

  useEffect(() => {
    fetch(`/api/v1/aws-sc/games/${gameId}/execution-metrics`)
      .then(res => res.json())
      .then(data => setMetrics(data));
  }, [gameId]);

  return (
    <Grid container spacing={3}>
      <Grid item xs={12} md={6}>
        <Card>
          <CardHeader title="Fill Rates by Node" />
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={formatFillRates(metrics?.fill_rates)}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="node" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="fillRate" fill="#8884d8" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card>
          <CardHeader title="On-Time Delivery" />
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={formatOTD(metrics?.on_time_delivery)}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  fill="#82ca9d"
                  label
                />
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12}>
        <Card>
          <CardHeader title="Lead Time Analysis" />
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={formatLeadTime(metrics?.lead_time_stats)}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="node" />
                <YAxis label={{ value: 'Days', angle: -90 }} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="avg" stroke="#8884d8" name="Average" />
                <Line type="monotone" dataKey="min" stroke="#82ca9d" name="Min" />
                <Line type="monotone" dataKey="max" stroke="#ffc658" name="Max" />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
}
```

---

## Feature 6: Integration Testing

### Test Suite Structure

#### A. Dual-Mode Comparison Test
```python
# backend/tests/integration/test_aws_sc_dual_mode.py

async def test_10_round_comparison():
    """
    Run 10 rounds in both legacy and execution mode
    Verify results are equivalent
    """
    # Setup
    game_legacy = create_game(use_aws_sc_planning=False)
    game_execution = create_game(use_aws_sc_planning=True)

    # Run 10 rounds
    for round_num in range(1, 11):
        # Legacy
        legacy_result = await run_round(game_legacy, round_num)

        # Execution
        execution_result = await run_round(game_execution, round_num)

        # Compare
        assert_inventory_match(legacy_result, execution_result)
        assert_orders_match(legacy_result, execution_result)
        assert_costs_match(legacy_result, execution_result)

    # Final comparison
    assert_final_scores_match(game_legacy, game_execution)
```

#### B. Performance Benchmark
```python
async def test_performance_benchmark():
    """
    Measure performance improvements from Phase 3
    """
    game = create_game(use_aws_sc_planning=True)

    # Measure round processing time
    times = []
    for round_num in range(1, 21):
        start = time.time()
        await run_round(game, round_num)
        elapsed = time.time() - start
        times.append(elapsed)

    avg_time = sum(times) / len(times)

    # Assertions
    assert avg_time < 300, f"Average round time {avg_time}ms exceeds target 300ms"
    assert max(times) < 500, f"Max round time {max(times)}ms exceeds target 500ms"
```

#### C. Capacity Constraints Test
```python
async def test_capacity_constraints():
    """
    Verify capacity limits are enforced
    """
    game = create_game(use_aws_sc_planning=True)

    # Set capacity limit at Factory
    await set_capacity(game, site="Factory", max_capacity=20)

    # Try to order 30 units (exceeds capacity)
    result = await create_work_orders(
        game,
        player_orders={'Distributor': 30},
        round_number=1
    )

    # Assertions
    assert len(result['created']) == 1
    assert result['created'][0].quantity_submitted == 20  # Capped at capacity
    assert len(result['queued']) == 1
    assert result['queued'][0]['quantity'] == 10  # Remainder queued
```

---

## Implementation Timeline

### Sprint 1: Performance (Week 1)
- Day 1-2: Implement `ExecutionCache` class
- Day 3: Add batch operations
- Day 4: Add lazy synchronization
- Day 5: Query optimization + testing

### Sprint 2: Capacity (Week 2)
- Day 1-2: Create `ProductionCapacity` model + migration
- Day 3: Implement capacity checking logic
- Day 4: Add capacity allocation/reset
- Day 5: Testing + validation

### Sprint 3: Aggregation & Scheduling (Week 3)
- Day 1-2: Implement order aggregation
- Day 3: Add sourcing schedules
- Day 4: Add time window constraints
- Day 5: Integration testing

### Sprint 4: Analytics (Week 4)
- Day 1-2: Implement metrics calculations
- Day 3: Create analytics API endpoints
- Day 4: Build frontend dashboard
- Day 5: Polish + documentation

### Sprint 5: Testing & Polish (Week 5)
- Day 1-2: Integration test suite
- Day 3: Performance benchmarking
- Day 4: Bug fixes
- Day 5: Documentation + Phase 3 completion report

---

## Success Criteria

### Performance
- [ ] Round processing time < 300ms average
- [ ] Cache hit rate > 95%
- [ ] DB queries reduced by 75%

### Capacity
- [ ] Capacity limits enforced correctly
- [ ] Queued orders handled properly
- [ ] Capacity resets at period boundaries

### Aggregation
- [ ] Orders batched by upstream site
- [ ] Reduction in order count > 50%
- [ ] Cost savings tracked

### Scheduling
- [ ] Periodic orders generated correctly
- [ ] Time windows enforced
- [ ] No delivery conflicts

### Analytics
- [ ] Fill rate calculated accurately
- [ ] On-time delivery tracked
- [ ] Lead time stats available
- [ ] Dashboard displays metrics

### Testing
- [ ] Dual-mode comparison passes (10 rounds)
- [ ] Performance benchmarks pass
- [ ] Edge cases handled
- [ ] No regressions in Phase 2 functionality

---

## Files to Create

### Backend
1. `backend/app/services/aws_sc_planning/execution_cache.py` (300 lines)
2. `backend/app/services/aws_sc_planning/execution_metrics.py` (400 lines)
3. `backend/app/api/endpoints/aws_sc_analytics.py` (250 lines)
4. `backend/migrations/versions/20260112_capacity_constraints.py` (150 lines)
5. `backend/migrations/versions/20260112_order_aggregation.py` (120 lines)
6. `backend/tests/integration/test_aws_sc_phase3.py` (500 lines)

### Frontend
1. `frontend/src/components/aws-sc/ExecutionDashboard.jsx` (300 lines)
2. `frontend/src/components/aws-sc/MetricsCard.jsx` (150 lines)
3. `frontend/src/components/aws-sc/LeadTimeChart.jsx` (200 lines)

### Documentation
1. `AWS_SC_PHASE3_COMPLETE.md` (800 lines)
2. `AWS_SC_ANALYTICS_GUIDE.md` (400 lines)
3. `AWS_SC_PERFORMANCE_TUNING.md` (350 lines)

**Total**: ~3,920 lines (estimated)

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Performance gains don't materialize | Medium | High | Benchmark early, adjust approach |
| Capacity logic breaks game balance | Medium | Medium | Extensive testing, make optional |
| Caching introduces stale data bugs | Low | High | Strict cache invalidation, tests |
| Analytics queries slow down DB | Low | Medium | Proper indexing, query optimization |
| Integration tests fail | Medium | Medium | Incremental testing, rollback plan |

---

## Dependencies

### External
- None (all features use existing dependencies)

### Internal
- Phase 2 complete ✅
- Database migration system working
- Async SQLAlchemy patterns established

---

## Next Steps

1. **User approval** of this implementation plan
2. **Start Sprint 1**: Performance optimization
3. **Iterative development**: Ship each feature independently
4. **Continuous testing**: Validate after each sprint
5. **Phase 3 completion**: All features delivered and tested

---

**Plan Status**: 📋 **READY FOR APPROVAL**
**Created**: 2026-01-12
**Author**: Claude Sonnet 4.5
**Estimated Duration**: 5 weeks (1 sprint per week)
**Estimated LOC**: ~3,920 lines
