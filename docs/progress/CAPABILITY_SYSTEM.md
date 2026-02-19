# User Capability System Documentation

## Overview

The application now implements a **granular capability-based permission system** that controls what functionality each user can access. Capabilities determine both backend API permissions and frontend UI visibility - **users only see navigation items and features they have permission to use**.

## Key Concepts

### Capabilities
Fine-grained permission flags that grant access to specific functionality. Examples:
- `view_games` - Can view game list
- `create_game` - Can create new games
- `view_trm_training` - Can access TRM training dashboard
- `system_admin` - Master capability that grants all others

### User Types
Users are assigned one of three types, each with default capabilities:

1. **SYSTEM_ADMIN** - Full access to everything
2. **GROUP_ADMIN** - Manage games, groups, and users within their group
3. **PLAYER** - Play games and view basic information

##  Architecture

### Backend Components

**1. Capability Definitions** (`backend/app/core/capabilities.py`)
- Defines all capability flags as enums
- Provides predefined capability sets for each user type
- Maps capabilities to navigation items

**2. Capability Service** (`backend/app/services/capability_service.py`)
- `get_user_capabilities()` - Get all capabilities for a user
- `user_has_capability()` - Check if user has specific capability
- `get_filtered_navigation_for_user()` - Filter navigation by capabilities
- `get_user_capabilities_list()` - Get list of capability strings

**3. API Endpoints** (`backend/app/api/endpoints/capabilities.py`)
- `GET /api/v1/capabilities/me` - Get current user's capabilities
- `GET /api/v1/capabilities/navigation` - Get filtered navigation
- `GET /api/v1/capabilities/check/{path}` - Check access to specific path
- `POST /api/v1/capabilities/validate` - Validate multiple capabilities

### Frontend Components

**1. useCapabilities Hook** (`frontend/src/hooks/useCapabilities.js`)
- Fetches user capabilities from API
- Provides `hasCapability()`, `hasAnyCapability()`, `hasAllCapabilities()` functions
- Caches capabilities for performance

**2. Enhanced Sidebar** (`frontend/src/components/Sidebar.jsx`)
- Automatically filters navigation based on user capabilities
- Only shows categories and items user can access
- Real-time capability checking

## Capability List

### Overview & Dashboard
- `view_dashboard` - Access main dashboard
- `view_analytics` - Access analytics page
- `view_sc_analytics` - Access supply chain analytics (AWS SC-inspired)

### Insights (NEW - AWS SC Integration)
- `view_insights` - Access AI-powered insights dashboard
- `manage_insights` - Manage and configure insights

### Gamification
- `view_games` - View game list
- `create_game` - Create new games
- `play_game` - Play games
- `delete_game` - Delete games
- `manage_games` - Full game management

### Supply Chain Design
- `view_sc_configs` - View supply chain configs
- `create_sc_config` - Create new configs
- `edit_sc_config` - Edit existing configs
- `delete_sc_config` - Delete configs
- `view_inventory_models` - View inventory models
- `manage_inventory_models` - Manage inventory models
- `view_group_configs` - View group-specific configs
- `manage_group_configs` - Manage group configs
- `view_ntier_visibility` - Access N-tier visibility dashboard (AWS SC-inspired)

### Planning & Optimization
- `view_order_planning` - View order planning and tracking (AWS SC-inspired)
- `manage_order_planning` - Manage order planning
- `view_demand_planning` - View demand planning
- `manage_demand_planning` - Manage demand planning
- `view_supply_planning` - View supply planning
- `manage_supply_planning` - Manage supply planning
- `view_optimization` - View optimization results
- `run_optimization` - Run optimization

### AI & ML Models
- `use_ai_assistant` - Access Claude-powered AI assistant (inspired by Amazon Q)
- `view_trm_training` - View TRM training dashboard
- `start_trm_training` - Start TRM training
- `manage_trm_models` - Manage TRM models
- `view_gnn_training` - View GNN training dashboard
- `start_gnn_training` - Start GNN training
- `manage_gnn_models` - Manage GNN models
- `view_model_setup` - View model setup
- `manage_model_setup` - Manage model configuration

### Collaboration
- `view_groups` - View groups
- `create_group` - Create new groups
- `manage_groups` - Full group management
- `view_players` - View players
- `manage_players` - Manage players
- `view_users` - View users
- `create_user` - Create new users
- `edit_user` - Edit user information
- `delete_user` - Delete users

### Administration
- `view_admin_dashboard` - View admin dashboard
- `view_system_monitoring` - View system monitoring
- `manage_system_config` - Manage system configuration
- `view_governance` - View governance settings
- `manage_governance` - Manage governance
- `manage_permissions` - Manage user permissions

### System-Level
- `system_admin` - Master capability (grants all others)

## Default Capability Sets

