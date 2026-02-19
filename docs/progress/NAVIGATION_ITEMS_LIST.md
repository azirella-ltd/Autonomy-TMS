# Complete Navigation Bar Items List

## Navigation Structure Overview

The left sidebar navigation is organized into **8 main categories** with a total of **33 navigation items** (some items are admin-only).

**AWS Supply Chain Integration**: The navigation has been enhanced with AWS SC-inspired items including Supply Chain Analytics, Insights, Order Planning & Tracking, N-Tier Visibility, and AI Assistant (Claude-powered).

---

## 1️⃣ Overview
**Category Icon**: Dashboard
**Category Capability**: `view_dashboard`

| # | Label | Path | Icon | Capability | Description |
|---|-------|------|------|------------|-------------|
| 1.1 | Dashboard | `/dashboard` | Dashboard | `view_dashboard` | Main user dashboard with game overview |
| 1.2 | Analytics | `/analytics` | Analytics | `view_analytics` | Analytics and reporting dashboard |
| 1.3 | Supply Chain Analytics | `/sc-analytics` | BarChart | `view_sc_analytics` | Comprehensive SC analytics and metrics |

---

## 2️⃣ Insights
**Category Icon**: Insights
**Category Capability**: `view_insights`

| # | Label | Path | Icon | Capability | Description |
|---|-------|------|------|------------|-------------|
| 2.1 | Supply Chain Insights | `/insights` | Insights | `view_insights` | AI-powered insights and recommendations |
| 2.2 | Performance Metrics | `/insights/performance` | Analytics | `view_insights` | Performance analytics and KPIs |
| 2.3 | Risk Analysis | `/insights/risk` | Assessment | `view_insights` | Risk assessment and mitigation |

---

## 3️⃣ Gamification
**Category Icon**: Games/Sports
**Category Capability**: `view_games`

| # | Label | Path | Icon | Capability | Description |
|---|-------|------|------|------------|-------------|
| 3.1 | The Beer Game | `/games` | Simulation | `view_games` | Browse and access Beer Game simulations |
| 3.2 | Create Game | `/games/new` | Extension | `create_game` | Create new game instance |
| 3.3 | My Games | `/dashboard` | Games | `view_games` | Quick link to user's active games |

---

## 4️⃣ Supply Chain Design
**Category Icon**: Network/Tree
**Category Capability**: `view_sc_configs`

| # | Label | Path | Icon | Capability | Description |
|---|-------|------|------|------------|-------------|
| 4.1 | Network Configs | `/system/supply-chain-configs` | Network | `view_sc_configs` | View and manage supply chain network configurations |
| 4.2 | Inventory Models | `/admin/model-setup` | Inventory | `view_inventory_models` | Configure inventory management models |
| 4.3 | N-Tier Visibility | `/visibility/ntier` | Visibility | `view_ntier_visibility` | Multi-tier supply chain visibility dashboard |
| 4.4 | Group Configs* | `/admin/group/supply-chain-configs` | Network | `view_group_configs` | Group-specific supply chain configurations (Admin only) |

*System Admin only

---

## 5️⃣ Order Planning & Optimization
**Category Icon**: LocalShipping
**Category Capability**: `view_demand_planning`

| # | Label | Path | Icon | Capability | Description |
|---|-------|------|------|------------|-------------|
| 5.1 | Order Planning & Tracking | `/planning/orders` | LocalShipping | `view_order_planning` | Track orders across supply chain network |
| 5.2 | Demand Planning | `/planning/demand` | Optimization | `view_demand_planning` | Demand forecasting and planning tools |
| 5.3 | Supply Planning | `/planning/supply` | Inventory | `view_supply_planning` | Supply planning and procurement |
| 5.4 | Optimization | `/planning/optimization` | Optimization | `view_optimization` | Supply chain optimization engine |

---

## 6️⃣ AI & ML Models
**Category Icon**: School/Training
**Category Capability**: `view_trm_training`

