# Available-to-Promise (ATP), Capable-to-Promise (CTP), and Allocated ATP (AATP)

## Comprehensive Reference Guide for Order Promising

---

## 1. Definitions

### Available-to-Promise (ATP)
ATP is the uncommitted portion of a company's inventory and planned production, maintained in the master schedule to support customer-order promising. ATP answers: **"Can we fulfill this order from existing supply?"**

ATP = On-Hand Inventory + Planned Receipts − Committed Orders (within a given time bucket)

### Capable-to-Promise (CTP)
CTP extends ATP by checking whether the company **can produce or procure** the required quantity if ATP is insufficient. CTP runs a finite-capacity MRP/scheduling check to determine if materials and capacity exist to fulfill the order by a requested date. CTP answers: **"If we don't have it, can we make/buy it in time?"**

### Allocated Available-to-Promise (AATP)
AATP pre-allocates ATP quantities across customer segments, channels, or priority classes **before** orders arrive. This ensures high-priority customers receive preferential access to constrained supply. AATP answers: **"Who gets supply first when demand exceeds availability?"**

---

## 2. ATP Calculation Methods

### 2.1 Discrete ATP (Standard)

Calculated per MPS bucket. ATP is computed for each bucket where there is a new MPS receipt:

```
ATP₁ = On-Hand + MPS₁ − Σ(Customer Orders before next MPS receipt)

ATPₙ = MPSₙ − Σ(Customer Orders between MPSₙ₋₁ and MPSₙ)
```

**Rules**:
- ATP is only calculated in periods with MPS receipts
- Customer orders are consumed against the earliest ATP bucket
- Negative ATP in any bucket is netted against previous buckets
- ATP cannot go negative — if it would, the order is rejected or rescheduled

### 2.2 Cumulative ATP

Cumulative ATP sums available quantities across all buckets up to a given period:

```
Cumulative ATPₙ = Σᵢ₌₁ⁿ ATPᵢ
```

This provides a running total view useful for promising orders across multiple periods.

### 2.3 ATP with Look-Ahead

Extends discrete ATP by looking forward to check if future supply can cover current demand shortfalls:

```
If ATP_current < 0:
    Borrow from ATP_future (with lead time offset)
    ATP_current = 0
    ATP_future = ATP_future - borrowed
```

### 2.4 Backward Consumption

Orders are first consumed against the requested delivery period, then consume backward (earlier periods) if the requested period's ATP is insufficient:

```
For order in period t:
    Consume ATP[t] first
    If remaining > 0: consume ATP[t-1], ATP[t-2], ...
    Stop at frozen fence
```

### 2.5 Forward Consumption

If the requested period has insufficient ATP, consume from future periods:

```
For order in period t:
    Consume ATP[t] first
    If remaining > 0: consume ATP[t+1], ATP[t+2], ...
    Propose later delivery date
```

---

## 3. ATP Example Calculation

| Period | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|--------|---|---|---|---|---|---|---|---|
| **On-Hand** | 50 | | | | | | | |
| **MPS** | | | 60 | | | 60 | | 60 |
| **Customer Orders** | 20 | 10 | 30 | 15 | 5 | 10 | 5 | 0 |
| **ATP** | 20 | | 10 | | | 45 | | 60 |

**Calculation**:
- ATP₁ = 50 (on-hand) − 20 (P1) − 10 (P2) = 20
- ATP₃ = 60 (MPS) − 30 (P3) − 15 (P4) − 5 (P5) = 10
- ATP₆ = 60 (MPS) − 10 (P6) − 5 (P7) = 45
- ATP₈ = 60 (MPS) − 0 (P8) = 60

**Total ATP = 135 units** available for new customer order promises.

---

## 4. CTP Process Flow

CTP is triggered when ATP check fails (insufficient quantity):

```
1. Order received → Check ATP
2. ATP sufficient? → YES → Promise order (ATP consumption)
3. ATP sufficient? → NO → Trigger CTP check
4. CTP Check:
   a. Check material availability (BOM explosion)
   b. Check supplier capacity (purchase lead times)
   c. Check production capacity (finite scheduling)
   d. Check logistics capacity (transportation)
5. All resources available? → YES → Promise with CTP date
6. All resources available? → NO →
   a. Propose partial fulfillment
   b. Propose alternative date
   c. Propose substitute product
   d. Reject order
```

### CTP Components

| Component | Check | Data Source |
|-----------|-------|-------------|
| **Material CTP** | Raw material and component availability | MRP, purchase orders, supplier capacity |
| **Capacity CTP** | Production resource availability | Finite capacity scheduling, work center calendars |
| **Transport CTP** | Logistics capacity and transit time | Transportation planning, carrier capacity |
| **Storage CTP** | Warehouse space availability | Warehouse management system |

