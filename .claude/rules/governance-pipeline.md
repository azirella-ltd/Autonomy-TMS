# Governance pipeline (TMS)

The pipeline decides **what agents can do autonomously** — not what
humans must approve. There is no approval-button workflow (see
[aiio-model.md](aiio-model.md)).

## Pipeline steps

- **Step 0 — Planning envelope.** Lane / mode constraints via
  Glenday Sieve. Shape the input before the agent sees it.
- **Step 1 — Impact scoring.** 5 dimensions:
  - cost (landed cost, rate, accessorials)
  - service (on-time, transit-window adherence)
  - capacity (lane / carrier headroom)
  - risk (disruption exposure, dependency concentration)
  - sustainability (CO2, mode shift)
- **Step 2 — AIIO mode assignment.** AUTOMATE / INFORM / INSPECT.
- **Step 3 — Guardrail directive override.** Per-facility directives
  that override default behaviour.

## Conventions

- Agents are referred to by **function name**, not technology.
  "Freight Procurement Agent" (not "FreightProcurementTRM") in user copy.
- Controls are **per-facility** with "apply to all facilities" option.
