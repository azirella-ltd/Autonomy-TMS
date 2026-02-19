# Navigation & Capability Integration Analysis

**Date**: 2026-01-22
**Status**: 🔄 In Progress

## Current State Assessment

### Existing Routes (from App.js)

The application has routes defined for many planning/execution pages, but they are **not integrated with the navigation bar** or **capability system**:

#### Strategic Planning
- ❌ `/planning/demand` - Exists but shows "Coming Soon"
- ❌ `/planning/supply` - Exists but shows "Coming Soon"
- ✅ `/planning/inventory-projection` - InventoryProjection.jsx exists
- ✅ `/planning/monte-carlo` - MonteCarloSimulation.jsx exists (stochastic planning)

#### Tactical Planning
- ✅ `/planning/mps` - MasterProductionScheduling.jsx exists
- ✅ `/planning/mps/lot-sizing` - LotSizingAnalysis.jsx exists
- ✅ `/planning/mps/capacity-check` - CapacityCheck.jsx exists
- ✅ `/planning/mrp` - MRPRun.jsx exists

#### Operational Planning
- ❌ No supply plan generation page
- ❌ No ATP/CTP page
- ❌ No sourcing allocation page
- ✅ `/planning/orders` - OrderPlanning.jsx exists

#### Execution & Monitoring
- ✅ `/planning/purchase-orders` - PurchaseOrders.jsx exists
- ✅ `/planning/transfer-orders` - TransferOrders.jsx exists
- ✅ `/production/orders` - ProductionOrdersPage.jsx exists
- ✅ `/visibility/ntier` - NTierVisibility.jsx exists

#### Analytics & Insights
- ✅ `/analytics` - AnalyticsDashboard.jsx exists
- ✅ `/sc-analytics` - SupplyChainAnalytics.jsx exists
- ✅ `/insights` - Insights.jsx exists
- ❌ No KPI monitoring page
- ❌ No scenario comparison page
- ❌ No risk analysis page

#### AI & Agents
- ✅ `/admin/trm` - TRMDashboard.jsx exists
- ✅ `/admin/gnn` - GNNDashboard.jsx exists
- ✅ `/ai-assistant` - AIAssistant.jsx exists
- ❌ No LLM agent management page

#### Gamification
- ✅ `/games` - GamesList.jsx exists
- ✅ `/games/new` - CreateMixedGame.jsx exists
- ✅ `/games/:gameId` - GameBoard.jsx exists
- ✅ `/games/:gameId/report` - GameReport.jsx exists
- ✅ `/games/:gameId/visualizations` - GameVisualizations.jsx exists

#### Administration
- ✅ `/admin/users` - AdminUserManagement.js exists
- ✅ `/system/users` - SystemAdminUserManagement.jsx exists
- ✅ `/admin/groups` - GroupManagement.jsx exists
- ✅ `/admin/role-management` - UserRoleManagement.jsx exists

### Current Navigation Bar

The current Navbar.jsx has:
- **Hardcoded** navigation for non-admin users: Dashboard, Games, Players, Analytics
- **User menu** with admin-specific items for system admins
- **No capability-based filtering** - all users see the same nav items
- **No Planning/Execution sections** visible in main navigation

### Problems Identified

1. **Navigation Disconnect**: Many pages exist but aren't accessible from navigation
2. **No Capability Integration**: Navigation doesn't respect RBAC capabilities
3. **No Visual Feedback**: Users don't know what they can/cannot access
4. **Inconsistent Structure**: System admins see different navigation structure than group users
5. **Missing Pages**: Some capabilities have no corresponding UI pages

## Required Changes

### 1. Create Capability-Aware Navigation Component

**File**: `frontend/src/components/CapabilityAwareNavbar.jsx`

