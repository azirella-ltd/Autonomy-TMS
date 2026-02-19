# The Beer Game Logic Guide

## Game Overview
- The Beer Game models a four-stage supply chain with roles arranged downstream to upstream: **Retailer → Wholesaler → Distributor → Manufacturer**.
- Time advances in discrete weekly steps. At the start of week 0 every role holds 12 units of inventory, no backlog, and an in-transit pipeline preloaded with 4 units to reflect the shipping lead time.
- All roles apply the same base-stock policy: they try to keep their inventory position at a target level (15 units by default) while facing lead times when receiving goods.

## Weekly Sequence of Play
1. **Arrivals land**
   - Each role removes the oldest value from its inbound shipment pipeline (lead time `L_ship`, default 2 weeks) and adds it to on-hand inventory.
   - The manufacturer also pops finished goods from a production pipeline that has lead time `L_prod` (default 2 weeks); those units are added to manufacturer inventory.

2. **Observe demand**
   - The retailer sees customer demand directly (`demand_series[t]` for week *t*).
   - Every upstream role uses the order placed by its immediate downstream partner in the same week as the new demand it must satisfy.
   - Total demand for a role in week *t* is: new demand + backlog carried over from previous weeks.

3. **Ship downstream**
   - A role ships as much as it can, constrained by on-hand inventory.
   - Shipments are committed immediately but only reach the downstream role after `L_ship` weeks because they enter the downstream role's inbound pipeline.

4. **Update state**
   - Inventory after shipping: `I' = max(0, I + arrivals + finished_goods - shipment)`
   - Backlog after shipping: `B_next = demand + previous_backlog - shipment`

5. **Place upstream order**
   - Inventory position combines what a role has, what it owes, and what is already on the way:
     `IP = (I' - B_next) + sum(inbound_pipeline) [+ sum(production_pipeline for manufacturer)]`
   - Order quantity: `O = max(0, target_stock - IP)`
   - The manufacturer also queues this order in its production pipeline so finished goods will arrive after `L_prod` weeks.

6. **Record costs and histories**
   - Holding and backlog costs are computed and logged.
   - Order and shipment histories are stored for later analysis.

## Demand Calculation
- Retailer: `demand_retailer[t] = demand_series[t]` (external customers)
- Upstream roles: `demand_role[t] = order_downstream[t]`
- Total demand to be met in week *t*: `total_demand = demand_role[t] + backlog[t]`
- Fulfilled demand equals `min(inventory, total_demand)`; the difference accumulates as backlog.

## Inventory Tracking
- Start-of-week inventory is last week's ending inventory.
- After arrivals from pipelines and shipping decisions, the role's next-week inventory is stored in `inv_history`.
- Inventory cannot drop below zero; unmet demand moves into backlog.

## Supply (Shipments and Production)
- After shipment decisions, the quantity shipped downstream is inserted into the last slot of the downstream role's inbound pipeline, guaranteeing it arrives after the shipping lead time.
- Manufacturer production mirrors orders: units produced this week equal the order it receives, and they join the production pipeline before becoming available as inventory after `L_prod` weeks.

## Backlog Cost Calculation
- Backlog is treated as accumulated unmet demand (no lost sales).
- Weekly backlog cost for a role is `backlog_cost_rate * backlog_units_at_end_of_week`.
  - Default backlog cost rate (`backlog_cost`) is 1.0 per unit per week for all roles.

## Holding Cost Calculation
- Holding cost reflects the expense of carrying inventory.
- Weekly holding cost for a role is `holding_cost_rate * inventory_units_at_end_of_week`.
  - Default holding cost rate (`holding_cost`) is 0.5 per unit per week for all roles.

## Total Cost per Week
- Total cost recorded for each role in week *t*:
  `total_cost = holding_cost + backlog_cost`
- Cumulative costs are tracked by `cost_history` and can be summed over the simulation horizon.

## Key Takeaways
- Demand moves upstream instantly as information (orders), while physical goods move downstream with shipping and production delays.
- The base-stock policy attempts to keep inventory position near the target, but lead times cause oscillations that create the classic Beer Game dynamics.
- Holding cost encourages lean inventories; backlog cost penalizes failing to meet demand, pushing players to balance both pressures when placing orders.