### CTP vs ATP Decision Matrix

| Scenario | ATP | CTP | Action |
|----------|-----|-----|--------|
| Stock available | ✅ Sufficient | Not needed | Promise from ATP |
| No stock, can produce | ❌ Insufficient | ✅ Feasible | Promise with CTP date |
| No stock, partial possible | ❌ Insufficient | ⚠️ Partial | Offer partial + backorder |
| No stock, cannot produce | ❌ Insufficient | ❌ Infeasible | Propose alternative or reject |

---

## 5. AATP (Allocated Available-to-Promise)

### 5.1 Concept

AATP segments available supply into **priority buckets** before orders arrive:

```
Total ATP = 1000 units

Allocation:
  Priority 1 (Strategic Accounts): 400 units (40%)
  Priority 2 (Key Accounts): 300 units (30%)
  Priority 3 (Standard): 200 units (20%)
  Priority 4 (Spot/Distributor): 100 units (10%)
```

### 5.2 AATP Consumption Logic

When an order arrives at priority P, the consumption sequence is:

```python
# AATP Consumption Sequence for order at priority P:
# 1. Own tier (P) first
# 2. Bottom-up from lowest priority (N, N-1, ..., P+1)
# 3. NEVER consume from higher priority (P-1, P-2, ..., 1)

def consume_aatp(order_priority, order_qty, allocations):
    """
    Consume AATP following priority consumption rules.

    Args:
        order_priority: Priority level of the incoming order (1=highest)
        order_qty: Quantity requested
        allocations: Dict of {priority: available_qty}

    Returns:
        consumed: Dict of {priority: consumed_qty}
        remaining: Unfulfilled quantity
    """
    remaining = order_qty
    consumed = {}

    # Step 1: Consume from own tier first
    own_available = allocations.get(order_priority, 0)
    own_consume = min(remaining, own_available)
    if own_consume > 0:
        consumed[order_priority] = own_consume
        remaining -= own_consume

    # Step 2: Bottom-up from lowest priority, skip own tier
    max_priority = max(allocations.keys())
    for p in range(max_priority, order_priority, -1):
        if remaining <= 0:
            break
        p_available = allocations.get(p, 0)
        p_consume = min(remaining, p_available)
        if p_consume > 0:
            consumed[p] = p_consume
            remaining -= p_consume

    # Step 3: NEVER consume above own priority
    return consumed, remaining

# Example: Priority 2 order for 350 units
# Allocations: P1=400, P2=300, P3=200, P4=100
# Consumption: P2(300) → P4(50) → remaining 0
# Result: Fulfilled from P2=300, P4=50. P1 untouched.
```

### 5.3 AATP Allocation Dimensions

AATP allocations can be segmented across multiple dimensions:

| Dimension | Examples |
|-----------|----------|
| **Customer Priority** | Strategic, Key, Standard, Spot |
| **Channel** | Direct, Distributor, E-commerce, Export |
| **Geography** | Region, Country, Territory |
| **Product** | Product family, SKU group |
| **Time** | Weekly, Monthly allocation buckets |

### 5.4 AATP Rule Types

| Rule Type | Description | Use Case |
|-----------|-------------|----------|
| **Fixed Allocation** | Absolute quantity reserved per segment | Critical customers with contractual minimums |
| **Proportional** | % of total ATP per segment | Fair-share across channels |
| **Priority-Based** | Sequential consumption by priority | Constrained supply situations |
| **Time-Fenced** | Different rules for different horizons | Short-term fixed, long-term flexible |
| **Minimum/Maximum** | Floor and ceiling per segment | Prevent starvation/hoarding |

---

## 6. Multi-Site ATP

### 6.1 Global ATP Check

For multi-site supply chains, ATP must be checked across the network:

```
1. Check local site ATP (requested fulfillment location)
2. If insufficient → Check alternative sites (per sourcing rules)
3. If found at alternative site → Add transfer lead time
4. Promise date = max(availability date, transfer time + today)
```

### 6.2 ATP Aggregation Hierarchy

```
Enterprise ATP (all sites combined)
    ├── Region ATP (sites within region)
    │       ├── DC ATP (specific distribution center)
    │       └── Plant ATP (manufacturing site)
    └── Channel ATP (by sales channel)
```

### 6.3 Multi-Site Sourcing Rules

| Rule | Description |
|------|-------------|
| **Preferred Source** | Check primary site first, fallback to alternates |
| **Closest Location** | Check site nearest to customer |
| **Least Cost** | Check site with lowest total cost to serve |
| **Load Balancing** | Distribute orders across sites to balance utilization |
| **Split Fulfillment** | Allow partial from multiple sites |

---

