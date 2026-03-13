# RCCP Implementation Spec — Rough-Cut Capacity Planning

**Status**: SPEC COMPLETE — Ready for execution
**Date**: 2026-03-13
**Depends on**: MPS (implemented), Supply Plan (implemented), Capacity Plan models (implemented)

---

## 1. What RCCP Is and Why It Matters

RCCP is the **capacity feasibility gate** between MPS and MRP. It validates whether the Master Production Schedule can be executed with available aggregate capacity across key (bottleneck) resources — work centers, production lines, labor pools, and shared utilities.

**Why it matters**: Running MRP against an infeasible MPS generates thousands of planned orders that cannot be executed. RCCP catches overloads at the aggregate level (hours, units, tonnes) before detailed scheduling creates cascading infeasibility downstream.

```
Demand Planning
    ↓ consensus demand
Supply Planning / MPS
    ↓ draft MPS (product × site × week quantities)
 ══════════════════════════════════════════════
║  RCCP  ← validates MPS against key resources ║
 ══════════════════════════════════════════════
    ↓ feasibility-adjusted MPS
MRP (net requirements, BOM explosion, planned orders)
    ↓
Execution (PO, MO, TO)
```

If RCCP returns **infeasible**, the MPS must be revised before MRP runs. This prevents the #1 planning failure mode: generating a beautiful MRP plan that the factory physically cannot execute.

---

## 2. Current State (What Exists)

### 2.1 What's Implemented

| Component | File | Status |
|-----------|------|--------|
| `CapacityPlan` model | `backend/app/models/capacity_plan.py` | Complete |
| `CapacityResource` model | `backend/app/models/capacity_plan.py` | Complete |
| `CapacityRequirement` model | `backend/app/models/capacity_plan.py` | Complete |
| `MPSCapacityCheck` model | `backend/app/models/mps.py` | Complete (MPS-specific) |
| Capacity Plan CRUD API | `backend/app/api/endpoints/capacity_plans.py` | Complete |
| `CapacityConstrainedMPS` service | `backend/app/services/capacity_constrained_mps.py` | Standalone, not integrated |
| RCCP Claude Skill | `backend/app/services/skills/rccp/SKILL.md` | Complete (6 rules, 3 methods) |
| Frontend `CapacityCheck.jsx` | `frontend/src/pages/planning/CapacityCheck.jsx` | Demo/placeholder |
| Frontend `CapacityPlanning.jsx` | `frontend/src/pages/planning/CapacityPlanning.jsx` | Exists |

### 2.2 What's Placeholder / Broken

1. **`_calculate_requirements_from_mps()`** in `capacity_plans.py` line 71: Uses `resource.available_capacity * 0.7` (hardcoded 70% utilization) instead of actual product-to-resource consumption rates.

2. **`_calculate_requirements_from_production_orders()`** in `capacity_plans.py` line 127: Uses `planned_quantity * 0.1` (hardcoded 0.1 hours/unit) instead of actual routing data.

3. **`CapacityCheck.jsx`**: Hardcoded demo resources (Assembly Line 0.5 units/product, Labor 0.25 units/product) and hardcoded production plan `[1200, 900, 1000, ...]`.

4. **`CapacityConstrainedMPS` service**: Uses standalone dataclasses (`ResourceRequirement`, `MPSProductionPlan`) disconnected from DB models. Not called by any API endpoint.

### 2.3 Critical Gap: No Bill of Resources (BoR)

The platform has no model linking **products to resource consumption rates**. This is the fundamental missing piece:

- `ProductionProcess` has aggregate `manufacturing_capacity_hours` but no per-work-center breakdown
- `ProductBom` defines material components but not resource/labor requirements
- `CapacityResource` defines available capacity but nothing says "Product X consumes 0.3 hours of Resource Y per unit"

---

## 3. Data Model Changes

### 3.1 New Model: `BillOfResources` (BoR)

The Bill of Resources links products to their resource consumption at each manufacturing site. This is the RCCP equivalent of the BOM — instead of "what materials does this product need?", it answers "what resource hours does this product consume?"

**File**: `backend/app/models/bill_of_resources.py`

```python
"""
Bill of Resources (BoR) — Links products to resource consumption rates.

The BoR is the foundation of RCCP. For each product manufactured at a site,
it defines how much of each resource (work center, labor pool, utility) is
consumed per unit produced.

Three levels of detail (matching the 3 RCCP methods):
  1. CPOF: Only site-level total hours/unit (no resource breakdown)
  2. Bill of Capacity: Hours/unit per resource (recommended default)
  3. Resource Profile: Time-phased hours/unit per resource per production phase

AWS SC Extension: Not a core AWS SC entity. Extension to support capacity planning.
"""

import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, ForeignKey, DateTime,
    Boolean, Enum, JSON, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.db.base_class import Base


class RCCPMethod(str, enum.Enum):
    """RCCP calculation method — determines which BoR fields are used."""
    CPOF = "cpof"                    # Overall factors only
    BILL_OF_CAPACITY = "bill_of_capacity"  # Per-resource hours/unit
    RESOURCE_PROFILE = "resource_profile"  # Time-phased per-resource


class ProductionPhase(str, enum.Enum):
    """Production phases for Resource Profile method."""
    SETUP = "setup"
    RUN = "run"
    TEARDOWN = "teardown"
    QUEUE = "queue"
    MOVE = "move"


class BillOfResources(Base):
    """
    Links a product to a resource with consumption rates.

    One row per (product, site, resource, phase) combination.
    For CPOF method: resource_id is NULL, only overall_hours_per_unit is used.
    For Bill of Capacity: resource_id is set, hours_per_unit is populated.
    For Resource Profile: resource_id + phase + lead_time_offset_days are set.
    """
    __tablename__ = "bill_of_resources"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("product.id"), nullable=False, index=True)
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False, index=True)

    # Resource link (NULL for CPOF method — site-level aggregate only)
    resource_id = Column(Integer, ForeignKey("capacity_resources.id"), nullable=True, index=True)

    # --- CPOF fields ---
    overall_hours_per_unit = Column(Float, nullable=True,
        comment="Total resource hours per product unit (CPOF method)")

    # --- Bill of Capacity fields ---
    hours_per_unit = Column(Float, nullable=True,
        comment="Hours of THIS resource consumed per product unit")
    setup_hours_per_batch = Column(Float, default=0.0,
        comment="Fixed setup hours per production batch on this resource")
    typical_batch_size = Column(Float, default=1.0,
        comment="Typical batch size for amortizing setup time")

    # --- Resource Profile fields ---
    phase = Column(Enum(ProductionPhase), nullable=True,
        comment="Production phase (setup/run/teardown/queue/move)")
    lead_time_offset_days = Column(Integer, default=0,
        comment="Days before MPS receipt date when this resource is consumed")
    phase_hours_per_unit = Column(Float, nullable=True,
        comment="Hours consumed during this specific phase")

    # --- Metadata ---
    is_critical = Column(Boolean, default=False,
        comment="True if this is a bottleneck/critical resource for RCCP")
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)

    # Production process link (optional — for traceability to routing)
    production_process_id = Column(Integer, ForeignKey("production_process.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    product = relationship("Product", back_populates="bill_of_resources")
    site = relationship("Node")
    resource = relationship("CapacityResource")
    config = relationship("SupplyChainConfig")
    production_process = relationship("ProductionProcess")

    __table_args__ = (
        UniqueConstraint(
            "config_id", "product_id", "site_id", "resource_id", "phase",
            name="uq_bor_product_site_resource_phase"
        ),
    )

    @property
    def effective_hours_per_unit(self) -> float:
        """
        Effective hours per unit including amortized setup.
        Used by Bill of Capacity method.
        """
        base = self.hours_per_unit or self.phase_hours_per_unit or self.overall_hours_per_unit or 0.0
        if self.setup_hours_per_batch and self.typical_batch_size:
            base += self.setup_hours_per_batch / self.typical_batch_size
        return base
```