### System Admin
```python
{
    "system_admin"  # Grants everything
}
```

### Group Admin
```python
{
    # Overview
    "view_dashboard",
    "view_analytics",
    "view_sc_analytics",

    # Insights
    "view_insights",

    # Gamification - Full access
    "view_games",
    "create_game",
    "play_game",
    "delete_game",
    "manage_games",

    # Supply Chain - View and manage group configs
    "view_sc_configs",
    "view_inventory_models",
    "view_group_configs",
    "manage_group_configs",
    "view_ntier_visibility",

    # Planning - View only
    "view_order_planning",
    "view_demand_planning",
    "view_supply_planning",
    "view_optimization",

    # AI/ML - View only + AI Assistant
    "use_ai_assistant",
    "view_trm_training",
    "view_gnn_training",
    "view_model_setup",

    # Collaboration - Full access within group
    "view_groups",
    "manage_groups",
    "view_players",
    "manage_players",
    "view_users",
    "create_user",
    "edit_user",
}
```

### Player
```python
{
    # Overview
    "view_dashboard",
    "view_analytics",

    # Insights - View only
    "view_insights",

    # Gamification - Play only
    "view_games",
    "play_game",

    # Supply Chain - View only
    "view_sc_configs",
    "view_ntier_visibility",

    # Planning - View only
    "view_order_planning",

    # Collaboration - View only
    "view_groups",
    "view_players",
}
```

## Usage Examples

### Backend - Check User Capability

```python
from app.services.capability_service import user_has_capability
from app.core.capabilities import Capability

# Check if user can create games
if user_has_capability(user, Capability.CREATE_GAME, db):
    # Allow game creation
    pass
else:
    raise HTTPException(status_code=403, detail="Not authorized")
```

### Backend - Get User Capabilities

```python
from app.services.capability_service import get_user_capabilities_list

# Get list of all user capabilities
capabilities = get_user_capabilities_list(user, db)
# Returns: ['view_dashboard', 'view_games', 'play_game', ...]
```

### Frontend - Check Capability in Component

```javascript
import { useCapabilities } from '../hooks/useCapabilities';

function GameCreationButton() {
  const { hasCapability } = useCapabilities();

  if (!hasCapability('create_game')) {
    return null; // Don't show button
  }

  return <Button>Create Game</Button>;
}
```

### Frontend - Check Multiple Capabilities

```javascript
import { useCapabilities } from '../hooks/useCapabilities';

function AdminPanel() {
  const { hasAnyCapability, hasAllCapabilities } = useCapabilities();

  // Check if user has any admin capability
  const canAccessAdmin = hasAnyCapability(
    'view_admin_dashboard',
    'manage_system_config'
  );

  // Check if user has all required capabilities
  const canManageSystem = hasAllCapabilities(
    'view_system_monitoring',
    'manage_system_config'
  );

  if (!canAccessAdmin) {
    return <AccessDenied />;
  }

  return <AdminDashboard canManage={canManageSystem} />;
}
```

## Navigation Filtering

The sidebar automatically filters navigation items based on user capabilities:

**System Admin sees**:
- All 7 categories
- All items within each category

**Group Admin sees**:
- Overview (Dashboard, Analytics)
- Gamification (The Beer Game, Create Game, My Games)
- Supply Chain Design (Network Configs, Inventory Models, Group Configs)
- Planning & Optimization (View only)
- AI & ML Models (View only)
- Collaboration (Groups, Players, Users)

**Player sees**:
- Overview (Dashboard only)
- Gamification (The Beer Game, My Games)
- Supply Chain Design (View only)
- Collaboration (View only)

## API Endpoints

### Get User Capabilities
```http
GET /api/v1/capabilities/me
Authorization: Bearer <token>

Response:
{
  "capabilities": [
    "view_dashboard",
    "view_games",
    "play_game"
  ],
  "user_type": "PLAYER"
}
```

### Get Filtered Navigation
```http
GET /api/v1/capabilities/navigation
Authorization: Bearer <token>

Response:
{
  "navigation": {
    "overview": {
      "category_capability": "view_dashboard",
      "items": {
        "/dashboard": ["view_dashboard"]
      }
    },
    "gamification": {
      "category_capability": "view_games",
      "items": {
        "/games": ["view_games"],
        "/games/new": ["create_game"]
      }
    }
  },
  "user_type": "GROUP_ADMIN"
}
```

### Check Path Access
```http
GET /api/v1/capabilities/check/admin/trm
Authorization: Bearer <token>

Response:
{
  "path": "/admin/trm",
  "allowed": true,
  "user_type": "GROUP_ADMIN"
}
```

