# Databricks Migration Analysis — Autonomy Platform

**Date:** 2026-04-12
**Scope:** Autonomy-Core, Autonomy-TMS, Autonomy-SCP
**Author:** Trevor (with Claude analysis)

---

## 1. Executive Summary

Moving Autonomy's PostgreSQL databases to Databricks is **not recommended as a primary database replacement**. Databricks is an OLAP analytics platform; Autonomy's workloads are OLTP (transactional, low-latency, referential-integrity-dependent). The free tier cannot run any of the three products. The paid tiers would cost $300-1,500+/month for a workload that PostgreSQL handles for $0 (self-hosted) or $30-80/month (managed).

**Databricks makes sense as a complementary analytics layer** — pulling operational data from PostgreSQL into Delta Lake for large-scale historical analysis, ML training pipelines, or customer-facing dashboards over aggregated data.

---

## 2. Current Database Inventory

### 2a. Autonomy-Core (Shared Data Model Package)

| Metric | Value |
|--------|-------|
| Tables | 98 ORM models + 2 association tables |
| Columns | ~1,430 |
| Migrations | 1 (canonical base — apps extend) |
| Docker DB services | None (pure Python package) |
| PostgreSQL-specific features | `ARRAY(String)` type in PowellEscalationLog |
| JSON columns | 30+ tables |
| Enums | 10+ custom types (TenantMode, AuditAction, ConformalMethod, etc.) |

Core is a shared library — it doesn't run its own database. SCP and TMS each instantiate the canonical schema in their own PostgreSQL instance and extend it with app-specific tables.

### 2b. Autonomy-TMS

| Metric | Value |
|--------|-------|
| Tables | 278 |
| Columns | 3,269 |
| Migrations | 214 |
| DB instances | 2 (operational PostgreSQL 16 + KB pgvector) |
| Extensions | uuid-ossp, pg_stat_statements, vector (pgvector 768-dim) |
| Custom enums | 15+ (transport_mode, equipment_type, shipment_status, exception_type, etc.) |
| JSON columns | 50+ tables |
| Estimated rows (post-seed) | 100K-200K |
| Estimated data size (seeded) | 50-200 MB |
| Estimated data size (1yr production) | 5-50 GB per tenant |

### 2c. Autonomy-SCP

| Metric | Value |
|--------|-------|
| Model classes | 153 |
| Migrations | 146 |
| DB instances | 2 (operational PostgreSQL 16 + KB pgvector) |
| Extensions | uuid-ossp, pg_stat_statements, vector |
| Powell decision tables | 12 TRM types |
| Seed scripts | 33 (24.5K LOC) |
| Estimated data size | Similar to TMS |

### Combined Platform Totals

| | Core | TMS | SCP | **Total** |
|--|------|-----|-----|-----------|
| Tables | 100 | 278 | ~200 | **~430 unique** (Core tables shared) |
| Columns | 1,430 | 3,269 | ~2,200 | **~5,500** |
| Migrations | 1 | 214 | 146 | **361** |
| DB instances | 0 | 2 | 2 | **4** |
| Estimated storage (seeded) | — | 200 MB | 200 MB | **~400 MB** |
| Estimated storage (1yr prod) | — | 5-50 GB | 5-50 GB | **10-100 GB** |

---

## 3. Will It Fit in the Databricks Free Tier?

**No.** The free tier (Community Edition / Free Edition) has fundamental blockers:

| Requirement | Free Tier Capability | Verdict |
|-------------|---------------------|---------|
| **Commercial use** | Prohibited (ToS) | Disqualifying |
| **Scheduled jobs** | Max 5 concurrent tasks | Blocks planning cascade (S&OP, daily refresh, 4h TRM cycles, continuous exceptions) |
| **JDBC/ODBC for FastAPI** | Available but no jobs compute | Backend can query, but no background processing |
| **Unity Catalog (governance)** | Not available | No RBAC, no audit logging — fails SOC II |
| **SQL warehouse size** | 2X-Small max (1 warehouse) | Insufficient for concurrent TRM decisions |
| **Multi-workspace** | 1 workspace, 1 metastore | Cannot isolate TMS vs SCP |
| **SLA / support** | None | Unacceptable for production |
| **pgvector equivalent** | None | RAG/embedding search needs separate solution |
| **Foreign key enforcement** | Informational only | 278-table referential integrity unenforceable |
| **Row-level security** | Not available | SOC II requirement |
| **Sub-second query latency** | Not guaranteed | TRM agents need <10ms decisions |