## 7. ATP in SAP IBP / SAP S/4HANA

### SAP ATP Methods

| Method | SAP Module | Description |
|--------|-----------|-------------|
| **Basic ATP** | S/4HANA MM/SD | Simple stock and receipt check |
| **Product Allocation** | S/4HANA SD | AATP with customer/channel allocation |
| **Rules-Based ATP** | SAP IBP | Multi-level ATP with business rules |
| **gATP** | SAP APO/IBP | Global ATP across multiple plants/DCs |
| **Backorder Processing** | SAP IBP | Automated rescheduling of confirmed orders |

### SAP IBP ATP Configuration

Key configuration objects:
- **Planning Area**: Time buckets, key figures for ATP quantities
- **Product Allocation**: Allocation hierarchy (customer group → material group)
- **Business Rules**: Consumption logic, substitution, partial delivery
- **Scope of Check**: Which supply elements to include (stock, planned orders, purchase orders)

---

## 8. ATP in Kinaxis RapidResponse

Kinaxis implements ATP as part of concurrent planning:

- **Real-Time ATP**: Instant recalculation on any data change
- **What-If ATP**: Test order promising scenarios before commitment
- **Multi-Tier ATP**: Check availability across BOMs and supply network
- **Constrained ATP**: Factor in material, capacity, and logistics constraints simultaneously
- **Rule Engine**: Configurable consumption, allocation, and substitution rules

---

## 9. Key Metrics for Order Promising

| Metric | Formula | Target |
|--------|---------|--------|
| **Order Promise Rate** | Orders promised / Orders received | > 95% |
| **Promise Accuracy** | Orders delivered as promised / Orders promised | > 98% |
| **ATP Coverage** | ATP quantity / Expected demand | > 1.0 |
| **CTP Conversion Rate** | CTP orders fulfilled / CTP orders triggered | > 80% |
| **AATP Utilization** | Allocated consumed / Allocated total | 70-90% |
| **Promise Lead Time** | Time from order receipt to promise confirmation | < 1 hour |
| **Rescheduling Rate** | Promised orders rescheduled / Total promised | < 5% |

---

## 10. ATP Integration with Planning Hierarchy

```
S&OP / IBP (Monthly)
    ↓ Demand plan + Supply authorization
Master Production Schedule (Weekly)
    ↓ Planned production receipts
ATP / AATP (Real-time / Daily)
    ↓ Order promises
MRP (Daily / Weekly)
    ↓ Component requirements
Execution (Continuous)
    ↓ Purchase orders, production orders, transfer orders
```

**Key Integration Points**:
- MPS provides planned receipts that feed ATP calculation
- ATP consumption triggers MRP regeneration when supply is committed
- AATP allocations are set during S&OP based on demand segmentation
- CTP triggers finite scheduling and MRP simulation on-demand

---

## 11. Advanced ATP Concepts

### 11.1 Profitable-to-Promise (PTP)

Extends ATP/CTP by evaluating **profitability** of fulfilling an order:
- Calculate margin impact of each fulfillment option
- Consider opportunity cost of consuming ATP (could a more profitable order arrive later?)
- Factor in expedite costs, penalty costs, and substitution costs

### 11.2 Capable-to-Match (CTM)

Used in process industries where substitution is common:
- Matches orders to supply considering product substitutability
- Optimizes across all open orders simultaneously (not one-at-a-time)
- Uses linear programming to maximize total fulfilled demand

### 11.3 Real-Time ATP

Modern platforms compute ATP in real-time (sub-second):
- In-memory data structures for instant recalculation
- Event-driven updates on any transaction (order, receipt, cancellation)
- Concurrent users with pessimistic/optimistic locking

### 11.4 Probabilistic ATP

Incorporates uncertainty into ATP calculations:
- Supply uncertainty: planned receipts may be delayed or short-shipped
- Demand uncertainty: forecast orders have probability weights
- Result: ATP expressed as probability distribution (e.g., "90% confidence of 500 units by Week 12")

---

## 12. Common ATP Pitfalls

1. **ATP not refreshed**: Stale ATP data leads to over-promising
2. **No allocation rules**: First-come-first-served starves strategic customers
3. **Ignoring transit time**: ATP at a remote site without lead time offset
4. **No safety stock protection**: ATP consuming safety stock intended for forecast demand
5. **Manual overrides without tracking**: Bypassing AATP rules without audit trail
6. **CTP without capacity check**: Promising production without validating resource availability
7. **No backlog management**: Old unfulfilled promises consuming future ATP

---

*Sources: ASCM CPIM Part 2 (MPR Module), ETH Zurich OPESS Course, SAP IBP Documentation, Kinaxis RapidResponse, Sana Commerce ATP Guide*
