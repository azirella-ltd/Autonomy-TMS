# RBAC UI Testing Guide

**Date**: 2026-01-22
**Status**: ✅ Ready for Testing

## Overview

The RBAC capability management UI has been fully integrated into the Group Admin User Management page. This guide provides step-by-step instructions for testing the functionality end-to-end.

## Prerequisites

1. **Database Setup**: RBAC tables created and permissions seeded
   ```bash
   # Verify database state
   docker compose exec backend python -c "
   from app.db.session import sync_engine
   from sqlalchemy import text
   from sqlalchemy.orm import sessionmaker

   SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
   db = SyncSessionLocal()

   perm_count = db.execute(text('SELECT COUNT(*) FROM permissions')).scalar()
   print(f'Permissions: {perm_count}')
   db.close()
   "
   ```
   **Expected Output**: `Permissions: 60`

2. **Services Running**: Frontend and backend containers are running
   ```bash
   docker compose ps frontend backend
   ```

3. **Test Users**: At least one Group Admin and one Player user in the same group

## Test Scenarios

### Scenario 1: View Default Capabilities

**Objective**: Verify that users have default capabilities based on their user type.

**Steps**:
1. Login as Group Admin: `groupadmin@example.com`
2. Navigate to **Admin → User Management**
3. Observe the user list - all users should be visible
4. Click the **Security icon** (🔒) for any Player user
5. The capability dialog should open with a default set of capabilities pre-selected

**Expected Result**:
- Dialog opens with title "Edit Capabilities for [username]"
- Some capabilities are pre-selected (based on PLAYER user type fallback)
- All 60 capabilities are displayed across 8 categories:
  - Strategic Planning (8)
  - Tactical Planning (9)
  - Operational Planning (9)
  - Execution & Monitoring (8)
  - Analytics & Insights (7)
  - AI & Agents (8)
  - Gamification (5)
  - Administration (6)
- Selection count shows at the top

### Scenario 2: Modify User Capabilities

**Objective**: Assign specific capabilities to a user and verify persistence.

**Steps**:
1. Login as Group Admin
2. Navigate to **Admin → User Management**
3. Click the **Security icon** for a Player user
4. In the capability dialog:
   - Click "Deselect All" to clear all capabilities
   - Expand "Tactical Planning" category
   - Select the following capabilities:
     - ☑ View MPS
     - ☑ Manage MPS
     - ☐ Approve MPS (leave unchecked)
   - Expand "Gamification" category
   - Select all capabilities in Gamification (5 total)
   - Verify selection count shows "7 of 60 capabilities selected"
5. Click "Save Capabilities"
6. Wait for success toast: "Capabilities updated successfully"
7. Close the dialog
8. Re-open the capability dialog for the same user

**Expected Result**:
- Success toast appears after saving
- Dialog closes automatically
- Upon re-opening, exactly 7 capabilities are selected:
  - Tactical Planning: view_mps, manage_mps (2)
  - Gamification: all 5 capabilities
- All other capabilities remain unselected
- Changes persist across page refreshes

### Scenario 3: Category-Level Selection

**Objective**: Use category-level checkboxes to select/deselect entire categories.

**Steps**:
1. Login as Group Admin
2. Navigate to **Admin → User Management**
3. Click **Security icon** for a user
4. Click "Deselect All" to start fresh
5. Click the checkbox next to "Operational Planning" category header
6. Observe the chip showing "9/9" next to the category name
7. Click the category checkbox again to deselect
8. Click "Select All" button
9. Observe all categories show full counts (e.g., "8/8", "9/9")
10. Click "Deselect All" button

**Expected Result**:
- Category checkbox selects/deselects all capabilities in that category
- Chip updates to show X/Y count
- Category checkbox shows:
  - ☐ Empty when 0 capabilities selected
  - ☑ Checked when all capabilities selected
  - ⊟ Indeterminate when some capabilities selected
- "Select All" button selects all 60 capabilities
- "Deselect All" button clears all selections

### Scenario 4: Expand/Collapse Categories

**Objective**: Test accordion expand/collapse functionality.

**Steps**:
1. Open capability dialog for any user
2. Click "Expand All" button
3. Verify all 8 categories are expanded
4. Click "Collapse All" button
5. Verify all categories are collapsed
6. Manually expand "Strategic Planning" by clicking the category row
7. Manually collapse it by clicking again

**Expected Result**:
- "Expand All" expands all 8 categories
- "Collapse All" collapses all categories
- Individual categories can be expanded/collapsed by clicking
- Expansion state is independent per category

### Scenario 5: Search and Filter (Manual Testing)