**Storage-wise the data fits** (~400 MB seeded, even 100 GB production is small for Databricks). The blockers are all functional, not capacity.

---

## 4. Architectural Incompatibilities

These are fundamental design mismatches, not just feature gaps:

### 4a. OLTP vs OLAP

| Autonomy Needs | PostgreSQL | Databricks |
|----------------|-----------|------------|
| Single-row inserts (agent decisions) | Optimized | Anti-pattern (batch-oriented) |
| Sub-10ms reads (TRM execution) | With indexes, yes | Seconds minimum |
| Concurrent writes (multi-agent) | Row-level locking | Optimistic concurrency, file-level |
| Complex JOINs across 278 tables | Optimized with FK indexes | Expensive shuffle operations |
| UPDATE individual rows | Native | Requires MERGE or DELETE+INSERT |

### 4b. Features Without Equivalent

| PostgreSQL Feature | Databricks Equivalent | Migration Effort |
|---|---|---|
| **pgvector** (768-dim embeddings) | None built-in — need Pinecone/Weaviate/Chroma sidecar | High (new infra + code rewrite) |
| **Foreign keys (enforced)** | Informational only — must validate in app code | High (rewrite all integrity checks) |
| **ARRAY(String)** columns | ARRAY type exists in Databricks SQL | Low |
| **Custom ENUMs** (15+ types) | VARCHAR + CHECK constraints | Medium |
| **JSON/JSONB** | VARIANT type (similar) | Low-Medium |
| **Row-level security** | Unity Catalog (paid only) | Medium |
| **pg_stat_statements** | Query History UI | Low |
| **Alembic migrations** | No equivalent — schema managed via notebooks/Terraform | High (rewrite migration pipeline) |
| **SQLAlchemy ORM** | No ORM — raw SQL or Spark DataFrames | Very High (rewrite entire backend) |
| **Async connections (asyncpg)** | JDBC/ODBC only (synchronous) | High |

### 4c. Backend Rewrite Scope

Autonomy's backend is built on **SQLAlchemy 2.0 async** with Alembic migrations. Databricks has no SQLAlchemy dialect for Delta Lake. Migration would require:

1. **Rewrite all 153+ model classes** from SQLAlchemy ORM to raw SQL or Spark
2. **Rewrite all 214+ migrations** to Databricks DDL
3. **Rewrite all async DB sessions** (asyncpg) to synchronous JDBC
4. **Rewrite referential integrity** from DB-enforced FKs to application-level validation
5. **Replace pgvector** with a dedicated vector database
6. **Rewrite the planning cascade** scheduler to work within Databricks jobs framework

**Estimated effort: 3-6 months full-time for one developer, per product.**

---

## 5. Cost Analysis — Paid Tiers

### Scenario A: Replace PostgreSQL Entirely with Databricks

**Assumptions:** Premium tier, AWS, 2 products (TMS + SCP), 50 GB each, moderate query load.

| Component | Monthly Cost |
|-----------|-------------|
| SQL Serverless compute (TRM decisions, API queries) — est. 200 DBU-hours/month | $140 |
| Jobs compute (planning cascade, daily refresh, S&OP) — est. 100 DBU-hours/month | $15 |
| All-purpose compute (dev/notebooks) — est. 50 DBU-hours/month | $28 |
| AWS infrastructure (S3 storage 100 GB, networking, NAT) | $30 |
| Vector DB sidecar (Pinecone/Weaviate for RAG) | $70-150 |
| **Databricks subtotal** | **$283-363** |
| Premium platform fee (if applicable) | $0-100 |
| **Total estimate** | **$300-500/month** |

**With growth (500 GB, more concurrent users):** $800-1,500/month

### Scenario B: Keep PostgreSQL, Add Databricks for Analytics

| Component | Monthly Cost |
|-----------|-------------|
| PostgreSQL (current Docker, self-hosted) | $0 |
| PostgreSQL (managed RDS, if desired) | $30-80 |
| Databricks SQL Serverless (analytics queries only) — 50 DBU-hours/month | $35 |
| S3 storage for Delta Lake (analytics copy) | $5 |
| **Total estimate** | **$35-120/month** |

