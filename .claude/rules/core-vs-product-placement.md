# Core-vs-product placement (TMS)

Two tests. Either is sufficient to force Core placement.

- **Rule 1 — Cross-product test.** If more than one product's agents,
  models, or services can reasonably consume it, it belongs in Core.
- **Rule 2 — Substrate test.** If it is the physics, canonical state, or
  cross-cutting infrastructure of the supply chain, it belongs in Core
  regardless of who consumes it today.

## Core owns (not TMS)

Canonical state and masters (sites, products, BOMs, transportation_lane,
trading_partners, geography, transfer_order, purchase_order, inventory,
capacity, lifecycle, commitments); all ERP connectors and raw-to-canonical
mapping; CDC ingestion; forecast synthesis; scenario engine; digital
twin / simulator; conformal prediction; outcome measurement; plane
registry; intersection contracts; training infrastructure; context
broker; temporal knowledge store; LLM narration framework; BSC framework;
governance pipeline framework; provisioning framework.

## TMS owns (and nothing else)

Transport-plane policy modules only — see [transport-plane-invariant.md](transport-plane-invariant.md).

## TMS is a sibling product, not a fork

**Architecture pivot (2026-04-10)**: SCP and TMS are two separate
products, not parent and fork. They share patterns and integrate via
MCP, but have **independent tech stacks from the database up**.

Anti-patterns to stop on sight:

- Do NOT copy code from `Autonomy-SCP` into this repo as "shared core"
- Do NOT add `git remote upstream` references to the SCP repo — the hook blocks this
- Do NOT share SQLAlchemy `Base`, models, or DB tables with SCP
- DO use the `@azirella-ltd/autonomy-frontend` npm package for shared frontend
- DO use MCP for any TMS↔SCP integration (e.g., TMS asking SCP for ATP constraints)

Shared code belongs in Autonomy-Core, published as
`@azirella-ltd/autonomy-frontend`, `@azirella-ltd/data-model`, or
`@azirella-ltd/powell-core`, and picked up here on a dependency bump —
never by pulling from SCP.

## Failure mode

Drift — writing cross-product logic in TMS "because the related code
lived there" (especially likely given the fork legacy). The softer
previous phrasing was rationalised around too easily. The two-rule test
above is stricter: cross-product plausibility OR substrate status is
sufficient.

**Never default to "put it here for now, we'll refactor later."** If
you cannot place correctly on first write, add to
[Autonomy-Core/docs/MIGRATION_REGISTER.md](../../../Autonomy-Core/docs/MIGRATION_REGISTER.md)
with a target tier.

## Cross-repo coordination

- [Autonomy-Core/docs/MIGRATION_REGISTER.md](../../../Autonomy-Core/docs/MIGRATION_REGISTER.md) — Core-bound migrations (includes TMS items slated for extraction / deprecation)
- [Autonomy-Core/docs/CONSUMER_ADOPTION_LOG.md](../../../Autonomy-Core/docs/CONSUMER_ADOPTION_LOG.md) — Core changes requiring TMS action
- [Autonomy-Core/docs/SPRINT_1_EXECUTION.md](../../../Autonomy-Core/docs/SPRINT_1_EXECUTION.md) — current partition sprint
- [Autonomy-Core/docs/TMS_ADOPTION_GUIDE_20260420.md](../../../Autonomy-Core/docs/TMS_ADOPTION_GUIDE_20260420.md) — **directional alert.** STOP list + PREPARE list for TMS. Read before the next commit.

Per CLAUDE.md cross-product rule: when ANY change is made to Autonomy-Core,
update `CONSUMER_ADOPTION_LOG.md` so TMS and SCP can discover and adopt.
