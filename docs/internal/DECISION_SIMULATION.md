# Decision Simulation Extension

## Overview

The decision simulation extension enables agents and humans to propose actions that require approval, simulate business impact in child scenarios, and present approval-ready business cases with probabilistic metrics.

**Key Insight**: The scenario concept supports all levels of the planning hierarchy - from strategic (network redesign, acquisitions) to tactical (inventory policies, sourcing rules) to operational (expedite requests, emergency purchases). The same proposal → simulate → approve workflow applies across all levels, with fewer degrees of freedom at execution time.

## Architecture

### Database Schema

Three new tables extend the scenario branching foundation:

**1. decision_proposals**
- Tracks proposed actions awaiting approval
- Links to child scenario (simulation environment)
- Stores business case and impact metrics
- Status: pending → approved/rejected → executed

**2. authority_definitions**
- Defines authority levels for agents/humans
- Specifies which actions require approval and from whom
- Hierarchical overrides: Agent-specific > Role-based > Config-wide > Group-wide

**3. business_impact_snapshots**
- Stores computed probabilistic balanced scorecard metrics
- Preserves before/after/comparison snapshots for audit trail
- Financial, customer, operational, strategic metrics with P10/P50/P90

### Business Impact Calculation Service

**File**: `backend/app/services/business_impact_service.py`

**Core Methods**:

1. **compute_business_impact()**
   - Runs probabilistic simulation comparing parent vs child scenario
   - Computes balanced scorecard metrics using Monte Carlo (1000 runs)
   - Generates business case with recommendation

2. **approve_proposal()**
   - Approves proposal and optionally commits child scenario to parent
   - Executes proposed changes and updates baseline

3. **reject_proposal()**
   - Rejects proposal and optionally deletes child scenario
   - Preserves audit trail of rejected proposals

**Probabilistic Balanced Scorecard**:

- **Financial**: total_cost, revenue, roi (P10/P50/P90)
- **Customer**: otif, fill_rate, backlog_value (distributions)
- **Operational**: inventory_turns, dos, cycle_time, bullwhip_ratio
- **Strategic**: flexibility_score, supplier_reliability, co2_emissions

**Business Case Generation**:
- Executive summary with improvement probability
- Key findings (cost, service level, inventory impacts)
- Recommendation (APPROVE / APPROVE WITH CAUTION / REJECT)
- Risk summary (downside exposure in P10 scenarios)

### API Endpoints

**File**: `backend/app/api/endpoints/supply_chain_config.py` (lines 2425+)

**Endpoints**:

1. `POST /supply-chain-configs/{config_id}/proposals` - Create proposal
2. `GET /supply-chain-configs/{config_id}/proposals` - List proposals (with status filter)
3. `GET /supply-chain-configs/proposals/{proposal_id}` - Get proposal details
4. `POST /supply-chain-configs/proposals/{proposal_id}/compute-impact` - Run simulation
5. `POST /supply-chain-configs/proposals/{proposal_id}/approve` - Approve and commit
6. `POST /supply-chain-configs/proposals/{proposal_id}/reject` - Reject and rollback

### Frontend Components

**File**: `frontend/src/components/supply-chain-config/DecisionProposalManager.jsx`

**Features**:
- List proposals with status filtering (all / pending / approved / rejected / executed)
- Create proposal dialog with action type selection
- Compute business impact button (runs probabilistic simulation)
- View business case with financial/operational/strategic metrics
- Approve/reject workflow with authority checks
- Probabilistic metrics visualization (P10/P50/P90 with trend indicators)

**Integration**: Added to ScenarioTreeManager page as second tab (Scenario Tree | Decision Proposals)

## Workflow

### 1. Create Proposal

Agent or human identifies a change that requires approval:
- **Strategic**: Network redesign, acquisition scenario, operating model change
- **Tactical**: Safety stock adjustment, sourcing rule change, capacity expansion
- **Operational**: Expedite shipment, emergency purchase, allocation override

```javascript
POST /supply-chain-configs/{config_id}/proposals
{
  "title": "Expedite shipment from Asia",
  "description": "Customer demand spike requires expedited air freight",
  "action_type": "expedite",
  "action_params": {"lane_id": 42, "quantity": 5000},
  "proposed_by": "agent_atp_001",
  "proposed_by_type": "agent"
}
```

### 2. Simulate Impact

System creates child scenario and runs planning workflows to compute business impact:

```javascript
POST /supply-chain-configs/proposals/{proposal_id}/compute-impact
{
  "planning_horizon": 52,
  "simulation_runs": 1000
}
```

