"""
Setup Matrix & Glenday Sieve — Changeover-aware sequencing for manufacturing.

Two components:

1. **Setup Matrix**: Loads sequence-dependent changeover times from
   `resource_capacity_constraint` (constraint_type='setup') and provides
   O(1) lookup of changeover time between any product pair on a resource.
   Falls back to `production_process.setup_time` when no pair-specific
   entry exists.

2. **Glenday Sieve**: Classifies products into Green/Yellow/Red/Blue
   runners by cumulative volume contribution (Pareto analysis).
   Green runners (~6% of SKUs, ~50% of volume) get dedicated capacity;
   remaining capacity is filled via nearest-neighbor changeover
   minimization.

Usage:
    matrix = SetupMatrix(site_id="PLANT_01", db=session)
    matrix.load()  # Populates from DB

    hours = matrix.get_changeover_time("PROD_A", "PROD_B", resource_id="LINE_1")

    sieve = GlendaySieve(site_id="PLANT_01", db=session)
    sieve.classify()  # Computes runner categories from historical volume

    category = sieve.get_category("PROD_A")  # -> RunnerCategory.GREEN

References:
    - Glenday Sieve: Ian Glenday, "Breaking Through to Flow" (2005)
    - Setup time optimization: SMED (Shingo, 1985)
    - Kinaxis MPS: Changeover matrix in finite scheduling
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)


# ============================================================================
# Setup Matrix
# ============================================================================

@dataclass
class ChangeoverEntry:
    """A single changeover time entry between two products on a resource."""
    from_product_id: str
    to_product_id: str
    resource_id: str
    setup_time_hours: float


class SetupMatrix:
    """Sequence-dependent changeover time matrix for a manufacturing site.

    Loads from `resource_capacity_constraint` where constraint_type='setup'.
    Provides O(1) lookup via (resource, from_product, to_product) key.
    Falls back to default_setup_time when no pair-specific entry exists.
    """

    def __init__(
        self,
        site_id: str,
        db: Optional[Any] = None,
        default_setup_time_hours: float = 1.0,
    ):
        self.site_id = site_id
        self.db = db
        self.default_setup_time = default_setup_time_hours

        # (resource_id, from_product_id, to_product_id) -> hours
        self._matrix: Dict[Tuple[str, str, str], float] = {}

        # resource_id -> default setup time (from production_process)
        self._resource_defaults: Dict[str, float] = {}

        # product_id -> product_group_id (for family-based fallback)
        self._product_groups: Dict[str, str] = {}

    def load(self) -> int:
        """Load setup matrix from database. Returns number of entries loaded."""
        if self.db is None:
            return 0

        count = 0
        try:
            count = self._load_constraint_entries()
            self._load_resource_defaults()
            self._load_product_groups()
        except Exception as e:
            logger.warning(f"Setup matrix load failed for {self.site_id}: {e}")
        return count

    def load_from_entries(self, entries: List[ChangeoverEntry]) -> None:
        """Load from pre-built entries (for testing / synthetic data)."""
        for entry in entries:
            key = (entry.resource_id, entry.from_product_id, entry.to_product_id)
            self._matrix[key] = entry.setup_time_hours

    def get_changeover_time(
        self,
        from_product: str,
        to_product: str,
        resource_id: Optional[str] = None,
    ) -> float:
        """Get changeover time between two products.

        Lookup priority:
        1. Exact (resource, from, to) entry in matrix
        2. Any-resource (*, from, to) entry
        3. Same product group → 30% of default (minor changeover)
        4. Same product → 0.0 (no changeover)
        5. Resource default from production_process.setup_time
        6. Global default_setup_time
        """
        if from_product == to_product:
            return 0.0

        # 1. Exact resource match
        if resource_id:
            key = (resource_id, from_product, to_product)
            if key in self._matrix:
                return self._matrix[key]

        # 2. Any-resource wildcard
        key = ("*", from_product, to_product)
        if key in self._matrix:
            return self._matrix[key]

        # 3. Same product group → minor changeover
        from_group = self._product_groups.get(from_product)
        to_group = self._product_groups.get(to_product)
        if from_group and to_group and from_group == to_group:
            base = self._resource_defaults.get(resource_id or "", self.default_setup_time)
            return base * 0.3  # 30% of full changeover for same family

        # 4. Resource default
        if resource_id and resource_id in self._resource_defaults:
            return self._resource_defaults[resource_id]

        # 5. Global default
        return self.default_setup_time

    @property
    def num_entries(self) -> int:
        return len(self._matrix)

    def _load_constraint_entries(self) -> int:
        """Load from resource_capacity_constraint table."""
        from app.models.resource_capacity import ResourceCapacityConstraint

        rows = (
            self.db.query(ResourceCapacityConstraint)
            .filter(
                ResourceCapacityConstraint.constraint_type == "setup",
                ResourceCapacityConstraint.from_product_id.isnot(None),
                ResourceCapacityConstraint.to_product_id.isnot(None),
            )
            .all()
        )
        count = 0
        for row in rows:
            resource = row.resource_id or "*"
            key = (resource, row.from_product_id, row.to_product_id)
            self._matrix[key] = row.setup_time_hours or self.default_setup_time
            count += 1

        logger.info(f"Setup matrix: loaded {count} entries for site {self.site_id}")
        return count

    def _load_resource_defaults(self) -> None:
        """Load default setup times from production_process."""
        from app.models.sc_entities import ProductionProcess, Site

        site = self.db.query(Site).filter(Site.name == self.site_id).first()
        if not site:
            return

        processes = (
            self.db.query(ProductionProcess)
            .filter(ProductionProcess.site_id == site.id)
            .all()
        )
        for proc in processes:
            if proc.id and proc.setup_time:
                self._resource_defaults[proc.id] = proc.setup_time

    def _load_product_groups(self) -> None:
        """Load product -> product_group mapping for family-based fallback."""
        from app.models.sc_entities import Product

        products = self.db.query(Product.id, Product.product_group_id).all()
        for pid, gid in products:
            if gid:
                self._product_groups[pid] = gid


# ============================================================================
# Glenday Sieve — Runner Classification
# ============================================================================

class RunnerCategory(str, Enum):
    """Glenday Sieve categories by cumulative volume contribution.

    Green: Top ~6% of SKUs, ~50% of volume — high runners, dedicated capacity
    Yellow: Next ~14%, cumulative ~95% — medium runners
    Red: Next ~30%, cumulative ~99% — low runners
    Blue: Remaining ~50% of SKUs, <1% of volume — strangers/one-offs
    """
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    BLUE = "blue"


@dataclass
class SieveResult:
    """Result of Glenday Sieve classification for a single product."""
    product_id: str
    category: RunnerCategory
    volume: float                # Total production volume
    volume_share: float          # Fraction of total volume
    cumulative_share: float      # Cumulative fraction at this rank
    rank: int                    # 1-based rank by volume


@dataclass
class GlendaySieveConfig:
    """Thresholds for Glenday Sieve classification."""
    green_cumulative_pct: float = 0.50   # Top cumulative 50% of volume
    yellow_cumulative_pct: float = 0.95  # Next cumulative up to 95%
    red_cumulative_pct: float = 0.99     # Next cumulative up to 99%
    # Blue = everything above 99%

    # Lookback for volume calculation (days of historical MO data)
    lookback_days: int = 90


class GlendaySieve:
    """Glenday Sieve: classifies products into runner categories.

    Uses historical production volume (from powell_mo_decisions or
    production_process data) to rank products by output volume and
    classify into Green/Yellow/Red/Blue runners.

    Green runners should be sequenced first with dedicated capacity
    windows. Remaining capacity is filled by Yellow/Red runners
    sequenced via nearest-neighbor changeover minimization.
    Blue runners are batched into campaign windows.
    """

    def __init__(
        self,
        site_id: str,
        config: Optional[GlendaySieveConfig] = None,
        db: Optional[Any] = None,
    ):
        self.site_id = site_id
        self.config = config or GlendaySieveConfig()
        self.db = db

        # product_id -> SieveResult
        self._classifications: Dict[str, SieveResult] = {}

        # Ordered list by volume descending
        self._ranked: List[SieveResult] = []

    def classify(self, volume_data: Optional[Dict[str, float]] = None) -> int:
        """Run Glenday Sieve classification.

        Args:
            volume_data: Optional pre-computed {product_id: total_volume}.
                If None, loads from DB (powell_mo_decisions).

        Returns:
            Number of products classified.
        """
        if volume_data is None:
            volume_data = self._load_volume_from_db()

        if not volume_data:
            return 0

        total_volume = sum(volume_data.values())
        if total_volume <= 0:
            return 0

        # Sort by volume descending
        sorted_products = sorted(
            volume_data.items(), key=lambda x: x[1], reverse=True
        )

        cumulative = 0.0
        self._ranked = []
        self._classifications = {}

        for rank, (product_id, volume) in enumerate(sorted_products, 1):
            share = volume / total_volume
            cumulative += share

            if cumulative <= self.config.green_cumulative_pct:
                category = RunnerCategory.GREEN
            elif cumulative <= self.config.yellow_cumulative_pct:
                category = RunnerCategory.YELLOW
            elif cumulative <= self.config.red_cumulative_pct:
                category = RunnerCategory.RED
            else:
                category = RunnerCategory.BLUE

            result = SieveResult(
                product_id=product_id,
                category=category,
                volume=volume,
                volume_share=share,
                cumulative_share=cumulative,
                rank=rank,
            )
            self._ranked.append(result)
            self._classifications[product_id] = result

        counts = self._category_counts()
        logger.info(
            f"Glenday Sieve for {self.site_id}: "
            f"{counts.get('green', 0)} green, {counts.get('yellow', 0)} yellow, "
            f"{counts.get('red', 0)} red, {counts.get('blue', 0)} blue "
            f"({len(self._ranked)} total products)"
        )
        return len(self._ranked)

    def get_category(self, product_id: str) -> RunnerCategory:
        """Get runner category for a product. Defaults to BLUE if unknown."""
        result = self._classifications.get(product_id)
        return result.category if result else RunnerCategory.BLUE

    def get_result(self, product_id: str) -> Optional[SieveResult]:
        """Get full sieve result for a product."""
        return self._classifications.get(product_id)

    def get_products_by_category(self, category: RunnerCategory) -> List[str]:
        """Get all product IDs in a given category, ranked by volume."""
        return [
            r.product_id for r in self._ranked
            if r.category == category
        ]

    def green_runners(self) -> List[str]:
        return self.get_products_by_category(RunnerCategory.GREEN)

    def _category_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for r in self._ranked:
            counts[r.category.value] = counts.get(r.category.value, 0) + 1
        return counts

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for API / dashboard."""
        return {
            "site_id": self.site_id,
            "total_products": len(self._ranked),
            "categories": self._category_counts(),
            "green_runners": self.green_runners(),
            "classifications": {
                r.product_id: {
                    "category": r.category.value,
                    "volume": r.volume,
                    "volume_share": round(r.volume_share, 4),
                    "cumulative_share": round(r.cumulative_share, 4),
                    "rank": r.rank,
                }
                for r in self._ranked
            },
        }

    def _load_volume_from_db(self) -> Dict[str, float]:
        """Load production volume from powell_mo_decisions."""
        if self.db is None:
            return {}

        try:
            from sqlalchemy import func
            from datetime import datetime, timedelta
            from app.models.powell_decisions import PowellMODecision

            cutoff = datetime.utcnow() - timedelta(days=self.config.lookback_days)
            rows = (
                self.db.query(
                    PowellMODecision.product_id,
                    func.sum(PowellMODecision.planned_qty).label("total_qty"),
                )
                .filter(
                    PowellMODecision.site_id == self.site_id,
                    PowellMODecision.created_at >= cutoff,
                    PowellMODecision.planned_qty.isnot(None),
                )
                .group_by(PowellMODecision.product_id)
                .all()
            )
            return {r.product_id: float(r.total_qty) for r in rows if r.product_id}
        except Exception as e:
            logger.warning(f"Glenday volume load failed: {e}")
            return {}