### 3.2 New Model: `RCCPRun`

Captures the result of an RCCP validation run against an MPS plan. Separate from `CapacityPlan` (which is a generic container) — `RCCPRun` is specifically the RCCP-as-gate result.

```python
class RCCPRunStatus(str, enum.Enum):
    FEASIBLE = "feasible"
    OVERLOADED = "overloaded"
    LEVELLING_RECOMMENDED = "levelling_recommended"
    ESCALATE_TO_SOP = "escalate_to_sop"


class RCCPRun(Base):
    """
    Result of a single RCCP validation run against an MPS plan.

    Each run evaluates one MPS plan at one site using one RCCP method.
    Multiple runs can exist per MPS plan (e.g., different methods or what-if scenarios).
    """
    __tablename__ = "rccp_runs"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False, index=True)
    mps_plan_id = Column(Integer, ForeignKey("mps_plans.id"), nullable=False, index=True)
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False, index=True)

    # Method used
    method = Column(Enum(RCCPMethod), nullable=False, default=RCCPMethod.BILL_OF_CAPACITY)

    # Result
    status = Column(Enum(RCCPRunStatus), nullable=False)
    is_feasible = Column(Boolean, nullable=False)

    # Horizon
    planning_horizon_weeks = Column(Integer, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)

    # Summary metrics
    max_utilization_pct = Column(Float, comment="Peak utilization across all resources and weeks")
    avg_utilization_pct = Column(Float, comment="Average utilization across all resources and weeks")
    overloaded_resource_count = Column(Integer, default=0)
    overloaded_week_count = Column(Integer, default=0)
    chronic_overload_resources = Column(JSON, default=list,
        comment="Resource IDs overloaded for 3+ consecutive weeks")
    overtime_required = Column(Boolean, default=False)

    # MPS adjustments recommended
    mps_adjustments = Column(JSON, default=list,
        comment="List of {product_id, original_week, adjusted_week, quantity, reason}")

    # Resource load detail
    resource_loads = Column(JSON, default=list,
        comment="List of {resource_id, week, required_hours, available_hours, utilization_pct, status}")

    # Rules applied (from SKILL.md)
    rules_applied = Column(JSON, default=list,
        comment="Rule names applied during this run")

    # Demand variability
    demand_variability_cv = Column(Float, nullable=True,
        comment="CV of demand at this site — triggers Rule 6 buffer if > 0.4")
    variability_buffer_applied = Column(Boolean, default=False)

    # Audit
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    mps_plan = relationship("MPSPlan")
    site = relationship("Node")
    config = relationship("SupplyChainConfig")
```

### 3.3 Add Relationship to `Product`

Add to `Product` model in `sc_entities.py`:

```python
bill_of_resources = relationship("BillOfResources", back_populates="product")
```

### 3.4 Migration

**File**: `backend/migrations/versions/20260313_rccp_bill_of_resources.py`

Creates:
- `bill_of_resources` table
- `rccp_runs` table
- Adds `bill_of_resources` relationship to Product

---

## 4. RCCP Service

**File**: `backend/app/services/rccp_service.py`

### 4.1 Core Interface

