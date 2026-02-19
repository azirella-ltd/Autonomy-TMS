# Quick Test Guide - Sprint 4 Features

**⏱️ Time Required**: 15-20 minutes
**👤 Testers Needed**: 1 (some features need 2)
**🎯 Goal**: Verify all 5 Sprint 4 features work

---

## Setup (2 minutes)

1. **Open Application**
   ```
   http://localhost:8088
   ```

2. **Login**
   - Email: `systemadmin@autonomy.ai`
   - Password: `Autonomy@2025`

3. **Create or Open Test Game**
   - Use existing game with AI suggestions enabled
   - OR create new game: Mixed game, enable AI suggestions

4. **Play 2-3 Rounds** (if new game)
   - Accept some AI suggestions
   - Modify some AI suggestions
   - Reject some AI suggestions

---

## Quick Feature Tests

### 1️⃣ Chat (2 minutes)

**Tab**: Chat

✅ **Quick Test**:
1. Type: "What should I order?"
2. Wait for AI response (3-5 sec)
3. Type: "Why?"
4. Check AI references previous message

**Pass Criteria**: AI responds with context

---

### 2️⃣ Analytics (3 minutes)

**Tab**: Analytics

✅ **Quick Test**:
1. Check pattern badge shows (Conservative/Aggressive/Balanced/Reactive)
2. Check acceptance rate shows percentage
3. Scroll to history table - see suggestions
4. Check insights list has recommendations

**Pass Criteria**: All 4 sections display data

---

### 3️⃣ Visibility (3 minutes)

**Tab**: Visibility

✅ **Quick Test**:
1. Toggle "Share Inventory" ON
2. Check Sankey diagram loads
3. Check health score displays (0-100)
4. Check bottleneck section shows

**Pass Criteria**: Diagram and metrics display

---

### 4️⃣ Negotiations (4 minutes)

**Tab**: Negotiate

✅ **Quick Test**:
1. Click "New Proposal"
2. Select target player (any)
3. Select type: "Order Adjustment"
4. Enter quantity: `+10`
5. Click "Create Proposal"
6. Check proposal appears in list

**Pass Criteria**: Proposal created successfully

---

### 5️⃣ Global Optimization (3 minutes)

**Tab**: AI (or wherever AI suggestions are)

✅ **Quick Test**:
1. Find "Global" button (purple)
2. Click it
3. Wait for recommendations (3-5 sec)
4. Check shows 4 roles with quantities
5. Check shows expected impact metrics

**Pass Criteria**: All 4 roles show recommendations

---

## Quick Checks (3 minutes)

### Console Errors
- [ ] Open DevTools (F12) → Console
- [ ] No red errors during tests

### Tab Navigation
- [ ] All 9 tabs load without errors
- [ ] Switching tabs doesn't lose data

### Mobile View
- [ ] Resize browser to 400px wide
- [ ] Layout adapts reasonably

---

## Results

| Feature | Status | Notes |
|---------|--------|-------|
| Chat | ⏳ | |
| Analytics | ⏳ | |
| Visibility | ⏳ | |
| Negotiations | ⏳ | |
| Global Optimization | ⏳ | |

**Overall**: ⏳ PENDING

---

## If Something Fails

1. **Check Backend Logs**:
   ```bash
   docker compose logs backend --tail 50
   ```

2. **Check Browser Console** (F12):
   - Look for red error messages
   - Note the error text

3. **Try Refresh**:
   - Hard refresh: Ctrl+Shift+R (Windows) or Cmd+Shift+R (Mac)
   - Clear cache if needed

4. **Restart Services**:
   ```bash
   docker compose restart backend
   ```

---

## Next Steps

✅ **If all tests pass**: Sprint 4 is working! Ready for production.

❌ **If tests fail**: Document errors and report to development team.

---

**Quick Test Duration**: ~15-20 minutes
**Detailed Test Duration**: ~2-3 hours (see PHASE7_SPRINT4_BROWSER_TESTING_GUIDE.md)
