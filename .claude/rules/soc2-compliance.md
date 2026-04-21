# SOC II compliance (TMS addenda)

Cross-product SOC II framework lives in Autonomy-Core. TMS-specific
notes below.

## Database security

- **RLS on every tenant-scoped table.** New tables get a policy in the
  Alembic migration that creates them. TMS has its own DB (`tms-db`);
  RLS is applied there, **not shared with SCP**.
- **`pgaudit`** for DDL / ROLE / WRITE.
- **SSL/TLS** enforced on every connection.
- **Column-level encryption** for high-sensitivity fields.

## Model & training data

- **Tenant-scoped checkpoints** at `/{tenant_id}/{config_id}/`. No
  cross-tenant training.
- **Right to deletion** — when a tenant is deleted, TMS checkpoints,
  embeddings, and project44 connector credentials go with them.

## Access control

- **Least-privilege PostgreSQL roles.**
- **`SET LOCAL`** for tenant context in connection pooling.

## Change management

- **Schema changes via Alembic only.** The bash hook blocks DDL from
  the shell.
- The TMS Alembic chain is independent of SCP — never reference SCP
  migration files.

## Provisioning error visibility

Provisioning failures must be ERROR-level and leave `status=failed`
on the step. Tenant admin must see the failure in the UI.

## Customer tenant model

Every customer gets two tenants:
- **Operational** (`TenantMode.PRODUCTION`) — real transportation data
  from TMS / ERP extraction
- **Learning** (`TenantMode.LEARNING`) — demo config, training /
  simulation
