#!/bin/bash
#
# Documentation Export Script
# Packages documentation for sharing
#

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="${PROJECT_ROOT}/docs_export"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
EXPORT_NAME="autonomy_docs_${TIMESTAMP}"

echo -e "${BLUE}=================================="
echo "Documentation Export"
echo "==================================${NC}"
echo ""

# Create output directory
mkdir -p "${OUTPUT_DIR}/${EXPORT_NAME}"

echo "Exporting documentation..."

# Copy main documentation files
echo "  - Main documentation..."
cp "${PROJECT_ROOT}/DOCUMENTATION_INDEX.md" "${OUTPUT_DIR}/${EXPORT_NAME}/"
cp "${PROJECT_ROOT}/README.md" "${OUTPUT_DIR}/${EXPORT_NAME}/" 2>/dev/null || true
cp "${PROJECT_ROOT}/CLAUDE.md" "${OUTPUT_DIR}/${EXPORT_NAME}/"
cp "${PROJECT_ROOT}/DAG_Logic.md" "${OUTPUT_DIR}/${EXPORT_NAME}/"
cp "${PROJECT_ROOT}/AGENT_SYSTEM.md" "${OUTPUT_DIR}/${EXPORT_NAME}/"

# Copy phase documentation
echo "  - Phase documentation..."
mkdir -p "${OUTPUT_DIR}/${EXPORT_NAME}/phases"
cp "${PROJECT_ROOT}"/AWS_SC_PHASE*.md "${OUTPUT_DIR}/${EXPORT_NAME}/phases/" 2>/dev/null || true

# Copy deployment documentation
echo "  - Deployment documentation..."
mkdir -p "${OUTPUT_DIR}/${EXPORT_NAME}/deployment"
cp "${PROJECT_ROOT}/deploy/DEPLOYMENT.md" "${OUTPUT_DIR}/${EXPORT_NAME}/deployment/"
cp "${PROJECT_ROOT}/deploy/deploy.sh" "${OUTPUT_DIR}/${EXPORT_NAME}/deployment/"
cp "${PROJECT_ROOT}/deploy/rollback.sh" "${OUTPUT_DIR}/${EXPORT_NAME}/deployment/"

# Copy testing documentation
echo "  - Testing documentation..."
mkdir -p "${OUTPUT_DIR}/${EXPORT_NAME}/testing"
cp "${PROJECT_ROOT}/backend/tests/integration/README.md" "${OUTPUT_DIR}/${EXPORT_NAME}/testing/integration_tests.md" 2>/dev/null || true

# Copy API examples
echo "  - API documentation..."
mkdir -p "${OUTPUT_DIR}/${EXPORT_NAME}/api"
cat > "${OUTPUT_DIR}/${EXPORT_NAME}/api/API_REFERENCE.md" << 'EOF'
# API Reference

## Access API Documentation

When the application is running, access interactive API documentation at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Quick API Examples

### Authentication
```bash
# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=systemadmin@autonomy.ai&password=Autonomy@2025"

# Get current user
curl -X GET http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Templates
```bash
# List templates
curl http://localhost:8000/api/v1/templates?page=1&page_size=20

# Get featured templates
curl http://localhost:8000/api/v1/templates/featured?limit=5

# Quick start wizard
curl -X POST http://localhost:8000/api/v1/templates/quick-start \
  -H "Content-Type: application/json" \
  -d '{"industry":"retail","difficulty":"beginner","num_players":4}'
```

### Health Checks
```bash
# Liveness probe
curl http://localhost:8000/api/v1/health/live

# Readiness probe
curl http://localhost:8000/api/v1/health/ready

# Detailed health
curl http://localhost:8000/api/v1/health/detailed

# Metrics
curl http://localhost:8000/api/v1/metrics
```

## API Endpoints Summary

### Core Game API
- `POST /api/v1/mixed-games/` - Create new game
- `POST /api/v1/mixed-games/{id}/start` - Start game
- `POST /api/v1/mixed-games/{id}/play-round` - Play round
- `GET /api/v1/mixed-games/{id}/state` - Get game state

### Templates API
- `GET /api/v1/templates` - List templates
- `GET /api/v1/templates/{id}` - Get template
- `POST /api/v1/templates/quick-start` - Quick start wizard
- `GET /api/v1/templates/featured` - Featured templates

### Analytics API
- `POST /api/v1/stochastic/analytics/monte-carlo/start` - Start Monte Carlo
- `GET /api/v1/stochastic/analytics/monte-carlo/{job_id}/status` - Check status
- `POST /api/v1/advanced-analytics/sensitivity-analysis` - Sensitivity analysis
- `POST /api/v1/stochastic/analytics/variability` - Variability metrics

See interactive documentation for complete API reference.
EOF

# Create quick start guide
echo "  - Quick start guide..."
cat > "${OUTPUT_DIR}/${EXPORT_NAME}/QUICK_START.md" << 'EOF'
# Quick Start Guide

## 1. Installation

### Prerequisites
- Docker 20.10+
- Docker Compose 2.0+
- 8GB RAM minimum
- 20GB disk space

### Setup
```bash
# Clone repository
git clone <repository-url>
cd Autonomy

# Initialize environment
make init-env

