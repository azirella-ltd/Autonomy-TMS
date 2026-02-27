# Planning Cascade Demo - Captured Output

**Autonomy Platform - Distributor Prototype**

*Demo captured: February 2026*

---

## Overview: Planning Cascade Flow

```
Planning Cascade
├── 📋 S&OP Policy Envelope (θ_SOP)
│   └── Service tiers, safety stock targets, expedite caps
├── 📦 MPS / Supply Baseline Pack (SupBP)
│   └── 5 candidate methods with tradeoff frontier
├── 🚚 Supply Agent → Supply Commit (SC)
│   └── PO recommendations with integrity/risk checks
├── 📊 Allocation Agent → Allocation Commit (AC)
│   └── Segment allocations with priority sequencing
└── ⚡ Execution
    └── Feed-back signals for re-tuning
```

**Key Architecture Points:**
- **Feed-Forward Contracts**: Each layer produces hash-linked artifacts (traceable decisions)
- **Feed-Back Signals**: Execution outcomes re-tune upstream parameters
- **Dual-Mode Architecture**:
  - **INPUT mode**: Customer provides S&OP params + MRP output
  - **FULL mode**: Autonomy simulation optimizes all layers

---

## Step 1: S&OP Policy Envelope

**Purpose**: Define the "guardrails" that govern all downstream decisions.

### Service Level Targets by Segment

| Segment | OTIF Floor | Fill Rate Target |
|---------|------------|------------------|
| STRATEGIC | 99% | 99% |
| STANDARD | 95% | 98% |
| TRANSACTIONAL | 90% | 95% |

### Inventory Policies by Category

| Category | Safety Stock (WOS) | DOS Ceiling | Expedite Cap |
|----------|-------------------|-------------|--------------|
| Frozen Proteins | 2.0 weeks | 21 days | $15,000 |
| Refrigerated Dairy | 1.5 weeks | 14 days | $10,000 |
| Dry Pantry | 3.0 weeks | 45 days | $5,000 |
| Frozen Desserts | 2.0 weeks | 28 days | $8,000 |
| Beverages | 2.5 weeks | 35 days | $6,000 |

### Financial Guardrails (θ_SOP Parameters)

- **Total Inventory Cap**: $2,500,000
- **GMROI Target**: 3.0x

---

## Step 2: Current Inventory State

**Purpose**: Snapshot of 25 SKUs with inventory position and demand.

### Inventory State (Sample - 10 of 25 SKUs)

| SKU | Name | Category | On Hand | In Transit | Avg Daily Demand | DOS |
|-----|------|----------|---------|------------|------------------|-----|
| FP001 | Chicken Breast IQF | frz_protein | 398 | 87 | 21.4 | 18.6 days |
| FP002 | Beef Patties 80/20 | frz_protein | 450 | 89 | 17.1 | 26.3 days |
| FP003 | Pork Chops Bone-In | frz_protein | 159 | 48 | 11.4 | 13.9 days |
| FP004 | Turkey Breast Deli | frz_protein | 179 | 50 | 8.6 | 20.8 days |
| FP005 | Seafood Mix Premium | frz_protein | 177 | 19 | 5.7 | 31.1 days |
| RD001 | Cheddar Block Sharp | ref_dairy | 383 | 162 | 28.6 | 13.4 days |
| RD002 | Mozzarella Block LMPS | ref_dairy | 1,134 | 245 | 35.7 | 31.8 days |
| RD003 | Cream Cheese Block | ref_dairy | 443 | 146 | 25.7 | 17.2 days |
| RD004 | Greek Yogurt Plain | ref_dairy | 1,189 | 233 | 42.9 | 27.7 days |
| RD005 | Butter Salted Grade AA | ref_dairy | 167 | 93 | 14.3 | 11.7 days |

### Demand by Customer Segment (Weekly)

- **Strategic**: 1,002 units
- **Standard**: 1,670 units
- **Transactional**: 668 units

---

## Step 3: Supply Baseline Pack (SupBP) Candidates

**Purpose**: In FULL mode, generate 5 different supply plans to show cost vs. service tradeoffs.

### Candidate Supply Plans (Tradeoff Frontier)