```python
class RCCPService:
    """
    Rough-Cut Capacity Planning Service.

    Validates MPS feasibility against aggregate resource capacity.
    Supports three methods (CPOF, Bill of Capacity, Resource Profile).
    """

    def __init__(self, db: Session):
        self.db = db

    def validate_mps(
        self,
        mps_plan_id: int,
        site_id: int,
        method: RCCPMethod = RCCPMethod.BILL_OF_CAPACITY,
        planning_horizon_weeks: int = 12,
        created_by: Optional[int] = None,
    ) -> RCCPRun:
        """
        Run RCCP validation against an MPS plan at a site.

        Steps:
          1. Load MPS plan items for this site
          2. Load BoR entries for each product at this site
          3. Calculate time-phased resource loads using the selected method
          4. Compare loads against available capacity
          5. Apply decision rules (overload detection, overtime, levelling, chronic detection)
          6. Persist RCCPRun record
          7. Return result
        """

    def _calculate_loads_cpof(
        self,
        mps_items: List[MPSPlanItem],
        bor_entries: List[BillOfResources],
        resources: List[CapacityResource],
        n_weeks: int,
    ) -> Dict[int, List[float]]:
        """
        Method 1: Capacity Planning Using Overall Factors.

        load(week) = sum(mps_qty(product, week)) * overall_hours_per_unit
        Distribute across resources using historical percentages.
        Returns: {resource_id: [load_week_1, load_week_2, ...]}
        """

    def _calculate_loads_bill_of_capacity(
        self,
        mps_items: List[MPSPlanItem],
        bor_entries: List[BillOfResources],
        n_weeks: int,
    ) -> Dict[int, List[float]]:
        """
        Method 2: Bill of Capacity (recommended default).

        load(resource, week) = sum(mps_qty(product, week) * hours_per_unit(product, resource))
        Returns: {resource_id: [load_week_1, load_week_2, ...]}
        """

    def _calculate_loads_resource_profile(
        self,
        mps_items: List[MPSPlanItem],
        bor_entries: List[BillOfResources],
        n_weeks: int,
    ) -> Dict[int, List[float]]:
        """
        Method 3: Resource Profile (time-phased).

        load(resource, week + offset) = mps_qty(product, need_week) * phase_hours(product, phase, resource)
        Offset determined by lead_time_offset_days on each BoR entry.
        Returns: {resource_id: [load_week_1, load_week_2, ...]}
        """

    def _apply_decision_rules(
        self,
        loads: Dict[int, List[float]],
        resources: Dict[int, CapacityResource],
        demand_cv: float,
    ) -> Tuple[RCCPRunStatus, List[dict], List[dict], List[str], bool, bool]:
        """
        Apply the 6 decision rules from SKILL.md:

        Rule 1: Overload Detection (load > capacity → flag CRITICAL/WARNING)
        Rule 2: Overtime Authorization (overload < 20% + flexibility → recommend overtime)
        Rule 3: MPS Levelling (overtime insufficient → shift to adjacent underloaded week)
        Rule 4: Underload Alert (load < 60% capacity → INFO)
        Rule 5: Chronic Overload (same resource 3+ consecutive weeks → escalate to S&OP)
        Rule 6: High-Variability Hedge (CV > 0.4 → inflate loads by 10%)

        Returns: (status, resource_loads, mps_adjustments, rules_applied,
                  overtime_required, variability_buffer_applied)
        """

    def _compute_demand_cv(self, mps_items: List[MPSPlanItem]) -> float:
        """
        Compute coefficient of variation of demand across MPS items.
        CV = std(weekly_quantities) / mean(weekly_quantities)
        """

    def suggest_levelling(
        self,
        rccp_run_id: int,
    ) -> List[dict]:
        """
        Given an infeasible RCCP run, suggest MPS quantity shifts.

        For each overloaded week:
          1. Identify how much excess load exists
          2. Find nearest underloaded week (within ±2 weeks)
          3. Propose shifting quantity from overloaded → underloaded
          4. Re-validate after shift

        Returns list of {product_id, from_week, to_week, quantity, reason}
        """

    def auto_select_method(
        self,
        config_id: int,
        site_id: int,
    ) -> RCCPMethod:
        """
        Auto-select the best RCCP method based on available BoR data.

        - If BoR entries have phase + lead_time_offset → RESOURCE_PROFILE
        - If BoR entries have resource_id + hours_per_unit → BILL_OF_CAPACITY
        - If BoR entries only have overall_hours_per_unit → CPOF
        - If no BoR entries exist → raise error (must define BoR first)
        """
```

### 4.2 Algorithm Detail: Bill of Capacity (Default Method)

```python
def _calculate_loads_bill_of_capacity(self, mps_items, bor_entries, n_weeks):
    """
    For each week w in planning horizon:
        For each resource r:
            load[r][w] = 0
            For each product p with MPS quantity in week w:
                bor = find BoR entry for (product=p, resource=r)
                if bor exists:
                    load[r][w] += mps_qty[p][w] * bor.effective_hours_per_unit
    """
    # Index BoR by (product_id, resource_id)
    bor_index = {}
    for bor in bor_entries:
        if bor.resource_id is not None:
            bor_index[(bor.product_id, bor.resource_id)] = bor

    # Collect unique resource IDs from BoR
    resource_ids = {bor.resource_id for bor in bor_entries if bor.resource_id}

    # Initialize loads
    loads = {rid: [0.0] * n_weeks for rid in resource_ids}

    for item in mps_items:
        weekly_qtys = item.weekly_quantities or []
        for week_idx in range(min(n_weeks, len(weekly_qtys))):
            qty = weekly_qtys[week_idx] or 0.0
            if qty <= 0:
                continue
            for rid in resource_ids:
                bor = bor_index.get((item.product_id, rid))
                if bor:
                    loads[rid][week_idx] += qty * bor.effective_hours_per_unit

    return loads
```

### 4.3 Algorithm Detail: Decision Rules

```python
def _apply_decision_rules(self, loads, resources, demand_cv):
    resource_loads = []
    mps_adjustments = []
    rules_applied = set()
    overtime_required = False
    variability_buffer = False
    has_chronic = False

    # Rule 6: High-variability demand hedge (apply BEFORE comparing)
    if demand_cv > 0.4:
        rules_applied.add("rule_6_variability_hedge")
        variability_buffer = True
        for rid in loads:
            loads[rid] = [l * 1.10 for l in loads[rid]]  # Inflate by 10%

    for rid, weekly_loads in loads.items():
        resource = resources[rid]
        available = resource.effective_capacity
        consecutive_overloaded = 0

        for week_idx, required in enumerate(weekly_loads):
            util_pct = (required / available * 100) if available > 0 else 0
            status = "ok"

            # Rule 1: Overload detection
            if util_pct > 110:
                status = "critical"
                rules_applied.add("rule_1_overload_critical")
            elif util_pct > 100:
                status = "warning"
                rules_applied.add("rule_1_overload_warning")

            # Rule 4: Underload alert
            if util_pct < 60:
                status = "underloaded"
                rules_applied.add("rule_4_underload")

            # Rule 2: Overtime authorization
            if util_pct > 100 and util_pct <= 120:
                if getattr(resource, 'notes', '') and 'overtime_available' in (resource.notes or ''):
                    overtime_required = True
                    rules_applied.add("rule_2_overtime")

            # Rule 5: Chronic overload tracking
            if util_pct > 100:
                consecutive_overloaded += 1
            else:
                consecutive_overloaded = 0

            if consecutive_overloaded >= 3:
                has_chronic = True
                rules_applied.add("rule_5_chronic_overload")

            resource_loads.append({
                "resource_id": rid,
                "resource_name": resource.resource_name,
                "week": week_idx + 1,
                "required_hours": round(required, 1),
                "available_hours": round(available, 1),
                "utilization_pct": round(util_pct, 1),
                "status": status,
            })

    # Determine overall status
    any_overloaded = any(rl["status"] in ("critical", "warning") for rl in resource_loads)

    if has_chronic:
        status = RCCPRunStatus.ESCALATE_TO_SOP
    elif any_overloaded and overtime_required:
        status = RCCPRunStatus.LEVELLING_RECOMMENDED
    elif any_overloaded:
        status = RCCPRunStatus.OVERLOADED
    else:
        status = RCCPRunStatus.FEASIBLE

    return (status, resource_loads, mps_adjustments,
            list(rules_applied), overtime_required, variability_buffer)
```

