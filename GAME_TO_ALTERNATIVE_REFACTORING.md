# Terminology Refactoring Plan

## Overview

This document outlines the comprehensive terminology refactoring:

| Old Term | New Term (DB/Code) | New Term (UI) | Notes |
|----------|-------------------|---------------|-------|
| Game | Scenario | Scenario | Simulation/scenario |
| Player | Participant | User | Avoids conflict with auth `users` table |
| Gamification | Simulation | Simulation | Section name |
| Beer Game | Beer Game | Beer Game | Keep as simulation type name |

This aligns with professional supply chain planning terminology.

## Scope Summary

| Layer | Impact | Files | Estimated Changes |
|-------|--------|-------|-------------------|
| Database | 7 tables, 62 FK references | 27+ tables | HIGH |
| Backend Models | 27 model files | ~1,940 lines | HIGH |
| Backend Services | 46 service files | ~2,000 lines | HIGH |
| API Endpoints | 7 endpoint files, 30+ routes | ~500 lines | MEDIUM |
| Frontend | 30+ files | ~2,029 references | HIGH |

## Phased Approach

### Phase 1: Database Schema Migration (Breaking Change)

**Tables to rename:**
```sql
games                → scenarios
game_rounds          → scenario_periods
player_rounds        → participant_periods (optional: keep for simulation context)
player_actions       → participant_decisions
```

**Columns to rename:**
```sql
game_id              → scenario_id (in 22+ tables)
game_round_id        → scenario_period_id
```

**Migration strategy:**
1. Create new tables with new names
2. Copy data from old tables
3. Update all foreign key references
4. Drop old tables

### Phase 2: Backend Models

**Files to update:**
- `app/models/game.py` → `app/models/scenario.py`
- Update all imports across 46+ services

**Class renames:**
```python
Game          → Scenario
GameStatus    → ScenarioStatus
GameRound     → ScenarioPeriod
Round         → ScenarioPeriod (consolidate)
```

### Phase 3: Backend Services

**Major service files:**
- `mixed_game_service.py` → `mixed_scenario_service.py`
- `agent_game_service.py` → `agent_scenario_service.py`
- Update all method names and parameter names

### Phase 4: API Endpoints

**Route changes:**
```
/games                    → /scenarios
/mixed-games              → /mixed-scenarios
/agent-games              → /agent-scenarios
/games/{game_id}          → /scenarios/{scenario_id}
```

**Backwards compatibility:**
- Add redirect routes from old paths to new paths
- Deprecation warnings for 1-2 releases

### Phase 5: Frontend

**File renames:**
```
pages/GameBoard.js        → pages/ScenarioBoard.js
pages/GamesList.js        → pages/ScenariosList.js
pages/CreateMixedGame.js  → pages/CreateMixedScenario.js
services/gameService.js   → services/scenarioService.js
```

**Navigation updates:**
- Update menu items
- Update route paths
- Update breadcrumbs

### Phase 6: User-Facing Text

**Labels to update:**
```
"View Games"              → "View Scenarios"
"Create Game"             → "Create Scenario"
"Play Game"               → "Run Scenario"
"Game Report"             → "Scenario Report"
"Join Game"               → "Join Scenario"
```

## Execution Order

1. **Create database migration** (Alembic)
2. **Update models** with new table/class names
3. **Update services** with new method/parameter names
4. **Update API routes** with backwards-compatible redirects
5. **Update frontend** pages, components, services
6. **Update user-facing text** labels and navigation
7. **Remove deprecated redirects** after grace period

## Risk Mitigation

1. **Backwards compatibility**: Keep old API routes with 301 redirects
2. **Feature flag**: Allow toggling between old/new terminology
3. **Gradual rollout**: Deploy in stages with monitoring
4. **Comprehensive testing**: Unit, integration, and E2E tests

## Files Modified List

### Database/Migrations
- [ ] `alembic/versions/xxxx_rename_game_to_scenario.py` (NEW)

### Backend Models
- [ ] `app/models/game.py` → `app/models/scenario.py`
- [ ] `app/models/__init__.py`
- [ ] `app/models/supply_chain.py`
- [ ] All 27 model files with scenario_id references

### Backend Services (46 files)
- [ ] `services/mixed_game_service.py` → `services/mixed_scenario_service.py`
- [ ] `services/agent_game_service.py` → `services/agent_scenario_service.py`
- [ ] `services/engine.py`
- [ ] `services/simulation_service.py`
- [ ] ... (42 more)

### Backend API Endpoints (7 files)
- [ ] `api/endpoints/game.py` → `api/endpoints/scenario.py`
- [ ] `api/endpoints/mixed_game.py` → `api/endpoints/mixed_scenario.py`
- [ ] `api/endpoints/agent_game.py` → `api/endpoints/agent_scenario.py`
- [ ] `api/endpoints/beer_game_execution.py`
- [ ] `api/endpoints/transfer_orders.py`
- [ ] `api/endpoints/reporting.py`
- [ ] `api/endpoints/websocket.py`

### Backend Schemas
- [ ] `schemas/game.py` → `schemas/scenario.py`
- [ ] `schemas/player.py` → `schemas/participant.py`
- [ ] `schemas/metrics.py`
- [ ] `schemas/websocket.py`

### Frontend Pages (10 files)
- [ ] `pages/GameBoard.js` → `pages/ScenarioBoard.js`
- [ ] `pages/GamesList.js` → `pages/ScenariosList.js`
- [ ] `pages/CreateMixedGame.js` → `pages/CreateMixedScenario.js`
- [ ] `pages/GameReport.jsx` → `pages/ScenarioReport.jsx`
- [ ] `pages/GameStats.jsx` → `pages/ScenarioStats.jsx`
- [ ] `pages/GameVisualizations.jsx` → `pages/ScenarioVisualizations.jsx`
- [ ] `pages/GameLobby.jsx` → `pages/ScenarioLobby.jsx`
- [ ] `pages/GameRoom.jsx` → `pages/ScenarioRoom.jsx`
- [ ] `pages/PlayGame.jsx` → `pages/PlayScenario.jsx`
- [ ] `App.js` (routes)

### Frontend Components (15+ files)
- [ ] `components/game/` → `components/scenario/`
- [ ] All scenario-specific components

### Frontend Services
- [ ] `services/gameService.js` → `services/scenarioService.js`
- [ ] `services/gameApi.js` → `services/scenarioApi.js`
- [ ] `contexts/GameContext.jsx` → `contexts/ScenarioContext.jsx`

### Configuration
- [ ] `navigationConfig.js`
- [ ] Capability definitions

## Current Progress

- [ ] Phase 1: Database Migration
- [ ] Phase 2: Backend Models
- [ ] Phase 3: Backend Services
- [ ] Phase 4: API Endpoints
- [ ] Phase 5: Frontend
- [ ] Phase 6: User-Facing Text

## Notes

- The "Simulation" section name replaces "Gamification" for professional terminology
- "Participant" terminology replaces "Player" for human participants in the simulation context
- "Beer Game" is kept as a specific simulation type name (proper noun)
