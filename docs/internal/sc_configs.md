# Seeded Supply Chain Configurations

The seeding script (`backend/scripts/seed_default_group.py`) creates supply chain configurations and administrator accounts.

## Default TBG configuration
- **Group/Config name:** `TBG` / `Default TBG` (inventory-only template).
- **Admin user:** `tbg_admin`
- **Password:** `Autonomy@2026`
- **Seeding logic:** Created via `ensure_supply_chain_config` inside the default `config_specs` loop.

## Case TBG configuration
- **Group/Config name:** `TBG` / `Case TBG` (manufacturer master type with Case-from-Six-Pack BOM and `Case Mfg` node).
- **Admin user:** `tbg_admin`
- **Password:** `Autonomy@2026`
- **Seeding logic:** Added in the `config_specs` loop via `ensure_case_config`, naming the manufacturer `Case Mfg` with a 1:4 Six-Pack BOM.

## Six-Pack TBG configuration
- **Group/Config name:** `TBG` / `Six-Pack TBG` (adds a `Six-Pack Mfg` that builds Six-Packs 1:6 from Bottles before `Case Mfg` assembles Cases 1:4).
- **Admin user:** `tbg_admin`
- **Password:** `Autonomy@2026`
- **Seeding logic:** Added via `ensure_six_pack_config` in the `config_specs` loop.

## Bottle TBG configuration
- **Group/Config name:** `TBG` / `Bottle TBG` (introduces `Bottle Mfg` converting Ingredients 1:1 into Bottles feeding `Six-Pack Mfg` 1:6 and `Case Mfg` 1:4).
- **Admin user:** `tbg_admin`
- **Password:** `Autonomy@2026`
- **Seeding logic:** Added via `ensure_bottle_config` in the `config_specs` loop.

## Complex_SC configuration
- **Group/Config name:** `Complex_SC` / `Complex_SC` (multi-region, multi-echelon template).
- **Admin user:** `complex_sc_admin`
- **Password:** `Autonomy@2026`
- **Seeding logic:** Added after the default loop with `ensure_multi_region_config`.

## Database bootstrap account
- **User:** `beer_user`
- **Password:** `Autonomy@2026`
- **Purpose:** Initial MariaDB account created by `init_db.sql` for application access.
