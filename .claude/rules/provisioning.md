# Provisioning (TMS — evolving)

The 17-step provisioning pipeline adapted for transportation:

```
warm_start → sop_graphsage → cfa_optimization → lgbm_forecast →
demand_tgnn → supply_tgnn → inventory_tgnn → trm_training →
rl_training → backtest_evaluation → transportation_plan →
capacity_validation → decision_seed → site_tgnn → conformal →
scenario_bootstrap → briefing
```

## Key changes vs SC Planning

- `supply_plan` → `transportation_plan` (load assignments, carrier allocations)
- `rccp_validation` → `capacity_validation` (carrier capacity vs. demand)
- Forecast targets **shipping volumes**, not product demand
- TRM training data from **freight execution history**, not manufacturing / inventory

## Invariants

- **Only tenant admin can provision.** Never systemadmin.
- **No RL at provisioning time.** TRM weights load from disk. Site tGNN
  trains via behavioural cloning only.
- **`decision_seed` runs real TRM decision cycle** — never fabricated
  cards. Produces `context_data` JSONB with real reasoning.
- **Failures are ERROR-level and leave `status=failed`.** Tenant admin
  must see them in the UI.
- **Provisioning framework lives in Autonomy-Core.** TMS owns only the
  step *definitions*. See [core-vs-product-placement.md](core-vs-product-placement.md).