**Objective**: Verify capabilities can be found by searching/scanning.

**Steps**:
1. Open capability dialog
2. Click "Expand All"
3. Scroll through all categories
4. Visually locate these capabilities:
   - "View MPS" in Tactical Planning
   - "Manage AI Agents" in AI & Agents
   - "View Games" in Gamification
   - "Manage Permissions" in Administration
5. Note the descriptions under each capability label

**Expected Result**:
- All capabilities have clear labels (e.g., "View MPS", "Manage MPS")
- All capabilities have helpful descriptions
- Categories are logically organized
- No duplicate capability names across categories

### Scenario 6: Permissions Enforcement

**Objective**: Verify Group Admins can only edit users in their own group.

**Steps**:
1. Create two groups: "Group A" and "Group B"
2. Create Group Admin for each group
3. Create Player users in each group
4. Login as Group Admin for "Group A"
5. Navigate to **Admin → User Management**
6. Verify only users from "Group A" are visible
7. Attempt to access capability endpoint for user in "Group B" via API:
   ```bash
   curl -X GET http://localhost:8088/api/users/<group_b_user_id>/capabilities \
     -H "Cookie: session=<group_a_admin_session>"
   ```

**Expected Result**:
- Group Admin only sees users from their own group
- API returns 403 Forbidden when attempting to access users from other groups
- Success toast shows when updating users in their own group
- Error toast shows when attempting unauthorized access

### Scenario 7: System Admin Access

**Objective**: Verify System Admins can manage all users across all groups.

**Steps**:
1. Login as System Admin: `systemadmin@autonomy.ai`
2. Navigate to **Admin → System Users** (not User Management)
3. Verify users from all groups are visible
4. Select a user from any group
5. Edit their capabilities
6. Save changes

**Expected Result**:
- System Admin sees all users across all groups
- Can edit capabilities for any user
- Changes persist successfully
- No permission errors

### Scenario 8: Database Verification

**Objective**: Verify capabilities are persisted in the database correctly.

**Steps**:
1. Assign 3 specific capabilities to a user via UI:
   - view_mps
   - manage_mps
   - view_games
2. Save changes
3. Query the database directly:
   ```bash
   docker compose exec backend python -c "
   from app.db.session import sync_engine
   from sqlalchemy import text
   from sqlalchemy.orm import sessionmaker

   SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
   db = SyncSessionLocal()

   # Replace <user_id> with actual user ID
   user_id = <user_id>

   result = db.execute(text('''
       SELECT p.name, p.category
       FROM permissions p
       JOIN role_permissions rp ON p.id = rp.permission_id
       JOIN roles r ON rp.role_id = r.id
       JOIN user_roles ur ON r.id = ur.role_id
       WHERE ur.user_id = :user_id
       ORDER BY p.category, p.name
   '''), {'user_id': user_id}).fetchall()

   print(f'Capabilities for user {user_id}:')
   for name, category in result:
       print(f'  {category}: {name}')

   db.close()
   "
   ```

**Expected Result**:
- Database query returns exactly the 3 capabilities assigned:
  - Tactical Planning: view_mps
  - Tactical Planning: manage_mps
  - Gamification: view_games
- Custom role exists with slug `user_<user_id>_custom`
- Role-permission associations are correct
- User-role association is correct

### Scenario 9: Error Handling

**Objective**: Verify proper error messages for various failure scenarios.

**Steps**:
1. **Network Error Simulation**:
   - Stop backend container: `docker compose stop backend`
   - Try to open capability dialog
   - Observe error toast
   - Restart backend: `docker compose start backend`

2. **Invalid User ID**:
   - Try to access capabilities for non-existent user via API
   - Verify 404 error response

3. **Concurrent Edits**:
   - Open capability dialog for User A
   - In another tab/browser, change User A's capabilities
   - In first tab, save different capabilities
   - Verify last write wins (expected behavior)

**Expected Result**:
- "Failed to load user capabilities" toast when backend is down
- "Failed to update capabilities" toast when save fails
- 404 error for non-existent users
- No data corruption from concurrent edits

### Scenario 10: UI Responsiveness

**Objective**: Verify UI remains responsive during loading and saving.

**Steps**:
1. Open capability dialog
2. Observe loading state while capabilities are fetched
3. Toggle 20+ capabilities
4. Click "Save Capabilities"
5. Observe saving state
6. Verify dialog remains disabled during save
7. Verify "Cancel" button is disabled during save

**Expected Result**:
- Capability selector is disabled while loading
- Loading spinner or skeleton is shown (if implemented)
- Save button shows "Saving…" with spinner during save
- Cancel button is disabled during save
- Dialog cannot be closed during save
- All interactions are prevented during save
- Success/error feedback is immediate after save completes

