# Mobile App Testing Guide - Task 3

**Task**: Option 2, Task 3 - Mobile Testing & Polish
**Estimated Time**: 1 day (8 hours)
**Prerequisites**: Firebase configuration complete (Task 2)

---

## Overview

This guide covers comprehensive testing of The Beer Game mobile application on physical devices. You'll test:

1. Core app functionality
2. Push notifications
3. Offline mode
4. WebSocket real-time updates
5. User preferences
6. Edge cases and error handling

---

## Testing Environment Setup

### Required Devices

**iOS Testing**:
- Device: iPhone 12 or newer
- OS: iOS 16.0 or higher
- Storage: 200MB free space
- Network: WiFi + Cellular (for offline testing)

**Android Testing**:
- Device: Google Pixel 6 or newer (or equivalent)
- OS: Android API 30+ (Android 11+)
- Storage: 200MB free space
- Network: WiFi + Cellular (for offline testing)

### Test Accounts

Create test accounts for different roles:

```bash
# System Admin
Email: systemadmin@autonomy.ai
Password: Autonomy@2025

# Test Player 1
Email: player1@test.com
Password: TestPassword123!

# Test Player 2
Email: player2@test.com
Password: TestPassword123!

# Test Player 3
Email: player3@test.com
Password: TestPassword123!
```

### Development Tools

- [ ] Xcode (for iOS logs)
- [ ] Android Studio (for Android logs)
- [ ] Charles Proxy or similar (for network monitoring - optional)
- [ ] Spreadsheet for test tracking (Excel, Google Sheets)

---

## Test Plan Overview

### Test Categories

| Category | Tests | Est. Time |
|----------|-------|-----------|
| **Installation & Launch** | 5 tests | 30 min |
| **Authentication** | 8 tests | 45 min |
| **Game Functionality** | 15 tests | 2 hours |
| **Push Notifications** | 12 tests | 1.5 hours |
| **Offline Mode** | 8 tests | 1 hour |
| **Real-Time Updates** | 6 tests | 45 min |
| **User Preferences** | 6 tests | 30 min |
| **Edge Cases** | 10 tests | 1 hour |
| **Performance** | 5 tests | 30 min |
| **Bug Fixes & Polish** | - | 1.5 hours |

**Total**: ~8 hours

---

## Part 1: Installation & Launch Testing (30 minutes)

### Test 1.1: Fresh Install (iOS)

**Steps**:
1. Delete app if already installed
2. Install from TestFlight or Xcode
3. Launch app

**Expected**:
- [ ] App installs without errors
- [ ] App icon appears on home screen
- [ ] Launch screen displays
- [ ] App loads to login screen in < 3 seconds
- [ ] No crash or freeze

**Actual Result**: ________________

### Test 1.2: Fresh Install (Android)

**Steps**:
1. Delete app if already installed
2. Install from APK or Android Studio
3. Launch app

**Expected**:
- [ ] App installs without errors
- [ ] App icon appears in app drawer
- [ ] Launch screen displays
- [ ] App loads to login screen in < 3 seconds
- [ ] No crash or freeze

**Actual Result**: ________________

### Test 1.3: App Permissions

**Steps**:
1. On first launch, app requests permissions
2. Review requested permissions

**Expected (iOS)**:
- [ ] Requests notification permission
- [ ] Permission dialog is clear and descriptive
- [ ] App functions if permission denied

**Expected (Android)**:
- [ ] Requests notification permission
- [ ] Permission dialog is clear and descriptive
- [ ] App functions if permission denied

**Actual Result**: ________________

### Test 1.4: Cold Start Performance

**Steps**:
1. Force quit the app
2. Clear from background
3. Relaunch and time the load

**Expected**:
- [ ] iOS: Loads in < 3 seconds
- [ ] Android: Loads in < 3 seconds
- [ ] Splash screen shows during load
- [ ] No blank screens

