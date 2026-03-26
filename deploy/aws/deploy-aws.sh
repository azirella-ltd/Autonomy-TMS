#!/bin/bash
# ===========================================================================
# Autonomy Platform — AWS EC2 Bootstrap Script
#
# Run on a fresh Ubuntu 22.04/24.04 EC2 instance to deploy the full stack.
# Can be passed as user_data in Terraform or run manually via SSH.
#
# Usage:
#   # As user_data (automatic on first boot):
#   terraform apply   # user_data references this script
#
#   # Manual:
#   scp deploy/aws/deploy-aws.sh ubuntu@<IP>:/tmp/
#   ssh ubuntu@<IP> "sudo bash /tmp/deploy-aws.sh"
#
#   # With options:
#   sudo bash deploy-aws.sh \
#     --repo https://github.com/your-org/Autonomy.git \
#     --branch main \
#     --tier starter \
#     --db-host ""            # empty = local Docker PostgreSQL
#     --gpu-worker ""         # empty = no GPU worker
#     --llm-api-base ""       # empty = no LLM
#
# Tiers:
#   starter      — everything on this machine (default)
#   standard     — app only, expects --db-host for external PostgreSQL
#   professional — app only, expects --db-host + --gpu-worker
#   worker       — GPU worker node only (vLLM + embeddings + RAG DB)
# ===========================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults (overridable via flags or environment)
# ---------------------------------------------------------------------------
REPO_URL="${AUTONOMY_REPO_URL:-https://github.com/your-org/Autonomy.git}"
BRANCH="${AUTONOMY_BRANCH:-main}"
TIER="${AUTONOMY_TIER:-starter}"
INSTALL_DIR="/opt/autonomy"
DB_HOST="${AUTONOMY_DB_HOST:-}"
GPU_WORKER="${AUTONOMY_GPU_WORKER:-}"
LLM_API_BASE="${AUTONOMY_LLM_API_BASE:-}"
LOG_FILE="/var/log/autonomy-deploy.log"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case $1 in
    --repo)        REPO_URL="$2"; shift 2 ;;
    --branch)      BRANCH="$2"; shift 2 ;;
    --tier)        TIER="$2"; shift 2 ;;
    --db-host)     DB_HOST="$2"; shift 2 ;;
    --gpu-worker)  GPU_WORKER="$2"; shift 2 ;;
    --llm-api-base) LLM_API_BASE="$2"; shift 2 ;;
    --install-dir) INSTALL_DIR="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
exec > >(tee -a "$LOG_FILE") 2>&1

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
ok()  { log "OK: $*"; }
err() { log "ERROR: $*"; exit 1; }

log "========================================"
log "Autonomy Platform — AWS Deployment"
log "========================================"
log "Tier:        $TIER"
log "Repo:        $REPO_URL"
log "Branch:      $BRANCH"
log "Install dir: $INSTALL_DIR"
log "DB host:     ${DB_HOST:-local Docker}"
log "GPU worker:  ${GPU_WORKER:-none}"
log "LLM API:     ${LLM_API_BASE:-none}"
log "========================================"

# ---------------------------------------------------------------------------
# Step 1: System packages
# ---------------------------------------------------------------------------
log "Step 1: Installing system packages..."

export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y -qq \
  apt-transport-https ca-certificates curl gnupg lsb-release \
  git make jq unzip python3-pip

ok "System packages installed"

# ---------------------------------------------------------------------------
# Step 2: Docker
# ---------------------------------------------------------------------------
log "Step 2: Installing Docker..."

if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
  usermod -aG docker ubuntu
  systemctl enable docker
  systemctl start docker
  ok "Docker installed"
else
  ok "Docker already installed"
fi

# Docker Compose plugin (V2)
if ! docker compose version &>/dev/null; then
  apt-get install -y -qq docker-compose-plugin
fi
ok "Docker Compose $(docker compose version --short) ready"

# ---------------------------------------------------------------------------
# Step 3: NVIDIA drivers (GPU worker only)
# ---------------------------------------------------------------------------
if [[ "$TIER" == "worker" ]] || [[ "$TIER" == "professional" && -z "$GPU_WORKER" ]]; then
  log "Step 3: Installing NVIDIA drivers..."

  if ! command -v nvidia-smi &>/dev/null; then
    apt-get install -y -qq nvidia-driver-535 nvidia-container-toolkit
    nvidia-ctk runtime configure --runtime=docker
    systemctl restart docker
    ok "NVIDIA drivers installed"
  else
    ok "NVIDIA drivers already present: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo 'unknown')"
  fi
else
  log "Step 3: Skipping NVIDIA (not needed for tier=$TIER)"
fi

# ---------------------------------------------------------------------------
# Step 4: Clone repository
# ---------------------------------------------------------------------------
log "Step 4: Cloning Autonomy repository..."

if [[ -d "$INSTALL_DIR/.git" ]]; then
  cd "$INSTALL_DIR"
  git fetch origin
  git checkout "$BRANCH"
  git pull origin "$BRANCH"
  ok "Repository updated"
else
  git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
  ok "Repository cloned"
fi

cd "$INSTALL_DIR"
chown -R ubuntu:ubuntu "$INSTALL_DIR"

# ---------------------------------------------------------------------------
# Step 5: Generate .env
# ---------------------------------------------------------------------------
log "Step 5: Configuring environment..."

if [[ ! -f .env ]]; then
  cp .env.template .env 2>/dev/null || cp .env.example .env 2>/dev/null || true

  # Generate secure secrets
  SECRET_KEY=$(openssl rand -hex 32)
  DB_PASSWORD=$(openssl rand -hex 16)
  PGADMIN_PASSWORD=$(openssl rand -hex 12)

  # Determine DB connection
  if [[ -n "$DB_HOST" ]]; then
    PG_HOST="$DB_HOST"
  else
    PG_HOST="db"
  fi

  cat > .env <<ENVEOF