| # | Label | Path | Icon | Capability | Description |
|---|-------|------|------|------------|-------------|
| 6.1 | AI Assistant | `/ai-assistant` | SmartToy | `use_ai_assistant` | Claude-powered AI assistant (inspired by Amazon Q) |
| 6.2 | TRM Training | `/admin/trm` | Training | `view_trm_training` | Train Tiny Recursive Models (7M params) |
| 6.3 | GNN Training | `/admin/gnn` | Training | `view_gnn_training` | Train Graph Neural Networks (128M+ params) |
| 6.4 | Model Management | `/admin/model-setup` | Assessment | `view_model_setup` | Manage trained models and configurations |

---

## 7️⃣ Collaboration
**Category Icon**: People
**Category Capability**: `view_groups`

| # | Label | Path | Icon | Capability | Description |
|---|-------|------|------|------------|-------------|
| 7.1 | Groups | `/admin/groups` | People | `view_groups` | Manage organizational groups |
| 7.2 | Players | `/players` | People | `view_players` | View and manage game players |
| 7.3 | Role Management | `/admin/role-management` | AdminPanelSettings | `manage_permissions` | Assign roles and capabilities to users |
| 7.4 | User Management* | `/admin/users` | People | `view_users` | System-wide user management (Admin only) |

*System Admin only

---

## 8️⃣ Administration
**Category Icon**: Admin Panel Settings
**Category Capability**: `view_admin_dashboard`
**Visibility**: System Admin only

| # | Label | Path | Icon | Capability | Description |
|---|-------|------|------|------------|-------------|
| 8.1 | Admin Dashboard | `/admin` | Admin | `view_admin_dashboard` | System administration dashboard |
| 8.2 | System Monitoring | `/admin/monitoring` | Monitor Heart | `view_system_monitoring` | System health and performance monitoring |
| 8.3 | System Config | `/system-config` | Settings | `manage_system_config` | Global system configuration |
| 8.4 | Governance | `/admin/governance` | Account Balance | `view_governance` | Governance policies and compliance |

---

## Complete Navigation Tree

```
📊 Overview
   ├── Dashboard (/dashboard)
   ├── Analytics (/analytics)
   └── Supply Chain Analytics (/sc-analytics)

💡 Insights
   ├── Supply Chain Insights (/insights)
   ├── Performance Metrics (/insights/performance)
   └── Risk Analysis (/insights/risk)

🎮 Gamification
   ├── The Beer Game (/games)
   ├── Create Game (/games/new)
   └── My Games (/dashboard)

🔗 Supply Chain Design
   ├── Network Configs (/system/supply-chain-configs)
   ├── Inventory Models (/admin/model-setup)
   ├── N-Tier Visibility (/visibility/ntier)
   └── Group Configs* (/admin/group/supply-chain-configs)

🚚 Order Planning & Optimization
   ├── Order Planning & Tracking (/planning/orders)
   ├── Demand Planning (/planning/demand)
   ├── Supply Planning (/planning/supply)
   └── Optimization (/planning/optimization)

🤖 AI & ML Models
   ├── AI Assistant (/ai-assistant)
   ├── TRM Training (/admin/trm)
   ├── GNN Training (/admin/gnn)
   └── Model Management (/admin/model-setup)

👥 Collaboration
   ├── Groups (/admin/groups)
   ├── Players (/players)
   ├── Role Management (/admin/role-management)
   └── User Management* (/admin/users)

⚙️ Administration* (System Admin Only)
   ├── Admin Dashboard (/admin)
   ├── System Monitoring (/admin/monitoring)
   ├── System Config (/system-config)
   └── Governance (/admin/governance)

* Items marked with asterisk are System Admin only
```

---

## Navigation Item Count by User Type

### System Admin
- **Categories**: 8
- **Items**: 34 total
- **Full Access**: All categories and items visible

### Group Admin
- **Categories**: 7 (no Administration)
- **Items**: 30 total
- **Access**: Overview, Insights, Gamification, Supply Chain Design, Order Planning, AI/ML, Collaboration (including Role Management)
- **Restricted**: Cannot see Administration category, System-wide User Management

### Player
- **Categories**: 6
- **Items**: ~15 total
- **Access**: Overview, Insights (view only), Gamification (play only), Supply Chain (view only), Order Planning (view only)
- **Limited**: View-only access to most features, can only play games

---

## Path Reference (Alphabetical)