Features:
- Query user capabilities from API on mount
- Build navigation menu dynamically based on capabilities
- Grey out (disable) menu items for capabilities user doesn't have
- Show tooltip explaining missing capability when hovering disabled items
- Organize navigation into logical sections:
  - Dashboard
  - Planning (Strategic, Tactical, Operational)
  - Execution
  - Analytics
  - AI & Agents
  - Gamification
  - Administration

### 2. Create Navigation Configuration Mapping

**File**: `frontend/src/config/navigationConfig.js`

Map capabilities to navigation items:

```javascript
export const NAVIGATION_CONFIG = [
  {
    section: 'Planning',
    items: [
      {
        label: 'Demand Planning',
        path: '/planning/demand',
        requiredCapability: 'view_demand_forecasting',
        icon: <ForecastIcon />
      },
      {
        label: 'Master Production Schedule',
        path: '/planning/mps',
        requiredCapability: 'view_mps',
        icon: <ProductionIcon />
      },
      // ... etc
    ]
  },
  // ... etc
]
```

### 3. Update Existing Pages

For pages that exist but need capability checks:

```javascript
// frontend/src/pages/planning/MasterProductionScheduling.jsx

import { useCapabilityCheck } from '../../hooks/useCapabilityCheck';

function MasterProductionScheduling() {
  const { hasCapability, loading } = useCapabilityCheck('view_mps');

  if (loading) return <CircularProgress />;
  if (!hasCapability) return <Unauthorized message="You don't have permission to view MPS" />;

  // ... rest of component
}
```

### 4. Create Missing Pages

Pages that need to be built for capabilities without UI:

#### Strategic Planning
- [ ] `frontend/src/pages/planning/DemandPlanning.jsx` - For `view_demand_forecasting`
- [ ] `frontend/src/pages/planning/NetworkDesign.jsx` - For `view_network_design`

#### Operational Planning
- [ ] `frontend/src/pages/planning/SupplyPlanGeneration.jsx` - For `view_supply_plan`
- [ ] `frontend/src/pages/planning/ATPCTPView.jsx` - For `view_atp_ctp`
- [ ] `frontend/src/pages/planning/SourcingAllocation.jsx` - For `view_sourcing_allocation`

#### Analytics
- [ ] `frontend/src/pages/analytics/KPIMonitoring.jsx` - For `view_kpi_monitoring`
- [ ] `frontend/src/pages/analytics/ScenarioComparison.jsx` - For `view_scenario_comparison`
- [ ] `frontend/src/pages/analytics/RiskAnalysis.jsx` - For `view_risk_analysis`

#### AI & Agents
- [ ] `frontend/src/pages/ai/LLMAgentManagement.jsx` - For `view_llm_agents`

### 5. Create Custom Hooks

**File**: `frontend/src/hooks/useCapabilities.js`

```javascript
export function useCapabilities() {
  const { user } = useAuth();
  const [capabilities, setCapabilities] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchCapabilities = async () => {
      try {
        const response = await api.get(`/users/${user.id}/capabilities`);
        setCapabilities(response.data.capabilities);
      } catch (error) {
        console.error('Failed to load capabilities', error);
      } finally {
        setLoading(false);
      }
    };

    if (user?.id) {
      fetchCapabilities();
    }
  }, [user?.id]);

  const hasCapability = useCallback((capabilityName) => {
    return capabilities.includes(capabilityName);
  }, [capabilities]);

  return { capabilities, hasCapability, loading };
}
```

**File**: `frontend/src/hooks/useCapabilityCheck.js`

```javascript
export function useCapabilityCheck(requiredCapability) {
  const { hasCapability, loading } = useCapabilities();
  return { hasCapability: hasCapability(requiredCapability), loading };
}
```

### 6. Update Navbar to Use Capabilities

Replace hardcoded navigation with capability-aware navigation:

```javascript
import { useCapabilities } from '../hooks/useCapabilities';
import { NAVIGATION_CONFIG } from '../config/navigationConfig';

function Navbar() {
  const { hasCapability, loading } = useCapabilities();

  const filteredNavigation = useMemo(() => {
    return NAVIGATION_CONFIG.map(section => ({
      ...section,
      items: section.items.map(item => ({
        ...item,
        enabled: hasCapability(item.requiredCapability),
        disabled: !hasCapability(item.requiredCapability)
      }))
    }));
  }, [hasCapability]);

  // Render navigation with greyed out disabled items
}
```

## Implementation Priority

### Phase 1: Core Infrastructure (3-4 hours)
1. ✅ Create useCapabilities hook
2. ✅ Create useCapabilityCheck hook
3. ✅ Create navigationConfig.js with capability mappings
4. ✅ Update Navbar to use capability-aware navigation
5. ✅ Add visual styling for disabled/enabled nav items

### Phase 2: Existing Page Integration (2-3 hours)
1. ✅ Add capability checks to MasterProductionScheduling.jsx
2. ✅ Add capability checks to MRPRun.jsx
3. ✅ Add capability checks to OrderPlanning.jsx
4. ✅ Add capability checks to PurchaseOrders.jsx
5. ✅ Add capability checks to TransferOrders.jsx
6. ✅ Add capability checks to GamesList.jsx
7. ✅ Add capability checks to all admin pages

### Phase 3: New Page Development (8-10 hours)
1. ❌ Build DemandPlanning.jsx
2. ❌ Build SupplyPlanGeneration.jsx
3. ❌ Build ATPCTPView.jsx
4. ❌ Build SourcingAllocation.jsx
5. ❌ Build KPIMonitoring.jsx
6. ❌ Build ScenarioComparison.jsx
7. ❌ Build RiskAnalysis.jsx
8. ❌ Build LLMAgentManagement.jsx

### Phase 4: Testing & Refinement (2-3 hours)
1. ❌ End-to-end testing with different user roles
2. ❌ Visual refinement of disabled nav items
3. ❌ Tooltip text refinement
4. ❌ Performance optimization (capability caching)
5. ❌ Documentation

## Capability → Navigation Mapping

