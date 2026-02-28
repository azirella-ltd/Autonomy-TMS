# Gamification System - Quick Test Guide

**Purpose**: 10-minute browser test to verify gamification features work
**Status**: Ready for testing after frontend container rebuild

---

## 🚀 Setup (1 minute)

1. **Restart Frontend**:
   ```bash
   docker compose restart frontend
   ```

2. **Wait for rebuild** (~30 seconds)

3. **Open Browser**:
   ```
   http://localhost:8088
   ```

4. **Login**:
   - Email: `systemadmin@autonomy.ai`
   - Password: `Autonomy@2026`

---

## ✅ Test 1: Achievements Tab (2 minutes)

1. **Open any game** or create a new one
2. **Click "Achievements" tab** (should be visible in right sidebar)
3. **Verify display**:
   - [ ] See 17 achievements
   - [ ] Some have lock icons 🔒 (locked)
   - [ ] Header shows "Level 1" with progress bar
   - [ ] Points and achievements count visible

4. **Test filters**:
   - [ ] Click "Unlocked" button - list changes
   - [ ] Click "Locked" button - list changes
   - [ ] Click "All" button - shows all 17
   - [ ] Select category dropdown - filters by category

5. **Check Progress**:
   - [ ] Click "Check Progress" button
   - [ ] Should show toast notification if any achievements unlocked
   - [ ] Or show "No new achievements" message

---

## ✅ Test 2: Leaderboard Tab (2 minutes)

1. **Click "Leaderboard" tab**
2. **Verify display**:
   - [ ] See 6 leaderboard buttons at top
   - [ ] First leaderboard ("Global Champions") is selected
   - [ ] Header shows leaderboard name and description
   - [ ] See "Your Rank" section if you have stats

3. **Test switching**:
   - [ ] Click "Best Win Rate" button
   - [ ] Leaderboard table updates
   - [ ] Click other leaderboards - each loads

4. **Check table**:
   - [ ] See columns: Rank, Player, Score
   - [ ] Top 3 have medals (🥇🥈🥉)
   - [ ] Top 3 have colored borders
   - [ ] Your player highlighted (if in list)

---

## ✅ Test 3: Achievement Unlock (3 minutes)

### Test "First Steps" Achievement

