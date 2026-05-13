"""TMS production_order shim — re-exports canonical ProductionOrder from Core.

The canonical `ProductionOrder` + `ProductionOrderComponent` live in
`azirella_data_model.work_order.production_order`. SCP and TMS both
consume the entity (SCP for manufacturing planning/execution TRMs;
TMS for capacity reads and promise-date sizing), so per CLAUDE.md
Rule 1 + Rule 2 the class is Core substrate.

Promoted 2026-05-13 because the previous shape — two full ORM classes,
one in SCP, one in TMS, both claiming `__tablename__ = "production_orders"`
— would 500 the auth path under the AD-13 modular monolith the same way
ScenarioUser did before its Core promotion.

TMS doesn't have its own plane-specific relationship targets for
ProductionOrder today — the existing TMS consumers (`capacity_plans`,
`ctp_service`) read columns + canonical relationships only, and the
ERP-extraction consumers (food_dist_history_generator, sap_*,
integrations/{odoo,b1,d365}) write canonical columns only. If TMS later
adds plane-specific relationships, attach them here following the same
pattern Autonomy-SCP@scenario.py uses for Scenario.scenario_users.

Several TMS consumers of `ProductionOrder` are actually mis-placed per
CLAUDE.md Rule 1+2 — Group A ERP extractors that belong in Core
(MIGRATION_REGISTER §1.1-1.2) and one Group B order-adjustment advisor
that should query SCP via MCP. Their cleanup is a separate workstream;
this commit only resolves the dual-mount table-name collision.
"""
from azirella_data_model.work_order.production_order import (  # noqa: F401
    ProductionOrder,
    ProductionOrderComponent,
)


__all__ = [
    "ProductionOrder",
    "ProductionOrderComponent",
]
