# Rename "The Beer Game" to "Autonomy"

## Context

The product/platform has been called "The Beer Game" throughout the codebase, but The Beer Game is actually just one supply chain configuration used for learning. The product name is **Autonomy**. This rename separates the product identity from the simulation module.

## Naming Convention

| Context | Old | New |
|---------|-----|-----|
| Product/platform name | "The Beer Game" | "Autonomy" |
| SC config names | "Default TBG", "Case TBG", etc. | "Default Beer Game", "Case Beer Game", etc. |
| Code classes/functions | `BeerGameX`, `BeerLine` | Generic: `SimulationX`, `SupplyChainLine` |
| Constants | `DEFAULT_TBG_*` | `DEFAULT_BEER_GAME_*` |
| Infrastructure | `beer-game-*`, `beer_game` | `autonomy-*`, `autonomy` |
| Admin users | `tbg_admin` | `beer_game_admin` |
| API endpoints | `/beer-game-execution` | `/simulation-execution` |
| DB table | `beer_game_steps` | `simulation_steps` |

---

## Phase 1: Backend Code Renames

The largest phase. Rename classes, functions, constants, then file names, then imports.

### Class/Function Renames

- `engine.py`: `BeerLine` -> `SupplyChainLine`
- `rl/config.py`: `BeerGameParams` -> `SimulationParams`
- `rl/aws_sc_config.py`: `BeerGameParamsV2` -> `SimulationParamsV2`, `beer_game_to_sc_state` -> `simulation_to_sc_state`, `from_beer_game_dict` -> `from_simulation_dict`
- `sc_planning/beer_game_execution_adapter.py`: `BeerGameExecutionAdapter` -> `SimulationExecutionAdapter`
- `sc_planning/beer_game_adapter.py`: `BeerGameToSCAdapter` -> `SimulationToSCAdapter`
- `beer_game_execution_engine.py`: `BeerGameExecutionEngine` -> `SimulationExecutionEngine`
- `sc_execution/beer_game_executor.py`: `BeerGameExecutor` -> `SimulationExecutor`
- `sc_execution/site_id_mapper.py`: `BeerGameIdMapper` -> `SimulationIdMapper`
- `llm_agent/beer_game_openai_agents.py`: `BeerGameNodeAgent` -> `SimulationNodeAgent`, `BeerGameSupervisorAgent` -> `SimulationSupervisorAgent`, `BeerGameGlobalAgent` -> `SimulationGlobalAgent`, `BeerGameAgentsOrchestrator` -> `SimulationAgentsOrchestrator`
- `llm_agent/autonomy_tbg_agent.py`: `call_beer_game_gpt` -> `call_simulation_gpt`
- `llm_agent/strategist_adapter.py`: `BeerGameClient` -> `SimulationClient`, `RunBeerGameSimRequest` -> `RunSimulationRequest`

### Constants & Config Defaults

- `group_service.py`: `DEFAULT_TBG_SITE_TYPE_DEFINITIONS` -> `DEFAULT_BEER_GAME_SITE_TYPE_DEFINITIONS`
- `core/config.py`: `PROJECT_NAME = "Beer Game API"` -> `"Autonomy API"`
- `core/db_urls.py`: `beer_game_dev.db` -> `autonomy_dev.db`, fallback DB names -> `autonomy`
- `seed_default_group.py`: All TBG constants -> Beer Game equivalents
- `seed_default_tbg.py`, `seed_three_fg_tbg.py`, `seed_variable_tbg.py`: Config name refs
- Training scripts: `DEFAULT_CONFIG_NAME` defaults

### File Renames (after all internal refs updated)

| Old | New |
|-----|-----|
| `services/beer_game_execution_engine.py` | `services/simulation_execution_engine.py` |
| `services/sc_planning/beer_game_execution_adapter.py` | `services/sc_planning/simulation_execution_adapter.py` |
| `services/sc_planning/beer_game_adapter.py` | `services/sc_planning/simulation_adapter.py` |
| `services/sc_execution/beer_game_executor.py` | `services/sc_execution/simulation_executor.py` |
| `api/endpoints/beer_game_execution.py` | `api/endpoints/simulation_execution.py` |
| `llm_agent/beer_game_openai_agents.py` | `llm_agent/simulation_openai_agents.py` |
| `llm_agent/autonomy_tbg_agent.py` | `llm_agent/autonomy_simulation_agent.py` |
| `scripts/seed_default_tbg.py` | `scripts/seed_default_beer_game.py` |
| `scripts/seed_three_fg_tbg.py` | `scripts/seed_three_fg_beer_game.py` |
| `scripts/seed_variable_tbg.py` | `scripts/seed_variable_beer_game.py` |
| `scripts/convert_beer_game_to_aws_sc.py` | `scripts/convert_simulation_to_aws_sc.py` |
| `scripts/play_naive_agent_Default_TBG.py` | `scripts/play_naive_agent_Default_Beer_Game.py` |
| `scripts/play_naive_agent_Six_Pack_TBG.py` | `scripts/play_naive_agent_Six_Pack_Beer_Game.py` |
| `scripts/play_naive_agent_Bottle_TBG.py` | `scripts/play_naive_agent_Bottle_Beer_Game.py` |

