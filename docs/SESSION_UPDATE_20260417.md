# TMS Session Update — 2026-04-17

**What changed on SCP + Core today that TMS needs to know about.**

---

## 1. Terminology rename complete (game→scenario, round→period)

SCP commit `f3f6fc1d`. 104 files, 15 DB columns renamed, zero stale "game" or "round" terminology remaining. Alembic migration `20260417_terminology_rename` drops the `rounds` table, renames `scenario_rounds` → `scenario_periods`, and renames 15 columns.

**TMS action:** Run the same migration pattern on TMS if it has equivalent stale columns. Check:
```sql
SELECT table_name, column_name FROM information_schema.columns
WHERE (column_name LIKE '%game%' OR column_name LIKE '%round%')
  AND table_schema='public' AND table_name NOT LIKE 'turnaround%';
```

## 2. PPO production extensions in Core (commit `4c45227`)

`azirella_data_model.ml.rl_harness.TwinRlTrainer` now has full production PPO:
- Multi-epoch sub-iterations (ppo_epochs=4)
- Shuffled minibatch sampling (minibatch_size=64)
- Old log-prob capture for importance-sampling ratio
- KL-divergence early stopping (kl_target=0.015)
- Cosine/linear LR schedule

**TMS action:** Bump `azirella-data-model` pin to `4124f0b` (latest Core). The new TwinRlTrainer is backward-compatible.

## 3. Four more modules extracted to Core (commit `221b793`)

| Core path | What |
|---|---|
| `azirella_data_model.optimization.plan_versions` | PlanVersion enum |
| `azirella_data_model.optimization.capacity_gap_analyzer` | Gap analysis + proposal emission |
| `azirella_data_model.optimization.synthetic_capacity_seeder` | Regional calendar + peak-from-plan capacity bootstrapping |
| `azirella_data_model.ml.pretrained_trm_registry` | Per-TRM adapter dispatch with stats |

**TMS action:** Import these from Core when porting, not from SCP. SCP files are re-export shims.

## 4. BaseScenarioService in Core (commit `4124f0b`)

New abstract base class at `azirella_data_model.simulation.scenario_service.BaseScenarioService`. Products subclass and implement:

```python
class TmsScenarioService(BaseScenarioService):
    def _solve(self, scenario_id, config_id):
        # Call TransportationPlanGenerator
        ...
    def _report(self, scenario_id, config_id):
        # Call MovementGapAnalyzer
        ...
    def _list_query(self, tenant_id):
        # Query TMS's scenario table
        ...
    def _scenario_config_id(self, scenario_id):
        # TMS's scenario → config mapping
        ...
    def _state_query(self, scenario_id):
        # TMS state from transportation_plan
        ...
    def create_scenario(self, **kwargs):
        # TMS-specific scenario table INSERT
        ...
```

Lifecycle logic (start/stop/reset/advance/finish) is in the base class — zero duplication.

**TMS action:** Create `TmsScenarioService(BaseScenarioService)` with the 6 abstract methods implemented for TMS tables.

## 5. Per-cell BSC solve-split (SCP commit `cff4cba7`)

`ConstrainedPlanGenerator` now splits cells into weight-homogeneous groups when `max_axis_std > 0.05` and solves each group independently. Results merged.

**TMS action:** When TMS builds its equivalent plan generator, use the same pattern. The threshold (0.05) should be configurable per tenant via `tenant_solver_features`.

## 6. BSC Overrides admin page (SCP commit `cff4cba7`)

New `/admin/bsc-overrides` page with 5-axis editor + resolver preview. Uses the CRUD endpoints at `/tenants/{t}/bsc-weights-overrides` (already exist in SCP, TMS needs its own router).

**TMS action:** Port the page or share via Core frontend components when that's available.

## 7. Legacy Beer Game engine deleted (SCP commits `f5f98060` → `4dd3d175`)

`mixed_scenario_service.py` (10,456 lines) and `mixed_scenario.py` (3,768 lines) are deleted from SCP. Replaced by `ScenarioService` (now inheriting `BaseScenarioService` from Core).

**TMS action:** If TMS forked any code from `mixed_scenario_service.py`, it's now dead upstream. Replace with `TmsScenarioService(BaseScenarioService)`.

## 8. Current Core pin

Latest Core commit: `4124f0b`. Includes:
- Production PPO
- BaseScenarioService
- plan_versions + capacity_gap_analyzer + synthetic_capacity_seeder + pretrained_trm_registry
- BSC attainment + resolver
- Constrained solver family
- RL harness + scenarios
- Digital twin interface
- node_type_utils

**TMS requirements.txt:** bump pin to `4124f0b` to get everything.
