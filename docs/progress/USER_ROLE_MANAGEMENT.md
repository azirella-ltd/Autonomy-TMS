# User Role & Capability Management System

## Overview

The Beer Game now includes a comprehensive **User Role & Capability Management** interface that allows Group Admins to assign roles and customize capabilities for users within their group. This feature provides granular control over user permissions and access levels.

**Date**: January 2026
**Version**: 1.0

---

## Key Features

### 1. **Role-Based Management**
- Assign predefined role templates (Group Admin, Player, Game Manager, Analyst)
- Each role comes with a default set of capabilities
- Quick-apply templates for common use cases

### 2. **Granular Capability Control**
- 50+ individual capability flags across 7 categories
- Custom capability selection for specialized roles
- Real-time capability counting and tracking

### 3. **User-Friendly Interface**
- Three-tab layout: User Roles, Role Templates, Capability Reference
- Accordion-style capability selection by category
- Visual indicators for role and capability counts
- Searchable user table with filtering

### 4. **Access Control**
- Group Admins can only manage users within their group
- System Admins can manage all users (except other System Admins)
- Built-in safeguards prevent privilege escalation

---

## Access the Feature

**Navigation**: Collaboration → Role Management

**Path**: `/admin/role-management`

**Capability Required**: `manage_permissions` (Group Admin and above)

**URL**: http://172.29.20.187:8088/admin/role-management

---

## User Interface

### Tab 1: User Roles

**Purpose**: View and manage user roles and capabilities

**Features**:
- Summary cards showing total users, admins, players, and custom roles
- User table with columns:
  - Name (with admin badge for System Admins)
  - Email
  - Role (as chip)
  - Capabilities count
  - Status (Active/Inactive)
  - Actions (Edit button)

**User Actions**:
- Click "Edit" to open the Role Management Dialog
- View capability counts at a glance
- See role assignments with color-coded chips

---

### Tab 2: Role Templates

**Purpose**: Browse predefined role templates

**Available Templates**:

#### 1. Group Admin
- **Description**: Full access to group management and game creation
- **Capabilities**: 29 capabilities
- **Access**: Full gamification, supply chain view, planning view, AI tools, collaboration

#### 2. Player
- **Description**: Basic access to play games and view information
- **Capabilities**: 10 capabilities
- **Access**: View-only for most features, can play games

#### 3. Game Manager
- **Description**: Create and manage games without admin access
- **Capabilities**: 16 capabilities
- **Access**: Game creation, SC viewing, planning viewing, limited collaboration

#### 4. Analyst
- **Description**: View-only access with analytics and insights
- **Capabilities**: 18 capabilities
- **Access**: Full analytics, insights, SC visibility, planning visibility, ML model viewing

**Display**: Cards showing role name, description, and capability preview (10 visible + count of remaining)

---

### Tab 3: Capability Reference

**Purpose**: Complete documentation of all available capabilities

**Organization**: Accordion-style by category

**Categories**:
1. Overview & Dashboard (3 capabilities)
2. Insights (2 capabilities)
3. Gamification (5 capabilities)
4. Supply Chain Design (9 capabilities)
5. Planning & Optimization (8 capabilities)
6. AI & ML Models (9 capabilities)
7. Collaboration (9 capabilities)

**Display**: Grid layout with capability name, description, and ID (flag)

---

## Edit User Dialog

**Triggered By**: Clicking "Edit" button on a user

**Sections**:

### 1. Quick Apply Role Template
- **Purpose**: Rapidly assign a predefined role
- **Layout**: 4 button cards (2×2 grid)
- **Behavior**: Clicking a template applies that role's capabilities
- **Visual**: Selected template is highlighted

### 2. Custom Capability Selection
- **Purpose**: Fine-tune capabilities beyond templates
- **Organization**: Accordions by category
- **Display**: Checkboxes for each capability with description
- **Counter**: Shows "X selected" at top
- **Per-Category Counter**: Shows "X/Y" capabilities selected in each category

**Actions**:
- **Cancel**: Close dialog without saving
- **Save Changes**: Apply role and capabilities to user

---

## Capability Categories

### 1. Overview & Dashboard
- `view_dashboard` - Access main dashboard
- `view_analytics` - Access analytics page
- `view_sc_analytics` - Access supply chain analytics

### 2. Insights
- `view_insights` - Access AI-powered insights dashboard
- `manage_insights` - Manage and configure insights

### 3. Gamification
- `view_games` - View game list
- `create_game` - Create new games
- `play_game` - Play games
- `delete_game` - Delete games
- `manage_games` - Full game management

