"""
RCCP Service — Rough-Cut Capacity Planning

Validates MPS feasibility against aggregate capacity using three methods:
  1. CPOF (Capacity Planning using Overall Factors)
  2. Bill of Capacity (per-resource hours/unit)
  3. Resource Profile (time-phased with lead-time offsets)

Integrates Glenday Sieve changeover-adjusted capacity estimation.
Seven decision rules per the SKILL.md specification.
"""

import logging
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Tuple, Any
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.rccp import BillOfResources, RCCPRun, RCCPMethod, RCCPRunStatus, ProductionPhase
from app.models.mps import MPSPlan, MPSPlanItem
from app.models.capacity_plan import CapacityResource
from app.models.sc_entities import Product, ProductionProcess
from app.models.supply_chain_config import Site
from app.services.powell.engines.setup_matrix import SetupMatrix, GlendaySieve, GlendaySieveConfig, RunnerCategory

logger = logging.getLogger(__name__)


class RCCPService:
    """Rough-Cut Capacity Planning Service."""

    def __init__(self, db: Session):
        self.db = db

    # ── Method Detection ──────────────────────────────────────────────

    def detect_method(self, config_id: int, site_id: int) -> Dict[str, Any]:
        """Auto-detect best RCCP method based on available BoR data.

        Returns dict with: recommended_method, reason, bor_entry_count,
        has_resource_detail, has_phase_detail
        """
        bor_entries = self.db.query(BillOfResources).filter(
            BillOfResources.config_id == config_id,
            BillOfResources.site_id == site_id,
            BillOfResources.is_active == True,
        ).all()

        count = len(bor_entries)
        has_resource = any(e.resource_id is not None for e in bor_entries)
        has_phase = any(e.phase is not None for e in bor_entries)

        if has_phase:
            method = RCCPMethod.RESOURCE_PROFILE
            reason = "Phase-level resource profiles available — using most accurate method"
        elif has_resource:
            method = RCCPMethod.BILL_OF_CAPACITY
            reason = "Per-resource hours available — using Bill of Capacity method"
        elif count > 0:
            method = RCCPMethod.CPOF
            reason = "Only overall hours available — using CPOF method"
        else:
            method = RCCPMethod.CPOF
            reason = "No BoR data found — defaulting to CPOF (will auto-generate from production_process)"

        return {
            "recommended_method": method.value,
            "reason": reason,
            "bor_entry_count": count,
            "has_resource_detail": has_resource,
            "has_phase_detail": has_phase,
        }

    # ── Core Validation ───────────────────────────────────────────────

    def validate_mps(
        self,
        mps_plan_id: int,
        site_id: int,
        method: Optional[RCCPMethod] = None,
        planning_horizon_weeks: int = 12,
        changeover_adjusted: bool = True,
        created_by: Optional[int] = None,
    ) -> RCCPRun:
        """Run RCCP validation against an MPS plan for a site.

        This is the main entry point. Steps:
        1. Load MPS quantities by product by week
        2. Load BoR data (auto-generate if missing)
        3. Load capacity resources
        4. Auto-detect method if not specified
        5. Compute resource loads using selected method
        6. Apply Glenday changeover adjustment if enabled
        7. Apply variability buffer (Rule 6) if applicable
        8. Evaluate all 7 decision rules
        9. Persist and return RCCPRun
        """
        # Load MPS plan
        mps_plan = self.db.query(MPSPlan).filter(MPSPlan.id == mps_plan_id).first()
        if not mps_plan:
            raise ValueError(f"MPS plan {mps_plan_id} not found")

        config_id = mps_plan.supply_chain_config_id

        # Auto-detect method
        if method is None:
            detection = self.detect_method(config_id, site_id)
            method = RCCPMethod(detection["recommended_method"])
            # Auto-generate BoR if nothing exists
            if detection["bor_entry_count"] == 0:
                self.auto_generate_bor(config_id, site_id)

        # Load MPS quantities: {product_id: {week_number: quantity}}
        mps_quantities = self._load_mps_quantities(mps_plan, site_id, planning_horizon_weeks)

        # Load BoR entries
        bor_entries = self.db.query(BillOfResources).filter(
            BillOfResources.config_id == config_id,
            BillOfResources.site_id == site_id,
            BillOfResources.is_active == True,
        ).all()

        # Load capacity resources for this site
        resources = self._load_capacity_resources(config_id, site_id)

        # Compute start/end dates
        start_date = mps_plan.start_date
        if isinstance(start_date, date) and not isinstance(start_date, datetime):
            start_date = datetime.combine(start_date, datetime.min.time())
        end_date = start_date + timedelta(weeks=planning_horizon_weeks)

        # Compute resource loads based on method
        resource_loads = self._compute_loads(
            method, mps_quantities, bor_entries, resources, planning_horizon_weeks
        )

        # Glenday changeover adjustment
        changeover_details: List[Dict] = []
        glenday_summary: Optional[Dict] = None
        total_changeover_hours = 0.0
        if changeover_adjusted and resources:
            changeover_details, glenday_summary, total_changeover_hours = (
                self._apply_changeover_adjustment(
                    config_id, site_id, mps_quantities, resources, resource_loads
                )
            )

        # Compute demand variability
        demand_cv = self._compute_demand_variability(config_id, site_id)
        variability_buffer = False

        # Rule 6: High-variability demand hedge — inflate required hours by 10%
        if demand_cv is not None and demand_cv > 0.4:
            variability_buffer = True
            for load in resource_loads:
                load["required_hours"] = round(load["required_hours"] * 1.10, 2)
                if load["available_hours"] > 0:
                    load["utilization_pct"] = round(
                        (load["required_hours"] / load["available_hours"]) * 100, 2
                    )
                load["status"] = self._classify_status(load["utilization_pct"])

        # Apply decision rules
        rules_applied: List[str] = []
        mps_adjustments: List[Dict] = []
        overtime_required = False
        chronic_resources: List[int] = []

        # Rule 1: Overload detection
        overloaded = [l for l in resource_loads if l["utilization_pct"] > 100]
        if overloaded:
            rules_applied.append("overload_detection")

        # Rule 2: Overtime authorization — allow 20% overtime for flexible resources.
        # A resource is considered flexible if its utilization_target_percent > 85%
        # (i.e. the planner has marked it as available for stretch usage).
        for load in overloaded:
            resource_meta = next(
                (r for r in resources if r["id"] == load["resource_id"]), None
            )
            util_target = resource_meta.get("utilization_target_pct", 85.0) if resource_meta else 85.0
            is_flexible = (util_target > 85.0) if resource_meta else False
            if is_flexible and load["utilization_pct"] <= 120:
                overtime_required = True
                load["available_hours"] = round(load["available_hours"] * 1.20, 2)
                load["utilization_pct"] = round(
                    (load["required_hours"] / load["available_hours"]) * 100, 2
                ) if load["available_hours"] > 0 else load["utilization_pct"]
                load["status"] = self._classify_status(load["utilization_pct"])
                if "overtime_authorization" not in rules_applied:
                    rules_applied.append("overtime_authorization")

        # Rule 3: MPS levelling — shift production to underloaded weeks
        still_overloaded = [l for l in resource_loads if l["utilization_pct"] > 100]
        if still_overloaded:
            levelling_adjustments = self._apply_mps_levelling(
                resource_loads, mps_quantities, planning_horizon_weeks
            )
            if levelling_adjustments:
                mps_adjustments.extend(levelling_adjustments)
                rules_applied.append("mps_levelling")

        # Rule 4: Underload alert — resources with < 60% utilization
        underloaded = [l for l in resource_loads if l["utilization_pct"] < 60]
        if underloaded:
            rules_applied.append("underload_alert")

        # Rule 5: Chronic overload (3+ consecutive weeks above 100%)
        chronic_resources = self._detect_chronic_overload(resource_loads)
        if chronic_resources:
            rules_applied.append("chronic_overload")

        # Rule 6 already applied above
        if variability_buffer:
            rules_applied.append("variability_hedge")

        # Rule 7: Changeover-heavy mix — changeover > 20% of original capacity
        changeover_heavy = [
            d for d in changeover_details
            if d.get("changeover_hours", 0) > 0.20 * d.get("original_capacity", 1)
        ]
        if changeover_heavy:
            rules_applied.append("changeover_heavy_mix")

        # Determine overall status
        final_overloaded = [l for l in resource_loads if l["utilization_pct"] > 100]
        if chronic_resources:
            status = RCCPRunStatus.ESCALATE_TO_SOP
        elif mps_adjustments:
            status = RCCPRunStatus.LEVELLING_RECOMMENDED
        elif final_overloaded:
            status = RCCPRunStatus.OVERLOADED
        else:
            status = RCCPRunStatus.FEASIBLE

        is_feasible = status == RCCPRunStatus.FEASIBLE

        # Utilization statistics
        utils = [l["utilization_pct"] for l in resource_loads if l["available_hours"] > 0]
        max_util = max(utils) if utils else 0.0
        avg_util = sum(utils) / len(utils) if utils else 0.0

        overloaded_resource_ids = set(
            l["resource_id"] for l in resource_loads if l["utilization_pct"] > 100
        )
        overloaded_weeks = set(
            l["week"] for l in resource_loads if l["utilization_pct"] > 100
        )

        # Persist RCCPRun
        run = RCCPRun(
            config_id=config_id,
            mps_plan_id=mps_plan_id,
            site_id=site_id,
            method=method,
            status=status,
            is_feasible=is_feasible,
            planning_horizon_weeks=planning_horizon_weeks,
            start_date=start_date,
            end_date=end_date,
            max_utilization_pct=round(max_util, 2),
            avg_utilization_pct=round(avg_util, 2),
            overloaded_resource_count=len(overloaded_resource_ids),
            overloaded_week_count=len(overloaded_weeks),
            chronic_overload_resources=list(chronic_resources),
            overtime_required=overtime_required,
            mps_adjustments=mps_adjustments,
            resource_loads=resource_loads,
            rules_applied=rules_applied,
            demand_variability_cv=demand_cv,
            variability_buffer_applied=variability_buffer,
            changeover_adjusted=changeover_adjusted,
            total_changeover_hours=total_changeover_hours,
            changeover_details=changeover_details,
            glenday_summary=glenday_summary,
            created_by=created_by,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        logger.info(
            f"RCCP run {run.id}: method={method.value} status={status.value} "
            f"max_util={max_util:.1f}% avg_util={avg_util:.1f}% "
            f"overloaded_resources={len(overloaded_resource_ids)} "
            f"rules={rules_applied}"
        )

        return run

    # ── Load Computation Methods ──────────────────────────────────────

    def _compute_loads(
        self,
        method: RCCPMethod,
        mps_quantities: Dict[str, Dict[int, float]],
        bor_entries: List[BillOfResources],
        resources: List[Dict],
        horizon_weeks: int,
    ) -> List[Dict[str, Any]]:
        """Compute resource loads using the selected method."""
        if method == RCCPMethod.CPOF:
            return self._compute_cpof(mps_quantities, bor_entries, resources, horizon_weeks)
        elif method == RCCPMethod.BILL_OF_CAPACITY:
            return self._compute_bill_of_capacity(mps_quantities, bor_entries, resources, horizon_weeks)
        elif method == RCCPMethod.RESOURCE_PROFILE:
            return self._compute_resource_profile(mps_quantities, bor_entries, resources, horizon_weeks)
        else:
            raise ValueError(f"Unsupported RCCP method: {method}")

    def _compute_cpof(
        self,
        mps_quantities: Dict[str, Dict[int, float]],
        bor_entries: List[BillOfResources],
        resources: List[Dict],
        horizon_weeks: int,
    ) -> List[Dict[str, Any]]:
        """CPOF: overall hours/unit distributed across all resources.

        Uses overall_hours_per_unit from BoR entries.  When multiple resources
        exist the total load is split proportionally to each resource's
        available weekly hours.
        """
        # Build product -> overall_hours_per_unit map
        product_hours: Dict[str, float] = {}
        for bor in bor_entries:
            if bor.overall_hours_per_unit is not None:
                product_hours[bor.product_id] = bor.overall_hours_per_unit

        # Compute total weekly capacity for proportional splitting
        total_weekly_capacity = sum(r.get("available_hours_per_week", 0.0) for r in resources)

        loads: List[Dict[str, Any]] = []
        for resource in resources:
            resource_weekly = resource.get("available_hours_per_week", 0.0)
            proportion = (resource_weekly / total_weekly_capacity) if total_weekly_capacity > 0 else (
                1.0 / max(len(resources), 1)
            )

            for week in range(1, horizon_weeks + 1):
                total_required = 0.0
                for product_id, weeks_map in mps_quantities.items():
                    qty = weeks_map.get(week, 0.0)
                    hours = product_hours.get(product_id, 0.0)
                    total_required += qty * hours

                # Apportion to this resource
                total_required *= proportion

                available = resource_weekly
                util = (total_required / available * 100) if available > 0 else 0.0

                loads.append({
                    "resource_id": resource["id"],
                    "resource_name": resource["name"],
                    "week": week,
                    "required_hours": round(total_required, 2),
                    "available_hours": round(available, 2),
                    "utilization_pct": round(util, 2),
                    "status": self._classify_status(util),
                })
        return loads

    def _compute_bill_of_capacity(
        self,
        mps_quantities: Dict[str, Dict[int, float]],
        bor_entries: List[BillOfResources],
        resources: List[Dict],
        horizon_weeks: int,
    ) -> List[Dict[str, Any]]:
        """Bill of Capacity: per-resource hours/unit including amortised setup.

        Uses effective_hours_per_unit (= hours_per_unit + setup_hours_per_batch /
        typical_batch_size) for each (product, resource) pair.
        """
        # Build (product_id, resource_id) -> effective_hours map
        bor_map: Dict[Tuple[Any, int], float] = {}
        for bor in bor_entries:
            if bor.resource_id is not None and bor.hours_per_unit is not None:
                key = (bor.product_id, bor.resource_id)
                bor_map[key] = bor.effective_hours_per_unit

        loads: List[Dict[str, Any]] = []
        for resource in resources:
            for week in range(1, horizon_weeks + 1):
                total_required = 0.0
                for product_id, weeks_map in mps_quantities.items():
                    qty = weeks_map.get(week, 0.0)
                    hours = bor_map.get((product_id, resource["id"]), 0.0)
                    total_required += qty * hours

                available = resource.get("available_hours_per_week", 0.0)
                util = (total_required / available * 100) if available > 0 else 0.0

                loads.append({
                    "resource_id": resource["id"],
                    "resource_name": resource["name"],
                    "week": week,
                    "required_hours": round(total_required, 2),
                    "available_hours": round(available, 2),
                    "utilization_pct": round(util, 2),
                    "status": self._classify_status(util),
                })
        return loads

    def _compute_resource_profile(
        self,
        mps_quantities: Dict[str, Dict[int, float]],
        bor_entries: List[BillOfResources],
        resources: List[Dict],
        horizon_weeks: int,
    ) -> List[Dict[str, Any]]:
        """Resource Profile: time-phased consumption with lead-time offsets.

        Each BoR entry carries a phase (setup/run/teardown/queue/move), a
        phase_hours_per_unit, and a lead_time_offset_days.  The offset shifts
        the resource consumption backward in time — a 14-day offset means
        the resource is consumed two weeks before the MPS need date.
        """
        # Build (product_id, resource_id) -> list of (phase_hours, offset_weeks)
        profile_map: Dict[Tuple[Any, int], List[Tuple[float, int]]] = defaultdict(list)
        for bor in bor_entries:
            if bor.resource_id is not None and bor.phase is not None and bor.phase_hours_per_unit is not None:
                key = (bor.product_id, bor.resource_id)
                offset_weeks = max(0, bor.lead_time_offset_days // 7)
                profile_map[key].append((bor.phase_hours_per_unit, offset_weeks))

        # Accumulate loads by (resource_id, week)
        loads_accum: Dict[Tuple[int, int], float] = defaultdict(float)

        for product_id, weeks_map in mps_quantities.items():
            for need_week, qty in weeks_map.items():
                for resource in resources:
                    key = (product_id, resource["id"])
                    phases = profile_map.get(key, [])
                    for phase_hours, offset in phases:
                        # Offset shifts consumption earlier (backward from need date)
                        target_week = need_week - offset
                        if 1 <= target_week <= horizon_weeks:
                            loads_accum[(resource["id"], target_week)] += qty * phase_hours

        loads: List[Dict[str, Any]] = []
        for resource in resources:
            for week in range(1, horizon_weeks + 1):
                required = loads_accum.get((resource["id"], week), 0.0)
                available = resource.get("available_hours_per_week", 0.0)
                util = (required / available * 100) if available > 0 else 0.0

                loads.append({
                    "resource_id": resource["id"],
                    "resource_name": resource["name"],
                    "week": week,
                    "required_hours": round(required, 2),
                    "available_hours": round(available, 2),
                    "utilization_pct": round(util, 2),
                    "status": self._classify_status(util),
                })
        return loads

    # ── Glenday Changeover Adjustment ─────────────────────────────────

    def _apply_changeover_adjustment(
        self,
        config_id: int,
        site_id: int,
        mps_quantities: Dict[str, Dict[int, float]],
        resources: List[Dict],
        resource_loads: List[Dict],
    ) -> Tuple[List[Dict], Optional[Dict], float]:
        """Apply Glenday Sieve changeover-adjusted capacity.

        For each resource/week:
        1. Count distinct products in MPS
        2. Classify via Glenday Sieve
        3. Estimate changeover hours using SetupMatrix
        4. Deduct from available capacity
        """
        site = self.db.query(Site).filter(Site.id == site_id).first()
        site_key = site.name if site else str(site_id)

        # Load setup matrix and Glenday sieve
        setup_matrix = SetupMatrix(site_id=site_key, db=self.db)
        setup_matrix.load()

        sieve = GlendaySieve(site_id=site_key, db=self.db)

        # Build volume data from MPS for sieve classification
        volume_data: Dict[str, float] = {}
        for product_id, weeks_map in mps_quantities.items():
            total = sum(weeks_map.values())
            if total > 0:
                volume_data[str(product_id)] = total

        sieve.classify(volume_data=volume_data)

        # Determine max week across resource loads
        max_week = max((l["week"] for l in resource_loads), default=0)

        changeover_details: List[Dict] = []
        total_co_hours = 0.0

        for resource in resources:
            for week in range(1, max_week + 1):
                # Products scheduled on this resource in this week
                products_this_week: List[str] = []
                for product_id, weeks_map in mps_quantities.items():
                    if weeks_map.get(week, 0) > 0:
                        products_this_week.append(str(product_id))

                if len(products_this_week) <= 1:
                    continue  # No changeover needed

                # Count green runners in this week
                green_count = sum(
                    1 for p in products_this_week
                    if sieve.get_category(p) == RunnerCategory.GREEN
                )

                # Estimate changeover: (n-1) changeovers for n products
                # Use setup matrix for pair-wise times, summed across sequence
                changeover_hours = 0.0
                for i in range(len(products_this_week) - 1):
                    co_time = setup_matrix.get_changeover_time(
                        products_this_week[i], products_this_week[i + 1]
                    )
                    changeover_hours += co_time

                total_co_hours += changeover_hours

                original_capacity = resource.get("available_hours_per_week", 0.0)
                adjusted_capacity = max(0.0, original_capacity - changeover_hours)

                changeover_details.append({
                    "resource_id": resource["id"],
                    "week": week,
                    "changeover_hours": round(changeover_hours, 2),
                    "distinct_products": len(products_this_week),
                    "green_runners": green_count,
                    "adjusted_capacity": round(adjusted_capacity, 2),
                    "original_capacity": round(original_capacity, 2),
                })

                # Update the corresponding resource load entry
                for load in resource_loads:
                    if load["resource_id"] == resource["id"] and load["week"] == week:
                        load["available_hours"] = round(adjusted_capacity, 2)
                        if adjusted_capacity > 0:
                            load["utilization_pct"] = round(
                                (load["required_hours"] / adjusted_capacity) * 100, 2
                            )
                        else:
                            load["utilization_pct"] = 999.0
                        load["status"] = self._classify_status(load["utilization_pct"])
                        break

        glenday_summary = sieve.to_dict() if sieve._ranked else None

        return changeover_details, glenday_summary, round(total_co_hours, 2)

    # ── Decision Rules ────────────────────────────────────────────────

    def _apply_mps_levelling(
        self,
        resource_loads: List[Dict],
        mps_quantities: Dict[str, Dict[int, float]],
        horizon_weeks: int,
    ) -> List[Dict]:
        """Rule 3: Recommend shifting MPS quantity to nearest underloaded week (+-2 weeks).

        Identifies the product contributing the most load in an overloaded week
        and proposes shifting a portion to the most underloaded neighbouring
        week within a 2-week window.
        """
        adjustments: List[Dict] = []
        overloaded = [l for l in resource_loads if l["utilization_pct"] > 100]

        for load in overloaded:
            week = load["week"]
            resource_id = load["resource_id"]

            # Find underloaded weeks within +-2
            candidates = [
                l for l in resource_loads
                if l["resource_id"] == resource_id
                and abs(l["week"] - week) <= 2
                and l["week"] != week
                and l["utilization_pct"] < 85
            ]
            if not candidates:
                continue

            # Pick the most underloaded candidate
            best = min(candidates, key=lambda l: l["utilization_pct"])

            # Find the product contributing the most load in the overloaded week
            for product_id, weeks_map in mps_quantities.items():
                qty = weeks_map.get(week, 0)
                if qty > 0:
                    # Shift a portion to relieve overload
                    excess_pct = (load["utilization_pct"] - 95) / load["utilization_pct"]
                    shift_qty = qty * min(excess_pct, 0.5)  # Max 50% shift
                    if shift_qty > 0:
                        adjustments.append({
                            "product_id": product_id,
                            "original_week": week,
                            "adjusted_week": best["week"],
                            "quantity": round(shift_qty, 1),
                            "reason": (
                                f"Shift to week {best['week']} "
                                f"(util {best['utilization_pct']:.0f}%) to relieve "
                                f"overload at {load['utilization_pct']:.0f}%"
                            ),
                        })
                        break  # One adjustment per overloaded resource-week

        return adjustments

    def _detect_chronic_overload(self, resource_loads: List[Dict]) -> List[int]:
        """Rule 5: Detect resources overloaded for 3+ consecutive weeks.

        Returns list of resource IDs that are chronically overloaded.
        """
        by_resource: Dict[int, List[Dict]] = defaultdict(list)
        for load in resource_loads:
            by_resource[load["resource_id"]].append(load)

        chronic: List[int] = []
        for resource_id, loads in by_resource.items():
            sorted_loads = sorted(loads, key=lambda l: l["week"])
            consecutive = 0
            for load in sorted_loads:
                if load["utilization_pct"] > 100:
                    consecutive += 1
                    if consecutive >= 3:
                        chronic.append(resource_id)
                        break
                else:
                    consecutive = 0
        return chronic

    # ── BoR Auto-Generation ───────────────────────────────────────────

    def auto_generate_bor(self, config_id: int, site_id: int) -> int:
        """Auto-generate Bill of Resources from production_process data.

        Creates BoR entries by reading ProductionProcess records for the site
        and converting setup_time + operation_time into hours_per_unit.
        Returns count of entries created.
        """
        from app.models.sc_entities import ProductBom

        processes = self.db.query(ProductionProcess).filter(
            ProductionProcess.site_id == site_id,
        ).all()

        if not processes:
            logger.warning(
                f"No production processes for site {site_id} — cannot auto-generate BoR"
            )
            return 0

        # Get capacity resources for this site
        cap_resources = self.db.query(CapacityResource).filter(
            CapacityResource.site_id == site_id,
        ).all()

        # Get products linked to this site via ProductBom -> ProductionProcess
        process_ids = [p.id for p in processes]
        product_ids_from_bom = set()
        if process_ids:
            bom_rows = (
                self.db.query(ProductBom.product_id)
                .filter(ProductBom.production_process_id.in_(process_ids))
                .distinct()
                .all()
            )
            product_ids_from_bom = {row.product_id for row in bom_rows}

        products: List[Product] = []
        if product_ids_from_bom:
            products = self.db.query(Product).filter(
                Product.id.in_(product_ids_from_bom)
            ).all()

        if not products:
            # Fallback: get all products for the config
            products = self.db.query(Product).filter(
                Product.config_id == config_id
            ).all()

        # Index processes by product_id for quick lookup via BOM linkage
        process_by_product: Dict[str, ProductionProcess] = {}
        for proc in processes:
            bom_products = (
                self.db.query(ProductBom.product_id)
                .filter(ProductBom.production_process_id == proc.id)
                .all()
            )
            for (pid,) in bom_products:
                process_by_product[pid] = proc

        count = 0
        for product in products:
            # Find matching process
            process = process_by_product.get(product.id)
            if not process and processes:
                # Use first process as generic fallback
                process = processes[0]

            if not process:
                continue

            setup_time = process.setup_time or 0.0
            operation_time = process.operation_time or 0.0
            lot_size = process.lot_size if process.lot_size and process.lot_size > 0 else 1.0

            if cap_resources:
                # Create per-resource BoR entries (Bill of Capacity)
                for cr in cap_resources:
                    existing = self.db.query(BillOfResources).filter(
                        BillOfResources.config_id == config_id,
                        BillOfResources.product_id == product.id,
                        BillOfResources.site_id == site_id,
                        BillOfResources.resource_id == cr.id,
                    ).first()
                    if existing:
                        continue

                    bor = BillOfResources(
                        config_id=config_id,
                        product_id=product.id,
                        site_id=site_id,
                        resource_id=cr.id,
                        hours_per_unit=operation_time,
                        setup_hours_per_batch=setup_time,
                        typical_batch_size=lot_size,
                        production_process_id=process.id,
                        is_active=True,
                    )
                    self.db.add(bor)
                    count += 1
            else:
                # Create CPOF entry (no resource breakdown)
                existing = self.db.query(BillOfResources).filter(
                    BillOfResources.config_id == config_id,
                    BillOfResources.product_id == product.id,
                    BillOfResources.site_id == site_id,
                    BillOfResources.resource_id == None,
                ).first()
                if existing:
                    continue

                bor = BillOfResources(
                    config_id=config_id,
                    product_id=product.id,
                    site_id=site_id,
                    overall_hours_per_unit=operation_time + (setup_time / lot_size),
                    setup_hours_per_batch=setup_time,
                    typical_batch_size=lot_size,
                    production_process_id=process.id,
                    is_active=True,
                )
                self.db.add(bor)
                count += 1

        self.db.commit()
        logger.info(f"Auto-generated {count} BoR entries for config={config_id} site={site_id}")
        return count

    # ── Helper Methods ────────────────────────────────────────────────

    def _load_mps_quantities(
        self, mps_plan: MPSPlan, site_id: int, horizon_weeks: int
    ) -> Dict[str, Dict[int, float]]:
        """Load MPS quantities as {product_id: {week: quantity}}.

        MPSPlanItem stores quantities as a JSON array in weekly_quantities,
        where index 0 = week 1, index 1 = week 2, etc.  The array length
        matches mps_plan.planning_horizon_weeks.
        """
        items = self.db.query(MPSPlanItem).filter(
            MPSPlanItem.plan_id == mps_plan.id,
            MPSPlanItem.site_id == site_id,
        ).all()

        result: Dict[str, Dict[int, float]] = defaultdict(dict)

        for item in items:
            quantities = item.weekly_quantities
            if not quantities:
                continue

            if isinstance(quantities, list):
                # JSON array: index 0 = week 1
                for idx, qty in enumerate(quantities):
                    week = idx + 1
                    if 1 <= week <= horizon_weeks and qty and qty > 0:
                        result[item.product_id][week] = (
                            result[item.product_id].get(week, 0) + qty
                        )
            elif isinstance(quantities, dict):
                # Dict keyed by week number (string or int)
                for wk_key, qty in quantities.items():
                    week = int(wk_key) if isinstance(wk_key, str) else wk_key
                    if 1 <= week <= horizon_weeks and qty and qty > 0:
                        result[item.product_id][week] = (
                            result[item.product_id].get(week, 0) + qty
                        )

        return dict(result)

    def _load_capacity_resources(self, config_id: int, site_id: int) -> List[Dict]:
        """Load capacity resources as list of dicts with hours_per_week.

        Computes weekly available hours from CapacityResource fields.
        If shifts_per_day, hours_per_shift, and working_days_per_week are all
        provided, those are used for a shift-based weekly figure (with
        efficiency applied).  Otherwise, the effective_capacity property
        (= available_capacity * efficiency_percent / 100) is used directly.
        """
        from app.models.capacity_plan import CapacityPlan, CapacityPlanStatus

        resources = (
            self.db.query(CapacityResource)
            .join(CapacityPlan)
            .filter(
                CapacityPlan.supply_chain_config_id == config_id,
                CapacityPlan.status.in_([CapacityPlanStatus.ACTIVE, CapacityPlanStatus.DRAFT]),
                CapacityPlan.is_deleted == False,
                CapacityResource.site_id == site_id,
            )
            .all()
        )

        result: List[Dict] = []
        for r in resources:
            # Prefer shift-based calculation if all shift fields are present
            if r.hours_per_shift and r.shifts_per_day and r.working_days_per_week:
                hours_per_week = (
                    r.hours_per_shift
                    * r.shifts_per_day
                    * r.working_days_per_week
                    * (r.efficiency_percent / 100.0)
                )
            else:
                # Use effective_capacity property (available_capacity * efficiency)
                hours_per_week = r.effective_capacity

            result.append({
                "id": r.id,
                "name": r.resource_name,
                "available_hours_per_week": round(hours_per_week, 2),
                "utilization_target_pct": r.utilization_target_percent,
                "resource_type": r.resource_type.value if r.resource_type else None,
            })
        return result

    def _compute_demand_variability(
        self, config_id: int, site_id: int
    ) -> Optional[float]:
        """Compute coefficient of variation of recent demand for this site.

        Uses the Forecast table (forecast_quantity field, ordered by
        forecast_date descending) for up to 52 weeks of history.
        """
        try:
            from app.models.sc_entities import Forecast

            forecasts = (
                self.db.query(Forecast.forecast_quantity)
                .filter(
                    Forecast.config_id == config_id,
                    Forecast.site_id == site_id,
                    Forecast.forecast_quantity.isnot(None),
                )
                .order_by(Forecast.forecast_date.desc())
                .limit(52)
                .all()
            )

            values = [
                f.forecast_quantity for f in forecasts
                if f.forecast_quantity and f.forecast_quantity > 0
            ]
            if len(values) < 4:
                return None

            mean = sum(values) / len(values)
            if mean <= 0:
                return None
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            std = variance ** 0.5
            return round(std / mean, 3)
        except Exception as exc:
            logger.debug(f"Demand variability computation failed: {exc}")
            return None

    @staticmethod
    def _classify_status(utilization_pct: float) -> str:
        """Classify utilization into a human-readable status label."""
        if utilization_pct > 110:
            return "critical"
        elif utilization_pct > 100:
            return "warning"
        elif utilization_pct < 60:
            return "underloaded"
        return "ok"

    # ── CRUD Helpers ──────────────────────────────────────────────────

    def get_runs(
        self,
        config_id: int,
        site_id: Optional[int] = None,
        mps_plan_id: Optional[int] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[RCCPRun], int]:
        """List RCCP runs with optional filters, newest first."""
        q = self.db.query(RCCPRun).filter(RCCPRun.config_id == config_id)
        if site_id is not None:
            q = q.filter(RCCPRun.site_id == site_id)
        if mps_plan_id is not None:
            q = q.filter(RCCPRun.mps_plan_id == mps_plan_id)
        total = q.count()
        runs = q.order_by(RCCPRun.created_at.desc()).offset(offset).limit(limit).all()
        return runs, total

    def get_run(self, run_id: int) -> Optional[RCCPRun]:
        """Get a single RCCP run by ID."""
        return self.db.query(RCCPRun).filter(RCCPRun.id == run_id).first()

    def get_bor_entries(
        self,
        config_id: int,
        site_id: int,
        product_id: Optional[str] = None,
    ) -> List[BillOfResources]:
        """List active BoR entries for a config/site, optionally filtered by product."""
        q = self.db.query(BillOfResources).filter(
            BillOfResources.config_id == config_id,
            BillOfResources.site_id == site_id,
            BillOfResources.is_active == True,
        )
        if product_id is not None:
            q = q.filter(BillOfResources.product_id == product_id)
        return q.all()

    def create_bor(self, data: Dict) -> BillOfResources:
        """Create a single BoR entry."""
        bor = BillOfResources(**data)
        self.db.add(bor)
        self.db.commit()
        self.db.refresh(bor)
        return bor

    def create_bor_bulk(self, entries: List[Dict]) -> List[BillOfResources]:
        """Create multiple BoR entries in a single transaction."""
        created: List[BillOfResources] = []
        for data in entries:
            bor = BillOfResources(**data)
            self.db.add(bor)
            created.append(bor)
        self.db.commit()
        for bor in created:
            self.db.refresh(bor)
        return created

    def update_bor(self, bor_id: int, data: Dict) -> Optional[BillOfResources]:
        """Update a BoR entry by ID. Returns None if not found."""
        bor = self.db.query(BillOfResources).filter(BillOfResources.id == bor_id).first()
        if not bor:
            return None
        for k, v in data.items():
            if v is not None and hasattr(bor, k):
                setattr(bor, k, v)
        bor.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(bor)
        return bor

    def delete_bor(self, bor_id: int) -> bool:
        """Delete a BoR entry by ID. Returns True if deleted."""
        bor = self.db.query(BillOfResources).filter(BillOfResources.id == bor_id).first()
        if not bor:
            return False
        self.db.delete(bor)
        self.db.commit()
        return True