1. **Create a new game** (if you haven't completed one)
2. **Play through the game**:
   - Place orders for a few rounds
   - Complete at least 1 full round

3. **Go to Achievements tab**
4. **Click "Check Progress"** button
5. **Expected result**:
   - [ ] Toast notification: "Achievement Unlocked! First Steps"
   - [ ] "First Steps" achievement now has ✅ check icon
   - [ ] No longer has 🔒 lock icon
   - [ ] Points updated in header

6. **Check stats**:
   - [ ] Total points increased by 10
   - [ ] Achievements count increased by 1
   - [ ] Progress bar moved slightly

---

## ✅ Test 4: Level System (1 minute)

1. **Check current level** in achievements header
2. **Note your total points**
3. **Calculate next level**:
   - Level 1: Need 10 points total
   - Level 2: Need 40 points total
   - Level 3: Need 90 points total

4. **Progress bar**:
   - [ ] Shows percentage to next level
   - [ ] Animates smoothly
   - [ ] Text shows "X% to Level N"

---

## ✅ Test 5: Player Profile Badge (1 minute)

### If implemented in header:
1. **Look for compact badge** in top nav
2. **Should show**:
   - [ ] "Lvl X" with your level
   - [ ] Trophy icon with points

### Full version (if shown):
1. **Should display**:
   - [ ] Large level circle
   - [ ] Progress bar
   - [ ] Achievement count
   - [ ] Quick stats grid (games, win rate, streak)

---

## 🐛 Common Issues & Solutions

### Issue: "Not authenticated" error
**Solution**: Make sure you're logged in. Refresh page and log in again.

### Issue: Achievements tab not visible
**Solution**:
```bash
docker compose restart frontend
# Wait 30 seconds, then refresh browser
```

### Issue: Leaderboards show "No rankings yet"
**Solution**: This is normal if no games have been completed. Play a game first.

### Issue: "Check Progress" does nothing
**Solution**: Check browser console (F12) for errors. Backend may not be running.

### Issue: Components not loading
**Solution**:
```bash
# Check frontend logs
docker compose logs frontend --tail 50

# Rebuild frontend
docker compose restart frontend
```

---

## 📊 Expected Results

### After First Game:
- [ ] "First Steps" achievement unlocked (10 points)
- [ ] Level: Still 1 (need 10 total for level 2)
- [ ] Stats: 1 game played, achievements: 1/17

### After 10 Games:
- [ ] "Veteran Player" unlocked (25 points)
- [ ] Level: 2-3 depending on other achievements
- [ ] Appears on leaderboards

### After Completing Various Actions:
- Accept AI suggestion → "Team Player" progress
- Complete negotiation → "Negotiator" progress
- Win with low cost → "Cost Cutter" unlocked
- Perfect service → "Perfect Service" progress

---

## 🎯 Success Criteria

**Test passes if**:
✅ All 5 tests complete without errors
✅ Achievements tab displays and filters work
✅ Leaderboard tab displays and switches work
✅ At least one achievement can be unlocked
✅ Level and points update correctly
✅ No console errors in browser (F12)

**Test fails if**:
❌ Tabs don't appear in GameRoom
❌ "Not authenticated" errors
❌ Components don't load
❌ Console shows React errors
❌ Achievement checking fails

---

## 📝 Test Report Template

```markdown
## Gamification Test Results

**Date**: __________
**Tester**: __________
**Browser**: __________ (version: __)

### Results
- [ ] Test 1: Achievements Tab - PASS/FAIL
- [ ] Test 2: Leaderboard Tab - PASS/FAIL
- [ ] Test 3: Achievement Unlock - PASS/FAIL
- [ ] Test 4: Level System - PASS/FAIL
- [ ] Test 5: Profile Badge - PASS/FAIL

### Issues Found:
1.
2.
3.

### Screenshots:
- [ ] Achievements tab
- [ ] Leaderboard tab
- [ ] Achievement unlock toast

### Overall: PASS / FAIL
```

---

## 🔧 Advanced Testing

### Test All Achievement Categories

**Progression**:
- Play 1, 10, 50, 100 games

**Performance**:
- Win with cost <500
- Maintain 100% service for 10 rounds
- Win with avg inventory <5
- Complete game with zero backlog

**Social**:
- Accept 5 AI suggestions
- Complete 10 negotiations
- Share visibility 20 times

**Mastery**:
- Win with bullwhip <1.5
- Win 5 games in a row
- Reach level 20

**Special**:
- Play in first month (auto-unlocked)
- Complete game between 12AM-4AM
- Complete 20-round game in <10 minutes

### Test All Leaderboards

1. **Global Champions** (total points)
   - Should rank by points descending

2. **Best Win Rate** (win percentage)
   - Should rank by win% descending

3. **Cost Efficiency** (avg cost)
   - Should rank by cost **ascending** (lower is better)

4. **Service Excellence** (service level)
   - Should rank by service% descending

5. **Weekly/Monthly** (time-based points)
   - Should only show this week/month's players

---

## 🎉 Next Steps After Testing

**If tests pass**:
1. Mark Sprint 5 Days 1-2 as verified ✅
2. Begin Day 3: Reports & Templates
3. Add achievements to game completion flow
4. Set up automated leaderboard updates

**If tests fail**:
1. Document errors with screenshots
2. Check browser console for errors
3. Check backend logs: `docker compose logs backend --tail 100`
4. Fix issues and re-test

---

**Test Duration**: 10 minutes
**Prerequisites**: Docker containers running, logged in
**Next**: Full integration testing with real gameplay

🎮 **Happy Testing!**