### 4. Supply Chain Design
- `view_sc_configs` - View supply chain configs
- `create_sc_config` - Create new configs
- `edit_sc_config` - Edit existing configs
- `delete_sc_config` - Delete configs
- `view_inventory_models` - View inventory models
- `manage_inventory_models` - Manage inventory models
- `view_group_configs` - View group-specific configs
- `manage_group_configs` - Manage group configs
- `view_ntier_visibility` - Access N-tier visibility dashboard

### 5. Planning & Optimization
- `view_order_planning` - View order planning and tracking
- `manage_order_planning` - Manage order planning
- `view_demand_planning` - View demand planning
- `manage_demand_planning` - Manage demand planning
- `view_supply_planning` - View supply planning
- `manage_supply_planning` - Manage supply planning
- `view_optimization` - View optimization results
- `run_optimization` - Run optimization

### 6. AI & ML Models
- `use_ai_assistant` - Access Claude-powered AI assistant
- `view_trm_training` - View TRM training dashboard
- `start_trm_training` - Start TRM training
- `manage_trm_models` - Manage TRM models
- `view_gnn_training` - View GNN training dashboard
- `start_gnn_training` - Start GNN training
- `manage_gnn_models` - Manage GNN models
- `view_model_setup` - View model setup
- `manage_model_setup` - Manage model configuration

### 7. Collaboration
- `view_groups` - View groups
- `create_group` - Create new groups
- `manage_groups` - Full group management
- `view_players` - View players
- `manage_players` - Manage players
- `view_users` - View users
- `create_user` - Create new users
- `edit_user` - Edit user information
- `delete_user` - Delete users

---

## Backend API

### Endpoints

#### 1. List Users
```http
GET /api/v1/users
Authorization: Bearer <token>

Returns all users that the current user can manage.
Group Admins see only users in their group.
System Admins see all users.
```

#### 2. Get User Capabilities
```http
GET /api/v1/users/{user_id}/capabilities
Authorization: Bearer <token>

Returns:
{
  "id": 123,
  "email": "user@example.com",
  "full_name": "User Name",
  "user_type": "PLAYER",
  "capabilities": ["view_dashboard", "view_games", ...],
  "is_active": true
}
```

#### 3. Update User Capabilities
```http
PUT /api/v1/users/{user_id}/capabilities
Authorization: Bearer <token>
Content-Type: application/json

{
  "user_type": "GROUP_ADMIN",
  "capabilities": ["view_dashboard", "create_game", ...]
}

Returns:
{
  "success": true,
  "message": "User capabilities updated successfully",
  "user": { ... }
}
```

### Access Control Rules

**Group Admin Can**:
- ✅ View users in their group
- ✅ Edit users in their group (except System Admins)
- ✅ Assign any role except System Admin
- ✅ Grant any capability except system-level permissions

**Group Admin Cannot**:
- ❌ View users outside their group
- ❌ Edit System Admin users
- ❌ Create System Admin users
- ❌ Grant system-level capabilities

**System Admin Can**:
- ✅ View all users
- ✅ Edit any user (including other System Admins)
- ✅ Assign any role including System Admin
- ✅ Grant any capability

---

## Technical Implementation

### Frontend Components

**Main Component**: `frontend/src/pages/admin/UserRoleManagement.jsx`
- 850+ lines of React code
- Material-UI components for UI
- Three-tab interface with state management
- Real-time capability counting
- Role template quick-apply functionality

**Key State**:
```javascript
const [users, setUsers] = useState([]);
const [selectedUser, setSelectedUser] = useState(null);
const [editDialogOpen, setEditDialogOpen] = useState(false);
```

**Role Templates**:
```javascript
const roleTemplates = {
  GROUP_ADMIN: { label, description, capabilities: [...] },
  PLAYER: { label, description, capabilities: [...] },
  GAME_MANAGER: { label, description, capabilities: [...] },
  ANALYST: { label, description, capabilities: [...] },
};
```

**Capability Categories**:
```javascript
const capabilityCategories = {
  overview: { label, capabilities: [...] },
  insights: { label, capabilities: [...] },
  // ... 7 categories total
};
```

### Backend Implementation

**API Endpoint**: `backend/app/api/endpoints/user_capabilities.py`
- 200+ lines of Python code
- FastAPI router with 3 endpoints
- Capability checking and validation
- Group-level access control
- Pydantic models for request validation

