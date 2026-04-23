"""Tenant model — re-exports from canonical azirella-data-model.

The SQLAlchemy Tenant class is now defined in azirella-data-model and
re-exported here so that existing imports (`from app.models.tenant import Tenant`)
continue to work unchanged. This file also keeps TMS-local enums that aren't
in the canonical package.

Stage 3 Phase 3a — TMS adopts azirella-data-model tenant subpackage.
"""
from enum import Enum

# ── Canonical re-exports ─────────────────────────────────────────────────────
# These are the SAME class objects from the shared package, not duplicates.
# Every `from app.models.tenant import Tenant` across TMS resolves to the
# canonical class via this re-export.
from azirella_data_model.tenant import Tenant, TenantMode  # noqa: F401


# ── TMS-local enums (not in canonical) ───────────────────────────────────────

class TenantIndustry(str, Enum):
    """Customer industry vertical — drives default stochastic parameters.

    The canonical Tenant uses a plain String(50) column for industry so each
    app can define its own verticals. This enum is kept here for TMS code
    that references it by name. SCP has its own version with manufacturing
    verticals.
    """
    FOOD_BEVERAGE = "food_beverage"
    PHARMACEUTICAL = "pharmaceutical"
    AUTOMOTIVE = "automotive"
    ELECTRONICS = "electronics"
    CHEMICAL = "chemical"
    INDUSTRIAL_EQUIPMENT = "industrial_equipment"
    CONSUMER_GOODS = "consumer_goods"
    METALS_MINING = "metals_mining"
    AEROSPACE_DEFENSE = "aerospace_defense"
    BUILDING_MATERIALS = "building_materials"
    TEXTILE_APPAREL = "textile_apparel"
    WHOLESALE_DISTRIBUTION = "wholesale_distribution"
    THIRD_PARTY_LOGISTICS = "third_party_logistics"


class ClockMode(str, Enum):
    """Clock progression mode for Learning tenants.

    Pre-AIIO legacy (Beer Scenario simulation). Kept for backward compatibility
    with existing TMS seed scripts and config generators that reference it.
    """
    TURN_BASED = "turn_based"
    TIMED = "timed"
    REALTIME = "realtime"