## API Testing

### Test API Endpoints Directly

**Get User Capabilities**:
```bash
# Replace <user_id> and <session_cookie>
curl -X GET "http://localhost:8088/api/users/<user_id>/capabilities" \
  -H "Cookie: session=<session_cookie>" \
  -H "Content-Type: application/json"
```

**Expected Response**:
```json
{
  "user_id": 2,
  "email": "player@example.com",
  "user_type": "PLAYER",
  "capabilities": [
    "view_mps",
    "manage_mps",
    "view_games"
  ]
}
```

**Update User Capabilities**:
```bash
curl -X PUT "http://localhost:8088/api/users/<user_id>/capabilities" \
  -H "Cookie: session=<session_cookie>" \
  -H "Content-Type: application/json" \
  -d '{
    "capabilities": [
      "view_mps",
      "manage_mps",
      "approve_mps",
      "view_games",
      "create_game",
      "play_game"
    ]
  }'
```

**Expected Response**:
```json
{
  "success": true,
  "message": "User capabilities updated successfully",
  "user_id": 2,
  "capabilities": [
    "view_mps",
    "manage_mps",
    "approve_mps",
    "view_games",
    "create_game",
    "play_game"
  ]
}
```

## Common Issues and Troubleshooting

### Issue 1: Capabilities Not Loading

**Symptoms**: Dialog opens but shows 0 capabilities selected

**Possible Causes**:
- User has no roles assigned (falls back to empty)
- API endpoint not returning data
- Network error

**Diagnosis**:
```bash
# Check if user has roles
docker compose exec backend python -c "
from app.db.session import sync_engine
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
db = SyncSessionLocal()

user_id = <user_id>
result = db.execute(text('SELECT COUNT(*) FROM user_roles WHERE user_id = :user_id'), {'user_id': user_id}).scalar()
print(f'User {user_id} has {result} roles')

db.close()
"
```

**Solution**:
- This is expected for users without custom capabilities assigned
- Fallback to user type capabilities is working correctly
- Assign capabilities via UI to create custom role

### Issue 2: Changes Not Persisting

**Symptoms**: Capabilities revert to previous state after page refresh

**Possible Causes**:
- API save request failed silently
- Browser cache issue
- Database transaction not committed

**Diagnosis**:
- Check browser console for API errors
- Check backend logs: `docker compose logs backend --tail=50`
- Query database directly (see Scenario 8)

**Solution**:
- Clear browser cache
- Restart backend: `docker compose restart backend`
- Check for database migration issues

### Issue 3: Permission Denied Errors

**Symptoms**: 403 Forbidden error when editing capabilities

**Possible Causes**:
- Group Admin trying to edit user in different group
- Group Admin trying to edit System Admin
- User not logged in as admin

**Diagnosis**:
- Verify user type: Group Admin or System Admin
- Verify user's group_id matches target user's group_id
- Check backend logs for permission check failures

**Solution**:
- Login as correct admin user
- Ensure target user is in the same group
- System Admins can edit any user

## Success Criteria

✅ All 10 test scenarios pass without errors
✅ Capabilities persist across page refreshes
✅ Database queries confirm correct data structure
✅ API endpoints return correct responses
✅ Permission enforcement works correctly
✅ UI is responsive and provides clear feedback
✅ Error handling is graceful with helpful messages
✅ No console errors in browser developer tools
✅ No backend errors in Docker logs

## Next Steps After Testing

1. **Create Demo Video**: Record walkthrough of capability editing
2. **User Documentation**: Write end-user guide for Group Admins
3. **Role Templates**: Consider adding predefined role templates (Demand Planner, Supply Planner, etc.)
4. **Audit Trail UI**: Build UI to view role_permission_grants and user_role_assignments audit tables
5. **Bulk Operations**: Add ability to assign same capabilities to multiple users at once
6. **Export/Import**: Add ability to export/import user capabilities as JSON
7. **Capability Search**: Add search/filter box in capability selector dialog

## Related Documentation

- [RBAC_MIGRATION_COMPLETE.md](RBAC_MIGRATION_COMPLETE.md) - Database migration details
- [RBAC_INTEGRATION_COMPLETE.md](RBAC_INTEGRATION_COMPLETE.md) - RBAC service implementation
- [backend/app/components/admin/CapabilitySelector.jsx](../../frontend/src/components/admin/CapabilitySelector.jsx) - Capability selector component
- [backend/app/pages/admin/UserManagement.js](../../frontend/src/pages/admin/UserManagement.js) - User management page with RBAC integration
