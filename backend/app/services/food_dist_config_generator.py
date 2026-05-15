"""SCP shim — canonical Food Dist config generator in Core.

``FoodDistConfigGenerator`` + ``FoodDistCascadeDataGenerator`` + 7
dataclasses + ``TemperatureCategory`` enum now live in
``azirella_data_model.synthetic_tenants.food_dist.config_generator``
(lifted 2026-05-16 per MIGRATION_REGISTER §1.1.6 + the audit verdict
that SCP is the canonical version).

Two plane-specific dependencies stay as lazy in-function imports
inside the lifted Core module:
  - ``app.models.agent_config.AgentConfig`` (per-tenant agent registry)
  - ``app.models.tenant.ClockMode`` (SCP-local enum, plane-scoped)

They resolve to the calling plane's ``app.*`` namespace at runtime.
"""
from azirella_data_model.synthetic_tenants.food_dist.config_generator import (  # noqa: F401
    TemperatureCategory,
    ProductDefinition,
    ProductGroupDefinition,
    SupplierDefinition,
    CustomerDefinition,
    RDCDefinition,
    DCConfiguration,
    FoodDistConfigGenerator,
    FoodDistCascadeDataGenerator,
)


__all__ = [
    "TemperatureCategory",
    "ProductDefinition",
    "ProductGroupDefinition",
    "SupplierDefinition",
    "CustomerDefinition",
    "RDCDefinition",
    "DCConfiguration",
    "FoodDistConfigGenerator",
    "FoodDistCascadeDataGenerator",
]