**Algorithm**:
1. Get effective configurations (parent baseline vs child with changes)
2. Run planning workflows (ATP/CTP/MRP) for both scenarios
3. Compute probabilistic metrics using stochastic sampler
4. Generate comparative business case with P10/P50/P90 distributions

### 3. Review Business Case

Decision maker reviews probabilistic impact:

```json
{
  "business_case": {
    "summary": "Analysis shows improvement in 8/12 key metrics. Expected cost increase: $12,500. Expected service level improvement: +3.2%.",
    "recommendation": "APPROVE WITH CAUTION - Moderate positive impact, monitor cost risks",
    "key_findings": [
      "Total cost expected to increase by $12,500 (P50)",
      "Fill rate expected to improve by 3.2%",
      "Inventory turns expected to increase by 0.8"
    ],
    "risks": [
      "High cost risk: P10 scenario shows $25,000 increase",
      "Low risk - minimal downside exposure on service level"
    ]
  },
  "financial_impact": {
    "total_cost": {"p10": 25000, "p50": 12500, "p90": 5000},
    "revenue": {"p10": 180000, "p50": 195000, "p90": 210000},
    "roi": {"p10": 0.05, "p50": 0.12, "p90": 0.18}
  },
  "operational_impact": {
    "fill_rate": {"p10": 0.88, "p50": 0.932, "p90": 0.97},
    "inventory_turns": {"p10": 11.2, "p50": 12.8, "p90": 14.5}
  },
  "improvement_probability": {
    "customer.fill_rate": 0.89,
    "operational.inventory_turns": 0.76,
    "financial.total_cost": 0.32
  }
}
```

### 4. Approve or Reject

**Approve**:
```javascript
POST /supply-chain-configs/proposals/{proposal_id}/approve
{
  "approved_by": "manager_001",
  "commit_to_parent": true  // Commits child scenario to parent baseline
}
```

**Reject**:
```javascript
POST /supply-chain-configs/proposals/{proposal_id}/reject
{
  "rejected_by": "manager_001",
  "reason": "Cost increase too high relative to service improvement",
  "delete_scenario": true  // Deletes child scenario (keeps audit trail)
}
```

## Use Cases

### Strategic: Network Redesign

**Scenario**: Add new distribution center in Midwest

**Proposal**:
- Action Type: `network_redesign`
- Action Params: `{new_dc_location: "Chicago", capacity: 10000, capex: 5000000}`

**Business Impact**:
- Financial: $5M capex, $200K annual operating cost, $300K logistics savings → ROI = 6.7%
- Customer: OTIF +5%, lead time -2 days
- Strategic: Flexibility +15 points, supplier diversification +2 sources

**Approval Authority**: VP Supply Chain or higher

### Tactical: Safety Stock Adjustment

**Scenario**: Increase safety stock for high-demand SKU

**Proposal**:
- Action Type: `increase_safety_stock`
- Action Params: `{product_id: "SKU-1234", current_ss: 500, proposed_ss: 750}`

**Business Impact**:
- Financial: Inventory holding cost +$12K/year, stockout cost -$45K/year → Net savings $33K
- Customer: Fill rate 92% → 97%
- Operational: DOS 30 → 38 days, inventory turns 12 → 11

**Approval Authority**: Planner (if < $50K), Manager (if > $50K)

### Operational: Expedite Shipment

**Scenario**: Air freight instead of ocean freight due to demand spike

**Proposal**:
- Action Type: `expedite`
- Action Params: `{lane_id: 42, quantity: 5000, original_lead_time: 21, new_lead_time: 3}`

**Business Impact**:
- Financial: Expedite cost +$15K, stockout cost avoided -$60K → Net savings $45K
- Customer: Fill rate maintained at 95% (vs 78% without expedite)
- Strategic: CO2 emissions +500 tons

**Approval Authority**: Agent (if < $10K), Manager (if > $10K)

## Authority Framework

### Authority Levels

1. **Agent Autonomous** (no approval required)
   - Actions below threshold (e.g., < $10K)
   - Standard operational decisions within bounds

2. **Manager Approval**
   - Medium-impact decisions ($10K - $100K)
   - Tactical changes affecting single product/node

3. **Director Approval**
   - High-impact decisions ($100K - $1M)
   - Multi-node tactical changes
   - Short-term strategic adjustments

4. **VP Approval**
   - Very high-impact decisions (> $1M)
   - Network-wide strategic changes
   - Acquisitions, major expansions

