# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The Beer Game is a comprehensive supply chain simulation featuring AI-powered agents, real-time analytics, and multiplayer gameplay. The system implements:

- **Classic Beer Game**: Multi-echelon supply chain simulation with bullwhip effect
- **AI Agent System**: Multiple agent strategies (naive, bullwhip, conservative, ML-based, optimizer, LLM-powered)
- **Temporal GNN**: Graph neural network for supply chain prediction and optimization
- **DAG-based Configuration**: Flexible supply chain network topology using directed acyclic graphs
- **Multi-Agent LLM**: OpenAI-based agent orchestrator with supervisor and global planner agents

## Tech Stack

**Backend**: FastAPI (Python 3.10+), SQLAlchemy 2.0, PyTorch 2.2.0, PyTorch Geometric
**Frontend**: React 18, Material-UI 5, Recharts, D3-Sankey
**Database**: MariaDB 10.11
**Infrastructure**: Docker, Docker Compose, Nginx proxy

## Development Commands

### Starting the Application

```bash
# CPU mode (default)
make up

# GPU mode (requires NVIDIA Docker)
make up FORCE_GPU=1
# or
make gpu-up

# Development mode with overrides
make up-dev

# Remote access (HTTP)
make up-remote

# HTTPS with self-signed cert
make up-tls
```

### Service Management

```bash
# Stop containers (keeps volumes)
make down

# View logs
make logs

# Restart backend only
make restart-backend

# Restart frontend only
make restart-frontend

# Rebuild backend
make rebuild-backend

# Rebuild frontend
make rebuild-frontend
```

### Database Operations

```bash
# Initialize database (first time)
docker compose exec backend python -m app.db.init_db

# Bootstrap defaults (configs, users, games)
make db-bootstrap

# Reset games and rebuild training data
make db-reset

# Completely rebuild database
make rebuild-db

# Reseed after rebuild
make reseed-db

# Reset admin password to Autonomy@2025
make reset-admin
```

### OpenAI/LLM Configuration

```bash
# Check OpenAI connectivity
make openai-check

# Setup helper venv for OpenAI scripts
make openai-venv
```

Required environment variables in `.env`:
```env
OPENAI_API_KEY=sk-your-api-key
OPENAI_PROJECT=proj_your_project_id
GPT_ID=g-xxxxxxxxxxxxxxxxxxxxxxxx
AUTONOMY_LLM_MODEL=gpt-5-mini
AUTONOMY_CUSTOM_GPT=user:my-custom-gpt  # Optional
AUTONOMY_ENABLE_SUPERVISOR=true         # Default: true
AUTONOMY_ENABLE_GLOBAL_AGENT=false      # Default: false
```

### Training & Dataset Generation

```bash
# Generate SimPy training dataset
make generate-simpy-data

# Train temporal GNN (generates data + trains)
make train-gnn

# Train on GPU with custom parameters
make train-default-gpu TRAIN_EPOCHS=50 TRAIN_DEVICE=cuda

# Remote training
make remote-train REMOTE=user@host EPOCHS=50
```

Training parameters:
- `CONFIG_NAME`: Supply chain config to use (default: "Default TBG")
- `SIMPY_NUM_RUNS`: Number of simulation runs (default: 128)
- `SIMPY_TIMESTEPS`: Timesteps per run (default: 64)
- `SIMPY_WINDOW`: History window (default: 52)
- `SIMPY_HORIZON`: Forecast horizon (default: 1)
- `TRAIN_EPOCHS`: Training epochs (default: 10)
- `TRAIN_DEVICE`: cuda or cpu (default: cuda)

### Testing & Debugging

```bash
# Run backend server locally
cd backend
uvicorn main:app --reload

# Run round-by-round debugging script
cd backend
python scripts/manual_round_driver.py --max-rounds 6

# Export game history
cd backend
python scripts/export_round_history.py --game-id <id>

# Play a naive agent game
cd backend
python scripts/play_naive_agent_Default_TBG.py
```

### Proxy Management

```bash
# Restart proxy (picks up config changes)
make proxy-restart

# Force recreate proxy container
make proxy-recreate

# View proxy logs
make proxy-logs
```

## Architecture

### Backend Structure (`backend/app/`)

**Core Services** (`services/`)
- `engine.py`: Core Beer Game simulation engine with `BeerLine` and `Node` classes
- `mixed_game_service.py`: Main game orchestration service (375KB - handles mixed human/AI games)
- `agent_game_service.py`: Pure agent game management
- `agents.py`: Agent strategy implementations (naive, bullwhip, conservative, ml_forecast, optimizer, reactive)
- `llm_agent.py`: LLM agent wrapper with fallback to heuristic strategies
- `llm_payload.py`: OpenAI request/response handling for multi-agent system
- `supply_chain_config_service.py`: DAG-based supply chain configuration
- `group_service.py`: Group and session management
- `auth_service.py`: JWT authentication and authorization