| Path | Label | Category | Admin Only |
|------|-------|----------|------------|
| `/admin` | Admin Dashboard | Administration | ✅ |
| `/admin/gnn` | GNN Training | AI & ML Models | - |
| `/admin/governance` | Governance | Administration | ✅ |
| `/admin/group/supply-chain-configs` | Group Configs | Supply Chain Design | ✅ |
| `/admin/groups` | Groups | Collaboration | - |
| `/admin/model-setup` | Inventory Models / Model Management | Supply Chain / AI & ML | - |
| `/admin/monitoring` | System Monitoring | Administration | ✅ |
| `/admin/trm` | TRM Training | AI & ML Models | - |
| `/admin/users` | User Management | Collaboration | ✅ |
| `/analytics` | Analytics | Overview | - |
| `/dashboard` | Dashboard / My Games | Overview / Gamification | - |
| `/games` | The Beer Game | Gamification | - |
| `/games/new` | Create Game | Gamification | - |
| `/planning/demand` | Demand Planning | Planning & Optimization | - |
| `/planning/optimization` | Optimization | Planning & Optimization | - |
| `/planning/supply` | Supply Planning | Planning & Optimization | - |
| `/players` | Players | Collaboration | - |
| `/system-config` | System Config | Administration | ✅ |
| `/system/supply-chain-configs` | Network Configs | Supply Chain Design | - |

---

## Top Navigation Bar

In addition to the left sidebar, there is a **top navigation bar** that includes:

### Left Side
- **Breadcrumbs** - Shows current location in hierarchy
  - Example: `Home > Games > The Beer Game`
  - Clickable navigation back through hierarchy

### Right Side
- **Help** (non-admin users) - Help documentation
- **Notifications** (non-admin users) - System notifications badge
- **User Menu** - Avatar/name dropdown with:
  - Profile
  - Settings
  - Logout

---

## Summary Statistics

| Metric | Count |
|--------|-------|
| **Total Categories** | 8 |
| **Total Navigation Items** | 34 |
| **Public Items** | 30 |
| **System Admin Only** | 4 |
| **Overview Items** | 3 |
| **Insights Items** | 3 |
| **Gamification Items** | 3 |
| **Supply Chain Design Items** | 4 |
| **Planning & Optimization Items** | 4 |
| **AI/ML Items** | 4 |
| **Collaboration Items** | 4 |
| **Administration Items** | 4 |

**AWS Supply Chain Integration**: Added 8 new navigation items inspired by AWS SC including Supply Chain Analytics, Insights dashboard, Order Planning & Tracking, N-Tier Visibility, and AI Assistant (Claude-powered).

---

## Icon Reference

| Icon Name | Material-UI Component | Used For |
|-----------|----------------------|----------|
| Dashboard | `DashboardIcon` | Overview, Dashboard |
| Analytics | `AnalyticsIcon` | Analytics |
| Games/Sports | `GamesIcon` | Gamification category, My Games |
| Simulation | `SimulationIcon` (ViewInAr) | The Beer Game |
| Extension | `ExtensionIcon` | Create Game |
| Network/Tree | `NetworkIcon` (AccountTree) | Supply Chain configs |
| Inventory | `InventoryIcon` | Inventory Models, Supply Planning |
| Trending Up | `TrendingUpIcon` | Planning category, Demand Planning |
| Optimization | `OptimizationIcon` | Optimization |
| Training/School | `TrainingIcon` (School) | AI & ML category, TRM/GNN Training |
| Assessment | `AssessmentIcon` | Model Management |
| People | `PeopleIcon` | Collaboration, Groups, Players, Users |
| Admin Panel | `AdminIcon` (AdminPanelSettings) | Administration |
| Monitor | `MonitoringIcon` (MonitorHeart) | System Monitoring |
| Settings | `SettingsIcon` | System Config |
| Governance | `GovernanceIcon` (AccountBalance) | Governance |

---

## Future Navigation Items (Placeholder Routes)

These routes exist in the navigation but may need implementation:

- `/analytics` - Analytics dashboard
- `/planning/demand` - Demand planning module
- `/planning/supply` - Supply planning module
- `/planning/optimization` - Optimization engine
- `/admin/governance` - Governance module

All other routes are fully implemented and functional.