### Validate Multiple Capabilities
```http
POST /api/v1/capabilities/validate
Authorization: Bearer <token>
Content-Type: application/json

[
  "create_game",
  "delete_game",
  "manage_system_config"
]

Response:
{
  "results": {
    "create_game": true,
    "delete_game": true,
    "manage_system_config": false
  },
  "user_type": "GROUP_ADMIN"
}
```

## Testing Capability System

### 1. Login as Different User Types

**System Admin**:
- Email: `systemadmin@autonomy.ai`
- Password: `Autonomy@2025`
- Should see: All 7 categories with all items

**Group Admin** (if created):
- Should see: 6 categories (no Administration)
- Should see: Restricted items in some categories

**Player**:
- Should see: Limited categories and items
- Should NOT see: Admin features, training dashboards, user management

### 2. Check Navigation Visibility

1. Log in with different users
2. Observe sidebar navigation
3. Verify only permitted items are visible
4. Attempt to access restricted URLs directly (should be blocked or show access denied)

### 3. Verify API Responses

```bash
# Get capabilities
curl -X GET http://172.29.20.187:8088/api/v1/capabilities/me \
  -H "Authorization: Bearer <token>"

# Get filtered navigation
curl -X GET http://172.29.20.187:8088/api/v1/capabilities/navigation \
  -H "Authorization: Bearer <token>"

# Check specific path
curl -X GET http://172.29.20.187:8088/api/v1/capabilities/check/admin/trm \
  -H "Authorization: Bearer <token>"
```

## Future Enhancements

### 1. Custom Capability Sets
Allow admins to create custom capability sets beyond the three default user types:
- "Analytics Viewer" - Read-only access to analytics and reports
- "Game Manager" - Full game management without admin access
- "ML Engineer" - Access to model training but not system admin

### 2. Role-Based Assignment
Integrate with existing RBAC system:
- Assign capabilities via roles
- Role inheritance
- Temporal capabilities (expires after certain time)

### 3. UI for Managing Capabilities
Admin interface to:
- View all capabilities
- Assign/revoke capabilities for users
- Create custom capability sets
- Audit capability usage

### 4. Capability Caching
Improve performance:
- Cache capabilities in Redis
- Invalidate on user update
- Reduce database queries

### 5. Capability Analytics
Track capability usage:
- Which capabilities are most used
- Which users access which features
- Identify unused capabilities

## Migration from Old System

The capability system works alongside the existing user type system:

**Old System** → **New System**
- `user_type = SYSTEM_ADMIN` → Capability set with `system_admin`
- `user_type = GROUP_ADMIN` → Predefined GROUP_ADMIN_CAPABILITIES
- `user_type = PLAYER` → Predefined PLAYER_CAPABILITIES

No database migration required - capabilities are derived from user_type.

## Troubleshooting

### User Can't See Expected Navigation Items

1. **Check user capabilities**:
   ```javascript
   GET /api/v1/capabilities/me
   ```

2. **Verify capability requirements** in `backend/app/core/capabilities.py`:
   - Check `get_navigation_capabilities()`
   - Verify required capability for the item

3. **Check frontend filtering** in `Sidebar.jsx`:
   - Verify `hasCapability()` is working
   - Check console for errors

### API Returns 403 Forbidden

1. **Verify user has required capability**:
   ```python
   # In endpoint, add capability check
   if not user_has_capability(user, Capability.VIEW_GAMES, db):
       raise HTTPException(status_code=403, detail="Access denied")
   ```

2. **Check capability service logs**:
   - Backend logs should show capability checks
   - Verify correct user type

### Navigation Not Filtering

1. **Check useCapabilities hook**:
   - Verify API call succeeds
   - Check browser console for errors
   - Verify capabilities array is populated

2. **Check Sidebar implementation**:
   - Ensure `getNavigationStructure` receives `hasCapability`
   - Verify filtering logic in Sidebar component

## Files Reference

### Backend
- `backend/app/core/capabilities.py` - Capability definitions
- `backend/app/services/capability_service.py` - Capability checking utilities
- `backend/app/api/endpoints/capabilities.py` - API endpoints
- `backend/app/api/api_v1/api.py` - API router registration

### Frontend
- `frontend/src/hooks/useCapabilities.js` - Capability checking hook
- `frontend/src/components/Sidebar.jsx` - Capability-filtered navigation

## Summary

The capability system provides:

✅ **Granular control** - 50+ capability flags for fine-grained access control
✅ **Automatic filtering** - Navigation automatically filtered by user capabilities
✅ **User-friendly** - Users only see what they can access
✅ **Extensible** - Easy to add new capabilities and capability sets
✅ **API-driven** - Frontend queries backend for capabilities
✅ **Type-safe** - Strongly typed capabilities with enums
✅ **Performant** - Capabilities cached on frontend, minimal API calls
✅ **Secure** - Backend enforces permissions, frontend just hides UI

**Users now only see navigation items and features they have permission to use!**