### Authority Definitions Example

```sql
INSERT INTO authority_definitions (
  customer_id, agent_id, action_type, max_value, requires_approval, approval_authority
) VALUES
  (1, 'agent_atp_001', 'expedite', 10000, false, null),          -- Autonomous < $10K
  (1, 'agent_atp_001', 'expedite', 100000, true, 'manager'),     -- Manager approval $10K-$100K
  (1, null, 'network_redesign', null, true, 'vp'),               -- VP approval for network changes
  (1, null, 'increase_safety_stock', 50000, true, 'manager');    -- Manager approval for safety stock > $50K
```

## Integration with Planning Workflows

**Phase 1 (Current)**: Simplified simulation using config entities
- Estimates metrics based on node/lane/market counts
- Monte Carlo randomness for probability distributions
- ~5-10 second computation time

**Phase 2 (Future)**: Full planning workflow integration
- Run AWS SC planning workflows (ATP/CTP/MRP) in child scenario
- Use stochastic sampler for operational variables (lead times, yields, demand)
- Compare parent vs child supply plans with full probabilistic propagation
- ~30-60 second computation time with parallel simulation

## Benefits

1. **Risk-Free Experimentation**: Test changes in child scenarios without affecting baseline

2. **Data-Driven Decisions**: Probabilistic metrics replace gut feel with quantified trade-offs

3. **Audit Trail**: Full history of proposals, business cases, and approval decisions

4. **Agent Autonomy**: Agents can propose and test changes, escalating to humans only when needed

5. **Human-AI Collaboration**: AI generates proposals and business cases, humans make final decisions

6. **Multi-Level Planning**: Same workflow works for strategic, tactical, and operational decisions

7. **Compliance**: Authority definitions enforce approval workflows and prevent unauthorized changes

## Future Enhancements

### Phase 2: Full Planning Integration
- Integrate with AWS SC planning workflows (demand → targets → requirements)
- Use stochastic sampler for operational variables
- Multi-product, multi-BOM scenario simulation
- Capacity constraint checking (ATP/CTP)

### Phase 3: Advanced Business Cases
- Sensitivity analysis (which variables drive the most impact?)
- What-if scenarios (optimistic/pessimistic cases)
- Monte Carlo variance reduction techniques
- Machine learning for business case quality prediction

### Phase 4: Authority & Approval Workflows
- Role-based access control integration
- Email/Slack notifications for pending approvals
- Approval delegation and escalation rules
- Batch approval for similar proposals

### Phase 5: Agent Learning from Decisions
- Track approval/rejection patterns
- Train agents to propose higher-quality changes
- Learn authority boundaries dynamically
- Improve business case generation using historical data

## Testing

### Manual Testing

1. Create scenario branch (TBG Root → Test Branch)
2. Navigate to Scenarios tab → Decision Proposals
3. Click "Create Proposal"
4. Fill in title, description, action type
5. Click "Compute Impact" → Wait for simulation (5-10 seconds)
6. Review business case (financial, operational, strategic metrics)
7. Click "Approve" → Child scenario commits to parent
8. Verify parent config updated with changes

### Automated Testing

```bash
# Run backend tests
cd backend
pytest tests/test_business_impact_service.py
pytest tests/test_decision_proposals.py

# Test API endpoints
curl -X POST http://localhost:8000/api/supply-chain-configs/1/proposals \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Proposal", "action_type": "expedite", ...}'

curl -X POST http://localhost:8000/api/supply-chain-configs/proposals/1/compute-impact \
  -H "Content-Type: application/json" \
  -d '{"planning_horizon": 52, "simulation_runs": 1000}'

curl -X POST http://localhost:8000/api/supply-chain-configs/proposals/1/approve \
  -H "Content-Type: application/json" \
  -d '{"approved_by": "user_001", "commit_to_parent": true}'
```

## Summary

The decision simulation extension transforms scenario branching from a configuration management tool into a comprehensive decision support system. By combining git-like branching with probabilistic business impact calculation and approval workflows, the system enables:

- **Safe experimentation** at all planning levels (strategic → tactical → operational)
- **Quantified trade-offs** with P10/P50/P90 distributions instead of point estimates
- **Human-AI collaboration** where agents own decisions and humans accept or override
- **Audit trail** preserving full history of decisions and business cases
- **Unified workflow** across all planning hierarchy levels with fewer degrees of freedom at execution time

This positions the platform for enterprise-grade supply chain planning with AI agents that operate within well-defined authority boundaries while maintaining human oversight for high-impact decisions.
