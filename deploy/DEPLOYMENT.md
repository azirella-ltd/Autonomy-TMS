# Autonomy Platform — Deployment Guide

Full-stack deployment from a local machine to a horizontally scaled multi-machine architecture. The platform grows with the customer: start small, scale by splitting services onto dedicated machines as load increases.

## Networking: Cloudflare Tunnel (Primary)

The platform uses **Cloudflare Tunnel** to expose local Docker stacks to the internet — no open ports, no public IPs required. Cloudflare handles DNS, SSL (free wildcard), CDN, and DDoS protection.

```
User → https://food-dist.azirella.com
       ↓ (Cloudflare edge — SSL termination, CDN, WAF)
       ↓
Cloudflare Tunnel (encrypted, outbound-only)
       ↓
localhost:8088 → Nginx → Frontend / Backend
```

**Setup**: `./scripts/setup_cloudflare_tunnel.sh` — creates a wildcard tunnel routing `*.azirella.com` to your local Docker stack. See [Cloudflare Tunnel Setup](#cloudflare-tunnel-setup) below.

**Subdomain routing** (Option C — Hybrid):
- `login.azirella.com` → Login portal
- `autonomy.azirella.com` → Default app (all tenants via JWT)
- `{tenant-slug}.azirella.com` → Vanity subdomain per tenant

All subdomains route to the same containers. Tenant isolation is enforced by the backend (JWT `tenant_slug` claim), not by infrastructure routing.

---

## Architecture Tiers

| Tier | When | Machines | Monthly Cost (est.) |
|------|------|----------|---------------------|
| **Starter** | PoC, < 5 users, 1 config | 1 EC2 (t3.xlarge) | ~$150 |
| **Standard** | Production, 5-50 users, 2-5 configs | 2 EC2 (app + DB) | ~$400 |
| **Professional** | Multi-tenant, 50-200 users, GPU training | 3-4 EC2 (app + DB + GPU worker) | ~$900 |
| **Enterprise** | Large customer, per-site agents, HA | 5+ EC2 / ECS + RDS + ALB | ~$2,000+ |

All tiers use the same Docker images. Scaling is done by splitting services to separate machines — no code changes needed.

---

## Tier 1: Starter (Single Machine)

Everything on one EC2 instance. Good for demos, PoCs, and small tenants.

```
┌─────────────────────────────────────────────┐
│  EC2: t3.xlarge (4 vCPU, 16 GB)            │
│                                             │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐  │
│  │  Nginx  │→ │ Frontend │  │ PostgreSQL│  │
│  │  Proxy  │→ │ (React)  │  │ + pgvector│  │
│  │  :8088  │  │  :3000   │  │   :5432   │  │
│  └─────────┘  └──────────┘  └───────────┘  │
│       ↓                                     │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐ │
│  │ Backend  │  │ KB DB    │  │ pgAdmin   │ │
│  │ (FastAPI)│  │ (RAG)    │  │  :5050    │ │
│  │  :8000   │  │  :5433   │  └───────────┘ │
│  └──────────┘  └──────────┘                 │
└─────────────────────────────────────────────┘
```

**Instance**: t3.xlarge (4 vCPU, 16 GB RAM, 100 GB gp3)
**LLM**: External API (Claude/OpenAI) or none
**Deploy**: `docker compose up -d`

### Quick Start

```bash
# 1. Provision with Terraform
cd deploy/aws
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars (set your IP, region, repo URL)
terraform init && terraform apply

# 2. SSH in and deploy
ssh -i autonomy-dev.pem ubuntu@<AUTONOMY_IP>
cd /opt/autonomy
cp .env.template .env
# Edit .env (set passwords, SECRET_KEY)
make up

# 3. Bootstrap data
make db-bootstrap
make reset-admin
```

### When to upgrade to Tier 2

- PostgreSQL memory pressure > 80% sustained
- Backend response times > 2s on planning endpoints
- Multiple tenants with concurrent provisioning
- Need automated backups / point-in-time recovery

---

## Tier 2: Standard (App + Database Split)

Separate the database to its own machine (or RDS). The most common production setup.

```
┌─────────────────────────┐     ┌─────────────────────────┐
│  EC2: t3.xlarge (App)   │     │  EC2: r6g.large (DB)    │
│                         │     │  — or RDS PostgreSQL —   │
│  ┌───────┐ ┌─────────┐  │     │                         │
│  │ Nginx │ │Frontend │  │     │  ┌───────────────────┐  │
│  │ :8088 │ │ :3000   │  │     │  │ PostgreSQL 16     │  │
│  └───────┘ └─────────┘  │     │  │ + pgvector        │  │
│  ┌─────────┐ ┌───────┐  │────→│  │ + pgaudit (SOC II)│  │
│  │Backend  │ │KB DB   │  │     │  │ :5432             │  │
│  │ :8000   │ │(local) │  │     │  └───────────────────┘  │
│  └─────────┘ └───────┘  │     │                         │
└─────────────────────────┘     └─────────────────────────┘
```

**App machine**: t3.xlarge — runs proxy, frontend, backend, KB DB
**DB machine**: r6g.large (2 vCPU, 16 GB) or **RDS PostgreSQL** (db.r6g.large)

### RDS Option (Recommended)

```bash
# In terraform.tfvars, add:
use_rds           = true
rds_instance_class = "db.r6g.large"
rds_storage_gb     = 100
rds_multi_az       = false  # true for HA ($$$)
```

Benefits: automated backups, point-in-time recovery, minor version upgrades, pgvector extension, monitoring via CloudWatch.

### Manual DB Split

```bash
# On the DB machine:
docker compose -f docker-compose.db-only.yml up -d

# On the App machine, update .env:
POSTGRESQL_HOST=<DB_PRIVATE_IP>
POSTGRESQL_PORT=5432
docker compose -f docker-compose.yml -f docker-compose.apps.yml up -d
```

### When to upgrade to Tier 3

- TRM training takes > 30 minutes
- Need local LLM (vLLM + Qwen) for air-gapped or cost reasons
- GNN/GraphSAGE training needed
- Provisioning pipeline bottlenecked by compute

---

## Tier 3: Professional (App + DB + GPU Worker)

Add a GPU machine for TRM/GNN training and local LLM inference.

```
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ EC2: t3.xlarge   │   │ RDS PostgreSQL   │   │ EC2: g5.xlarge   │
│ (App Server)     │   │ (Managed DB)     │   │ (GPU Worker)     │
│                  │   │                  │   │                  │
│ Nginx + Frontend │   │ PostgreSQL 16    │   │ vLLM (Qwen 3 8B)│
│ Backend (FastAPI)│──→│ pgvector         │   │ Embeddings (TEI) │
│ KB DB (RAG)      │   │ RLS + pgaudit    │   │ RAG DB (pgvector)│
│                  │──→│                  │   │                  │
│ APScheduler jobs │   │ Automated backups│   │ TRM Training     │
│                  │────────────────────────→ │ GNN Training     │
└──────────────────┘   └──────────────────┘   └──────────────────┘
```

**GPU machine**: g5.xlarge (1 A10G GPU, 24 GB VRAM, 4 vCPU, 16 GB RAM)

```bash
# On GPU worker:
docker compose -f docker-compose.worker.yml up -d

# On App server .env, point to worker:
LLM_API_BASE=http://<GPU_WORKER_IP>:8001/v1
LLM_MODEL_NAME=qwen3-8b
EMBEDDING_API_BASE=http://<GPU_WORKER_IP>:8080
KB_DATABASE_URL=postgresql+psycopg2://...:5433/autonomy_rag
```

**Cost control**: GPU worker can be a Spot Instance ($0.40/hr vs $1.01/hr on-demand for g5.xlarge) with interruption handling — training checkpoints are saved to S3.

### When to upgrade to Tier 4

- Multiple tenants each needing real-time TRM inference at sites
- High availability required (no single points of failure)
- Per-site agent isolation needed for compliance
- > 200 concurrent users

---

## Tier 4: Enterprise (Per-Site Agent Machines)

Each supply chain site (or cluster of sites) gets its own agent machine running its TRM hive. The central app server orchestrates, but execution is distributed.

```
                    ┌──────────────────┐
                    │   ALB / CloudFront│
                    └────────┬─────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
   ┌──────────────────┐         ┌──────────────────┐
   │ ECS: App Server 1│         │ ECS: App Server 2│
   │ (Frontend+Backend│         │ (Frontend+Backend│
   │  behind ALB)     │         │  behind ALB)     │
   └────────┬─────────┘         └────────┬─────────┘
            │                            │
   ┌────────┴────────────────────────────┴────────┐
   │              RDS Aurora PostgreSQL            │
   │              (Multi-AZ, Read Replicas)        │
   └──────────────────────────────────────────────┘
            │
   ┌────────┴──────────────────────────────────────┐
   │           Site Agent Machines (ECS Tasks)      │
   │                                                │
   │  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
   │  │ Site:   │  │ Site:   │  │ Site:   │  ...  │
   │  │ Factory │  │ CDC-West│  │ RDC-NW  │       │
   │  │ 11 TRMs │  │ 7 TRMs  │  │ 6 TRMs  │       │
   │  │ tGNN    │  │ tGNN    │  │ tGNN    │       │
   │  └─────────┘  └─────────┘  └─────────┘       │
   └───────────────────────────────────────────────┘
            │
   ┌────────┴──────────────────────────────────────┐
   │           GPU Training Cluster (Spot)          │
   │  ┌─────────┐  ┌─────────┐                    │
   │  │ vLLM    │  │ Training│                    │
   │  │ Qwen 3  │  │ TRM/GNN │                    │
   │  └─────────┘  └─────────┘                    │
   └───────────────────────────────────────────────┘
```

**Key components**:
- **ALB**: Application Load Balancer with health checks, SSL termination
- **ECS Fargate**: App servers auto-scale 2-8 tasks based on CPU/request count
- **Aurora PostgreSQL**: Multi-AZ, automated failover, read replicas for analytics
- **Site Agents**: Each runs as an ECS task with its own TRM model checkpoints loaded from S3
- **GPU Cluster**: Spot instances for training, on-demand for inference (vLLM)

**Per-site agent isolation**: Each site agent container loads only the TRM checkpoints for its `(tenant_id, config_id, site_id)` from S3. The agent's `site_capabilities.py` determines which TRMs to activate based on the site's `master_type`. Site agents communicate via the tGNN directive table in PostgreSQL — no direct inter-agent networking.

---

## Infrastructure as Code

All tiers use the same Terraform in `deploy/aws/`:

```bash
cd deploy/aws

# Tier 1: Single machine
terraform apply -var="tier=starter"

# Tier 2: App + RDS
terraform apply -var="tier=standard" -var="use_rds=true"

# Tier 3: App + RDS + GPU
terraform apply -var="tier=professional" -var="use_rds=true" -var="gpu_worker=true"

# Tier 4: ECS + Aurora + site agents
terraform apply -var="tier=enterprise"
```

### terraform.tfvars Reference

```hcl
# Required
aws_region          = "eu-central-1"
project_name        = "autonomy"
environment         = "prod"
allowed_ssh_cidrs   = ["<YOUR_IP>/32"]

# Tier selection
tier                = "starter"  # starter | standard | professional | enterprise

# Database (Tier 2+)
use_rds             = false
rds_instance_class  = "db.r6g.large"
rds_multi_az        = false

# GPU Worker (Tier 3+)
gpu_worker          = false
gpu_instance_type   = "g5.xlarge"
gpu_spot            = true      # Use Spot for training (60% cheaper)

# Autonomy Instance
autonomy_instance_type = "t3.xlarge"
autonomy_volume_size   = 100
autonomy_repo_url      = "https://github.com/your-org/Autonomy.git"

# SAP Integration (optional, any tier)
sap_ami_id          = ""
sap_cal_external_id = ""
```

---

## Deployment Script

The `deploy/aws/deploy-aws.sh` script automates initial setup on any EC2 instance:

```bash
# From your local machine:
scp deploy/aws/deploy-aws.sh ubuntu@<EC2_IP>:/tmp/
ssh ubuntu@<EC2_IP> "bash /tmp/deploy-aws.sh"
```

Or via Terraform user_data (runs automatically on first boot).

### What the script does

1. Installs Docker, Docker Compose, Make, git
2. Clones the Autonomy repo
3. Generates `.env` from template with secure random secrets
4. Builds and starts all containers
5. Runs database bootstrap (creates tables, seeds defaults)
6. Creates system admin user
7. Prints access URLs

---

## Deployment Checklist

### Pre-Deploy

- [ ] AWS account with IAM user (AdministratorAccess or scoped policy)
- [ ] AWS CLI configured (`aws configure`)
- [ ] Terraform >= 1.5 installed
- [ ] SSH key pair (auto-generated or existing)
- [ ] Domain name (optional — can use IP initially)

### Deploy

- [ ] `terraform apply` — infrastructure provisioned
- [ ] SSH access confirmed
- [ ] `.env` configured (passwords, SECRET_KEY, LLM keys)
- [ ] `make up` — all containers healthy
- [ ] `make db-bootstrap` — data seeded
- [ ] Login as systemadmin@autonomy.com / Autonomy@2026

### Post-Deploy

- [ ] Create tenant(s) and tenant admin(s)
- [ ] Upload SC config or run ERP import (SAP/D365/Odoo)
- [ ] Run provisioning (16-step Powell Cascade)
- [ ] Verify Decision Stream populates
- [ ] Configure backups (pg_dump cron or RDS automated)
- [ ] Set up monitoring (CloudWatch agent or Prometheus)

---

## Backup & Recovery

### Tier 1-2 (Docker PostgreSQL)

```bash
# Backup (add to cron: 0 2 * * *)
docker compose exec -T db pg_dump -U autonomy_user -Fc autonomy > backup_$(date +%Y%m%d).dump

# Restore
docker compose exec -T db pg_restore -U autonomy_user -d autonomy --clean < backup_20260326.dump
```

### Tier 2+ (RDS)

Automated daily snapshots with 7-day retention. Point-in-time recovery to any second within the retention window.

```bash
# Manual snapshot
aws rds create-db-snapshot \
  --db-instance-identifier autonomy-db \
  --db-snapshot-identifier autonomy-manual-$(date +%Y%m%d)
```

---

## SSL / TLS

### Quick (Self-Signed)

```bash
make up-tls  # Generates self-signed cert, serves on :8443
```

### Production (Let's Encrypt via Certbot)

```bash
sudo apt install certbot
sudo certbot certonly --standalone -d autonomy.yourdomain.com
# Copy certs to config/dev-proxy/ssl/
# Update nginx.tls.conf with cert paths
make proxy-restart
```

### Production (AWS ACM + ALB)

For Tier 4, use AWS Certificate Manager (free) with ALB SSL termination. No cert management needed on instances.

---

## Cost Optimization

| Resource | Starter | Standard | Professional | Enterprise |
|----------|---------|----------|-------------|-----------|
| App EC2 | $120/mo | $120/mo | $120/mo | ECS ~$200/mo |
| Database | (included) | RDS $140/mo | RDS $140/mo | Aurora $400/mo |
| GPU Worker | — | — | Spot $290/mo | Spot $580/mo |
| ALB | — | — | — | $25/mo |
| S3 (checkpoints) | — | — | $5/mo | $20/mo |
| Data Transfer | $5/mo | $10/mo | $15/mo | $50/mo |
| **Total** | **~$125** | **~$270** | **~$570** | **~$1,275** |

**Tips**:
- Use Savings Plans for app servers (up to 72% off)
- Spot Instances for GPU training (up to 60% off, with interruption handling)
- Reserved Instances for RDS (up to 40% off for 1-year)
- Schedule SAP instances (start/stop) — saves ~70% vs always-on
- gp3 EBS volumes (20% cheaper than gp2, better baseline IOPS)

---

## Health Checks

| Endpoint | Expected | Used By |
|----------|----------|---------|
| `GET /healthz` | 200 "ok" | ALB / proxy |
| `GET /api/health` | 200 | Docker healthcheck |
| `GET /api/v1/health/live` | 200 | Kubernetes liveness |
| `GET /api/v1/health/ready` | 200 | Kubernetes readiness |

---

## Security

- **Network**: Cloudflare Tunnel (outbound-only, no open ports) or VPC with private subnets
- **Database**: RLS enforced per tenant, pgaudit logging, encrypted at rest (RDS KMS)
- **Secrets**: AWS Secrets Manager (Tier 2+) or `.env` file (Tier 1)
- **Auth**: JWT + HTTP-only cookies, CSRF protection, MFA support
- **SOC II**: See CLAUDE.md § SOC II Compliance for full requirements

---

## Cloudflare Tunnel Setup

For local or single-machine deployments, Cloudflare Tunnel provides production-grade HTTPS access with zero port forwarding.

### Quick Start

```bash
./scripts/setup_cloudflare_tunnel.sh
```

This creates a wildcard tunnel: `*.azirella.com` → `localhost:8088`.

### What Cloudflare Provides (Free)

| Feature | Detail |
|---------|--------|
| **Wildcard DNS** | `*.azirella.com` CNAME to tunnel |
| **Wildcard SSL** | Automatic, free, renewed by Cloudflare |
| **DDoS protection** | Always-on at edge |
| **CDN** | Static asset caching at 300+ PoPs |
| **Zero Trust** | Optional — add Cloudflare Access for extra auth layer |
| **No open ports** | Tunnel is outbound-only from your machine |

### After Tunnel Setup

1. Update `.env`:
```env
APP_DOMAIN=azirella.com
APP_SCHEME=https
APP_PORT=
SUBDOMAIN_ROUTING_ENABLED=true
COOKIE_DOMAIN=.azirella.com
CSRF_COOKIE_DOMAIN=.azirella.com
COOKIE_SECURE=true
```

2. Populate tenant slugs:
```sql
UPDATE tenants SET slug='food-dist', subdomain='food-dist' WHERE id=3;
UPDATE tenants SET slug='sap-demo', subdomain='sap-demo' WHERE id=20;
UPDATE tenants SET slug='d365-demo', subdomain='d365-demo' WHERE id=24;
UPDATE tenants SET slug='odoo-demo', subdomain='odoo-demo' WHERE id=26;
```

3. Restart: `docker compose restart backend`

4. Test: `https://food-dist.azirella.com` should load and redirect to login

### Local Dev vs Production

| Setting | Local Dev | Production (Cloudflare) |
|---------|-----------|------------------------|
| `APP_DOMAIN` | `localhost` | `azirella.com` |
| `APP_SCHEME` | `http` | `https` |
| `APP_PORT` | `8088` | *(empty)* |
| `SUBDOMAIN_ROUTING_ENABLED` | `false` | `true` |
| `COOKIE_DOMAIN` | *(empty)* | `.azirella.com` |
| `COOKIE_SECURE` | `false` | `true` |

### Cloudflare + AWS (Tier 2+)

When scaling to AWS, Cloudflare Tunnel can point to an EC2 instance instead of localhost — same setup, just change the origin in the tunnel config. Or use Cloudflare as DNS-only (orange cloud off) and point to an ALB directly.
