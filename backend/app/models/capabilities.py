"""TMS capability manifest.

Declares the Core capabilities (``azirella_data_model`` subpackages) that
TMS consumes. Importing this module ensures every capability's classes
are registered on ``Base.metadata`` before SQLAlchemy configures mappers
or before migrations run ``create_all()``.

See ``Autonomy-Core/docs/CAPABILITY_MANIFEST.md`` for the pattern and the
"what goes in Core vs. variant" decision rule.

TMS currently does NOT consume:
- ``simulation`` — TMS has its own local ``PlanningScenario`` /
  ``MonteCarloScenario`` models. Migrate to ``azirella_data_model.simulation.Scenario`` when the TMS scenario surface matures.
- ``commitment`` — no TMS table subclasses ``CommitmentMixin`` yet.
  When TMS adds delivery promising (``DeliveryCommitment``), subclass
  the mixin and add this capability to the manifest.
"""
# noqa: F401 on every import — we load for side-effect (table registration)
from azirella_data_model import Base  # noqa: F401

# --- Tenant + auth ---
from azirella_data_model import tenant as _tenant  # noqa: F401

# --- Master data (AWS SC DM) ---
from azirella_data_model import master as _master  # noqa: F401

# --- AIIO governance ---
from azirella_data_model import governance as _governance  # noqa: F401

# --- Powell framework ---
from azirella_data_model import powell as _powell  # noqa: F401

# --- Context Engine ---
from azirella_data_model import context_engine as _context_engine  # noqa: F401


# Manifest metadata — available for inspection / documentation.
TMS_CAPABILITIES = (
    "tenant",
    "master",
    "governance",
    "powell",
    "context_engine",
)

__all__ = ["Base", "TMS_CAPABILITIES"]
