# Code Sweep Report: AWS Field Name Migration

**Generated**: 2026-01-07
**Purpose**: Identify all code locations requiring updates for AWS Supply Chain field renames

---

## Executive Summary

This report catalogs all files that reference the old field names that will be renamed in the AWS Supply Chain alignment migration.

### Total Impact

- **Backend Python files**: 50+ files affected
- **Frontend JavaScript files**: 30+ files estimated
- **Database migration files**: 15+ files
- **Total lines requiring changes**: 800-1000+ estimated

---

## Field Rename Summary

| Old Field Name | New Field Name | Tables Affected | Est. References |
|----------------|----------------|-----------------|-----------------|
| `item_id` | `product_id` | ALL | 400+ |
| `node_id` | `site_id` | ALL | 350+ |
| `upstream_node_id` | `from_site_id` | lanes | 50+ |
| `downstream_node_id` | `to_site_id` | lanes | 50+ |
| `nodes.name` | `nodes.description` | nodes | 100+ |
| `nodes.type` | `nodes.site_type` | nodes | 80+ |

---

## Backend Files Requiring Updates


### 1. Core Models (app/models/)

**app/models/supply_chain_config.py** (CRITICAL)
- `item_id` references: 3
- `node_id` references: 12
- `upstream_node_id` references: 7
- `downstream_node_id` references: 7
- **Actions Required**:
  - Update all Column definitions
  - Update ForeignKey references
  - Update relationship back_populates
  - Update __table_args__ unique constraints

**app/models/game.py**
- Field references in JSON config blobs
- **Actions Required**: Update JSON schema documentation

**app/models/player.py**
- `node_key` → `site_key` (if exists)
- **Actions Required**: Update Column definition

---

### 2. Pydantic Schemas (app/schemas/)

**app/schemas/supply_chain_config.py** (CRITICAL)
- `item_id` references: 2+
- `node_id` references: 6+
- `upstream_node_id` references: 4
- `downstream_node_id` references: 4
- **Actions Required**:
  - Update all BaseModel field definitions
  - Update Field aliases if used
  - Update example values in docstrings

**app/schemas/simulation.py** (CRITICAL)
- `item_id` references: 2
- `node_id` references: 2
- **Actions Required**:
  - Update OrderRequest model
  - Update Shipment model
  - Update NodeState model
  - Update RoundContext model

**app/schemas/supply_chain.py**
- Field references in state models
- **Actions Required**: Update field names

---

### 3. Service Layer (app/services/)

**app/services/mixed_game_service.py** (CRITICAL - 7200+ lines)
- `item_id` references: 237 occurrences
- `node_id` references: extensive
- `upstream_node_id` / `downstream_node_id`: 4 occurrences
- **Actions Required**:
  - Update config snapshot building
  - Update order placement logic
  - Update topology building
  - Update all dictionary key accesses
  - Update JSON path extractions
  - ⚠️ HIGHEST RISK FILE - requires thorough testing

**app/services/supply_chain_config_service.py**
- `item_id` references: 11
- `node_id` references: extensive
- `upstream_node_id` / `downstream_node_id`: 2
- **Actions Required**:
  - Update CRUD operations
  - Update validation logic
  - Update query filters

**app/services/group_service.py**
- `item_id` references: 2
- `node_id` references: 2
- **Actions Required**: Update query references

---

### 4. API Endpoints (app/api/endpoints/)

**app/api/endpoints/supply_chain_config.py**
- `item_id` references: 18
- `upstream_node_id` / `downstream_node_id`: 12
- **Actions Required**:
  - Update request/response models
  - Update query parameters
  - Update error messages

**app/api/endpoints/auth.py**
- `item_id` references: 2
- `upstream_node_id` / `downstream_node_id`: 10
- **Actions Required**: Update references in auth logic

---

### 5. CRUD Operations (app/crud/)

**app/crud/crud_supply_chain_config.py**
- `item_id` references: 4
- `upstream_node_id` / `downstream_node_id`: 4
- **Actions Required**:
  - Update SQLAlchemy queries
  - Update filter conditions

---

### 6. Simulation Code (app/simulation/)

**app/simulation/helpers.py**
- `item_id` references: 19
- **Actions Required**: Update helper functions

**app/simulation/debug_logging.py**
- `item_id` references: 4
- **Actions Required**: Update log messages