---

## 5. Changeover-Adjusted Available Capacity (Glenday Sieve Integration)

### 5.1 The Problem with Naive RCCP

Standard RCCP compares **required hours** (from MPS × BoR) against **available hours** (from resource definition). But available hours assumes the resource is producing for 100% of its scheduled time. In reality, changeovers consume significant capacity — and the amount consumed depends on the **product mix** being scheduled.

A line running 3 green runners all week loses maybe 2 hours to changeovers. The same line running 40 blue runners loses 30+ hours. Naive RCCP says both are "85% utilized" — the Glenday-informed version says one is feasible and the other is not.

### 5.2 How It Works

The `RCCPService` uses the existing Glenday Sieve (`engines/setup_matrix.py`) and SetupMatrix to **deduct expected changeover time** from available capacity before comparing against required load. This makes RCCP's feasibility judgment reflect the sequencing reality without doing detailed scheduling.

```
Naive RCCP:
  effective_capacity = shifts × hours × efficiency
  utilization = required_hours / effective_capacity

Glenday-adjusted RCCP:
  changeover_loss = estimated_changeover_hours(product_mix, setup_matrix, sieve)
  adjusted_capacity = effective_capacity - changeover_loss
  utilization = required_hours / adjusted_capacity
```

### 5.3 Changeover Estimation Algorithm

The key insight: at the RCCP (aggregate/weekly) level, we don't know the exact sequence — that's an execution-level decision. But we CAN estimate expected changeover loss from the product mix using the Glenday Sieve classification and the SetupMatrix.

```python
def _estimate_changeover_loss(
    self,
    resource_id: int,
    weekly_product_quantities: Dict[str, float],
    setup_matrix: SetupMatrix,
    sieve: GlendaySieve,
) -> float:
    """
    Estimate changeover hours lost for a resource in one week,
    given the product mix to be produced.

    Uses Glenday categories to estimate number of changeovers:
      - Green runners: scheduled in long campaigns → few changeovers
      - Yellow/Red: nearest-neighbor sequencing → moderate changeovers
      - Blue runners: batched into campaign windows → one changeover per batch

    Algorithm:
    1. Count distinct products by runner category
    2. Estimate changeover count per category:
       - Green: 1 changeover per green runner per week (long campaigns)
       - Yellow: 1 changeover per yellow runner (nearest-neighbor helps)
       - Red/Blue: 1 changeover each, using average setup time
    3. For each estimated changeover, use setup_matrix average for
       that category pair. If no matrix data, use category-based defaults.
    4. Sum total estimated changeover hours.

    This is deliberately conservative (overestimates changeovers) because
    the actual nearest-neighbor sequencing at execution time will be more
    efficient. A conservative RCCP catches real problems; an optimistic
    RCCP misses them.
    """
    if not weekly_product_quantities:
        return 0.0

    products = list(weekly_product_quantities.keys())
    if len(products) <= 1:
        return 0.0  # Single product → no changeovers

    # Classify products
    green = [p for p in products if sieve.get_category(p) == RunnerCategory.GREEN]
    yellow = [p for p in products if sieve.get_category(p) == RunnerCategory.YELLOW]
    red = [p for p in products if sieve.get_category(p) == RunnerCategory.RED]
    blue = [p for p in products if sieve.get_category(p) == RunnerCategory.BLUE]

    total_changeover_hours = 0.0
    resource_key = str(resource_id)

    # Green runners: 1 changeover each (they run in long dedicated campaigns)
    # Changeover FROM previous green TO next green
    for i, prod in enumerate(green):
        prev = green[i - 1] if i > 0 else (yellow + red + blue)[-1] if (yellow + red + blue) else None
        if prev:
            total_changeover_hours += setup_matrix.get_changeover_time(
                prev, prod, resource_key
            )

    # Yellow runners: 1 changeover each (nearest-neighbor reduces some)
    for i, prod in enumerate(yellow):
        prev = yellow[i - 1] if i > 0 else (green[-1] if green else None)
        if prev:
            total_changeover_hours += setup_matrix.get_changeover_time(
                prev, prod, resource_key
            )

    # Red + Blue: 1 changeover each, often worst-case (dissimilar products)
    others = red + blue
    for i, prod in enumerate(others):
        prev = others[i - 1] if i > 0 else (yellow[-1] if yellow else green[-1] if green else None)
        if prev:
            total_changeover_hours += setup_matrix.get_changeover_time(
                prev, prod, resource_key
            )

    # Transition between category groups (green→yellow, yellow→red+blue)
    if green and yellow:
        total_changeover_hours += setup_matrix.get_changeover_time(
            green[-1], yellow[0], resource_key
        )
    if yellow and others:
        total_changeover_hours += setup_matrix.get_changeover_time(
            yellow[-1], others[0], resource_key
        )
    elif green and others:
        total_changeover_hours += setup_matrix.get_changeover_time(
            green[-1], others[0], resource_key
        )

    return total_changeover_hours
```

### 5.4 Integration into RCCP Load Calculation

The changeover adjustment is applied **after** the BoR-based load calculation and **before** the decision rules:

```python
def validate_mps(self, ...):
    # Step 1: Calculate raw resource loads from BoR
    loads = self._calculate_loads_bill_of_capacity(mps_items, bor_entries, n_weeks)

    # Step 2: Load Glenday Sieve and SetupMatrix for this site
    sieve = GlendaySieve(site_id=site_key, db=self.db)
    sieve.classify()
    setup_matrix = SetupMatrix(site_id=site_key, db=self.db)
    setup_matrix.load()

    # Step 3: Compute changeover-adjusted available capacity per resource per week
    adjusted_capacities = {}
    changeover_details = []

    for resource_id, weekly_loads in loads.items():
        resource = resources[resource_id]
        adjusted_capacities[resource_id] = []

        for week_idx in range(n_weeks):
            # Determine product mix for this resource in this week
            product_mix = self._get_weekly_product_mix(
                mps_items, bor_entries, resource_id, week_idx
            )

            # Estimate changeover loss
            changeover_hours = self._estimate_changeover_loss(
                resource_id, product_mix, setup_matrix, sieve
            )

            adjusted = resource.effective_capacity - changeover_hours
            adjusted_capacities[resource_id].append(max(0, adjusted))

            if changeover_hours > 0:
                changeover_details.append({
                    "resource_id": resource_id,
                    "week": week_idx + 1,
                    "changeover_hours": round(changeover_hours, 1),
                    "distinct_products": len(product_mix),
                    "green_runners": len([p for p in product_mix
                                         if sieve.get_category(p) == RunnerCategory.GREEN]),
                    "adjusted_capacity": round(adjusted, 1),
                    "original_capacity": round(resource.effective_capacity, 1),
                })

    # Step 4: Apply decision rules using ADJUSTED capacities
    # (instead of raw resource.effective_capacity)
    status, resource_loads, ... = self._apply_decision_rules(
        loads, adjusted_capacities, demand_cv
    )
```

### 5.5 `_get_weekly_product_mix` Helper

```python
def _get_weekly_product_mix(
    self,
    mps_items: List[MPSPlanItem],
    bor_entries: List[BillOfResources],
    resource_id: int,
    week_idx: int,
) -> Dict[str, float]:
    """
    For a given resource and week, return {product_id: quantity} for all
    products that consume this resource in this week.

    Uses BoR to determine which products use which resources.
    Uses MPS quantities for the volume.
    """
    # Index: which products use this resource?
    products_on_resource = {
        bor.product_id for bor in bor_entries
        if bor.resource_id == resource_id
    }

    mix = {}
    for item in mps_items:
        if item.product_id in products_on_resource:
            qty = (item.weekly_quantities or [])[week_idx] if week_idx < len(item.weekly_quantities or []) else 0
            if qty > 0:
                mix[str(item.product_id)] = qty

    return mix
```

### 5.6 New Decision Rule: Rule 7 — Changeover-Heavy Mix Alert

Add to the RCCP SKILL.md and service:

```
Rule 7: Changeover-Heavy Mix
Condition: changeover_hours > 0.20 * effective_capacity for any resource/week
Action: Flag WARNING — changeover losses exceed 20% of capacity
Severity: WARNING
Recommendation: Consider Glenday-style campaign scheduling — dedicate
  capacity windows to green runners, batch blue runners into campaign slots.
  Reducing product variety on this resource by 30% could recover N hours.
Reasoning: High changeover-to-run ratio indicates the product mix is
  fragmented. Glenday Sieve campaign scheduling (green runners first,
  nearest-neighbor fill) typically recovers 15-25% of lost capacity.
```

### 5.7 RCCPRun Model Extension

Add changeover-related fields to `RCCPRun`:

```python
# In RCCPRun model — new fields:
changeover_adjusted = Column(Boolean, default=False,
    comment="True if changeover-adjusted capacity was used")
total_changeover_hours = Column(Float, nullable=True,
    comment="Total estimated changeover hours across all resources and weeks")
changeover_details = Column(JSON, default=list,
    comment="Per-resource per-week changeover breakdown")
glenday_summary = Column(JSON, nullable=True,
    comment="Glenday Sieve classification summary for this site")
```

### 5.8 RCCPValidateRequest Extension

```python
class RCCPValidateRequest(BaseModel):
    mps_plan_id: int
    site_id: int
    method: Optional[RCCPMethod] = None
    planning_horizon_weeks: int = 12
    changeover_adjusted: bool = True  # Default ON — use Glenday-adjusted capacity
```

### 5.9 Frontend: Changeover Visibility

Add to the RCCP validation page:

```
┌─── Changeover Analysis ────────────────────────────────┐
│                                                         │
│  Glenday Classification (43 products at this site):     │
│  ● Green: 3 (48% volume)  ● Yellow: 6 (44% volume)    │
│  ● Red: 12 (7% volume)    ● Blue: 22 (<1% volume)     │
│                                                         │
│  ┌── Changeover Loss by Resource ──────────────────┐   │
│  │ Resource    │ Wk1  │ Wk2  │ Wk3  │ Wk4  │ Avg  │   │
│  │ Assembly    │ 4.2h │ 3.8h │ 6.1h │ 5.5h │ 4.9h │   │
│  │ Machining   │ 2.1h │ 2.1h │ 3.0h │ 2.8h │ 2.5h │   │
│  │ Packaging   │ 1.0h │ 1.2h │ 1.5h │ 1.3h │ 1.3h │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  ⚠ Week 3 Assembly: 6.1h changeover = 15% of capacity  │
│    (11 distinct products, 0 green runners)              │
│    Recommendation: Consolidate blue runners into Wk4    │
│    campaign window to reduce Wk3 changeovers by ~40%    │
│                                                         │
│  Toggle: [✓] Changeover-adjusted  [ ] Naive capacity    │
└─────────────────────────────────────────────────────────┘
```

### 5.10 Why This Matters (Practical Impact)

Consider a machining center with 80 available hours/week:

| Scenario | Products | Changeover Loss | Adjusted Capacity | MPS Load | Naive Util | Real Util |
|----------|----------|-----------------|-------------------|----------|------------|-----------|
| Green campaign | 3 green | 2h | 78h | 68h | 85% | **87%** |
| Mixed week | 3 green + 8 yellow | 8h | 72h | 68h | 85% | **94%** |
| Fragmented | 3 green + 8 yellow + 15 red | 18h | 62h | 68h | 85% | **110% !!** |

