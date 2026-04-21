# No fallbacks, no hardcoded values (TMS)

**Fallbacks are a safety issue in TMS.** A fabricated metric value
(e.g. `|| 94.2`) hides missing data and creates false confidence in
system state. Transportation decisions based on phantom numbers can
cause real operational harm — a "94.2% on-time" card backed by
nothing masks a carrier performance problem that would otherwise
trigger action.

## Rules

- **No fallback values for metrics, KPIs, or business data.** If a
  metric cannot be calculated or found, surface the absence clearly
  (show "No data", an `<Alert>`, or raise an error). Never substitute a
  hardcoded number.
- **No `|| <number>` patterns for business data.** Only `|| 0` is
  acceptable for counters where zero is the truthful default. Never for
  rates, scores, costs, or percentages.
- **Column names match the actual DB schema** — check model definitions
  first; do not best-guess.
- **No hardcoded entity references.** IDs, names, codes come from
  tenant data.
- **No hardcoded demo data.** All data from DB or calculations on DB data.
- **Economic parameters explicitly set per tenant.** Missing → error
  surfaced to the tenant admin.
- **Frontend rule**: when API data is unavailable, show an `<Alert>`
  explaining what's missing and how to fix it (e.g., "Run provisioning",
  "Check metric configuration", "Connect project44"). Never render a
  chart or card with invented numbers.

## Enforcement

The [governance-reviewer](../agents/governance-reviewer.md) agent
checks for fallback patterns. Run it proactively when touching
services, endpoints, or UI components that read tenant data.
