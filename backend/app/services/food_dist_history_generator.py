"""SCP shim — canonical Food Dist history generator in Core.

``FoodDistHistoryGenerator`` (the 3-year transactional-history seeder
for Food Dist demos) now lives in
``azirella_data_model.synthetic_tenants.food_dist.history_generator``
(lifted 2026-05-16 per MIGRATION_REGISTER §1.1.6 + audit verdict —
SCP is canonical; TMS's copy was a regression that reverted SCP's
trading_partners-canonical customer model).
"""
from azirella_data_model.synthetic_tenants.food_dist.history_generator import (  # noqa: F401
    FoodDistHistoryGenerator,
)


__all__ = ["FoodDistHistoryGenerator"]