Naive RCCP says all three are feasible at 85%. Glenday-adjusted RCCP correctly identifies the fragmented week as **infeasible** — the factory cannot execute this MPS without overtime or product consolidation. This is exactly the kind of hidden overload that causes shop floor chaos when MRP generates orders against an "approved" MPS.

### 5.11 Relationship Between RCCP and MO Execution

```
RCCP (Tactical — weekly)
  Uses: GlendaySieve.classify() + SetupMatrix
  Purpose: ESTIMATE changeover loss from product mix
  Fidelity: Approximate (doesn't know exact sequence)
  Output: Adjusted available capacity, changeover-heavy alerts

        ↓ MPS approved as feasible

MRP (Operational — daily)
  Explodes MPS into planned orders

        ↓ Planned orders released as MOs

MO Execution Engine (Execution — per-order)
  Uses: GlendaySieve + SetupMatrix + nearest-neighbor sequencing
  Purpose: OPTIMIZE actual changeover sequence
  Fidelity: Exact (knows sequence, real changeover times)
  Output: Sequenced MOs with minimized total changeover

        ↓ Actual changeover times observed

Feedback to RCCP:
  Actual changeover times → refine estimation model
  Actual vs estimated → adjust conservatism factor
```

The same Glenday Sieve classification and SetupMatrix data is used at both levels — RCCP estimates conservatively, MO Execution optimizes precisely. Actual outcomes feed back to improve RCCP's estimates over time.

---

## 6. API Endpoints

**File**: `backend/app/api/endpoints/rccp.py`

Mount at `/api/v1/rccp`.

### 5.1 Endpoint Summary

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/validate` | Run RCCP validation against an MPS plan |
| `GET` | `/runs` | List RCCP runs (filter by config, MPS plan, site, status) |
| `GET` | `/runs/{run_id}` | Get single RCCP run with full detail |
| `POST` | `/runs/{run_id}/suggest-levelling` | Generate MPS levelling suggestions |
| `GET` | `/bor` | List Bill of Resources entries (filter by config, product, site) |
| `POST` | `/bor` | Create BoR entry |
| `PUT` | `/bor/{bor_id}` | Update BoR entry |
| `DELETE` | `/bor/{bor_id}` | Delete BoR entry |
| `POST` | `/bor/bulk` | Bulk create/update BoR entries (for import) |
| `GET` | `/bor/auto-detect-method` | Auto-detect best RCCP method for a config/site |

### 5.2 Key Endpoint: `POST /validate`

```python
class RCCPValidateRequest(BaseModel):
    mps_plan_id: int
    site_id: int
    method: Optional[RCCPMethod] = None  # Auto-detect if not provided
    planning_horizon_weeks: int = 12

class RCCPRunResponse(BaseModel):
    id: int
    mps_plan_id: int
    site_id: int
    method: RCCPMethod
    status: RCCPRunStatus
    is_feasible: bool
    max_utilization_pct: Optional[float]
    avg_utilization_pct: Optional[float]
    overloaded_resource_count: int
    overloaded_week_count: int
    chronic_overload_resources: List[int]
    overtime_required: bool
    variability_buffer_applied: bool
    mps_adjustments: List[dict]
    resource_loads: List[dict]
    rules_applied: List[str]