| Method | Description | Est. Cost | Est. OTIF |
|--------|-------------|-----------|-----------|
| REORDER_POINT | Classic (r, Q) policy with safety stock buffer | $125,000 | 94% |
| PERIODIC_REVIEW | (R, S) policy with fixed review intervals | $118,000 | 95% |
| MIN_COST_EOQ | Economic Order Quantity minimizing total cost | $105,000 | 92% |
| SERVICE_MAXIMIZED | Maximize service level within budget | $142,000 | 98% |
| **PARAMETRIC_CFA** | **Powell CFA with learned θ parameters** | **$115,000** | **96%** |

### Tradeoff Frontier Visualization

```
OTIF ▲
 98% │              ● SERVICE_MAXIMIZED ($142K)
     │
 96% │     ● PARAMETRIC_CFA ($115K) ← SELECTED
     │
 95% │        ● PERIODIC_REVIEW ($118K)
     │
 94% │  ● REORDER_POINT ($125K)
     │
 92% │● MIN_COST_EOQ ($105K)
     └──────────────────────────────────────► Cost
        $100K    $120K    $140K
```

### Mode Comparison

| INPUT Mode | FULL Mode |
|------------|-----------|
| Customer uploads their existing MRP output | System generates 5 candidates for tradeoff analysis |

---

## Step 4: Supply Agent → Supply Commit (SC)

**Purpose**: AI agent selects optimal method, validates decisions, and explains reasoning.

### 🤖 Agent Reasoning Panel

**Why Did The Agent Choose This?**

```
AGENT REASONING

Decision Summary:
Selected PARAMETRIC_CFA method based on optimal cost-service tradeoff.
This method uses learned θ parameters from CFA optimization.

Key Factors:
• Cost optimization (weight: 0.4)
• Service level constraints (weight: 0.35)
• Lead time feasibility (weight: 0.25)

Confidence Score: 87%
Based on data quality and model fit for current demand patterns
```

### Supply Commit Summary

| Metric | Value |
|--------|-------|
| Selected Method | PARAMETRIC_CFA (best cost/service balance) |
| Generated POs | 47 purchase orders |
| Total Order Value | $115,000 |
| Projected OTIF | 96% |
| Projected DOS | 18.5 days |

### Integrity Checks (Blocking)

These checks **must pass** for submission:

- ✓ No negative inventory projections
- ✓ All orders within lead time feasibility
- ✓ All orders meet MOQ requirements

### Risk Flags (Advisory)

These flags **suggest review** but don't block:

- ⚠ **SERVICE_RISK**: FP003 (Pork Chops) projected OTIF 89% < 90% floor
- ⚠ **DOS_CEILING**: DP002 (Rice) projected DOS 48 > 45 day ceiling

### Supply Commit Status

- **Status**: PENDING_REVIEW
- **Requires Review**: Yes (2 risk flags)

---

## 👤 Human-in-the-Loop Override

**Purpose**: Allow humans to adjust agent recommendations with full traceability.

### User Review Actions

| Action | Description |
|--------|-------------|
| **Accept** | Accept agent recommendation unchanged |
| **Override** | Make any changes (adjustments to complete replacement) |

### Example Adjustment Table

| SKU | Agent Qty | Your Adj | Change | Rationale |
|-----|-----------|----------|--------|-----------|
| FP003 | 500 | 600 | +20% | Low ROP risk |
| DP002 | 300 | 250 | -17% | DOS ceiling |
| BV001 | 400 | 400 | — | (no change) |

> User's adjustments are tracked and compared to agent baseline for continuous learning and agent performance scoring

### Key Governance Benefits

1. **Agent Owns Decision** - AI makes the primary recommendation
2. **Human Has Final Say** - Approval authority with adjustment capability
3. **Full Audit Trail** - All changes tracked with rationale
4. **Learning Feedback** - Overrides train future agent decisions

---

## Step 5: Allocation Agent → Allocation Commit (AC)

**Purpose**: Distribute committed supply across customer segments based on OTIF floors.

### Allocation by Customer Segment

