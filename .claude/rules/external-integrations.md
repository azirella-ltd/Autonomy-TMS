# External integrations (TMS-specific)

TMS depends on several external systems that SCP does not. They all
sit behind connector services; never call them directly from domain
code.

## Integrations

- **project44** — real-time visibility, ETA, exception detection.
  Primary visibility source.
  - OAuth connector + webhook handler at
    [integrations/project44/](../../integrations/project44/)
  - Webhook receiver + config + tracking ops at
    [api/endpoints/p44_integration.py](../../api/endpoints/p44_integration.py)
- **Carrier APIs** — EDI 204 / 214 / 990, API-based tender / track.
- **Weather** — NOAA, Weather.com; disruption prediction (Context Broker).
- **Port / Terminal** — AIS data, terminal operating systems.
- **Rate sources** — DAT, Greenscreens, Freightwaves SONAR.

## Invariants

- **Connector credentials are per-tenant** and stored encrypted. No
  shared tokens across tenants.
- **Incoming webhooks** produce canonical events (HiveSignal, CDC) that
  flow through the standard decision path, never into domain code
  directly.
- **Rate sources** feed the FreightRate canonical entity; don't cache
  rate quotes in ad-hoc tables.
- **When an external system is unavailable**, the UI surfaces the
  outage via `<Alert>`, never fabricates a value. See
  [no-fallbacks.md](no-fallbacks.md).

## Where the contract lives

External-signal routing is a **Core** concern — the Context Broker
decides which tier (strategic / tactical / operational / execution)
an external signal affects based on horizon, duration, and scope. TMS
writes the connector, Core owns the routing logic.
