"""SQLAlchemy Base — re-exports from canonical azirella-data-model.

Stage 3 Phase 3a: TMS now uses the canonical Base so that ALL models
(canonical re-exports + TMS-specific entities) register against the
same metadata. Cross-model relationships resolve because everything
is on one shared metadata object.

Previously TMS had its own Base via declarative_base(cls=CustomBase)
with a table_names dict for Beer Game legacy naming (Game→games,
Player→players, Round→rounds). That dict is removed; any model that
relied on it must have an explicit __tablename__ attribute.
"""

# THE canonical Base — all TMS models must inherit from this.
from azirella_data_model.base import Base  # noqa: F401

# Import canonical tenant subpackage to register with Base metadata.
# Phase 3a only adopts tenant/; master, governance, and powell are
# imported in their respective Phase 3b/3c/3d sessions to avoid
# metadata collisions with TMS's local model files that haven't been
# rewritten as shims yet (e.g., supply_chain_config.py still defines
# SupplyChainConfig locally — would collide with canonical master/config.py).
import azirella_data_model.tenant  # noqa: F401

# Import TMS-specific models to register them with the same Base metadata.
# These are the models that stay in TMS (not canonical).
from app.models.tms.user_extensions import TMSUserExtension  # noqa: F401