| Segment | Requested | Allocated | Fill Rate | OTIF Floor | Status |
|---------|-----------|-----------|-----------|------------|--------|
| Strategic | 45,000 | 44,800 | 99.6% | 99% | ✓ |
| Standard | 75,000 | 73,500 | 98.0% | 95% | ✓ |
| Transactional | 30,000 | 27,000 | 90.0% | 90% | ⚠ |

### Allocation Details

- **Allocation Method**: PRIORITY_HEURISTIC
- **Logic**: Strategic → Standard → Transactional (OTIF floors honored)

### Integrity Checks

- ✓ Supply conservation maintained (allocated ≤ available)
- ✓ All segment OTIF floors met

### Allocation Commit Status

- **Status**: APPROVED
- **Ready for Execution**: Yes

### Key Insight

Transactional segment is **at the floor** (90.0% = 90% target). This is **intentional** - we prioritize Strategic and Standard customers. The system will NOT over-serve lower-tier customers at the expense of higher-tier ones.

---

## Step 6: Feed-Back Signals (Execution → Re-tuning)

**Purpose**: Continuous improvement loop from actual execution outcomes.

### Feed-Back Signals from Last Execution Cycle

| Signal Type | Metric | Value | Threshold | Fed Back To |
|-------------|--------|-------|-----------|-------------|
| ACTUAL_OTIF | Strategic OTIF | 98.5% | 99% | Supply Agent |
| EXPEDITE_FREQUENCY | Frozen expedites/week | 3.2 | 2.0 | S&OP |
| EO_WRITEOFF | E&O write-off % | 0.8% | 1.0% | S&OP |
| ALLOCATION_SHORTFALL | Transactional shortfall | 4.2% | 5.0% | Supply Agent |

### Re-tuning Recommendations

Based on the signals above:

- **Expedite frequency above target** → Consider increasing safety stock for frozen category
- **Strategic OTIF slightly below floor** → Review allocation reserves

### How Feed-Back Works

1. **Execution outcomes** are captured (actual OTIF, expedites, write-offs)
2. **Deviations from targets** become signals fed back to upstream layers
3. **S&OP parameters** are adjusted (safety stock, DOS ceilings, expedite caps)
4. **Agent policies** learn from patterns (better future decisions)

---

## Value Proposition Summary

| Traditional Systems | Autonomy |
|--------------------|----------|
| Black box recommendations | Agent reasoning visible |
| Accept or reject only | Granular human adjustment |
| Static parameters | Feed-back driven re-tuning |
| All-or-nothing purchase | Modular: INPUT → FULL upgrade path |

---

## Key Takeaways

1. **Transparency**: AI agents explain their reasoning - no more black boxes
2. **Governance**: Humans accept or override agent recommendations with full audit trail
3. **Traceability**: Hash-linked feed-forward contracts trace every decision
4. **Learning**: Feed-back signals enable continuous improvement
5. **Flexibility**: Same UI works for INPUT mode (customer provides) or FULL mode (Autonomy optimizes)

---

## Running the Demo

### Terminal Demo (No Server Required)
```bash
cd backend
pip install rich  # if not installed
python scripts/demo_planning_cascade.py
```

### Standalone Test
```bash
cd backend
python scripts/test_cascade_standalone.py
```

### Full UI Demo
```bash
make up
# Visit: http://localhost:8088/planning/cascade-dashboard
```

---

## Technical Reference

### API Endpoints

- `POST /api/v1/planning-cascade/run` - Run full cascade
- `GET /api/v1/planning-cascade/status/{config_id}` - Get cascade status
- `POST /api/v1/planning-cascade/supply-commit/{id}/review` - Review supply commit
- `GET /api/v1/planning-cascade/worklist/supply/{config_id}` - Supply worklist

### Database Tables

- `policy_envelope` - S&OP parameters
- `supply_baseline_pack` - MPS candidates
- `supply_commit` - Supply agent decisions
- `allocation_commit` - Allocation agent decisions
- `feed_back_signal` - Execution outcomes

### Files

- Backend Services: `backend/app/services/planning_cascade/`
- Frontend Components: `frontend/src/pages/planning/`
- Database Models: `backend/app/models/planning_cascade.py`
- API Endpoints: `backend/app/api/endpoints/planning_cascade.py`
