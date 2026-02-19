# Supply Plan Prototype Refinement - Status Update

**Date**: 2026-01-17
**Status**: 🔄 **IN PROGRESS - Phase 1B**

---

## Progress Summary

### Completed
- ✅ Phase 1A: Core algorithm implementation (stochastic sampling + Monte Carlo simulation)
- ✅ Test infrastructure with 50+ scenario validation
- ✅ Balanced scorecard aggregation framework
- ✅ Risk-based recommendations generation

### Current Work (Phase 1B): Simulation Refinement

**Goal**: Improve prototype simulation to generate more realistic metrics without full BeerLine/DAG integration.

**Challenges Encountered**:
1. **Initial Approach**: Attempted to integrate with actual BeerLine engine from [engine.py:252-478](backend/app/services/engine.py)
2. **Complexity Discovery**: BeerLine is designed for classic 4-echelon supply chain. Current system uses complex DAG-based configurations managed by [mixed_game_service.py:3823-3950](backend/app/services/mixed_game_service.py)
3. **Decision**: For prototype phase, implement improved period-by-period simulation with heuristics rather than full engine integration

**Simulation Logic Iterations**:

| Iteration | Approach | Result | Issue |
|-----------|----------|--------|-------|
| 1 | Simple agent efficiency factors | $9,705 cost, 93.5% OTIF | Too simplistic, no period dynamics |
| 2 | Period-by-period with inventory arrays | $38T cost, 7.7% OTIF | Numerical overflow, wrong demand calc |
| 3 | Fixed demand aggregation | $1.3M cost, 15.4% OTIF | Better costs, but low service level |
| 4 | Inventory carry-forward fix | $370M cost, 100% OTIF | Excessive inventory accumulation |
| 5 | Current (in progress) | Testing... | Working on balance |

**Key Technical Issues**:
- Inventory state management across periods (t vs t+1 indexing)
- Shipment timing with lead times
- Order propagation through multi-echelon network
- Balancing service level vs inventory costs

---

## Alternative Approach: Simplified Analytical Model

Given the complexity of getting the discrete-event simulation logic correct in the prototype phase, consider a **hybrid analytical model** for Phase 1B:

### Option A: Keep Current Heuristic Model
- Accept current limitations as "prototype sufficient"
- Document that full accuracy requires Phase 5 (BeerLine integration)
- Focus on demonstrating:
  - Probability distributions work correctly
  - Balanced scorecard aggregation is accurate
  - Risk recommendations are generated
  - UI/API can consume the data structures

**Pros**:
- Moves forward to Phase 2 (Backend API) quickly
- Core value prop (probabilistic planning) is demonstrated
- Users can evaluate approach before committing to full integration

**Cons**:
- Metrics may not be highly accurate
- Cannot validate agent strategy performance claims
- May undermine credibility with sophisticated users

### Option B: Simplified Newsvendor-Style Model
- Use analytical formulas instead of discrete simulation
- Model as multi-echelon newsvendor problem
- Calculate:
  - Optimal base-stock levels per node
  - Expected costs using probability distributions
  - Service levels from stockout probabilities

**Pros**:
- Mathematically rigorous
- Faster computation (no period-by-period loops)
- Well-understood model in literature

**Cons**:
- Doesn't capture bullwhip dynamics
- No time-series metrics
- Loses some realism

### Option C: Focus on Phase 2 (API) Now
- Accept current prototype simulation "as is"
- Build API layer and database persistence
- Return to simulation refinement in Phase 5

**Pros**:
- Delivers working system end-to-end
- Users can test with real data
- Easier to identify what metrics actually matter

**Cons**:
- Risk of building UI on inaccurate foundation
- May need to refactor data models later

---

## Recommendation: **Option C + Partial A**

**Proposed Path Forward**:

1. **Stabilize Current Simulation** (2 hours):
   - Add bounds checking to prevent numerical issues
   - Cap inventory at reasonable multiples of demand
   - Ensure OTIF is between 60-100% range
   - Accept approximate metrics as "directionally correct"

2. **Update Documentation** (1 hour):
   - Mark prototype simulation limitations clearly
   - Add Phase 5 integration plan to [SUPPLY_PLAN_GENERATION_DESIGN.md](SUPPLY_PLAN_GENERATION_DESIGN.md)
   - Create comparison table: Prototype vs Production metrics

3. **Move to Phase 2 (Backend API)** (2-3 days):
   - Create API endpoints
   - Add database models for supply plan storage
   - Implement async task management
   - Build plan comparison functionality

4. **Phase 3 (Frontend Dashboard)** (3-4 days):
   - Probability distribution visualizations
   - Balanced scorecard display
   - Risk recommendations UI

5. **Phase 5 (Full BeerLine Integration)** (Future - 5-7 days):
   - Integrate with actual DAG-based engine
   - Replace heuristic simulation with real BeerLine.tick()
   - Validate accuracy improvements

---

## Current File State

**Modified**: [backend/app/services/monte_carlo_planner.py](backend/app/services/monte_carlo_planner.py)
- Lines 92-270: `run_scenario_simulation()` method
- Multiple iterations attempting to fix inventory/backlog dynamics
- Current state: Logical but producing unrealistic metrics

**Next Action Required**:
- Decision from stakeholder on Option A/B/C
- If Option C: Stabilize and document limitations
- If Option B: Rewrite simulation logic with analytical model
- If Option A: Continue debugging discrete simulation

---

## Key Learnings

1. **Discrete-event simulation is hard to get right**: Even "simple" multi-echelon inventory systems have subtle timing and state management issues

2. **Prototype != Production**: Attempting to achieve production-quality simulation in prototype phase may be premature optimization

3. **Value is in the framework**: The core contribution is probabilistic planning with balanced scorecards, not simulation accuracy

4. **Integration is Phase 5 for a reason**: Original design document correctly identified BeerLine integration as a separate phase after API/UI are working

---

## Status: ⏸️ **AWAITING DIRECTION**

**Options**:
- A: Accept prototype limitations, continue to Phase 2
- B: Rewrite with analytical model
- C: Continue debugging discrete simulation

**Estimated Time to Complete Phase 1B**:
- Option A: 3 hours
- Option B: 1-2 days
- Option C: Unknown (depends on issue complexity)

**Recommendation**: **Option C** (Accept limitations, move to Phase 2)