**API Endpoints** (`api/endpoints/`)
- `mixed_game.py`: Mixed game API (human + AI)
- `agent_game.py`: Pure agent game API
- `auth.py`: Authentication (login, register, MFA)
- `supply_chain_config.py`: Supply chain network configuration
- `model.py`: Training and dataset generation endpoints
- `game.py`: Legacy game endpoints
- `websocket.py`: Real-time game updates

**Database Models** (`models/`)
- `game.py`: Game, Round, PlayerAction
- `player.py`: Player and PlayerRound
- `supply_chain_config.py`: SupplyChainConfig, Node, Lane, Item, Market
- `agent_config.py`: AgentConfig, AgentGameConfig
- `group.py`: Group model
- `user.py`: User, Role, Permission
- `gnn/`: GNN model definitions

**Business Logic**
- `agents/`: Agent strategy implementations
- `simulation/`: SimPy-based simulation for dataset generation
- `rl/`: Reinforcement learning components
- `data/`: Data processing utilities
- `utils/`: Helper utilities

### Frontend Structure (`frontend/src/`)

**Pages** (`pages/`)
- `admin/`: Admin dashboard, user management, model training UI
- `GameBoard.jsx`: Main game interface
- `Login.jsx`, `Register.jsx`: Authentication

**Components** (`components/`)
- `admin/`: Admin-specific components
- `game/`: Game board, inventory display, order forms
- `charts/`: Recharts-based visualizations
- `supply-chain-config/`: Network configuration UI with D3-Sankey diagrams
- `common/`: Shared UI components

**Services** (`services/`)
- `api.js`: Axios-based API client
- `auth.js`: Authentication service
- `gameService.js`: Game state management

### Supply Chain DAG System

The system uses a **4-master-type DAG model**:

1. **Market Supply**: Upstream source nodes
2. **Market Demand**: Terminal demand sink nodes
3. **Inventory**: Storage/fulfillment nodes (Distributor, Wholesaler, Retailer, DC, Component Supplier)
4. **Manufacturer**: Transform nodes with Bill of Materials (BOM)

**Key Concepts**:
- Each node has both an SC node type (human-friendly) and master type (routing)
- Lanes (edges) define material flow between nodes
- BOMs define transformation ratios (e.g., Case = 4 Six-Packs)
- Items flow through the network based on DAG topology

See `DAG_Logic.md` for detailed master node type mappings and config examples.

### Agent System Architecture

**Strategy Types** (see `AGENT_SYSTEM.md`):
- `naive`: Mirrors incoming demand
- `bullwhip`: Intentionally over-orders to demonstrate volatility
- `conservative`: Maintains stable orders
- `ml_forecast`: ML-based demand prediction
- `optimizer`: Cost function optimization
- `reactive`: Rapid response to inventory changes
- `llm`: Routes to OpenAI-based multi-agent system

**LLM Multi-Agent System** (`llm_agent/beer_game_openai_agents.py`):
- **Node Agents**: Per-role agents (retailer, wholesaler, distributor, factory) with structured JSON schemas
- **Supervisor Agent**: Reviews and validates node agent proposals, can clamp/rewrite orders
- **Global Planner Agent**: Optional rolling base-stock and variance target planning
- **BeerGameAgentsOrchestrator**: Manages agent lifecycle and tool registry

**Temporal GNN** (`backend/app/models/gnn/`):
- `SupplyChainTemporalGNN`: GAT-based message passing + temporal processing
- `SupplyChainAgent`: Per-node inference and training wrapper
- Training via `scripts/training/train_gnn.py` and `train_gpu_default.py`

### Game Engine Flow

1. **Initialization**: Create `BeerLine` with nodes and policies
2. **Round Tick** (`engine.py:BeerLine.tick()`):
   - Process incoming shipments → update inventory
   - Fulfill demand/backlog → calculate shipments to downstream
   - Receive orders from downstream → update node state
   - Agent decides order quantity → place order upstream
   - Update costs and metrics
3. **State Persistence**: Save `PlayerRound` records to database
4. **Analytics**: Compute bullwhip metrics, service levels, costs

### Database Schema

**Core Tables**:
- `users`: User accounts with role-based access
- `groups`: Organization/session containers
- `supply_chain_configs`: Network topology definitions
- `nodes`, `lanes`, `items`: DAG components
- `games`: Game instances
- `players`: Player assignments to games
- `rounds`: Per-round game state
- `player_rounds`: Per-player per-round metrics
- `agent_configs`: Agent strategy configurations
- `agent_game_configs`: Agent-to-game mappings

## Key Implementation Details

### Authentication
- JWT tokens with HTTP-only cookies
- CSRF protection via double-submit cookie pattern
- Role-based access: SYSTEM_ADMIN, MANAGER, PLAYER
- MFA support via TOTP (PyOTP)

### WebSocket Updates
Real-time game state broadcasting on round completion:
```python
# backend/app/api/endpoints/mixed_game.py
await manager.broadcast_to_game(game_id, {
    "type": "round_completed",
    "data": round_data
})
```

