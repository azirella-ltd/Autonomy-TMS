# Planning cascade (TMS — auto-execution)

Agents always act. No approval-button workflow. The cascade runs on a
schedule; user inspection is post-hoc via the Decision Stream.

## Schedule

| Cadence | What runs |
|---|---|
| **Weekly** (Monday 6am) | **S&OP** — GraphSAGE network / carrier-portfolio optimisation |
| **Daily 5am** | **Transportation Plan** — Plan of Record refresh: load builds, carrier assignments |
| **Every 4h** | **Execution** — TRM decision cycle at each facility |
| **Continuous** | **Exceptions** — shipment exception detection via project44 + carrier feeds |

## Cross-cutting properties

- Every scheduled run emits **AgentDecision** rows (ACTIONED) into the
  canonical table. Correlation IDs trace back to the upstream CDC event,
  project44 webhook, or schedule trigger.
- **Digital Twin simulation** never participates in the cascade — Twin
  is for training / scenario exploration only.
- See [plan-separation.md](plan-separation.md) for which plan_version
  each step writes.