@router.post("/validate", response_model=RCCPRunResponse)
async def validate_mps(
    request: RCCPValidateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run RCCP validation against an MPS plan at a specific site.

    If method is not specified, auto-detects based on available BoR data.
    Returns feasibility status, resource loads, and MPS adjustment recommendations.

    Requires: VIEW_MPS or MANAGE_MPS capability.
    """
    service = RCCPService(db)
    method = request.method or service.auto_select_method(
        config_id=mps_plan.supply_chain_config_id,
        site_id=request.site_id,
    )
    run = service.validate_mps(
        mps_plan_id=request.mps_plan_id,
        site_id=request.site_id,
        method=method,
        planning_horizon_weeks=request.planning_horizon_weeks,
        created_by=current_user.id,
    )
    return run
```

### 5.3 MPS Integration Point

Add to existing `backend/app/api/endpoints/mps.py`:

```python
@router.post("/{plan_id}/rccp-check", response_model=RCCPRunResponse)
async def run_rccp_check(
    plan_id: int,
    site_id: Optional[int] = Query(None, description="Site to check (default: all manufacturer sites)"),
    method: Optional[RCCPMethod] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run RCCP check on this MPS plan.

    If site_id is omitted, runs RCCP for ALL manufacturer sites in the config
    and returns the worst-case result.
    """
```

---

## 7. BoR Data Population

### 6.1 From ProductionProcess (Auto-Generate)

For sites that have `ProductionProcess` records but no BoR entries, auto-generate BoR entries at the CPOF level:

```python
def auto_generate_bor_from_production_process(
    db: Session,
    config_id: int,
    site_id: int,
) -> List[BillOfResources]:
    """
    Generate CPOF-level BoR entries from existing ProductionProcess records.

    For each ProductionProcess at this site:
      - overall_hours_per_unit = operation_time + (setup_time / lot_size)
      - is_critical = True (assume critical until refined)

    This is a bootstrap — gives immediate RCCP capability without
    requiring detailed work center definitions.
    """
```

### 6.2 From SAP Data (Import)

When SAP data is ingested via SAP Data Management:

- **SAP Work Centers** (`T_006`, `CRHD`, `CRCO`) → `CapacityResource` records
- **SAP Routings** (`PLPO`, `PLFL`) → `BillOfResources` entries with resource_id, hours_per_unit, setup_hours
- **SAP Capacity Headers** (`KAKO`, `KAZY`) → Available capacity per resource

Add to `backend/app/services/sap_config_builder.py`:

```python
def _build_bill_of_resources(self, sap_tables: dict) -> List[BillOfResources]:
    """
    Map SAP routing operations to BoR entries.

    SAP PLPO (routing operation):
      - ARBID → work_center_id → CapacityResource
      - VGW01-VGW06 → hours_per_unit (standard values)
      - RUEST → setup_hours_per_batch
      - LOSGR → typical_batch_size
    """
```

### 6.3 From Synthetic Data Generator

When generating synthetic companies via the wizard, include BoR entries:

```python
# In synthetic_data_generator.py, for manufacturer archetype:
# For each product at each manufacturing site:
#   Create BoR entries linking to the site's CapacityResources
#   Use archetype-appropriate hours/unit:
#     - Simple assembly: 0.1-0.3 hrs/unit
#     - Complex manufacturing: 0.5-2.0 hrs/unit
#     - Process industry: 0.01-0.05 hrs/unit (high volume)
```

---

## 8. Frontend

### 7.1 RCCP Validation Page

**File**: Update existing `frontend/src/pages/planning/CapacityCheck.jsx`

Replace the hardcoded demo with a real RCCP workflow:

```
┌─────────────────────────────────────────────────────────┐
│  RCCP Capacity Validation                               │
│                                                         │
│  MPS Plan: [Select MPS Plan ▾]                          │
│  Site:     [Select Site ▾]     (manufacturers only)     │
│  Method:   [Auto-detect ▾]     (CPOF / BoC / Profile)   │
│  Horizon:  [12] weeks                                   │
│                                                         │
│  [Run RCCP Check]                                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Status: ● OVERLOADED          Rules: #1, #3, #6       │
│                                                         │
│  ┌─── Resource Load Chart (stacked bar) ──────────┐    │
│  │                                                 │    │
│  │  ████████  ████████  ████████  ████████         │    │
│  │  ████████  ████████  ██████████████████         │    │
│  │  ████████  ████████  ██████████████████  ───100%│    │
│  │  ████████  ████████  ██████████████████         │    │
│  │  ████████  ████████  ████████  ████████         │    │
│  │  Wk1       Wk2       Wk3       Wk4             │    │
│  │                                                 │    │
│  │  █ Assembly  █ Machining  █ Packaging  ─── cap  │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─── Resource Detail Table ──────────────────────┐    │
│  │ Resource  │ Wk1  │ Wk2  │ Wk3  │ Wk4  │ Peak  │    │
│  │ Assembly  │ 82%  │ 78%  │ 105% │ 112% │ 112%  │    │
│  │ Machining │ 90%  │ 85%  │ 88%  │ 95%  │ 95%   │    │
│  │ Packaging │ 65%  │ 70%  │ 72%  │ 68%  │ 72%   │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─── Recommendations ───────────────────────────┐     │
│  │ ⚠ Assembly overloaded Wk3-4: shift 200 units  │     │
│  │   from Wk4 → Wk2 (Assembly at 78%)            │     │
│  │ ℹ Packaging underloaded all weeks (<75%)       │     │
│  │   Consider pulling forward MTS orders          │     │
│  │ [Apply Levelling Suggestions]                  │     │
│  └────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

### 7.2 BoR Management Page

**File**: New `frontend/src/pages/planning/BillOfResources.jsx`

Simple CRUD table for managing BoR entries:
- Filter by config, site, product
- Inline editing of hours_per_unit, setup_hours, batch_size
- Bulk import from CSV
- "Auto-generate from ProductionProcess" button
- Visual indicator showing which RCCP method the current BoR data supports

### 7.3 MPS Integration

Add to existing MPS page (`MasterProductionScheduling.jsx`):
- "RCCP Check" button on each MPS plan row
- Status badge showing last RCCP result (Feasible / Overloaded / Escalated)
- Inline warning banner when MPS is modified after an RCCP check

---

## 9. Powell Framework Integration

### 8.1 Planning Flow Position

```
Layer 4: S&OP GraphSAGE (weekly) — sets policy parameters θ
    ↓
Layer 3: Demand Planning — consensus demand
    ↓
Layer 2: MPS Generation — draft production schedule
    ↓
 ═══════════════════════════════════════
║  RCCP Service — validate MPS feasibility  ║
 ═══════════════════════════════════════
    ↓ if feasible
Layer 2: MRP — net requirements, BOM explosion
    ↓
Layer 1: TRM Execution — PO/MO/TO decisions
```

### 8.2 Escalation Integration

RCCP results feed into the existing escalation arbiter:

| RCCP Status | Escalation Action |
|-------------|-------------------|
| `FEASIBLE` | None — proceed to MRP |
| `OVERLOADED` | Suggest levelling; if auto-levelling enabled, apply and re-check |
| `LEVELLING_RECOMMENDED` | Present levelling options in Decision Stream |
| `ESCALATE_TO_SOP` | Trigger `VERTICAL_STRATEGIC` escalation via `EscalationArbiter` |

### 8.3 Decision Stream Integration

RCCP results appear in the Decision Stream inbox when:
- Status is `OVERLOADED` or `ESCALATE_TO_SOP`
- MPS adjustments are recommended
- Overtime authorization is needed

Decision type: `rccp_validation`, routed to MPS Manager (Layer 2) or S&OP Director (Layer 4 for chronic overloads).

### 8.4 Provisioning Stepper

Add RCCP BoR setup as a sub-step of the existing `supply_plan` provisioning step, or as a new step between `supply_plan` and `decision_seed`:

```
... → supply_plan → rccp_bor_setup → decision_seed → ...
```

The `rccp_bor_setup` step auto-generates BoR entries from ProductionProcess records if none exist.

---

## 10. Existing Code Cleanup

### 9.1 Replace Placeholder Logic

In `backend/app/api/endpoints/capacity_plans.py`:

- **`_calculate_requirements_from_mps()`** (line 71): Replace hardcoded `resource.available_capacity * 0.7` with actual BoR lookup via `RCCPService._calculate_loads_bill_of_capacity()`.

- **`_calculate_requirements_from_production_orders()`** (line 127): Replace hardcoded `planned_quantity * 0.1` with BoR lookup: `planned_quantity * bor.effective_hours_per_unit` for each resource.

### 9.2 Consolidate MPSCapacityCheck

`MPSCapacityCheck` in `mps.py` overlaps with `CapacityRequirement` in `capacity_plan.py`. Options:
- **Recommended**: Keep `MPSCapacityCheck` as the MPS-specific RCCP record (quick inline check), and `CapacityRequirement` as the detailed generic capacity record. Link `MPSCapacityCheck` to `RCCPRun`.
- Update `MPSCapacityCheck` to reference `rccp_run_id` so the MPS page can display which RCCP run validated it.

### 9.3 Integrate CapacityConstrainedMPS Service

The existing `CapacityConstrainedMPS` class in `capacity_constrained_mps.py` has useful levelling algorithms. Refactor to:
- Accept DB-sourced data (not standalone dataclasses)
- Be called by `RCCPService.suggest_levelling()` for the levelling logic
- Delete the standalone dataclasses (`ResourceRequirement`, `MPSProductionPlan`, etc.) that duplicate DB models

---

## 11. Permissions & Capabilities

Add to `backend/app/core/capabilities.py`:

```python
VIEW_RCCP = "view_rccp"
MANAGE_RCCP = "manage_rccp"
MANAGE_BOR = "manage_bor"
```

- `VIEW_RCCP`: View RCCP runs and results (MPS Manager, S&OP Director, VP)
- `MANAGE_RCCP`: Run RCCP validations (MPS Manager)
- `MANAGE_BOR`: Create/edit Bill of Resources entries (Tenant Admin, MPS Manager)

---

## 12. Execution Order

### Phase 1: Data Foundation
1. Create migration: `bill_of_resources` and `rccp_runs` tables
2. Create `BillOfResources` and `RCCPRun` models
3. Add `bill_of_resources` relationship to `Product`
4. Create Pydantic schemas for BoR and RCCP
5. Add permissions/capabilities

### Phase 2: Service Layer
6. Implement `RCCPService` with all 3 methods + 6 decision rules
7. Implement `auto_generate_bor_from_production_process()`
8. Refactor `CapacityConstrainedMPS` levelling logic into `RCCPService.suggest_levelling()`

### Phase 3: API Layer
9. Create `/api/v1/rccp` router with all endpoints
10. Add `POST /mps/{plan_id}/rccp-check` to MPS router
11. Replace placeholder logic in `capacity_plans.py` with real BoR lookups
12. Wire up `MPSCapacityCheck` to reference `RCCPRun`

### Phase 4: Frontend
13. Replace `CapacityCheck.jsx` with real RCCP validation page
14. Create `BillOfResources.jsx` management page
15. Add RCCP status badge to MPS plan list
16. Add RCCP results to Decision Stream

### Phase 5: Integration
17. Add RCCP check to provisioning stepper
18. Wire escalation arbiter for `ESCALATE_TO_SOP` status
19. Add BoR generation to synthetic data generator
20. Add SAP BoR import to `sap_config_builder.py`

---

## 13. Testing

### 12.1 Unit Tests

```python
# test_rccp_service.py

def test_cpof_method_calculates_total_site_load():
    """CPOF: sum(mps_qty) * overall_hours_per_unit"""

def test_bill_of_capacity_per_resource_load():
    """BoC: load(resource, week) = sum(mps_qty * hours_per_unit)"""

def test_resource_profile_time_phased_offset():
    """Profile: setup load placed at offset week, run load at MPS week"""

def test_rule_1_overload_detection_critical():
    """Utilization > 110% → CRITICAL status"""

def test_rule_1_overload_detection_warning():
    """Utilization 100-110% → WARNING status"""

def test_rule_2_overtime_authorization():
    """Overload < 20% + flexibility → recommend overtime"""

def test_rule_3_mps_levelling_shift():
    """Overtime insufficient → shift to nearest underloaded week"""

def test_rule_4_underload_alert():
    """Utilization < 60% → INFO underload"""

def test_rule_5_chronic_overload_3_weeks():
    """Same resource overloaded 3+ consecutive weeks → ESCALATE_TO_SOP"""

def test_rule_6_variability_hedge():
    """CV > 0.4 → inflate loads by 10%"""

def test_auto_select_method_bill_of_capacity():
    """BoR with resource_id + hours_per_unit → BILL_OF_CAPACITY"""

def test_auto_select_method_cpof():
    """BoR with only overall_hours_per_unit → CPOF"""

def test_feasible_mps_returns_feasible_status():
    """All resources within capacity → FEASIBLE"""

def test_setup_time_amortization():
    """effective_hours = run_hours + setup_hours / batch_size"""

def test_rule_7_changeover_heavy_mix():
    """Changeover > 20% of capacity → WARNING"""

def test_changeover_adjusted_capacity_reduces_available():
    """Glenday-adjusted capacity < naive capacity when product mix is fragmented"""

def test_green_runner_campaign_minimal_changeover():
    """3 green runners → ~2h changeover vs 15 blue runners → ~15h changeover"""

def test_single_product_no_changeover_loss():
    """One product on resource → 0 changeover hours"""

def test_changeover_uses_setup_matrix_data():
    """Changeover estimation uses actual SetupMatrix entries, not defaults"""

def test_changeover_toggle_off_uses_naive_capacity():
    """changeover_adjusted=False → uses raw effective_capacity"""
```

### 13.2 Integration Tests

```python
def test_mps_rccp_mps_adjustment_flow():
    """
    1. Create MPS plan with overloaded weeks
    2. Run RCCP → OVERLOADED
    3. Apply levelling suggestions
    4. Re-run RCCP → FEASIBLE
    """

def test_auto_generate_bor_from_production_process():
    """
    1. Create ProductionProcess with operation_time=0.5, setup_time=0.1, lot_size=100
    2. Auto-generate BoR
    3. Verify overall_hours_per_unit = 0.5 + 0.1/100 = 0.501
    """
```

---

## 14. References

- **APICS CPIM Part 2, Module 2 (MPR)**: MPS development, RCCP, demand management
- **Capacity_Planning_Guide.md**: `docs/knowledge/Capacity_Planning_Guide.md` — Section 4 (RCCP)
- **RCCP Claude Skill**: `backend/app/services/skills/rccp/SKILL.md` — 6 decision rules
- **MRP_Logic_Lot_Sizing_Guide.md**: `docs/knowledge/MRP_Logic_Lot_Sizing_Guide.md` — Section 2.6 (RCCP)
- **Powell Framework**: RCCP is a CFA (Cost Function Approximation) — parameterized feasibility check
- **Glenday Sieve**: Ian Glenday, "Breaking Through to Flow" (2005) — runner classification for campaign scheduling
- **Setup Matrix**: `backend/app/services/powell/engines/setup_matrix.py` — sequence-dependent changeover times
- **MO Execution Engine**: `backend/app/services/powell/engines/mo_execution_engine.py` — Glenday + nearest-neighbor sequencing