**app/simulation/sankey_logging.py**
- `node_id` references: 20
- **Actions Required**: Update Sankey diagram data structure

---

### 7. Tests (app/tests/, tests/)

**app/tests/test_mixed_game_seeding.py** - 2 occurrences
**app/tests/test_main_simulation.py** - 6 occurrences
**app/tests/test_supply_chain_config_service.py** - 8 occurrences
**tests/services/test_mixed_game_service.py** - 9 occurrences

**Actions Required**:
- Update all test fixtures
- Update assertion field names
- Update mock data

---

### 8. Scripts (scripts/)

**scripts/create_regional_sc_config.py**
- `item_id`: 12 occurrences
- `node_id`: 30 occurrences
- `upstream_node_id` / `downstream_node_id`: 20 occurrences
- **Actions Required**: Update config building scripts

**scripts/seed_default_group.py**
- `upstream_node_id` / `downstream_node_id`: 30 occurrences
- **Actions Required**: Update seeding data

---

### 9. Training/ML Code (app/rl/, app/train_*.py)

**app/rl/data_generator.py**
- `node_id`: 1 occurrence
- **Actions Required**: Update data generation

**app/train_tgnn_clean.py**
- `node_id`: 4 occurrences
- **Actions Required**: Update training data loading

---

### 10. LLM Agent Code (llm_agent/)

**llm_agent/beer_game_openai_agents.py**
- `node_id`: 18 occurrences
- **Actions Required**: Update LLM prompt context

**llm_agent/autonomy_client.py**
- `node_id`: 2 occurrences
- **Actions Required**: Update API client

---

### 11. Database Migrations (migrations/versions/)

**All existing migrations** - DO NOT MODIFY
- Historical migrations must remain unchanged
- Only new migrations should use new field names

---

## Frontend Files Requiring Updates

/home/trevor/Projects/The_Beer_Game/frontend/src/pages/admin/ModelSetup.jsx:15
/home/trevor/Projects/The_Beer_Game/frontend/src/pages/CreateMixedGame.js:2
/home/trevor/Projects/The_Beer_Game/frontend/src/pages/GameReport.jsx:15
/home/trevor/Projects/The_Beer_Game/frontend/src/services/supplyChainConfigService.js:6
/home/trevor/Projects/The_Beer_Game/frontend/src/components/supply-chain-config/SupplyChainConfigForm.jsx:4
/home/trevor/Projects/The_Beer_Game/frontend/src/components/supply-chain-config/ItemForm.jsx:2
/home/trevor/Projects/The_Beer_Game/frontend/src/components/supply-chain-config/MarketDemandForm.jsx:13
/home/trevor/Projects/The_Beer_Game/frontend/src/components/supply-chain-config/SupplyChainConfigSankey.jsx:3
/home/trevor/Projects/The_Beer_Game/frontend/src/components/supply-chain-config/ItemNodeConfigForm.jsx:22

### Frontend File Categories

1. **Services** (`frontend/src/services/`)
   - `supplyChainConfigService.js` - CRITICAL
   - `api.js` - API client

2. **Components** (`frontend/src/components/supply-chain-config/`)
   - `SupplyChainConfigForm.jsx`
   - `ItemForm.jsx`
   - `NodeForm.jsx`
   - `LaneForm.jsx`
   - `ItemNodeConfigForm.jsx`
   - All these use item_id, node_id extensively

3. **Pages** (`frontend/src/pages/`)
   - Admin pages referencing supply chain configs

---

## Migration Strategy

### Phase 1: Preparation (Week 1)

1. **Create feature branch**: `feature/aws-field-renames`
2. **Run this code sweep** to generate list
3. **Create automated search/replace scripts**
4. **Set up comprehensive test suite**

### Phase 2: Backend Updates (Week 2-3)

1. **Update Models** (Day 1-2)
   - supply_chain_config.py
   - Update all Column definitions
   - Update ForeignKey references

2. **Update Schemas** (Day 3)
   - supply_chain_config.py
   - simulation.py
   - All Pydantic models

3. **Update Services** (Day 4-7)
   - mixed_game_service.py (CRITICAL - allocate 2 days)
   - supply_chain_config_service.py
   - All other services

4. **Update API Endpoints** (Day 8)
   - supply_chain_config.py
   - All endpoints

5. **Update Tests** (Day 9-10)
   - All test files
   - Create new regression tests

