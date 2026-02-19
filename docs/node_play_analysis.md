# Node play analysis for Beer Game supply chains

This note summarizes how each node role behaves in the two canonical Beer Game supply-chain templates that ship with the repo: **Default TBG** (inventory-only) and **Case TBG** (with a Case manufacturer using a Six-Pack BOM). It highlights what each node orders or supplies per round and clarifies how Manufacturer logic is applied in both setups.

## Default TBG (inventory-only)
* **Topology and items** — The configuration contains a single finished good (Case) and wires Market Supply → Manufacturer → Distributor → Wholesaler → Retailer → Market Demand with deterministic order lead time 1 and supply lead time 2 on every lane.【F:backend/scripts/seed_default_group.py†L1034-L1099】
* **Node types** — Every internal role, including the "Manufacturer", is instantiated as an Inventory master type, so it behaves like any other stocking node with no bill of materials or production step.【F:backend/scripts/seed_default_group.py†L1056-L1076】
* **Play pattern per node**
  * **Retailer/Wholesaler/Distributor/"Manufacturer"** — Each node holds only Case inventory, observes matured inbound demand from its immediate downstream, and places replenishment orders upstream according to its agent/human decision just like a standard Beer Game echelon. There is no BOM explosion or component tracking; upstream orders are simply for Cases.【F:backend/scripts/seed_default_group.py†L1056-L1144】
  * **Market Supply** — Acts as the upstream source responding to Case orders coming from the Inventory-typed manufacturer lane with the configured delays.【F:backend/scripts/seed_default_group.py†L1078-L1100】
  * **Market Demand** — Pulls external Case demand only; no Six-Pack item exists in this scenario.【F:backend/scripts/seed_default_group.py†L1047-L1054】【F:backend/scripts/seed_default_group.py†L1118-L1144】

## Case TBG (Case Mfg with BOM)
* **Topology and items** — Two items are seeded: Six-Pack (supplied by Market Supply) and Case (demanded by Market Demand). The chain remains linear: Market Supply → Case Manufacturer → Distributor → Wholesaler → Retailer → Market Demand, with deterministic order lead time 1 and stochastic supply lead time 1–5 on each lane.【F:backend/scripts/seed_default_group.py†L890-L956】
* **Node types** — Downstream echelons map to Inventory master type, but the Case Mfg node is explicitly a Manufacturer master type, enabling BOM-driven production rather than simple pass-through storage.【F:backend/scripts/seed_default_group.py†L905-L938】
* **Manufacturer BOM and production**
  * The Case Mfg node declares a 1:4 BOM, consuming four Six-Packs to produce one Case. Manufacturing capacity and lead time metadata (168-hour capacity, zero production lead) are attached to the node for scheduling.【F:backend/scripts/seed_default_group.py†L930-L938】
  * During simulation setup, MixedGameService normalizes each manufacturer’s configured BOM, mapping produced items to required components and registering component sources when a single upstream supplier exists. This preserves the exact ratios (e.g., 1 Case : 4 Six-Packs) when exploding orders into component demand.【F:backend/app/services/mixed_game_service.py†L1554-L1627】
* **Play pattern per node**
  * **Case Mfg** — Receives Case demand from Distributor, translates it into Six-Pack component pull using the BOM, and places upstream orders on Market Supply (or a component supplier) with the lane’s order lead time baked into the request schedule. The manufacturer’s inbound components accrue in on-order/inbound queues until due, after which production can fulfill downstream Case demand.【F:backend/app/services/mixed_game_service.py†L1554-L1627】【F:backend/app/services/mixed_game_service.py†L1611-L1621】
  * **Distributor/Wholesaler/Retailer** — Operate as Inventory nodes for both Case and Six-Pack items, carrying per-item inventory/backlog state and issuing orders upstream based on observed downstream demand each round.【F:backend/scripts/seed_default_group.py†L961-L975】
  * **Market Supply** — Supplies Six-Pack components requested by the manufacturer; its lead time parameters govern when component arrivals become available for production.【F:backend/scripts/seed_default_group.py†L941-L956】
  * **Market Demand** — Generates external Case demand only; Six-Pack demand remains zeroed in the seed data, so all Six-Packs are produced only to satisfy Case production.【F:backend/scripts/seed_default_group.py†L890-L906】【F:backend/scripts/seed_default_group.py†L1002-L1014】

## Order maturation and round sequencing (applies to both configs)
* Market Demand orders are queued with their lane’s order lead time and only become visible to the supplying node when due; the same scheduling applies to every upstream replenishment request, so each echelon only reacts to matured orders for the current round.【F:docs/supply_chain_demand_flow.md†L10-L22】【F:docs/supply_chain_demand_flow.md†L25-L38】
* When a manufacturer is present (Case TBG), the BOM-derived component demand is registered on the upstream supplier before production, ensuring component shortages propagate as backlog if insufficient components arrive on time.【F:backend/app/services/mixed_game_service.py†L1554-L1627】