# ============================================================================
# Nearest-Neighbor Greedy Sequencer
# ============================================================================

@dataclass
class SequencedMO:
    """An MO with its position in the optimized sequence."""
    order_id: str
    product_id: str
    sequence_position: int
    changeover_hours: float     # Changeover time FROM previous order
    runner_category: RunnerCategory
    priority_score: float       # Original priority score


def sequence_with_glenday(
    orders: List[Dict[str, Any]],
    setup_matrix: SetupMatrix,
    sieve: GlendaySieve,
    available_capacity_hours: float,
    current_product: Optional[str] = None,
) -> List[SequencedMO]:
    """Glenday-aware sequencing: green runners first, then nearest-neighbor fill.

    Algorithm:
    1. Classify all orders by runner category
    2. Schedule GREEN runners first (sorted by due date within green)
    3. Compute remaining capacity after green runners
    4. If no remaining capacity, return only green runners
    5. Otherwise, fill with YELLOW/RED/BLUE via nearest-neighbor
       changeover minimization (greedy TSP from last green product)

    Args:
        orders: List of dicts with keys: order_id, product_id, priority,
            days_until_due, setup_time_hours, run_time_hours
        setup_matrix: Loaded SetupMatrix for changeover lookups
        sieve: Classified GlendaySieve
        available_capacity_hours: Total available capacity in scheduling window
        current_product: Product currently on the line (for first changeover)

    Returns:
        Ordered list of SequencedMO with positions and changeover times.
    """
    if not orders:
        return []

    # Partition by runner category
    green_orders = []
    other_orders = []

    for mo in orders:
        cat = sieve.get_category(mo["product_id"])
        if cat == RunnerCategory.GREEN:
            green_orders.append((mo, cat))
        else:
            other_orders.append((mo, cat))

    # Sort green runners by due date urgency (most urgent first)
    green_orders.sort(key=lambda x: x[0].get("days_until_due", 999))

    result: List[SequencedMO] = []
    pos = 1
    used_capacity = 0.0
    last_product = current_product

    # Phase 1: Schedule green runners
    for mo, cat in green_orders:
        changeover = setup_matrix.get_changeover_time(
            last_product or "", mo["product_id"]
        ) if last_product else 0.0

        run_hours = mo.get("run_time_hours", 0.0) + mo.get("setup_time_hours", 0.0)
        used_capacity += changeover + run_hours

        result.append(SequencedMO(
            order_id=mo["order_id"],
            product_id=mo["product_id"],
            sequence_position=pos,
            changeover_hours=changeover,
            runner_category=cat,
            priority_score=_priority_score(mo),
        ))
        last_product = mo["product_id"]
        pos += 1

    remaining_capacity = available_capacity_hours - used_capacity

    # Phase 2: If capacity remains, fill with others via nearest-neighbor
    if remaining_capacity > 0 and other_orders:
        # Build candidate pool
        candidates = list(other_orders)

        while candidates and remaining_capacity > 0:
            # Find nearest neighbor (minimum changeover from last_product)
            best_idx = -1
            best_changeover = float("inf")
            best_total = float("inf")

            for i, (mo, cat) in enumerate(candidates):
                changeover = setup_matrix.get_changeover_time(
                    last_product or "", mo["product_id"]
                ) if last_product else 0.0

                run_hours = mo.get("run_time_hours", 0.0) + mo.get("setup_time_hours", 0.0)
                total = changeover + run_hours

                # Prefer lower changeover; break ties by urgency
                if changeover < best_changeover or (
                    changeover == best_changeover and total < best_total
                ):
                    best_idx = i
                    best_changeover = changeover
                    best_total = total

            if best_idx < 0:
                break

            mo, cat = candidates.pop(best_idx)
            run_hours = mo.get("run_time_hours", 0.0) + mo.get("setup_time_hours", 0.0)
            total_hours = best_changeover + run_hours

            if total_hours > remaining_capacity:
                # Won't fit — skip (could try others, but greedy is fine)
                continue

            remaining_capacity -= total_hours

            result.append(SequencedMO(
                order_id=mo["order_id"],
                product_id=mo["product_id"],
                sequence_position=pos,
                changeover_hours=best_changeover,
                runner_category=cat,
                priority_score=_priority_score(mo),
            ))
            last_product = mo["product_id"]
            pos += 1

    return result


def _priority_score(mo: Dict[str, Any]) -> float:
    """Calculate priority score from MO dict."""
    priority = mo.get("priority", 3)
    days = mo.get("days_until_due", 30)
    return max(0.0, min(1.0,
        0.5 * (1.0 - (priority - 1) / 4.0) +
        0.5 * max(0, 1.0 - days / 30.0)
    ))
