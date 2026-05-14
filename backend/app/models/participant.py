"""TMS participant shim — re-exports canonical ScenarioUser from Core.

The canonical `ScenarioUser` (plus its enums and the back-relation on
`User`) lives in `azirella_data_model.simulation.scenario_user`. SCP and
TMS both consume it — moved 2026-05-13 because both planes registering
their own copy against the shared Base caused
`Multiple classes found for path "ScenarioUser"` 500s on the auth path
in the AD-13 modular-monolith topology. Same monkey-patch pattern
already used by `Scenario.scenario_users` in `app/models/scenario.py`.

This module adds the TMS-specific relationships to the canonical
ScenarioUser class. None of them target Core classes — they all
reference models that live only in TMS and are loaded before
configure_mappers() runs. The relationships are deliberately identical
to SCP's because the underlying tables (scenario_user_inventory,
orders, scenario_user_periods, function_assignments, agent_suggestions,
what_if_analyses) ARE substrate that both planes will eventually adopt
from Core; the per-plane shape is the migration bridge until each one
is promoted.

Backward-compatibility aliases (`Participant` → `ScenarioUser`, etc.)
are preserved for the small handful of legacy callsites still on the
pre-2026 names.
"""
from sqlalchemy.orm import relationship

# Canonical class + enums.
from azirella_data_model.simulation.scenario_user import (  # noqa: F401
    AgentMode,
    FunctionCategory,
    ScenarioUser,
    ScenarioUserFunction,
    ScenarioUserRole,
    ScenarioUserStrategy,
    ScenarioUserType,
)

# TMS-local model classes referenced by the relationships below — imported
# for module-load-time side-effects (registers them with Base.metadata).
from .supply_chain import ScenarioUserInventory, ScenarioUserPeriod, Order  # noqa: F401
from .function_assignment import FunctionAssignment  # noqa: F401

# All ScenarioUser back-relations whose targets live in Core are now
# declared in Core too:
#   - `.inventory` / `.orders` / `.scenario_user_periods` — §3.73 Step 2
#     (`azirella_data_model.simulation.supply_chain`).
#   - `.agent_suggestions` / `.what_if_analyses` — §3.73 Step 3
#     (`azirella_data_model.simulation.chat`).
#   - `.function_assignments` — §3.73 Step 2b
#     (`azirella_data_model.simulation.function_assignment`).


# Backward-compatibility aliases (temporary - remove after full migration)
Participant = ScenarioUser
ParticipantRole = ScenarioUserRole
ParticipantType = ScenarioUserType
ParticipantStrategy = ScenarioUserStrategy
ParticipantFunction = ScenarioUserFunction
ParticipantAction = None  # Will be set after scenario.py imports

__all__ = [
    "AgentMode",
    "FunctionCategory",
    "ScenarioUser",
    "ScenarioUserFunction",
    "ScenarioUserRole",
    "ScenarioUserStrategy",
    "ScenarioUserType",
    "Participant",
    "ParticipantRole",
    "ParticipantType",
    "ParticipantStrategy",
    "ParticipantFunction",
    "ParticipantAction",
]