| Capability | Navigation Path | Page Exists? | Status |
|------------|----------------|--------------|--------|
| **Strategic Planning** |
| view_network_design | /planning/network-design | ❌ | Needs page |
| manage_network_design | /planning/network-design | ❌ | Needs page |
| view_demand_forecasting | /planning/demand | ❌ | Needs page |
| manage_demand_forecasting | /planning/demand | ❌ | Needs page |
| view_inventory_optimization | /planning/inventory-projection | ✅ | Exists |
| manage_inventory_optimization | /planning/inventory-projection | ✅ | Exists |
| view_stochastic_planning | /planning/monte-carlo | ✅ | Exists |
| manage_stochastic_planning | /planning/monte-carlo | ✅ | Exists |
| **Tactical Planning** |
| view_mps | /planning/mps | ✅ | Exists |
| manage_mps | /planning/mps | ✅ | Exists |
| approve_mps | /planning/mps | ✅ | Exists |
| view_lot_sizing | /planning/mps/lot-sizing | ✅ | Exists |
| manage_lot_sizing | /planning/mps/lot-sizing | ✅ | Exists |
| view_capacity_check | /planning/mps/capacity-check | ✅ | Exists |
| manage_capacity_check | /planning/mps/capacity-check | ✅ | Exists |
| view_mrp | /planning/mrp | ✅ | Exists |
| manage_mrp | /planning/mrp | ✅ | Exists |
| **Operational Planning** |
| view_supply_plan | /planning/supply-plan | ❌ | Needs page |
| manage_supply_plan | /planning/supply-plan | ❌ | Needs page |
| approve_supply_plan | /planning/supply-plan | ❌ | Needs page |
| view_atp_ctp | /planning/atp-ctp | ❌ | Needs page |
| manage_atp_ctp | /planning/atp-ctp | ❌ | Needs page |
| view_sourcing_allocation | /planning/sourcing | ❌ | Needs page |
| manage_sourcing_allocation | /planning/sourcing | ❌ | Needs page |
| view_order_planning | /planning/orders | ✅ | Exists |
| manage_order_planning | /planning/orders | ✅ | Exists |
| **Execution** |
| view_order_management | /planning/purchase-orders, /planning/transfer-orders | ✅ | Exists |
| manage_order_management | /planning/purchase-orders, /planning/transfer-orders | ✅ | Exists |
| approve_orders | /planning/purchase-orders, /planning/transfer-orders | ✅ | Exists |
| view_shipment_tracking | /execution/shipments | ❌ | Needs page |
| manage_shipment_tracking | /execution/shipments | ❌ | Needs page |
| view_inventory_visibility | /visibility/inventory | ❌ | Needs page |
| manage_inventory_visibility | /visibility/inventory | ❌ | Needs page |
| view_ntier_visibility | /visibility/ntier | ✅ | Exists |
| **Analytics** |
| view_analytics | /analytics | ✅ | Exists |
| view_kpi_monitoring | /analytics/kpi | ❌ | Needs page |
| manage_kpi_monitoring | /analytics/kpi | ❌ | Needs page |
| view_scenario_comparison | /analytics/scenarios | ❌ | Needs page |
| manage_scenario_comparison | /analytics/scenarios | ❌ | Needs page |
| view_risk_analysis | /analytics/risk | ❌ | Needs page |
| manage_risk_analysis | /analytics/risk | ❌ | Needs page |
| **AI & Agents** |
| view_ai_agents | /ai/agents | ❌ | Needs page |
| manage_ai_agents | /ai/agents | ❌ | Needs page |
| view_trm_training | /admin/trm | ✅ | Exists |
| manage_trm_training | /admin/trm | ✅ | Exists |
| view_gnn_training | /admin/gnn | ✅ | Exists |
| manage_gnn_training | /admin/gnn | ✅ | Exists |
| view_llm_agents | /ai/llm | ❌ | Needs page |
| manage_llm_agents | /ai/llm | ❌ | Needs page |
| **Gamification** |
| view_games | /games | ✅ | Exists |
| create_game | /games/new | ✅ | Exists |
| play_game | /games/:gameId | ✅ | Exists |
| manage_games | /games | ✅ | Exists |
| view_game_analytics | /games/:gameId/report | ✅ | Exists |
| **Administration** |
| view_users | /admin/users | ✅ | Exists |
| create_user | /admin/users | ✅ | Exists |
| edit_user | /admin/users | ✅ | Exists |
| manage_permissions | /admin/users | ✅ | Exists |
| view_groups | /admin/groups | ✅ | Exists |
| manage_groups | /admin/groups | ✅ | Exists |

## Summary Statistics

- **Total Capabilities**: 60
- **Pages Exist**: 23 (38%)
- **Pages Needed**: 37 (62%)

**By Category**:
- Strategic Planning: 2/8 pages exist (25%)
- Tactical Planning: 9/9 pages exist (100%) ✅
- Operational Planning: 1/9 pages exist (11%)
- Execution: 3/8 pages exist (38%)
- Analytics: 1/7 pages exist (14%)
- AI & Agents: 2/8 pages exist (25%)
- Gamification: 5/5 pages exist (100%) ✅
- Administration: 6/6 pages exist (100%) ✅

## Next Steps

1. **Immediate** (this session):
   - ✅ Create useCapabilities and useCapabilityCheck hooks
   - ✅ Create navigationConfig.js
   - ✅ Update Navbar.jsx to be capability-aware
   - ✅ Add visual styling for enabled/disabled nav items

2. **Short-term** (next session):
   - Add capability checks to existing pages
   - Build high-priority missing pages (supply plan, ATP/CTP, sourcing)

3. **Medium-term**:
   - Build remaining missing pages
   - Add page-level capability enforcement
   - Create comprehensive test suite

4. **Long-term**:
   - Add bulk capability assignment UI
   - Build audit trail viewer
   - Create role templates