# Autonomy Platform — Generated $(date '+%Y-%m-%d %H:%M:%S')
# Tier: $TIER

# --- Environment ---
ENVIRONMENT=production
SECRET_KEY=$SECRET_KEY

# --- Database ---
DATABASE_TYPE=postgresql
POSTGRESQL_HOST=$PG_HOST
POSTGRESQL_PORT=5432
POSTGRESQL_DATABASE=autonomy
POSTGRESQL_USER=autonomy_user
POSTGRESQL_PASSWORD=$DB_PASSWORD

# --- RAG Knowledge Base ---
KB_DATABASE_URL=postgresql+psycopg2://autonomy_user:${DB_PASSWORD}@kb-db:5432/autonomy_rag
KB_ASYNC_DATABASE_URL=postgresql+asyncpg://autonomy_user:${DB_PASSWORD}@kb-db:5432/autonomy_rag

# --- LLM ---
LLM_API_BASE=${LLM_API_BASE:-http://localhost:8001/v1}
LLM_API_KEY=not-needed
LLM_MODEL_NAME=qwen3-8b
AUTONOMY_ENABLE_SUPERVISOR=true
AUTONOMY_ENABLE_GLOBAL_AGENT=false

# --- pgAdmin ---
PGADMIN_DEFAULT_EMAIL=admin@autonomy.com
PGADMIN_DEFAULT_PASSWORD=$PGADMIN_PASSWORD

# --- Claude Skills (off by default) ---
USE_CLAUDE_SKILLS=false
ENVEOF

  ok "Generated .env with secure secrets"
else
  ok ".env already exists — preserving"
fi

# ---------------------------------------------------------------------------
# Step 6: Start services
# ---------------------------------------------------------------------------
log "Step 6: Starting services (tier=$TIER)..."

case "$TIER" in
  starter)
    # Everything on one machine
    docker compose build --quiet
    docker compose up -d
    ;;
  standard)
    # App only — DB is external (RDS or separate EC2)
    docker compose -f docker-compose.yml -f docker-compose.apps.yml build --quiet
    docker compose -f docker-compose.yml -f docker-compose.apps.yml up -d
    ;;
  professional)
    # App + local KB DB — main DB external, GPU worker separate
    docker compose build --quiet
    docker compose up -d proxy frontend backend kb-db pgadmin
    ;;
  worker)
    # GPU worker only — vLLM + embeddings + RAG DB
    docker compose -f docker-compose.worker.yml up -d
    ;;
  *)
    err "Unknown tier: $TIER (expected: starter, standard, professional, worker)"
    ;;
esac

ok "Containers started"

# ---------------------------------------------------------------------------
# Step 7: Wait for health
# ---------------------------------------------------------------------------
if [[ "$TIER" != "worker" ]]; then
  log "Step 7: Waiting for services to be healthy..."

  RETRIES=60
  for i in $(seq 1 $RETRIES); do
    if curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
      ok "Backend healthy (attempt $i)"
      break
    fi
    if [[ $i -eq $RETRIES ]]; then
      err "Backend did not become healthy after $RETRIES attempts"
    fi
    sleep 5
  done
else
  log "Step 7: Worker tier — checking vLLM health..."
  RETRIES=120  # vLLM model loading takes time
  for i in $(seq 1 $RETRIES); do
    if curl -sf http://localhost:8001/health >/dev/null 2>&1; then
      ok "vLLM healthy (attempt $i)"
      break
    fi
    if [[ $i -eq $RETRIES ]]; then
      log "WARNING: vLLM not healthy after $RETRIES attempts (model may still be loading)"
    fi
    sleep 5
  done
fi

# ---------------------------------------------------------------------------
# Step 8: Bootstrap database
# ---------------------------------------------------------------------------
if [[ "$TIER" != "worker" ]]; then
  log "Step 8: Bootstrapping database..."

  # Wait for DB to accept connections
  sleep 10

  # Run migrations and seed data
  docker compose exec -T backend python -c "
from app.db.base_class import Base
from app.db.session import sync_engine
Base.metadata.create_all(bind=sync_engine)
print('Tables created')
" 2>/dev/null || log "WARNING: Table creation may have failed (might already exist)"

  make db-bootstrap 2>/dev/null || log "WARNING: Bootstrap may have partially failed"
  make reset-admin 2>/dev/null || true

  ok "Database bootstrapped"
fi

# ---------------------------------------------------------------------------
# Step 9: Print summary
# ---------------------------------------------------------------------------
PUBLIC_IP=$(curl -sf http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "localhost")

log ""
log "========================================"
log "Deployment Complete!"
log "========================================"
log ""

case "$TIER" in
  starter|standard|professional)
    log "Frontend:  http://$PUBLIC_IP:8088"
    log "API Docs:  http://$PUBLIC_IP:8000/docs"
    log "pgAdmin:   http://$PUBLIC_IP:5050"
    log ""
    log "Login:     systemadmin@autonomy.com / Autonomy@2026"
    ;;
  worker)
    log "vLLM API:     http://$PUBLIC_IP:8001/v1"
    log "Embeddings:   http://$PUBLIC_IP:8080"
    log "RAG DB:       postgresql://...:5433/autonomy_rag"
    log ""
    log "Point your app server .env to:"
    log "  LLM_API_BASE=http://$PUBLIC_IP:8001/v1"
    log "  EMBEDDING_API_BASE=http://$PUBLIC_IP:8080"
    ;;
esac

log ""
log "Tier: $TIER"
log "Log:  $LOG_FILE"
log "========================================"