**Actual Result**:
- iOS: _______ seconds
- Android: _______ seconds

### Test 1.5: Background Recovery

**Steps**:
1. Open app
2. Press home button (backgrounded)
3. Wait 5 minutes
4. Reopen app

**Expected**:
- [ ] App resumes from where you left off
- [ ] No data loss
- [ ] Session still valid (no re-login required)

**Actual Result**: ________________

---

## Part 2: Authentication Testing (45 minutes)

### Test 2.1: Valid Login

**Steps**:
1. Enter valid credentials
2. Tap "Login"

**Expected**:
- [ ] Loading indicator shows
- [ ] Successful login in < 2 seconds
- [ ] Navigate to dashboard/home screen
- [ ] JWT token stored securely

**Actual Result**: ________________

### Test 2.2: Invalid Credentials

**Steps**:
1. Enter invalid email/password
2. Tap "Login"

**Expected**:
- [ ] Error message displays: "Invalid credentials"
- [ ] Password field clears
- [ ] Can retry login

**Actual Result**: ________________

### Test 2.3: Network Error During Login

**Steps**:
1. Turn off WiFi and cellular
2. Attempt login

**Expected**:
- [ ] Error message: "Network error. Please check your connection."
- [ ] Retry button appears
- [ ] App doesn't crash

**Actual Result**: ________________

### Test 2.4: Registration Flow

**Steps**:
1. Tap "Register" or "Sign Up"
2. Fill in all fields
3. Submit

**Expected**:
- [ ] Form validation works (email format, password strength)
- [ ] Success message shows
- [ ] Auto-login after registration
- [ ] Navigate to onboarding or dashboard

**Actual Result**: ________________

### Test 2.5: Logout

**Steps**:
1. Login successfully
2. Navigate to Settings/Profile
3. Tap "Logout"

