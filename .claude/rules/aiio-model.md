# AIIO — Agents Always Act

Behavioural contract for every decision surface in TMS.

## States

| State | Meaning |
|---|---|
| **ACTIONED** | Agent executed the decision |
| **INFORMED** | Decision Stream surfaced it to a user |
| **INSPECTED** | User reviewed it |
| **OVERRIDDEN** | User rejected with reasoning |

No **PENDING / ACCEPTED / AUTO_EXECUTED / EXPIRED / REJECTED** — those
are retired terms.

## Consequences for TMS

- **No approval-button workflow.** No "Create Transportation Plan",
  "Generate Dispatch", or "Tender Now" buttons in the UI. Transport
  plans are generated automatically during provisioning and on the
  scheduled cascade.
- **Dispatch, tender, settlement, routing all fire ACTIONED first**,
  then appear in the Decision Stream.
- **Users inspect, override (with reasoning), or scenario-test.** They
  do not gate execution.
- **Governance pipeline** controls what agents can do autonomously.
