"""TMS DecisionLevelEnum — Python-side validation enum for user.decision_level.

Previously, this module defined a `TMSUserExtension` sibling table and a
monkey-patch that shadowed the canonical `User.decision_level` column
with a Python property. That design was **removed on 2026-04-13**
because:

1. The canonical User in azirella-data-model already has
   `decision_level: Mapped[Optional[str]]` — a permissive string column
   explicitly designed to let each app store its own role values.
2. The sibling table had no alembic migration — writes would have
   failed with "relation does not exist" at flush time.
3. The monkey-patch replaced the SQLAlchemy InstrumentedAttribute with
   a plain Python property, silently breaking class-level queries like
   `select(User).where(User.decision_level == "X")`.

The canonical column is the source of truth. This module keeps only
the Python-side enum so app code can use typed role constants for
validation and comparisons.

Call convention:
- WRITE: `user.decision_level = DecisionLevelEnum.MPS_MANAGER.value`
  (store the string, which is what the column expects)
- READ: `user.decision_level` returns a string; compare against
  `DecisionLevelEnum.X.value` or use `DecisionLevelEnum(user.decision_level)`
  to get an enum instance (may raise ValueError for unknown values)
"""

from enum import Enum as PyEnum


class DecisionLevelEnum(str, PyEnum):
    """Decision level classification for TMS users.

    Determines landing page routing and navigation section visibility.
    Currently uses the same values as SCP (inherited from the fork);
    TMS-specific role names (e.g., CAPACITY_PROMISE_ANALYST) will be
    added in a future refactor aligned with Workstream A3 (navigation
    type extension).

    Inherits from `str` so enum members compare equal to their string
    values — `DecisionLevelEnum.SC_VP == "SC_VP"` is True.
    """
    SC_VP = "SC_VP"
    SOP_DIRECTOR = "SOP_DIRECTOR"
    MPS_MANAGER = "MPS_MANAGER"
    ALLOCATION_MANAGER = "ALLOCATION_MANAGER"
    ORDER_PROMISE_MANAGER = "ORDER_PROMISE_MANAGER"
    ATP_ANALYST = "ATP_ANALYST"
    REBALANCING_ANALYST = "REBALANCING_ANALYST"
    PO_ANALYST = "PO_ANALYST"
    ORDER_TRACKING_ANALYST = "ORDER_TRACKING_ANALYST"
    EXECUTIVE = "EXECUTIVE"
    DEMO_ALL = "DEMO_ALL"