**Key Functions**:
```python
@router.put("/{user_id}/capabilities")
async def update_user_capabilities(...)

@router.get("/{user_id}/capabilities")
async def get_user_capabilities(...)

@router.get("")
async def list_group_users(...)
```

**Security Checks**:
- Verify `manage_permissions` capability
- Validate group membership
- Prevent System Admin modification by non-admins
- Validate user_type enum
- Prevent privilege escalation

### Database

**Current**: Capabilities are derived from `user_type` field
**Future**: Can add JSON field to store custom capabilities per user

**User Types**:
- `SYSTEM_ADMIN` - All capabilities
- `GROUP_ADMIN` - 29 predefined capabilities
- `PLAYER` - 10 predefined capabilities

---

## Usage Examples

### Example 1: Assign Game Manager Role

1. Navigate to **Collaboration → Role Management**
2. Find user in table, click **Edit**
3. In dialog, click **Game Manager** template
4. Review selected capabilities (16 total)
5. Optionally add/remove specific capabilities
6. Click **Save Changes**

**Result**: User can now create and manage games but doesn't have admin access

---

### Example 2: Create Custom Analyst Role

1. Navigate to **Collaboration → Role Management**
2. Find user, click **Edit**
3. Click **Analyst** template as base (18 capabilities)
4. Expand **AI & ML Models** accordion
5. Uncheck `use_ai_assistant` (if you want view-only)
6. Expand **Planning & Optimization**
7. Check `run_optimization` (to allow running optimizations)
8. Click **Save Changes**

**Result**: User has analyst capabilities with optimization execution rights

---

### Example 3: Grant Minimal Player Access

1. Find user, click **Edit**
2. Click **Player** template (10 capabilities)
3. Optionally expand categories to remove capabilities
4. For example, uncheck `view_analytics` for restricted access
5. Click **Save Changes**

**Result**: User can only play games and view basic information

---

## Best Practices

### For Group Admins

1. **Start with Templates**: Use role templates as a starting point
2. **Review Carefully**: Check all selected capabilities before saving
3. **Least Privilege**: Grant only the capabilities users need
4. **Regular Audits**: Periodically review user roles and capabilities
5. **Document Custom Roles**: Keep notes on why custom capabilities were granted

### Security Considerations

1. **Never over-grant**: Don't give users more access than they need
2. **Test thoroughly**: Test custom roles before deploying to production users
3. **Monitor usage**: Track which users have elevated capabilities
4. **Revoke when done**: Remove capabilities when users change roles
5. **Group isolation**: Remember Group Admins can only manage their group

---

## Troubleshooting

### Issue: Can't see Role Management in sidebar
**Solution**: Ensure you have `manage_permissions` capability (Group Admin or above)

### Issue: Can't edit a user
**Possible Causes**:
- User is a System Admin (only System Admins can edit them)
- User is in a different group (Group Admins can only edit their group)
- You don't have `manage_permissions` capability

### Issue: Save fails with "Not authorized"
**Solution**: Check that you're not trying to assign System Admin role as a Group Admin

### Issue: Capabilities don't update in UI
**Solution**: Refresh the page or log out/in to reload capabilities

---

## Future Enhancements

### Phase 2
- [ ] Custom capability sets saved to database (JSON field on User model)
- [ ] Capability inheritance from groups
- [ ] Temporal capabilities (expires after X days)
- [ ] Capability history/audit log
- [ ] Bulk capability assignment

### Phase 3
- [ ] Role hierarchy (roles can inherit from other roles)
- [ ] Capability groups (bundle related capabilities)
- [ ] UI to create custom role templates
- [ ] Export/import role configurations
- [ ] Integration with external RBAC systems

---

## Summary

The User Role & Capability Management system provides:

✅ **Fine-grained control** - 50+ capabilities across 7 categories
✅ **User-friendly interface** - Visual, intuitive role management
✅ **Role templates** - Quick-apply common user types
✅ **Custom roles** - Mix and match capabilities as needed
✅ **Group isolation** - Group Admins manage only their users
✅ **Security** - Built-in safeguards prevent privilege escalation
✅ **Flexibility** - Easy to add new capabilities as features grow

**Total Implementation**:
- 1 new navigation item
- 850+ lines of frontend code
- 200+ lines of backend code
- 3 API endpoints
- 4 role templates
- 50+ capability definitions

**Benefits**:
- Simplified user management for Group Admins
- Better security through least-privilege access
- Flexibility to create specialized roles
- Clear visibility into user permissions
- Scalable for future feature growth