### API Route

- `api_v1/api.py`: prefix `/beer-game-execution` -> `/simulation-execution`
- `main.py`: app title `"Autonomy API"` -> `"Autonomy API"`

### Makefile

- `CONFIG_NAME ?= Default TBG` -> `Default Beer Game`
- Targets: `seed-default-tbg` -> `seed-default-beer-game`, etc.
- `REMOTE_DIR ?= ~/beer-game` -> `~/autonomy`

---

## Phase 2: Frontend Renames

- `package.json`: `"beer-game-frontend"` -> `"autonomy-frontend"`
- `public/index.html`: title and meta -> "Autonomy"
- `pages/admin/Training.jsx`: `beer_game_steps` -> `simulation_steps`
- `pages/admin/Dashboard.jsx`: config identifiers `default_tbg` -> `default_beer_game`
- `pages/admin/GroupManagement.jsx`: remove "TBG" from messages
- `pages/admin/Governance.jsx`: `Default TBG` -> `Default Beer Game`
- `components/admin/GNNTrainingPanel.jsx`: config normalization comment
- `components/supply-chain-config/ScenarioTreeViewer.jsx`: placeholder text
- `pages/ProfilePage.jsx`: mock user data
- `config/navigationConfig.js`: comments
- `nginx.conf`: backend upstream name
- `assets/beer-game-diagram.svg`: SVG title text

---

## Phase 3: Infrastructure Renames

### Docker Compose (all 7 files)

- Container names: `beer-game-proxy` -> `autonomy-proxy`, `beer-game-frontend` -> `autonomy-frontend`, `the_beer_game_backend` -> `autonomy-backend`, `the_beer_game_db` -> `autonomy-db`
- Network: `beer-game-network` -> `autonomy-network`
- DB defaults: `beer_game` -> `autonomy`, `beer_user` -> `autonomy_user`

### Environment Files

- `.env`, `.env.example`, `.env.dev.template`, `.env.prod`: DB name and user

### Other Infrastructure

- `init_db_postgres.sql`: DB and user names
- Shell scripts: venv names, container references
- `backend/scripts/Dockerfile`: ENV vars

---

## Phase 4: Database Migration

Create new migration `20260209_rename_tbg_to_beer_game.py`:

- `UPDATE supply_chain_configs SET name`: all TBG -> Beer Game variants
- `UPDATE groups SET name`: TBG -> Beer Game variants
- `UPDATE users`: `tbg_admin` -> `beer_game_admin`
- `ALTER TABLE IF EXISTS beer_game_steps RENAME TO simulation_steps`

Old migration files are **NOT** modified.

---

## Phase 5: Documentation

- `CLAUDE.md`: Product name "The Beer Game" -> "Autonomy", keep "Beer Game" for simulation module references
- `README.md`, `EXECUTIVE_SUMMARY.md`: Product name updates
- Other architecture docs: Update product name references
- Historical docs (`docs/progress/`, `docs_export/`): Leave as-is
- PDF reference materials (`docs/The_Beer_Game/`): Leave as-is

---

## Phase 6: Cleanup & Verification

- Delete old SQLite dev databases (`beer_game*.db`)
- Clear `__pycache__` directories
- Update `MEMORY.md` with new terminology
- Full integration test: `make down`, clear volumes, `make up`, `make db-bootstrap`, verify login, verify configs

---

## Files NOT Modified

- Old Alembic migration files (historical records)
- PDF reference materials in `docs/The_Beer_Game/`, `docs/Knowledge/`
- Binary checkpoint/training data files (will regenerate with new names)
- `docs_export/` directory
- `node_modules/`

---

## Verification

- `make down && make up` - all containers start with new names
- `curl localhost:8088/api/health` - API responds
- `curl localhost:8088/` - Frontend loads
- Login at `localhost:8088` with default credentials
- Check `/api/v1/supply-chain-configs` returns "Default Beer Game" etc.
- `make db-bootstrap` succeeds
- Backend imports work: `python -c "from app.services.engine import SupplyChainLine"`
