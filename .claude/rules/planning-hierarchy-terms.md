# Planning-hierarchy terminology (TMS)

Canonical layer names — use consistently in TMS code, UI copy, and
documentation. Parallel to the SCP hierarchy but with TMS domain TRMs
at L3.

| Layer | Canonical name | Domain models | Cadence |
|---|---|---|---|
| L4 | **Strategic** (Network / S&OP GraphSAGE) | network design, carrier allocation | Monthly buckets |
| L3 | **Tactical** (domain tGNNs) | Movement, Carrier, Dock, Equipment | Weekly buckets |
| L2 | **Operational** (Site tGNN / hive coordinator) | intra-site transport coordination | Daily, always-on |
| L1 | **Execution** (transport TRMs) | TOExecution, Dispatch, LoadBuild, Appointment, Tender, Settlement, Routing, FreightProcurement, DockScheduling | Hourly / real-time |

## Forbidden synonyms

- **"Tier 1/2/3/4"** — reserved for plane-registry states.
- **"Layer 1/2/3/4"** as user-facing labels — the numbers invert
  between documents; use canonical names in UI.
- **"Tier N"** as a work-prioritisation label — use "Phase" or
  descriptive names.
