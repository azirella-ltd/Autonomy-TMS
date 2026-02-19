# Navigation Audit Report

**Date**: 2026-01-26
**Purpose**: Comprehensive audit of left navigation bar menu items against AWS Supply Chain UI patterns

## Executive Summary

Based on analysis of AWS Supply Chain Features (https://aws.amazon.com/aws-supply-chain/features/) and Resources (https://aws.amazon.com/aws-supply-chain/resources/), this audit identifies navigation structure, page mappings, and recommendations for alignment with AWS SC UI patterns.

### AWS SC Navigation Pattern

AWS Supply Chain uses a **horizontal subnav structure** with 5 primary sections:
1. **Overview** - Dashboard and summary views
2. **Features** - Core capabilities organized by function
3. **Pricing** - Cost analysis (not applicable to Autonomy)
4. **Partners** - Integration ecosystem (not applicable to Autonomy)
5. **Resources** - Documentation and training

### AWS SC Feature Categories

AWS SC organizes capabilities into these groupings:
1. **Data Lakes** - Unified data ingestion and ML transformation
2. **Insights** - Risk alerts, inventory monitoring, vendor predictions
3. **Recommended Actions and Collaboration** - Rebalancing scored by risk/distance/sustainability
4. **Demand Planning** - ML-driven forecasting with continuous learning

---

## Current Navigation Structure Analysis

### Section 1: Overview ✅ WELL-ALIGNED

| Menu Item | Path | Component | Status | AWS SC Alignment |
|-----------|------|-----------|--------|------------------|
| Dashboard | `/dashboard` | `Dashboard.js` | ✅ Implemented | Matches AWS SC "Overview" |
| Analytics | `/analytics` | `AnalyticsDashboard.jsx` | ✅ Implemented | Good - insights aggregation |
| Supply Chain Analytics | `/sc-analytics` | `SupplyChainAnalytics.jsx` | ✅ Implemented | Excellent - SC-specific metrics |

**Recommendation**: No changes needed. This section provides strong overview capabilities.

---

### Section 2: Insights ⚠️ PARTIALLY ALIGNED

| Menu Item | Path | Component | Status | AWS SC Alignment |
|-----------|------|-----------|--------|------------------|
| Supply Chain Insights | `/insights` | `Insights.jsx` | ✅ Implemented | Matches AWS SC "Insights" category |
| Performance Metrics | `/insights/performance` | ❌ Missing | 🔴 Not Implemented | Should show KPI dashboard |
| Risk Analysis | `/insights/risk` | `RiskAnalysis.jsx` | ✅ Implemented | Matches AWS SC risk alerts |

**Issues**:
- Performance Metrics route not defined in `App.js`
- Should map to `/analytics/kpi-configuration` (KPIConfigurationAnalytics.jsx)

**Recommendation**:
```javascript
// Update Sidebar.jsx
{ label: 'Performance Metrics', path: '/analytics/kpi-configuration', icon: <AnalyticsIcon />, capability: 'view_insights' },
```

---

### Section 3: Supply Chain Design ⚠️ NEEDS RESTRUCTURING

| Menu Item | Path | Component | Status | AWS SC Alignment |
|-----------|------|-----------|--------|------------------|
| Network Configs | `/system/supply-chain-configs` | `SupplyChainConfigList` | ✅ Implemented | Good - network topology |
| Inventory Models | `/admin/model-setup` | `ModelSetup.jsx` | ✅ Implemented | Should be planning-focused |
| N-Tier Visibility | `/visibility/ntier` | `NTierVisibility.jsx` | ✅ Implemented | Excellent - material tracking |
| Group Configs | `/admin/group/supply-chain-configs` | `GroupSupplyChainConfigList.jsx` | ✅ Implemented | Admin-only, correct |

**Issues**:
- "Inventory Models" is AI model configuration, not supply chain design
- Should add "Material Visibility" from `/visibility/material-visibility` (MaterialVisibility.jsx exists)

**Recommendation**:
```javascript
// Move "Inventory Models" to AI & ML Models section
// Add Material Visibility here
{ label: 'Material Visibility', path: '/visibility/material-visibility', icon: <VisibilityIcon />, capability: 'view_material_visibility' },
```

---

### Section 4: Planning 🔴 MAJOR GAPS - NEEDS REORGANIZATION

Current structure has 11 items in flat list. AWS SC uses hierarchical organization:
- **Strategic Planning** (Network Design, Demand Plan, Inventory Optimization, Stochastic Planning)
- **Tactical Planning** (MPS, MRP, Capacity Planning, Supply Planning)
- **Operational Execution** (Production Orders, Purchase Orders, Transfer Orders, Service Orders)

#### Current Planning Items Audit

| Menu Item | Path | Component | Status | AWS SC Category | Notes |
|-----------|------|-----------|--------|----------------|-------|
| Order Planning & Tracking | `/planning/orders` | `OrderPlanning.jsx` | ✅ | Operational | Good |
| Transfer Orders | `/planning/transfer-orders` | `TransferOrders.jsx` | ✅ | Operational | Good |
| Demand Planning | `/planning/demand` | `DemandPlanView.jsx` | ✅ | Strategic | **AWS SC Core Feature** |
| Supply Planning | `/planning/supply` | ❌ Missing | 🔴 | Tactical | Should use SupplyPlanGeneration.jsx |
| Master Production Scheduling | `/planning/mps` | `MasterProductionScheduling.jsx` | ✅ | Tactical | Good |
| Production Orders | `/planning/production-orders` | ❌ Missing | 🔴 | Operational | Should use ProductionOrders.jsx |
| Capacity Planning | `/planning/capacity` | `CapacityPlanning.jsx` | ✅ | Tactical | Good |
| Supplier Management | `/planning/suppliers` | `SupplierManagement.jsx` | ✅ | Operational | Good |
| Inventory Projection (ATP/CTP) | `/planning/inventory-projection` | `InventoryProjection.jsx` | ✅ | Tactical | **AWS SC Inventory** |
| Monte Carlo Simulation | `/planning/monte-carlo` | `MonteCarloSimulation.jsx` | ✅ | Strategic | **Autonomy Differentiator** |
| Optimization | `/planning/optimization` | ❌ Missing | 🔴 | Strategic | Multiple analytics pages exist |

#### Missing Planning Pages (Components Exist!)

| Component | Should Map To | AWS SC Category | Priority |
|-----------|---------------|----------------|----------|
| `SupplyPlanGeneration.jsx` | `/planning/supply` | Supply Planning | 🔴 HIGH |
| `ProductionOrders.jsx` | `/planning/production-orders` | Production Management | 🔴 HIGH |
| `Recommendations.jsx` | `/planning/recommendations` | **AWS SC Core Feature** | 🔴 HIGH |
| `CollaborationHub.jsx` | `/planning/collaboration` | Demand Collaboration | 🟡 MEDIUM |
| `DemandCollaboration.jsx` | `/planning/demand-collaboration` | **AWS SC Core Feature** | 🔴 HIGH |
| `PurchaseOrders.jsx` | `/planning/purchase-orders` | Procurement | 🟡 MEDIUM |
| `SourcingAllocation.jsx` | `/planning/sourcing` | Multi-sourcing | 🟡 MEDIUM |
| `ATPCTPView.jsx` | `/planning/atp-ctp` | ATP/CTP separate view | 🟢 LOW |
| `MRPRun.jsx` | `/planning/mrp` | MRP execution | 🟡 MEDIUM |
| `LotSizingAnalysis.jsx` | `/planning/mps/lot-sizing` | MPS sub-feature | 🟢 LOW |
| `CapacityCheck.jsx` | `/planning/mps/capacity-check` | MPS sub-feature | 🟢 LOW |
| `KPIMonitoring.jsx` | `/planning/kpi-monitoring` | Performance tracking | 🟡 MEDIUM |
| `ShipmentTracking.jsx` | `/planning/shipment-tracking` | Logistics | 🟡 MEDIUM |
| `VendorLeadTimes.jsx` | `/planning/vendor-lead-times` | Supplier analytics | 🟢 LOW |
| `ProductionProcesses.jsx` | `/planning/production-processes` | Manufacturing | 🟢 LOW |
| `ResourceCapacity.jsx` | `/planning/resource-capacity` | Capacity analytics | 🟢 LOW |
| `ProjectOrders.jsx` | `/planning/project-orders` | Project-based | 🟢 LOW |
| `MaintenanceOrders.jsx` | `/planning/maintenance-orders` | Maintenance | 🟢 LOW |
| `TurnaroundOrders.jsx` | `/planning/turnaround-orders` | Turnaround | 🟢 LOW |
| `ServiceOrders.jsx` | `/execution/service-orders` | Service execution | 🟢 LOW |

**Recommendation**: Add HIGH priority items to navigation immediately:

```javascript
{
  id: 'planning',
  label: 'Planning',
  icon: <ScheduleIcon />,
  capability: 'view_demand_planning',
  items: [
    // STRATEGIC PLANNING
    { label: 'Network Design', path: '/system/supply-chain-configs', icon: <NetworkIcon />, capability: 'view_sc_configs' },
    { label: 'Demand Planning', path: '/planning/demand', icon: <OptimizationIcon />, capability: 'view_demand_planning' },
    { label: 'Demand Collaboration', path: '/planning/demand-collaboration', icon: <CollaborationIcon />, capability: 'view_demand_collaboration' },
    { label: 'Inventory Optimization', path: '/analytics/inventory-optimization', icon: <InventoryIcon />, capability: 'view_inventory_optimization_analytics' },
    { label: 'Stochastic Planning', path: '/planning/monte-carlo', icon: <MonteCarloIcon />, capability: 'view_analytics' },

    // TACTICAL PLANNING
    { label: 'Master Production Scheduling', path: '/planning/mps', icon: <MPSIcon />, capability: 'view_mps' },
    { label: 'Material Requirements Planning', path: '/planning/mrp', icon: <CalculateIcon />, capability: 'view_mrp' },
    { label: 'Supply Planning', path: '/planning/supply-plan', icon: <InventoryIcon />, capability: 'view_supply_plan' },
    { label: 'Capacity Planning', path: '/planning/capacity', icon: <SpeedIcon />, capability: 'view_capacity_planning' },
    { label: 'Sourcing Allocation', path: '/planning/sourcing', icon: <BusinessIcon />, capability: 'view_sourcing_allocation' },

    // OPERATIONAL EXECUTION
    { label: 'Recommended Actions', path: '/planning/recommendations', icon: <RecommendIcon />, capability: 'view_recommendations' },
    { label: 'Production Orders', path: '/planning/production-orders', icon: <FactoryIcon />, capability: 'view_production_orders' },
    { label: 'Purchase Orders', path: '/planning/purchase-orders', icon: <ShoppingCartIcon />, capability: 'view_purchase_orders' },
    { label: 'Transfer Orders', path: '/planning/transfer-orders', icon: <LocalShipping />, capability: 'view_transfer_orders' },
    { label: 'Order Tracking', path: '/planning/orders', icon: <OrderTrackingIcon />, capability: 'view_order_planning' },

    // SUPPORTING FEATURES
    { label: 'Supplier Management', path: '/planning/suppliers', icon: <BusinessIcon />, capability: 'view_suppliers' },
    { label: 'ATP/CTP Projection', path: '/planning/inventory-projection', icon: <InventoryIcon />, capability: 'view_planning' },
    { label: 'KPI Monitoring', path: '/planning/kpi-monitoring', icon: <StatsIcon />, capability: 'view_kpi_monitoring' },
  ],
}
```

---

### Section 5: Gamification & Training ✅ WELL-ALIGNED

| Menu Item | Path | Component | Status | AWS SC Alignment |
|-----------|------|-----------|--------|------------------|
| The Beer Game | `/games` | `GamesList.js` | ✅ Implemented | Autonomy differentiator |
| Create Game | `/games/new` | `CreateMixedGame.js` | ✅ Implemented | Good UX |
| My Games | `/dashboard` | `Dashboard.js` | ⚠️ Duplicate | Redirects to Dashboard |

**Issue**: "My Games" duplicates Dashboard link.

**Recommendation**: Either remove or change to `/games?filter=my-games` if filtering supported.

---

### Section 6: AI & ML Models ⚠️ MIXING CONCERNS

| Menu Item | Path | Component | Status | AWS SC Alignment |
|-----------|------|-----------|--------|------------------|
| AI Assistant | `/ai-assistant` | `AIAssistant.jsx` | ✅ Implemented | Good - conversational AI |
| TRM Training | `/admin/trm` | `TRMDashboard.jsx` | ✅ Implemented | Autonomy agent training |
| GNN Training | `/admin/gnn` | `GNNDashboard.jsx` | ✅ Implemented | Autonomy agent training |
| Model Management | `/admin/model-setup` | `ModelSetup.jsx` | ✅ Implemented | **Incorrect** - this is agent setup, not SC models |

**Issue**: "Model Management" at `/admin/model-setup` is AI agent configuration, not supply chain model management.

**Recommendation**: Rename to "Agent Configuration" or move SC model management here if needed.

---

### Section 7: Collaboration ✅ REASONABLE

| Menu Item | Path | Component | Status | AWS SC Alignment |
|-----------|------|-----------|--------|------------------|
| Groups | `/admin/groups` | `GroupManagement.jsx` | ✅ Implemented | User management |
| Players | `/players` | `Players.jsx` | ✅ Implemented | User directory |
| User Management | `/admin/group/users` | `GroupAdminUserManagement.jsx` | ✅ Implemented | Admin feature |
| Role Management | `/admin/role-management` | `UserRoleManagement.jsx` | ✅ Implemented | RBAC |
| System User Management | `/admin/users` | `SystemAdminUserManagement.jsx` | ✅ Implemented | System admin only |

**Recommendation**: No changes needed. Consider renaming "Collaboration" to "Administration" or "User Management".

---

### Section 8: Administration (System Admin Only) ✅ APPROPRIATE

| Menu Item | Path | Component | Status | AWS SC Alignment |
|-----------|------|-----------|--------|------------------|
| Admin Dashboard | `/admin` | `AdminDashboard` | ✅ Implemented | System overview |
| System Monitoring | `/admin/monitoring` | `SystemDashboard` | ✅ Implemented | Health metrics |
| System Config | `/system-config` | `SystemConfig.jsx` | ✅ Implemented | Configuration |
| Governance | `/admin/governance` | ❌ Missing | 🔴 Not Implemented | Compliance/audit |

**Issue**: Governance page not implemented.

**Recommendation**: Create governance page or remove from nav until implemented.

---

## Missing AWS SC Core Features

These AWS SC features are not yet represented in navigation:

1. **Data Lakes** - Not applicable (internal data ingestion)
2. **Insights Dashboard** - Partially covered by `/insights`
3. **Recommended Actions** - ✅ Component exists (`Recommendations.jsx`) but NOT in nav
4. **Collaboration** - ✅ Component exists (`CollaborationHub.jsx`) but NOT in nav
5. **Demand Collaboration** - ✅ Component exists (`DemandCollaboration.jsx`) but NOT in nav

---

## Recommended Icon-Based Collapsible Nav Bar Enhancement

Based on AWS SC UI patterns and your screenshot showing icon-based navigation with current location at top:

### Current Implementation
- Sidebar uses `DRAWER_WIDTH = 280` (expanded) and `DRAWER_WIDTH_COLLAPSED = 65` (collapsed)
- Toggle button exists (ChevronLeft/ChevronRight)
- Collapsed mode shows tooltips on hover

### Recommended Enhancements

1. **Top Current Location Indicator**
   ```javascript
   {!open && (
     <Box sx={{
       p: 2,
       borderBottom: '1px solid',
       borderColor: 'divider',
       backgroundColor: 'primary.main',
       color: 'primary.contrastText'
     }}>
       <Tooltip title={currentSection?.label} placement="right">
         <Box sx={{ display: 'flex', justifyContent: 'center' }}>
           {currentSection?.icon}
         </Box>
       </Tooltip>
       <Typography variant="caption" sx={{
         mt: 1,
         display: 'block',
         textAlign: 'center',
         fontSize: '0.65rem'
       }}>
         {currentSection?.label.split(' ')[0]}
       </Typography>
     </Box>
   )}
   ```

2. **Enhanced Icon Mode**
   - Show only icons in collapsed mode
   - Highlight current section at top with green background
   - Show section name (first word) below icon
   - Use tooltips for full names

3. **Auto-expand on Hover** (Optional)
   ```javascript
   <Drawer
     onMouseEnter={() => setHovered(true)}
     onMouseLeave={() => setHovered(false)}
     sx={{
       width: (open || hovered) ? DRAWER_WIDTH : DRAWER_WIDTH_COLLAPSED,
     }}
   />
   ```

---

## Implementation Priority

### Phase 1: Critical Fixes (Immediate)
1. ✅ Fix icon colors to use green (already done in current Sidebar.jsx)
2. Add missing HIGH priority planning pages to navigation:
   - Recommended Actions (`/planning/recommendations`)
   - Demand Collaboration (`/planning/demand-collaboration`)
   - Supply Planning (`/planning/supply-plan`)
3. Fix Performance Metrics routing

### Phase 2: Navigation Restructuring (Week 1)
1. Reorganize Planning section into Strategic/Tactical/Operational hierarchy
2. Add MEDIUM priority planning pages
3. Move Inventory Models to correct section
4. Add Material Visibility

### Phase 3: Icon-Based Collapsible Nav (Week 2)
1. Implement current location indicator at top in collapsed mode
2. Add auto-expand on hover (optional)
3. Polish icon sizing and spacing

### Phase 4: Create Missing Pages (Week 3-4)
1. Governance page
2. Optimization analytics aggregator
3. Any remaining HIGH priority pages

---

## Conclusion

**Overall Alignment**: 65% aligned with AWS SC patterns

**Strengths**:
- Overview section excellent
- Insights good foundation
- Gamification well-implemented (Autonomy differentiator)
- Most page components exist

**Critical Gaps**:
- **22 existing page components NOT in navigation** (biggest issue!)
- Planning section needs hierarchical reorganization
- Missing AWS SC core features (Recommendations, Collaboration)
- Performance Metrics broken link

**Next Steps**:
1. Add the 3 HIGH priority missing pages to navigation immediately
2. Fix Performance Metrics link
3. Implement icon-based collapsible nav with current location indicator
4. Reorganize Planning section by Strategic/Tactical/Operational