**Expected**:
- [ ] Confirmation dialog: "Are you sure?"
- [ ] After logout, return to login screen
- [ ] Session cleared (can't go back to authenticated screens)
- [ ] Push token unregistered from backend

**Actual Result**: ________________

### Test 2.6: Session Expiration

**Steps**:
1. Login successfully
2. Wait for token to expire (or manually expire on backend)
3. Try to make an API call (e.g., load games list)

**Expected**:
- [ ] App detects expired token
- [ ] Auto-redirects to login screen
- [ ] Message: "Your session has expired. Please log in again."

**Actual Result**: ________________

### Test 2.7: Token Refresh

**Steps**:
1. Login successfully
2. Use app for extended period (> 15 minutes)
3. Continue using app

**Expected**:
- [ ] Token refreshes automatically
- [ ] No interruption to user experience
- [ ] No re-login required

**Actual Result**: ________________

### Test 2.8: Biometric Authentication (if implemented)

**Steps**:
1. Enable biometric login in settings
2. Logout
3. Use Face ID / Fingerprint to login

**Expected**:
- [ ] Biometric prompt appears
- [ ] Successful authentication logs in
- [ ] Failed authentication allows fallback to password

**Actual Result**: ________________

---

## Part 3: Game Functionality Testing (2 hours)

### Test 3.1: Games List Display

**Steps**:
1. Login and navigate to games list
2. Observe list of games

**Expected**:
- [ ] All assigned games displayed
- [ ] Game status shown (active, completed, pending)
- [ ] Tap on game navigates to game details
- [ ] Pull to refresh works

**Actual Result**: ________________

### Test 3.2: Create New Game

**Steps**:
1. Tap "Create Game" button
2. Fill in game details (name, config, players)
3. Submit

**Expected**:
- [ ] Form validation works
- [ ] Success message: "Game created successfully"
- [ ] New game appears in games list
- [ ] Can navigate to game details

**Actual Result**: ________________

### Test 3.3: Game Details View

**Steps**:
1. Tap on an active game
2. View game details screen

**Expected**:
- [ ] Game info displayed (name, config, current round)
- [ ] Player roles shown
- [ ] Your role highlighted
- [ ] Inventory, backlog, orders visible
- [ ] Chart/graph renders correctly

**Actual Result**: ________________

### Test 3.4: Place Order (Your Turn)

**Steps**:
1. Join game where it's your turn
2. Enter order quantity
3. Tap "Submit Order"

**Expected**:
- [ ] Input validation (positive number, max constraints)
- [ ] Confirmation dialog: "Submit order for X units?"
- [ ] Loading indicator
- [ ] Success message: "Order submitted"
- [ ] UI updates with submitted order
- [ ] Turn indicator updates

**Actual Result**: ________________

### Test 3.5: Place Order (Invalid Input)

**Steps**:
1. During your turn, enter invalid order:
   - Negative number
   - Decimal number
   - Text
   - Empty field

**Expected**:
- [ ] Validation error for negative: "Order must be positive"
- [ ] Validation error for decimal: "Order must be a whole number"
- [ ] Validation error for text: "Please enter a valid number"
- [ ] Validation error for empty: "Order quantity is required"
- [ ] Submit button disabled until valid

**Actual Result**: ________________

### Test 3.6: View Inventory & Metrics

**Steps**:
1. In active game, view your inventory section
2. Check metrics (cost, service level, etc.)

**Expected**:
- [ ] Current inventory displayed
- [ ] Backlog shown (if any)
- [ ] Incoming shipments displayed
- [ ] Outgoing orders displayed
- [ ] Total cost accumulated
- [ ] Service level percentage

**Actual Result**: ________________

### Test 3.7: Round Progression

**Steps**:
1. In an active game with all players
2. All players submit orders
3. Observe round progression

**Expected**:
- [ ] After all orders submitted, round auto-advances
- [ ] Loading indicator during processing
- [ ] New round displays updated inventory
- [ ] Notification sent to next player(s)

**Actual Result**: ________________

### Test 3.8: Game Completion

**Steps**:
1. Play game to completion (all rounds)
2. View final results

**Expected**:
- [ ] Game status changes to "Completed"
- [ ] Final scores displayed
- [ ] Rankings shown (if multiplayer)
- [ ] Can view full game history
- [ ] Notification: "Game completed!"

**Actual Result**: ________________

### Test 3.9: Analytics Charts

**Steps**:
1. View analytics/charts section in game details
2. Interact with charts

**Expected**:
- [ ] Line chart shows inventory over time
- [ ] Bar chart shows orders by round
- [ ] Bullwhip chart displays volatility
- [ ] Charts are interactive (zoom, pan)
- [ ] Legend is clear
- [ ] Data is accurate

**Actual Result**: ________________

### Test 3.10: Game History

**Steps**:
1. View completed game
2. Navigate to history/replay section

**Expected**:
- [ ] All rounds listed
- [ ] Can view each round's details
- [ ] Player actions displayed
- [ ] Inventory changes shown
- [ ] Can export/share results

**Actual Result**: ________________

### Test 3.11: Multi-Player Coordination

**Steps**:
1. Use 2 devices with different test accounts
2. Both join same game
3. Take turns submitting orders

**Expected**:
- [ ] Real-time updates when other player submits
- [ ] Turn indicator accurate on both devices
- [ ] No race conditions
- [ ] Notifications sent to correct player

**Actual Result**: ________________

### Test 3.12: Game Templates

**Steps**:
1. Navigate to templates section
2. Browse available templates
3. Select template for new game

**Expected**:
- [ ] Templates listed with descriptions
- [ ] Can preview template details
- [ ] Selecting template pre-fills game creation form
- [ ] Can modify template parameters

**Actual Result**: ________________

### Test 3.13: AI Agent Games

**Steps**:
1. Create game with AI agents
2. Start game
3. Observe AI behavior

**Expected**:
- [ ] AI agents auto-play their turns
- [ ] No delays waiting for AI
- [ ] Human players can still interact
- [ ] AI decisions logged

**Actual Result**: ________________

### Test 3.14: Search & Filter Games

**Steps**:
1. On games list, use search
2. Try filters (active, completed, etc.)

**Expected**:
- [ ] Search by game name works
- [ ] Filter by status works
- [ ] Filter by role works (if available)
- [ ] Combine search + filter
- [ ] Results update immediately

**Actual Result**: ________________

### Test 3.15: Game Deletion

**Steps**:
1. As game admin, attempt to delete game
2. Confirm deletion

**Expected**:
- [ ] Confirmation dialog: "Delete game? This cannot be undone."
- [ ] Game removed from list
- [ ] Players notified (optional)
- [ ] Can't access deleted game

**Actual Result**: ________________

---

## Part 4: Push Notifications Testing (1.5 hours)

### Test 4.1: Notification Permission Request

**Steps**:
1. Fresh install
2. Launch app
3. Login

**Expected**:
- [ ] Permission dialog appears
- [ ] Dialog explains why notifications needed
- [ ] Can proceed if denied

**Actual Result**: ________________

### Test 4.2: Token Registration

**Steps**:
1. After granting permission
2. Check backend

**Expected**:
- [ ] FCM token registered in backend
- [ ] Visible in `/api/v1/notifications/tokens` response
- [ ] Platform correct (ios/android)
- [ ] Device info captured

**Actual Result**: ________________

### Test 4.3: Test Notification

**Steps**:
1. In app settings, tap "Send Test Notification"
2. Wait for notification

**Expected**:
- [ ] Notification arrives within 5 seconds
- [ ] Title: "Test Notification"
- [ ] Body text displays correctly
- [ ] Sound plays
- [ ] Badge appears on app icon (iOS)
- [ ] Notification appears in notification center

**Actual Result**:
- Delivery time: _______ seconds

### Test 4.4: Game Started Notification

**Steps**:
1. Device 1: Create and start game
2. Device 2: Receive notification

**Expected**:
- [ ] Notification: "Game Started: [Game Name]"
- [ ] Body: "Your game has begun. It's your turn!"
- [ ] Tapping opens game
- [ ] Notification includes game ID in data

**Actual Result**: ________________

### Test 4.5: Your Turn Notification

**Steps**:
1. Device 1: Submit order (ends turn)
2. Device 2: Receive notification (next player)

**Expected**:
- [ ] Notification: "Your Turn!"
- [ ] Body: "It's your turn in [Game Name]"
- [ ] Tapping opens game at correct round
- [ ] Order form auto-focuses

**Actual Result**: ________________

### Test 4.6: Game Completed Notification

**Steps**:
1. Complete all rounds
2. All players receive notification

**Expected**:
- [ ] Notification: "Game Completed!"
- [ ] Body: "Your game [Game Name] has finished"
- [ ] Tapping opens results screen
- [ ] Shows final scores

**Actual Result**: ________________

### Test 4.7: Team Message Notification

**Steps**:
1. Device 1: Send team chat message
2. Device 2: Receive notification

**Expected**:
- [ ] Notification: "New Message from [Username]"
- [ ] Body shows message preview
- [ ] Tapping opens chat
- [ ] Unread badge shows

**Actual Result**: ________________

### Test 4.8: Foreground Notifications

**Steps**:
1. Have app open in foreground
2. Trigger notification

**Expected**:
- [ ] In-app banner displays at top
- [ ] Does NOT show in system notification center
- [ ] Can dismiss in-app banner
- [ ] Can tap to navigate

**Actual Result**: ________________

### Test 4.9: Background Notifications

**Steps**:
1. App in background (home screen)
2. Trigger notification

**Expected**:
- [ ] System notification appears
- [ ] Shows in notification center
- [ ] Badge updates
- [ ] Sound plays (if not in DND)

**Actual Result**: ________________

### Test 4.10: Locked Screen Notifications

**Steps**:
1. Lock device screen
2. Trigger notification

**Expected**:
- [ ] Notification appears on lock screen
- [ ] Can swipe to open app
- [ ] Privacy respected (no sensitive data shown)

**Actual Result**: ________________

### Test 4.11: Notification Preferences

**Steps**:
1. Go to Settings → Notifications
2. Disable "Your Turn" notifications
3. Trigger "Your Turn" event

**Expected**:
- [ ] Notification NOT sent
- [ ] Other notification types still work
- [ ] Preference saved

**Actual Result**: ________________

### Test 4.12: Quiet Hours

**Steps**:
1. Enable quiet hours (22:00-08:00)
2. Set device time to 23:00
3. Trigger notification

**Expected**:
- [ ] Notification blocked
- [ ] Logged in backend as "blocked_by_preferences"
- [ ] Change time to 12:00
- [ ] Notification delivers normally

**Actual Result**: ________________

---

## Part 5: Offline Mode Testing (1 hour)

### Test 5.1: Load App Offline

**Steps**:
1. Turn off WiFi and cellular
2. Launch app (previously logged in)

**Expected**:
- [ ] App loads from cache
- [ ] Shows offline indicator
- [ ] Can view cached data
- [ ] Message: "You are offline"

**Actual Result**: ________________

### Test 5.2: Queue Order Offline

**Steps**:
1. Go offline
2. Navigate to active game
3. Submit order

**Expected**:
- [ ] Order accepted locally
- [ ] Message: "Order queued. Will sync when online."
- [ ] Queue indicator shows "1 pending action"
- [ ] Order NOT sent to server yet

**Actual Result**: ________________

### Test 5.3: Sync on Reconnect

**Steps**:
1. With queued order, go back online
2. Wait for auto-sync

**Expected**:
- [ ] Auto-syncs within 5 seconds
- [ ] Success message: "X actions synced"
- [ ] Queue clears
- [ ] Server receives order
- [ ] UI updates

**Actual Result**:
- Sync time: _______ seconds

### Test 5.4: Queue Multiple Actions

**Steps**:
1. Go offline
2. Queue 3+ orders/actions
3. Go online

**Expected**:
- [ ] All actions queued
- [ ] Queue count shows correctly
- [ ] All sync successfully
- [ ] Order preserved (first queued = first synced)

**Actual Result**: ________________

### Test 5.5: Conflict Resolution

**Steps**:
1. Device 1: Go offline, queue order
2. Device 2: Online, submit different order for same round
3. Device 1: Go online, sync

**Expected**:
- [ ] Conflict detected
- [ ] User notified: "Your order conflicts with recent changes"
- [ ] Shows both orders
- [ ] User can choose which to keep

**Actual Result**: ________________

### Test 5.6: Partial Sync Failure

**Steps**:
1. Queue 3 actions offline
2. Go online
3. Simulate server error on 2nd action

**Expected**:
- [ ] 1st action syncs successfully
- [ ] 2nd action fails, shows error
- [ ] 3rd action waits in queue
- [ ] Retry button available
- [ ] Can retry failed action

**Actual Result**: ________________

### Test 5.7: Data Persistence Offline

**Steps**:
1. Go offline
2. Close app (force quit)
3. Reopen app (still offline)

**Expected**:
- [ ] Queue preserved
- [ ] Cached data still available
- [ ] No data loss

**Actual Result**: ________________

### Test 5.8: Network Flapping

**Steps**:
1. Rapidly toggle WiFi on/off/on/off
2. Queue actions during toggles

**Expected**:
- [ ] App handles gracefully
- [ ] No crashes
- [ ] No duplicate syncs
- [ ] Data integrity maintained

**Actual Result**: ________________

---

## Part 6: Real-Time Updates Testing (45 minutes)

### Test 6.1: WebSocket Connection

**Steps**:
1. Login
2. Monitor network traffic (optional)

**Expected**:
- [ ] WebSocket connects automatically
- [ ] Connection indicator shows "Connected"
- [ ] Maintains connection while app in foreground

**Actual Result**: ________________

### Test 6.2: Real-Time Order Update

**Steps**:
1. Device 1: Submit order
2. Device 2: Observe (same game)

**Expected**:
- [ ] Device 2 sees update within 2 seconds
- [ ] UI updates automatically (no refresh needed)
- [ ] Order appears in game state

**Actual Result**:
- Update latency: _______ seconds

### Test 6.3: WebSocket Reconnection

**Steps**:
1. Disconnect WebSocket (go offline)
2. Wait 10 seconds
3. Reconnect (go online)

**Expected**:
- [ ] WebSocket auto-reconnects within 5 seconds
- [ ] Missed updates fetched
- [ ] No data loss

**Actual Result**: ________________

### Test 6.4: Multiple Simultaneous Updates

**Steps**:
1. 3 devices in same game
2. All submit orders within 1 second

**Expected**:
- [ ] All devices receive all updates
- [ ] No update lost
- [ ] Correct order maintained
- [ ] UI consistent across devices

**Actual Result**: ________________

### Test 6.5: Background App Behavior

**Steps**:
1. Connect WebSocket
2. Background app
3. Wait 2 minutes
4. Foreground app

**Expected**:
- [ ] WebSocket disconnects after ~30 seconds in background (to save battery)
- [ ] Reconnects when foregrounded
- [ ] Fetches missed updates on reconnect

**Actual Result**: ________________

### Test 6.6: WebSocket Error Handling

**Steps**:
1. Simulate server WebSocket error
2. Observe app behavior

**Expected**:
- [ ] Error detected
- [ ] Auto-retry connection (exponential backoff)
- [ ] User sees "Connection lost, retrying..."
- [ ] Eventually reconnects or shows persistent error

**Actual Result**: ________________

---

## Part 7: User Preferences Testing (30 minutes)

### Test 7.1: View Preferences

**Steps**:
1. Go to Settings → Notifications

**Expected**:
- [ ] All preference options displayed
- [ ] Current values shown
- [ ] Toggles/switches work

**Actual Result**: ________________

### Test 7.2: Toggle Individual Notifications

**Steps**:
1. Disable "Game Started" notifications
2. Enable "Your Turn" notifications
3. Save

**Expected**:
- [ ] Changes saved to backend
- [ ] API returns 200
- [ ] Success message: "Preferences saved"
- [ ] Reload shows correct values

**Actual Result**: ________________

### Test 7.3: Set Quiet Hours

**Steps**:
1. Enable quiet hours
2. Set start: 22:00
3. Set end: 08:00
4. Save

**Expected**:
- [ ] Time pickers work correctly
- [ ] Validation prevents invalid ranges (optional)
- [ ] Saved successfully
- [ ] Notifications respect quiet hours

**Actual Result**: ________________

### Test 7.4: Disable All Notifications

**Steps**:
1. Toggle off all notification types
2. Save

**Expected**:
- [ ] All toggles off
- [ ] Saved successfully
- [ ] No notifications delivered (except forced ones)

**Actual Result**: ________________

### Test 7.5: Default Preferences

**Steps**:
1. Fresh account (no preferences set)
2. View notification preferences

**Expected**:
- [ ] Default values shown
- [ ] Game notifications: ON
- [ ] Team notifications: ON
- [ ] Analytics notifications: OFF
- [ ] Quiet hours: OFF

**Actual Result**: ________________

### Test 7.6: Theme/Appearance (if available)

**Steps**:
1. Go to Settings → Appearance
2. Toggle dark mode

**Expected**:
- [ ] UI switches immediately
- [ ] All screens respect theme
- [ ] No flashing/glitches
- [ ] Preference saved

**Actual Result**: ________________

---

## Part 8: Edge Cases & Error Handling (1 hour)

### Test 8.1: Low Memory

**Steps**:
1. Open many apps in background
2. Launch Beer Game app
3. Navigate to heavy screen (charts)

**Expected**:
- [ ] App handles gracefully
- [ ] No crash (iOS: no jetsam)
- [ ] May show loading states
- [ ] Can free memory if needed

**Actual Result**: ________________

### Test 8.2: Low Battery

**Steps**:
1. Reduce battery to < 10%
2. Use app

**Expected**:
- [ ] App functions normally
- [ ] May reduce background activity
- [ ] No unexpected behavior

**Actual Result**: ________________

### Test 8.3: Poor Network Connection

**Steps**:
1. Simulate 2G network (very slow)
2. Try to load games list

**Expected**:
- [ ] Loading indicators show
- [ ] Eventually times out gracefully (30s timeout)
- [ ] Error message: "Network too slow. Please try again."
- [ ] Retry option available

**Actual Result**: ________________

### Test 8.4: Server Error 500

**Steps**:
1. Trigger server 500 error (modify backend)
2. Try API call

**Expected**:
- [ ] Error detected
- [ ] User-friendly message: "Server error. Please try again later."
- [ ] Retry button
- [ ] No crash

**Actual Result**: ________________

### Test 8.5: Large Dataset

**Steps**:
1. Account with 100+ games
2. Load games list

**Expected**:
- [ ] List loads with pagination
- [ ] Smooth scrolling
- [ ] No lag
- [ ] Search/filter works

**Actual Result**: ________________

### Test 8.6: Rapid Actions

**Steps**:
1. Rapidly tap buttons (100+ taps/minute)
2. Try to break the app

**Expected**:
- [ ] Debouncing prevents duplicate actions
- [ ] No crashes
- [ ] No race conditions

**Actual Result**: ________________

### Test 8.7: Device Rotation

**Steps**:
1. Rotate device landscape/portrait
2. Test on all screens

**Expected**:
- [ ] Layout adjusts correctly
- [ ] No content cut off
- [ ] State preserved
- [ ] No crashes

**Actual Result**: ________________

### Test 8.8: Accessibility

**Steps**:
1. Enable VoiceOver (iOS) / TalkBack (Android)
2. Navigate app

**Expected**:
- [ ] All buttons have labels
- [ ] Navigation works
- [ ] Forms accessible
- [ ] Dynamic content announced

**Actual Result**: ________________

### Test 8.9: Long Text

**Steps**:
1. Create game with very long name (200+ chars)
2. Send chat message with long text

**Expected**:
- [ ] Text truncates with ellipsis
- [ ] Can expand to see full text
- [ ] No layout breaking

**Actual Result**: ________________

### Test 8.10: Special Characters

**Steps**:
1. Use emoji, Unicode, special chars in:
   - Game names
   - Chat messages
   - User names

**Expected**:
- [ ] Renders correctly
- [ ] No encoding issues
- [ ] No crashes

**Actual Result**: ________________

---

## Part 9: Performance Testing (30 minutes)

### Test 9.1: App Launch Time

**Measurement**: Time from tap icon to interactive screen

**iOS**:
- Cold start: _______ seconds
- Warm start: _______ seconds

**Android**:
- Cold start: _______ seconds
- Warm start: _______ seconds

**Expected**: < 3 seconds (cold), < 1 second (warm)

### Test 9.2: API Response Time

**Measurement**: Time for API calls to complete

**Tests**:
- Login: _______ ms (expect < 500ms)
- Load games list: _______ ms (expect < 1000ms)
- Submit order: _______ ms (expect < 500ms)
- Load game details: _______ ms (expect < 1000ms)

### Test 9.3: Memory Usage

**Tools**: Xcode Instruments (iOS), Android Profiler (Android)

**iOS**:
- Idle: _______ MB
- Active game: _______ MB
- Charts view: _______ MB

**Android**:
- Idle: _______ MB
- Active game: _______ MB
- Charts view: _______ MB

**Expected**: < 150MB active

### Test 9.4: Battery Drain

**Steps**:
1. Full battery (100%)
2. Use app continuously for 30 minutes
3. Check battery level

**Result**:
- Battery used: _______%
- Expected: < 10% per 30 min

### Test 9.5: Frame Rate

**Tools**: Xcode (iOS), Profile GPU Rendering (Android)

**Expected**: 60 FPS (or 120 FPS on capable devices)

**Measurements**:
- Games list scroll: _______ FPS
- Chart animation: _______ FPS
- Game board: _______ FPS

---

## Part 10: Bug Tracking & Polish (1.5 hours)

### Bug Tracking Template

Use this template for each bug found:

```
BUG #: ___
Title: _______________
Severity: [ ] Critical [ ] High [ ] Medium [ ] Low
Platform: [ ] iOS [ ] Android [ ] Both

Steps to Reproduce:
1.
2.
3.

Expected Behavior:


Actual Behavior:


Screenshots/Videos:


Environment:
- Device: _____________
- OS Version: _____________
- App Version: _____________

Status: [ ] Open [ ] In Progress [ ] Fixed [ ] Won't Fix
```

### Polish Checklist

**UI/UX**:
- [ ] All buttons have proper touch feedback
- [ ] Loading states consistent across app
- [ ] Error messages are helpful and user-friendly
- [ ] Empty states have helpful messages
- [ ] Icons are consistent
- [ ] Colors follow brand guidelines
- [ ] Typography is consistent
- [ ] Spacing is consistent

**Content**:
- [ ] No typos or grammatical errors
- [ ] All text is clear and concise
- [ ] Help text is available where needed
- [ ] Terms are defined (first use)

**Performance**:
- [ ] No janky scrolling
- [ ] Animations are smooth (60 FPS)
- [ ] Images load efficiently
- [ ] No memory leaks

**Accessibility**:
- [ ] Sufficient color contrast (4.5:1 minimum)
- [ ] Text is readable (min 12pt)
- [ ] Touch targets are at least 44x44pt
- [ ] VoiceOver/TalkBack works

---

## Test Report Template

After completing all tests, fill out this summary report:

### Summary

**Testing Date**: _______________
**Tester**: _______________
**App Version**: _______________
**Devices Tested**:
- iOS: _______________
- Android: _______________

### Results

**Total Tests**: _______
**Passed**: _______ (___%)
**Failed**: _______ (___%)
**Blocked**: _______

### Critical Issues

List any critical issues that block release:

1.
2.
3.

### High Priority Issues

List high priority issues that should be fixed before release:

1.
2.
3.

### Medium/Low Priority Issues

List issues that can be fixed post-release:

1.
2.
3.

### Performance Metrics

- Average app launch time: _______ seconds
- Average API response time: _______ ms
- Notification delivery time: _______ seconds
- Memory usage: _______ MB
- Battery drain: _______%/30min

### Recommendation

[ ] **PASS** - Ready for production release
[ ] **PASS WITH CONDITIONS** - Release with minor issues, fix in patch
[ ] **FAIL** - Do not release, critical issues must be fixed

**Conditions (if applicable)**:
_______________________________________________

**Next Steps**:
_______________________________________________

---

## Completion Checklist

Before considering Task 3 complete:

- [ ] All critical and high priority bugs fixed
- [ ] Test report completed and shared
- [ ] 95%+ tests passing
- [ ] Performance metrics meet targets
- [ ] Both iOS and Android tested on physical devices
- [ ] Push notifications working reliably
- [ ] Offline mode functioning correctly
- [ ] No crashes during extended use
- [ ] App approved by project lead/stakeholder

---

**Estimated Completion Time**: 1 day (8 hours)
**Next Step**: Production deployment or beta testing
**Status**: Ready to begin after Firebase configuration complete