### Phase 3: Frontend Updates (Week 3-4)

1. **Update Services** (Day 1-2)
2. **Update Components** (Day 3-5)
3. **Update Pages** (Day 6-7)
4. **E2E Testing** (Day 8-10)

### Phase 4: Migration & Deployment (Week 4)

1. **Backup Database** (critical!)
2. **Run Phase 1 migrations** (optional fields)
3. **Deploy code changes**
4. **Run Phase 2 migrations** (field renames)
5. **Smoke test in production**
6. **Monitor for issues**

---

## Automated Search/Replace Script

```bash
#!/bin/bash
# aws_field_rename.sh - Automated rename script

BACKEND_DIR="backend/app"
FRONTEND_DIR="frontend/src"

# Backend Python files
find $BACKEND_DIR -name "*.py" -type f -exec sed -i.bak \
  -e 's/\bitem_id\b/product_id/g' \
  -e 's/\bnode_id\b/site_id/g' \
  -e 's/\bupstream_node_id\b/from_site_id/g' \
  -e 's/\bdownstream_node_id\b/from_site_id/g' \
  {} +

# Frontend JavaScript files
find $FRONTEND_DIR -name "*.js" -o -name "*.jsx" -type f -exec sed -i.bak \
  -e 's/item_id/product_id/g' \
  -e 's/itemId/productId/g' \
  -e 's/node_id/site_id/g' \
  -e 's/nodeId/siteId/g' \
  -e 's/upstream_node_id/from_site_id/g' \
  -e 's/upstreamNodeId/fromSiteId/g' \
  -e 's/downstream_node_id/to_site_id/g' \
  -e 's/downstreamNodeId/toSiteId/g' \
  {} +

echo "✅ Automated renames complete. Review .bak files before committing."
```

⚠️ **WARNING**: This script is a starting point. Manual review is REQUIRED as some contexts may need different handling.

---

## Testing Checklist

### Unit Tests
- [ ] All model tests pass
- [ ] All schema validation tests pass
- [ ] All service tests pass
- [ ] All API endpoint tests pass

### Integration Tests
- [ ] Create supply chain config via API
- [ ] Update config with new field names
- [ ] Start game with config
- [ ] Run simulation rounds
- [ ] Query game history
- [ ] Verify JSON responses use new field names

### E2E Tests
- [ ] Login as admin
- [ ] Create new supply chain config in UI
- [ ] Add items, nodes, lanes with new structure
- [ ] Start game
- [ ] Play multiple rounds
- [ ] View game results
- [ ] Export game data

### Regression Tests
- [ ] Load existing configs (created before migration)
- [ ] Verify old configs still work
- [ ] Verify old game data can be queried
- [ ] Verify backwards compatibility if needed

---

## Rollback Plan

If migration fails:

1. **Stop application immediately**
2. **Run downgrade migration**: `alembic downgrade -1`
3. **Restore database backup** (if needed)
4. **Deploy previous code version**
5. **Investigate failure** before retry

---

## Risk Assessment

| Area | Risk Level | Mitigation |
|------|-----------|------------|
| Database Migration | 🔴 HIGH | Full backup, test on staging first |
| mixed_game_service.py | 🔴 HIGH | Extensive unit tests, manual QA |
| Frontend API calls | 🟡 MEDIUM | API versioning, backwards compat layer |
| Existing game data | 🟡 MEDIUM | Data migration scripts, validation |
| LLM Agent prompts | 🟢 LOW | Update templates, test prompts |

---

## Estimated Effort

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| Preparation | 1 week | None |
| Backend Updates | 2-3 weeks | Preparation complete |
| Frontend Updates | 1-2 weeks | Backend deployed |
| Testing & QA | 1 week | All code updated |
| Deployment | 3 days | All testing passed |
| **TOTAL** | **6-8 weeks** | - |

---

## Next Steps

1. Review this code sweep report
2. Decide: Big bang vs phased approach
3. Schedule migration window
4. Create detailed task breakdown
5. Assign developers
6. Set up test environments
7. Begin Phase 1 (optional fields) - LOW RISK
8. After Phase 1 stable, proceed with Phase 2 (renames) - HIGH RISK

---

## Contact

For questions about this migration, contact the development team.

**Document Version**: 1.0
**Last Updated**: 2026-01-07