# Start application
make up

# Bootstrap database
make db-bootstrap
```

## 2. Access Application

- **Frontend**: http://localhost:8088
- **API Docs**: http://localhost:8000/docs
- **Admin Panel**: http://localhost:8080

### Default Credentials
- Email: systemadmin@autonomy.ai
- Password: Autonomy@2025

## 3. Create Your First Game

### Option 1: Quick Start Wizard (Recommended)
1. Log in to the application
2. Click "Create New Game"
3. Select "Quick Start Wizard"
4. Choose industry and difficulty
5. Select recommended template
6. Launch game

### Option 2: Manual Configuration
1. Log in to the application
2. Navigate to "Supply Chain Configs"
3. Select or create a configuration
4. Create new game with selected config
5. Add players (human or AI)
6. Start game

## 4. Run a Simulation

1. Create game with AI agents
2. Start game
3. Click "Auto-play" to run simulation
4. View analytics dashboard
5. Export results

## 5. Advanced Features

### Monte Carlo Simulation
1. Create game
2. Navigate to "Stochastic Analytics"
3. Configure Monte Carlo parameters
4. Start simulation (50-1000 runs)
5. Analyze results

### Sensitivity Analysis
1. Run base simulation
2. Navigate to "Advanced Analytics"
3. Select "Sensitivity Analysis"
4. Choose parameters to vary
5. View tornado diagrams

## 6. Testing the System

### Run Tests
```bash
# Integration tests
./backend/scripts/run_integration_tests.sh

# Load tests
cd backend/tests/load
locust -f locustfile.py --users 10 --spawn-rate 2

# Health validation
./backend/scripts/validate_health.sh
```

## 7. Next Steps

- Read [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md) for complete documentation
- Explore [Template Library](http://localhost:8088/templates)
- Try different AI agent strategies
- Configure custom supply chain networks

## Troubleshooting

### Application won't start
```bash
# Check Docker status
docker compose ps

# View logs
make logs

# Restart services
make down && make up
```

### Database connection error
```bash
# Reset database
make db-reset

# Reinitialize
make db-bootstrap
```

### Port already in use
```bash
# Find process using port
lsof -i :8000

# Kill process
kill -9 <PID>
```

For more help, see [Troubleshooting Guide](deployment/DEPLOYMENT.md#troubleshooting).
EOF

# Create README for the export
cat > "${OUTPUT_DIR}/${EXPORT_NAME}/README.md" << 'EOF'
# Autonomy - Documentation Package

This package contains complete documentation for the Autonomy supply chain simulation platform.

## Contents

- **DOCUMENTATION_INDEX.md** - Master index of all documentation
- **QUICK_START.md** - Get started in 5 minutes
- **CLAUDE.md** - Development guide and command reference
- **DAG_Logic.md** - Supply chain topology documentation
- **AGENT_SYSTEM.md** - AI agent system documentation
- **phases/** - Phase-by-phase development documentation
- **deployment/** - Production deployment guides
- **testing/** - Testing documentation
- **api/** - API reference and examples

## Quick Links

1. [Start Here: Quick Start Guide](QUICK_START.md)
2. [Complete Documentation Index](DOCUMENTATION_INDEX.md)
3. [Deployment Guide](deployment/DEPLOYMENT.md)
4. [API Reference](api/API_REFERENCE.md)

## System Status

✅ **Production Ready** - All 6 phases complete

## Key Features

- Multi-echelon supply chain simulation
- AI-powered agents (ML, LLM, GNN)
- Stochastic modeling & Monte Carlo simulation
- Advanced analytics & sensitivity analysis
- Real-time collaboration
- Template library (36 templates)
- Interactive tutorials

## Technology Stack

- **Backend**: FastAPI, SQLAlchemy, PyTorch
- **Frontend**: React 18, Material-UI 5
- **Database**: MariaDB 10.11
- **Infrastructure**: Docker, Nginx

## Support

- For installation help, see QUICK_START.md
- For deployment help, see deployment/DEPLOYMENT.md
- For API documentation, see api/API_REFERENCE.md
- For troubleshooting, see deployment/DEPLOYMENT.md#troubleshooting

---

**Package Created**: $(date)
**Version**: 6.0 (Phase 6 Complete)
EOF

# Create archive
echo "  - Creating archive..."
cd "${OUTPUT_DIR}"
tar -czf "${EXPORT_NAME}.tar.gz" "${EXPORT_NAME}"
zip -r -q "${EXPORT_NAME}.zip" "${EXPORT_NAME}"

# Summary
echo ""
echo -e "${GREEN}✓ Documentation exported successfully!${NC}"
echo ""
echo "Export location:"
echo "  Directory: ${OUTPUT_DIR}/${EXPORT_NAME}"
echo "  Archive:   ${OUTPUT_DIR}/${EXPORT_NAME}.tar.gz"
echo "  ZIP:       ${OUTPUT_DIR}/${EXPORT_NAME}.zip"
echo ""
echo "Share the archive with:"
echo "  - Team members"
echo "  - Stakeholders"
echo "  - Users"
echo ""
echo "Or publish to:"
echo "  - Internal wiki"
echo "  - Documentation portal"
echo "  - GitHub Pages"
