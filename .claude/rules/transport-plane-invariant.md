# Transport-plane invariant

TMS is a **policy repo**, not a platform repo. Only Transport-plane
decision modules land here. Everything else lives in Autonomy-Core.

## Allowed

- Transport TRMs: TOExecution, Dispatch, LoadBuild, Appointment, Tender,
  Settlement, Routing, FreightProcurement, DockScheduling, and other
  transport-specific decision models
- Transport-plane feature engineering (canonical state → TMS agent
  tensors)
- Transport-plane objective functions (landed cost, service window,
  carbon, carrier utilisation)
- Transport-plane solver configurations (VRP, dispatch, consolidation)
- Carrier scorecard and freight procurement logic
- Transport-specific `DisruptionKind` extensions
- Transport-specific provisioning step *definitions* (framework is Core)
- Dispatcher UI, tracking visualisation, Decision-Stream surfacing
  filtered to transport

## Forbidden

- Canonical entities (incl. second copies of `TransferOrder`,
  `TradingPartner`, `Geography`) → Core
- ERP connectors, CDC ingestion, write-back → Core
- Digital twin / simulator / scenario engine → Core
- Conformal prediction framework → Core
- Plane registry, intersection contracts → Core
- BSC framework, governance pipeline framework → Core
- Training infrastructure (`TwinRlTrainer`, `RolloutHarness`,
  `BscRewardFunction`, `Trajectory`) → Core
- Context broker, temporal knowledge store, LLM narration framework → Core

## Sibling, not fork — anti-patterns

TMS was forked from SCP and is being unwound into a sibling product.
These patterns must go:

- Sharing `SQLAlchemy.Base` with SCP → **forbidden**
- Importing models from `Autonomy-SCP` → **forbidden**
- Adding a git remote pointing to `Autonomy-SCP` → **blocked by hook**
- Direct HTTP calls to SCP backend → use **MCP** domain tools instead
- Copying SCP code as "shared core" → extract to Autonomy-Core

## When in doubt

- Could SCP, CRM, WMS, or Portfolio use it? → Core (Rule 1).
- Is it physics, canonical state, or cross-cutting infrastructure? →
  Core (Rule 2).
- Can you name the specific second consumer or substrate property? If
  not, default to Core.

Add to `Autonomy-Core/docs/MIGRATION_REGISTER.md` if you can't place
correctly on first write.