### Scenario C: Stay on PostgreSQL (Current)

| Component | Monthly Cost |
|-----------|-------------|
| Docker containers (self-hosted) | $0 |
| Server/VPS (if not already running) | $20-50 |
| **Total estimate** | **$0-50/month** |

### Cost Comparison Summary

| Scenario | Monthly Cost | Dev Effort | Risk |
|----------|-------------|-----------|------|
| **A: Full Databricks** | $300-1,500 | 6-12 months | High — architectural mismatch |
| **B: PostgreSQL + Databricks analytics** | $35-120 | 2-4 weeks | Low — additive, no rewrite |
| **C: Stay on PostgreSQL** | $0-50 | 0 | None |

---

## 6. What Databricks Would Be Good For

Despite being wrong as a PostgreSQL replacement, Databricks excels at workloads Autonomy will eventually need:

| Use Case | Why Databricks Fits | When to Add |
|----------|-------------------|-------------|
| **Historical analytics** | Query months/years of decision history across tenants | When decision tables exceed 10M rows |
| **ML training pipelines** | Distributed training on large freight/planning datasets | When PyTorch training exceeds single-GPU capacity |
| **Customer dashboards** | Pre-aggregated metrics for executive reporting | When real-time isn't needed and batch refresh is acceptable |
| **Data lake for integrations** | Central store for project44, carrier EDI, weather, port data | When ingesting from 5+ external sources |
| **Cross-product analytics** | Join TMS + SCP data without shared tables | When executive console needs unified view |

---

## 7. Recommendation

### Short Term (Now)
**Stay on PostgreSQL.** The current stack is correct for the workload. Invest in:
- Proper backup strategy (the existing backup files are 117-byte placeholders)
- RLS implementation (documented as SOC II requirement but not implemented)
- Connection pooling (PgBouncer) for production readiness

### Medium Term (6-12 months, when data grows)
**Add Databricks as an analytics layer** (Scenario B):
- CDC pipeline from PostgreSQL → Delta Lake (Debezium or custom)
- Analytics notebooks for cross-tenant reporting
- ML training data preparation
- This uses the free tier legitimately for exploration, paid tier only for production analytics

### Long Term (12+ months)
**Evaluate Databricks Lakehouse if:**
- Data exceeds 1 TB across products
- Need distributed ML training
- Customer count requires multi-region analytics
- Executive console needs cross-product aggregation

---

## 8. If You Still Want to Explore the Free Tier

The free tier is useful for **learning and prototyping**, not production. Here's what you could validate:

1. **Export a sample dataset** from TMS (e.g., 1 month of decisions, 1K shipments)
2. **Load into Delta Lake** via notebook
3. **Test query patterns** — can Databricks SQL handle the JOIN-heavy queries Autonomy uses?
4. **Test latency** — measure query response times vs PostgreSQL
5. **Test the analytics use case** — build a cross-tenant dashboard on historical data

This would cost $0 and take 1-2 days. It validates whether Scenario B is worth pursuing without any production risk.

---

## Appendix: Feature Comparison Matrix

| Feature | PostgreSQL 16 | Databricks Free | Databricks Premium |
|---------|--------------|----------------|-------------------|
| ACID transactions | Full (row-level) | File-level only | File-level only |
| Foreign keys | Enforced | Informational | Informational |
| Sub-ms queries | Yes (indexed) | No | No |
| Vector search | pgvector | No | No |
| JSON support | JSONB (indexed) | VARIANT | VARIANT |
| Array types | Native | Native | Native |
| Row-level security | Native | No | Unity Catalog |
| Audit logging | pgaudit | No | Unity Catalog |
| ORM support | SQLAlchemy | No | No |
| Async drivers | asyncpg | No | No |
| Schema migrations | Alembic | Manual/Terraform | Manual/Terraform |
| Scheduled jobs | External (cron/APScheduler) | 5 max | Unlimited |
| Columnar analytics | Limited | Excellent | Excellent |
| Distributed compute | No | Limited | Yes |
| ML/Spark integration | No | Yes | Yes |
| Cost (self-hosted) | $0 | N/A | N/A |
| Cost (managed) | $30-80/mo | $0 | $300-1,500/mo |