### Agent Decision Flow
```python
# backend/app/services/agents.py
policy = get_policy_by_strategy(strategy_name)
order_quantity = policy.compute_order(node, context)
```

For LLM agents:
```python
# backend/app/services/llm_agent.py
response = orchestrator.call_beer_game_gpt(
    node_context, supervisor=True, global_agent=False
)
order_quantity = response["order_upstream"]
```

### Training Pipeline
1. Generate synthetic data via SimPy simulation (`generate_simpy_dataset.py`)
2. Build graph tensors from game history
3. Train temporal GNN (`train_gpu_default.py` or `train_gnn.py`)
4. Save checkpoint to `backend/checkpoints/`
5. Load in agent service for inference

### Frontend API Integration
```javascript
// frontend/src/services/api.js
const api = axios.create({
  baseURL: '/api',
  withCredentials: true
});
```

All API calls go through the Nginx proxy which routes:
- `/api/*` → Backend (port 8000)
- `/*` → Frontend (port 3000)

## Docker Compose Files

- `docker-compose.yml`: Base stack (proxy, frontend, backend, db, phpmyadmin)
- `docker-compose.dev.yml`: Dev overrides with hot-reload
- `docker-compose.gpu.yml`: GPU-enabled backend with NVIDIA runtime
- `docker-compose.prod.yml`: Production deployment (Gunicorn)
- `docker-compose.apps.yml`: Frontend + backend only (external DB)
- `docker-compose.db.yml`: Standalone database

Layer files with `-f` flag:
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up
```

## Environment Setup

```bash
# Initialize .env from template
make init-env

# Key variables
MARIADB_HOST=db
MARIADB_DATABASE=beer_game
MARIADB_USER=beer_user
MARIADB_PASSWORD=beer_password
SECRET_KEY=<generate-random-key>
OPENAI_API_KEY=sk-...
OPENAI_PROJECT=proj_...
GPT_ID=g-...
```

## Common Workflows

### Adding a New Agent Strategy
1. Implement strategy in `backend/app/services/agents.py`
2. Register in `AgentStrategy` enum
3. Add strategy to `get_policy_by_strategy()` factory
4. Update `AGENT_SYSTEM.md` documentation

### Creating a New Supply Chain Config
1. Use admin UI or POST to `/api/v1/supply-chain-configs`
2. Define nodes with master types (MARKET_SUPPLY, MARKET_DEMAND, INVENTORY, MANUFACTURER)
3. Create lanes connecting nodes
4. Define items and BOMs for manufacturers
5. Validate DAG topology

### Running a Game Simulation
1. Create game via `/api/v1/mixed-games/` or `/api/v1/agent-games/`
2. Assign players (human or AI)
3. POST to `/start` endpoint
4. Iteratively POST to `/play-round` for each round
5. GET `/state` or `/history` for analytics

### Debugging a Game Issue
1. Start backend with `uvicorn main:app --reload`
2. Run `scripts/manual_round_driver.py` to step through rounds
3. Set breakpoints in `engine.py:BeerLine.tick()` or agent strategy
4. Inspect `node.inventory`, `node.backlog`, `node.pipeline_shipments`
5. Check `PlayerRound` records in database for historical state

## Accessing Services

**Local Development**:
- Frontend: http://localhost:8088
- Backend API: http://localhost:8088/api
- API Docs: http://localhost:8000/docs
- Database Admin: http://localhost:8080 (root / 19890617)
- Direct Backend: http://localhost:8000

**Remote Server**:
- HTTP: http://172.29.20.187:8088
- HTTPS: https://172.29.20.187:8443 (with `make up-tls`)

**Default Login**:
- Email: systemadmin@autonomy.ai
- Password: Autonomy@2025

## Notes

### GPU Support
- Set `FORCE_GPU=1` for GPU builds
- Requires NVIDIA Docker runtime
- Backend uses PyTorch with CUDA for GNN training
- Falls back to CPU if GPU unavailable

### Docker Compose Version
The Makefile auto-detects Compose V2 (`docker compose`) vs V1 (`docker-compose`). For V1, it sets `COMPOSE_API_VERSION=1.44` to avoid `KeyError: 'ContainerConfig'` errors.

### Backend Entry Point
The backend uses `backend/main.py` as the FastAPI application entry point. Note: this file is 62K lines and contains extensive configuration.

### Seeding Process
When running `make up` with `FORCE_GPU=1`, the system automatically runs `make db-bootstrap` which:
1. Seeds Default TBG, Three FG TBG, and Variable TBG configs
2. Creates default users and groups
3. Generates showcase games with LLM and GNN agents

### Training Hyperparameters
Admin UI exposes: epochs, device, window, horizon, data source.
Code-only: architecture (hidden dims, layers), learning rate, batch size, RL hyperparameters.
No automated hyperparameter search - requires manual orchestration.
