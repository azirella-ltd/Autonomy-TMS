# Phase 7 Sprint 4 - Browser Testing Guide

**Date**: 2026-01-15
**Application URL**: http://localhost:8088
**Test Status**: ⏳ IN PROGRESS

---

## Pre-Testing Setup

### 1. Verify Services Are Running

```bash
# Check all services
docker compose ps

# Expected output:
# ✅ proxy - Up and healthy
# ✅ frontend - Up and healthy
# ✅ backend - Up and healthy
# ✅ db - Up and healthy
```

### 2. Login Credentials

**Default Admin Account**:
- Email: `systemadmin@autonomy.ai`
- Password: `Autonomy@2026`

**Test User** (if needed):
- Create via admin panel or registration

### 3. Test Game Setup

You'll need a game with:
- ✅ AI suggestions enabled
- ✅ Multiple human players (or mixed human/AI)
- ✅ At least 5-10 rounds played
- ✅ Some AI suggestions accepted/rejected

---

## Testing Checklist

### Feature 1: Multi-Turn Conversations (Chat Panel)

**Location**: GameRoom → "Chat" tab

#### Test 1.1: Send First Message ⏳
- [ ] Navigate to Chat tab
- [ ] Verify chat input box visible
- [ ] Type message: "What should I order this round?"
- [ ] Click Send button
- [ ] **Expected**: User message appears in chat
- [ ] **Expected**: AI response appears within 3-5 seconds
- [ ] **Expected**: AI response is contextually relevant

#### Test 1.2: Multi-Turn Context ⏳
- [ ] Send follow-up: "Why do you recommend that?"
- [ ] **Expected**: AI references previous suggestion
- [ ] Send another: "What if demand increases?"
- [ ] **Expected**: AI maintains conversation context

#### Test 1.3: Conversation History ⏳
- [ ] Scroll up in chat
- [ ] **Expected**: Previous messages visible
- [ ] **Expected**: Messages show timestamps
- [ ] **Expected**: User vs AI messages distinguishable

#### Test 1.4: Clear Conversation ⏳
- [ ] Look for "Clear" or "Reset" button
- [ ] Click clear button
- [ ] **Expected**: Confirmation dialog appears
- [ ] Confirm clearing
- [ ] **Expected**: All messages removed
- [ ] **Expected**: Can start new conversation

#### Test 1.5: Conversation Persistence ⏳
- [ ] Send message in Chat tab
- [ ] Switch to another tab (e.g., Game)
- [ ] Return to Chat tab
- [ ] **Expected**: Messages still visible
- [ ] Refresh browser page
- [ ] **Expected**: Conversation history persists

---

### Feature 2: Pattern Analysis (Analytics Tab)

**Location**: GameRoom → "Analytics" tab

#### Test 2.1: Navigate to Analytics ⏳
- [ ] Click "Analytics" tab in GameRoom
- [ ] **Expected**: Analytics panel loads
- [ ] **Expected**: No errors in browser console

#### Test 2.2: View Pattern Badge ⏳
- [ ] Locate "Your Decision Pattern" section
- [ ] **Expected**: Pattern badge visible (Conservative/Aggressive/Balanced/Reactive)
- [ ] **Expected**: Pattern description shown
- [ ] Note which pattern you have: __________

#### Test 2.3: Check Acceptance Rate ⏳
- [ ] Locate "Acceptance Rate" metric
- [ ] **Expected**: Percentage displayed (0-100%)
- [ ] **Expected**: Description: "How often you follow AI suggestions"
- [ ] Note your rate: _____%

#### Test 2.4: Check Modification Rate ⏳
- [ ] Locate "Avg Modification" metric
- [ ] **Expected**: Percentage displayed (0-100%)
- [ ] **Expected**: Description: "How much you adjust recommendations"
- [ ] Note your rate: _____%

#### Test 2.5: View Suggestion History ⏳
- [ ] Scroll to "Suggestion History" table
- [ ] **Expected**: Table with columns: Round, AI Suggested, You Ordered, Status, Score
- [ ] **Expected**: Status badges colored (green=Accepted, yellow=Modified, red=Rejected)
- [ ] **Expected**: Up to 20 recent rounds shown
- [ ] Count rows: _____ rounds

#### Test 2.6: Check AI Effectiveness ⏳
- [ ] Locate "AI Effectiveness" section
- [ ] **Expected**: Shows "AI Suggested" avg score
- [ ] **Expected**: Shows "Player Modified" avg score
- [ ] **Expected**: Shows "Improvement" score (+ or -)
- [ ] **Expected**: Cost savings and service improvement metrics

#### Test 2.7: View Insights ⏳
- [ ] Scroll to "Actionable Insights" section
- [ ] **Expected**: List of insights with 💡 emoji
- [ ] **Expected**: Insights are specific and actionable
- [ ] Read insights - do they make sense?
- [ ] Count insights: _____ insights

#### Test 2.8: Refresh Analytics ⏳
- [ ] Click "Refresh" button (if present)
- [ ] **Expected**: Analytics data reloads
- [ ] **Expected**: No errors
- [ ] **Expected**: Data updates if game state changed

---

### Feature 3: Visibility Dashboard (Visibility Tab)

**Location**: GameRoom → "Visibility" tab

#### Test 3.1: Navigate to Visibility ⏳
- [ ] Click "Visibility" tab
- [ ] **Expected**: Visibility dashboard loads
- [ ] **Expected**: No errors in console

#### Test 3.2: Enable Visibility Sharing ⏳
- [ ] Locate visibility sharing toggles
- [ ] **Expected**: Toggles for: Inventory, Backlog, Orders, Forecast, Costs
- [ ] Enable "Inventory" toggle
- [ ] **Expected**: Toggle turns on (visual feedback)
- [ ] Enable "Backlog" toggle
- [ ] **Expected**: Both toggles active

#### Test 3.3: View Sankey Diagram ⏳
- [ ] Locate Sankey diagram visualization
- [ ] **Expected**: Diagram shows supply chain flow
- [ ] **Expected**: Nodes labeled (Retailer, Wholesaler, Distributor, Factory)
- [ ] **Expected**: Flows show material/order quantities
- [ ] Hover over nodes/flows
- [ ] **Expected**: Tooltips show details

#### Test 3.4: Check Supply Chain Health Score ⏳
- [ ] Locate "Supply Chain Health" section
- [ ] **Expected**: Score displayed (0-100)
- [ ] **Expected**: Score has color indicator (green=good, yellow=moderate, red=poor)
- [ ] **Expected**: Health score components shown:
  - [ ] Inventory balance (30%)
  - [ ] Backlog management (30%)
  - [ ] Cost efficiency (25%)
  - [ ] Service level (15%)
- [ ] Note your score: _____ / 100

#### Test 3.5: View Bottleneck Detection ⏳
- [ ] Locate "Bottlenecks" section
- [ ] **Expected**: Shows which node is bottleneck (if any)
- [ ] **Expected**: Explanation of why it's a bottleneck
- [ ] **Expected**: Recommendations to resolve

#### Test 3.6: Check Bullwhip Severity ⏳
- [ ] Locate "Bullwhip Effect" section
- [ ] **Expected**: Severity level shown (Low/Moderate/High/Critical)
- [ ] **Expected**: Color-coded indicator
- [ ] **Expected**: Explanation of impact
- [ ] Note severity: __________

#### Test 3.7: View Shared Data from Other Players ⏳
- [ ] Look for other players' shared data
- [ ] **Expected**: If other players enabled sharing, their data visible
- [ ] **Expected**: Your own data always visible
- [ ] **Expected**: Non-shared data hidden or grayed out

---

### Feature 4: Agent Negotiation (Negotiate Tab)

**Location**: GameRoom → "Negotiate" tab

#### Test 4.1: Navigate to Negotiations ⏳
- [ ] Click "Negotiate" tab
- [ ] **Expected**: Negotiation panel loads
- [ ] **Expected**: "New Proposal" button visible
- [ ] **Expected**: Negotiations list (may be empty initially)

#### Test 4.2: Create Order Adjustment Negotiation ⏳
- [ ] Click "New Proposal" button
- [ ] **Expected**: Proposal form opens
- [ ] Select target player: (choose from dropdown)
  - [ ] Retailer
  - [ ] Wholesaler
  - [ ] Distributor
  - [ ] Factory
- [ ] Select negotiation type: "Order Adjustment"
- [ ] **Expected**: Form shows "Quantity Change" field
- [ ] Enter quantity change: `+10` (increase by 10)
- [ ] **Optional**: Add message: "Can you order 10 more units?"
- [ ] Click "Create Proposal"
- [ ] **Expected**: Success toast notification
- [ ] **Expected**: Form closes
- [ ] **Expected**: New proposal appears in list

#### Test 4.3: Create Inventory Share Negotiation ⏳
- [ ] Click "New Proposal"
- [ ] Select different target player
- [ ] Select type: "Inventory Share"
- [ ] **Expected**: Form shows:
  - [ ] "Units to Share" field
  - [ ] "Direction" dropdown (Give/Receive)
- [ ] Enter units: `15`
- [ ] Select direction: "Give to them"
- [ ] Click "Create Proposal"
- [ ] **Expected**: Proposal created successfully

#### Test 4.4: Create Lead Time Negotiation ⏳
- [ ] Click "New Proposal"
- [ ] Select type: "Lead Time Change"
- [ ] **Expected**: Form shows:
  - [ ] "Lead Time Change (rounds)" field
  - [ ] "Compensation ($)" field
- [ ] Enter lead time change: `-1` (faster delivery)
- [ ] Enter compensation: `50`
- [ ] Click "Create Proposal"
- [ ] **Expected**: Proposal created

#### Test 4.5: Create Price Adjustment Negotiation ⏳
- [ ] Click "New Proposal"
- [ ] Select type: "Price Adjustment"
- [ ] **Expected**: Form shows:
  - [ ] "Price Change ($/unit)" field
  - [ ] "Volume Commitment" field
- [ ] Enter price change: `-2` (discount)
- [ ] Enter volume commitment: `100`
- [ ] Click "Create Proposal"
- [ ] **Expected**: Proposal created

#### Test 4.6: View Negotiation List ⏳
- [ ] Scroll through negotiations list
- [ ] **Expected**: Each card shows:
  - [ ] From/To roles (e.g., "Retailer → Wholesaler")
  - [ ] Status badge (pending/accepted/rejected)
  - [ ] Negotiation type
  - [ ] Proposal details
  - [ ] Created timestamp
  - [ ] Expiration timestamp (if applicable)
- [ ] Count your negotiations: _____ total

#### Test 4.7: Accept a Negotiation (if you're target) ⏳
- [ ] Find a negotiation where you are the target
- [ ] **Expected**: Accept/Reject buttons visible
- [ ] Click "Accept" button
- [ ] **Expected**: Confirmation toast
- [ ] **Expected**: Status changes to "Accepted"
- [ ] **Expected**: Accept/Reject buttons disappear

#### Test 4.8: Reject a Negotiation ⏳
- [ ] Find another negotiation as target
- [ ] Click "Reject" button
- [ ] **Expected**: Status changes to "Rejected"
- [ ] **Expected**: Buttons disappear

#### Test 4.9: View Expired Negotiations ⏳
- [ ] Wait or look for expired negotiations
- [ ] **Expected**: Status shows "Expired"
- [ ] **Expected**: Cannot accept/reject expired proposals
- [ ] **Expected**: Gray or muted styling

#### Test 4.10: Refresh Negotiations ⏳
- [ ] Click "Refresh" button
- [ ] **Expected**: List reloads
- [ ] **Expected**: New negotiations appear if others created them

---

### Feature 5: Cross-Agent Optimization (AI Panel)

**Location**: GameRoom → "AI" tab → AI Suggestion panel

#### Test 5.1: Navigate to AI Suggestions ⏳
- [ ] Click "AI" tab (or wherever AI suggestions appear)
- [ ] **Expected**: AI suggestion panel visible
- [ ] **Expected**: Existing suggestion buttons visible

#### Test 5.2: Request Global Optimization ⏳
- [ ] Locate "Global" button (purple/distinctive color)
- [ ] **Expected**: Button has globe icon
- [ ] Click "Global" button
- [ ] **Expected**: Loading indicator appears
- [ ] **Expected**: Button disabled during loading
- [ ] Wait 3-5 seconds
- [ ] **Expected**: Global optimization results appear

#### Test 5.3: View Global Recommendations ⏳
- [ ] Locate "Global Optimization" section
- [ ] **Expected**: Shows recommendations for all 4 roles:
  - [ ] Retailer
  - [ ] Wholesaler
  - [ ] Distributor
  - [ ] Factory
- [ ] For each role, verify displays:
  - [ ] Recommended order quantity
  - [ ] Reasoning text
  - [ ] Your role highlighted (if you're one of them)

#### Test 5.4: Check Expected Impact ⏳
- [ ] Scroll to "Expected Impact" metrics
- [ ] **Expected**: Shows:
  - [ ] Cost Reduction (dollars/round)
  - [ ] Service Improvement (percentage)
  - [ ] Bullwhip Reduction (percentage)
- [ ] **Expected**: Values are numeric and reasonable

#### Test 5.5: View Coordination Strategy ⏳
- [ ] Locate "Coordination Strategy" section
- [ ] **Expected**: Text explanation of optimization approach
- [ ] **Expected**: Mentions strategy type:
  - Coordination (synchronized ordering)
  - Rebalancing (inventory redistribution)
  - Stabilization (convergence to equilibrium)

#### Test 5.6: Accept Your Role's Recommendation ⏳
- [ ] Find your role's recommendation card
- [ ] **Expected**: "Accept" button visible for your role only
- [ ] **Expected**: Other roles don't have Accept button (informational only)
- [ ] Click "Accept" for your role
- [ ] **Expected**: Order input field updates to recommended quantity
- [ ] **Expected**: Success feedback

#### Test 5.7: Compare with Single-Node Suggestion ⏳
- [ ] Request regular AI suggestion ("Balance Costs" or other button)
- [ ] **Expected**: Single-node suggestion appears
- [ ] Compare single vs global recommendation:
  - [ ] Are they different?
  - [ ] Does global consider system-wide effects?
  - [ ] Note differences: _____________

---

## Integration Testing

### Test I.1: Multi-Feature Workflow ⏳

**Scenario**: Use analytics to inform negotiations

1. [ ] Go to Analytics tab
2. [ ] Identify your pattern (e.g., "Aggressive")
3. [ ] Note acceptance rate
4. [ ] Go to Negotiate tab
5. [ ] Create negotiation based on pattern insight
6. [ ] Go to AI tab
7. [ ] Request global optimization
8. [ ] Compare global recommendations with your pattern

**Expected**: Features work together coherently

### Test I.2: Data Persistence Across Tabs ⏳

1. [ ] Create negotiation in Negotiate tab
2. [ ] Switch to Analytics tab
3. [ ] Switch to Visibility tab
4. [ ] Return to Negotiate tab
5. [ ] **Expected**: Negotiation still visible
6. [ ] **Expected**: No data loss

### Test I.3: Real-Time Updates ⏳

1. [ ] Have second player (or second browser) create negotiation
2. [ ] Click "Refresh" in your browser
3. [ ] **Expected**: New negotiation appears
4. [ ] Accept/reject in one browser
5. [ ] Refresh in other browser
6. [ ] **Expected**: Status updated

---

## Error Testing

### Test E.1: Empty States ⏳

#### No Suggestions Yet
- [ ] View Analytics with no AI suggestions used
- [ ] **Expected**: Empty state message
- [ ] **Expected**: Prompt to enable AI suggestions

#### No Negotiations
- [ ] View Negotiate tab with no negotiations
- [ ] **Expected**: "No negotiations yet" message
- [ ] **Expected**: "Create First Proposal" button

#### No Conversation History
- [ ] View Chat tab before sending messages
- [ ] **Expected**: Empty chat area
- [ ] **Expected**: Input box available

### Test E.2: Invalid Inputs ⏳

#### Negotiation Form
- [ ] Try to create negotiation without target player
- [ ] **Expected**: Error message "Please select a target player"
- [ ] Try to submit with empty proposal fields
- [ ] **Expected**: Validation error

#### Chat Input
- [ ] Try to send empty message
- [ ] **Expected**: Send button disabled or validation error

### Test E.3: Network Errors ⏳

#### Simulate Slow Network
- [ ] Open browser DevTools (F12)
- [ ] Go to Network tab → Throttling → Slow 3G
- [ ] Request global optimization
- [ ] **Expected**: Loading indicator remains visible
- [ ] **Expected**: Eventually completes or times out gracefully
- [ ] Reset throttling to "No throttling"

#### Backend Down (Optional)
- [ ] Stop backend: `docker compose stop backend`
- [ ] Try to load Analytics tab
- [ ] **Expected**: Error message or retry prompt
- [ ] Start backend: `docker compose start backend`
- [ ] **Expected**: Features work again after refresh

---

## Performance Testing

### Test P.1: Large Conversation ⏳
- [ ] Send 20+ messages in Chat
- [ ] **Expected**: Chat remains responsive
- [ ] **Expected**: Scrolling smooth
- [ ] **Expected**: No memory leaks (check DevTools Memory)

### Test P.2: Many Negotiations ⏳
- [ ] Create 10+ negotiations
- [ ] **Expected**: List renders quickly
- [ ] **Expected**: Scrolling smooth
- [ ] **Expected**: No lag when opening/closing forms

### Test P.3: Complex Visibility Dashboard ⏳
- [ ] Game with 10+ rounds
- [ ] Enable all visibility toggles
- [ ] **Expected**: Sankey diagram renders within 2 seconds
- [ ] **Expected**: Interactions (hover, zoom) responsive

---

## Browser Compatibility

### Test B.1: Chrome ⏳
- [ ] Test all features in Chrome
- [ ] Check console for errors
- [ ] Note Chrome version: __________

### Test B.2: Firefox ⏳
- [ ] Test all features in Firefox
- [ ] Check console for errors
- [ ] Note Firefox version: __________

### Test B.3: Safari (Mac only) ⏳
- [ ] Test all features in Safari
- [ ] Check console for errors
- [ ] Note Safari version: __________

### Test B.4: Edge ⏳
- [ ] Test all features in Edge
- [ ] Check console for errors
- [ ] Note Edge version: __________

---

## Console Error Check

### During All Tests ⏳
- [ ] Keep browser DevTools console open (F12)
- [ ] Monitor for errors during testing
- [ ] **Expected**: No red error messages
- [ ] **Acceptable**: Yellow warnings (non-critical)
- [ ] **Record any errors found**: _____________

---

## Accessibility Testing

### Test A.1: Keyboard Navigation ⏳
- [ ] Navigate tabs using Tab key
- [ ] **Expected**: Focus visible and logical order
- [ ] Press Enter to activate buttons
- [ ] **Expected**: Buttons activate

### Test A.2: Screen Reader (Optional) ⏳
- [ ] Enable screen reader (NVDA/JAWS/VoiceOver)
- [ ] Navigate through features
- [ ] **Expected**: Elements announced clearly
- [ ] **Expected**: Buttons have descriptive labels

---

## Mobile Testing (Optional)

### Test M.1: Responsive Design ⏳
- [ ] Resize browser to mobile width (375px)
- [ ] **Expected**: Layout adapts
- [ ] **Expected**: Tabs stack or scroll horizontally
- [ ] **Expected**: Forms remain usable

### Test M.2: Touch Interactions ⏳
- [ ] Test on actual mobile device or tablet
- [ ] **Expected**: Buttons large enough to tap
- [ ] **Expected**: Scrolling smooth
- [ ] **Expected**: No hover-dependent features broken

---

## Bug Report Template

If you find issues, document using this template:

```markdown
## Bug Report

**Feature**: [Feature name]
**Severity**: [Critical/High/Medium/Low]
**Browser**: [Chrome/Firefox/Safari/Edge] version X

### Steps to Reproduce
1. Step 1
2. Step 2
3. Step 3

### Expected Behavior
[What should happen]

### Actual Behavior
[What actually happened]

### Screenshots
[Attach screenshots if applicable]

### Console Errors
[Copy any console errors]

### Additional Context
[Any other relevant information]
```

---

## Test Results Summary

### Overall Status: ⏳ IN PROGRESS

| Feature | Status | Pass Rate | Notes |
|---------|--------|-----------|-------|
| Multi-Turn Conversations | ⏳ | __/8 | |
| Pattern Analysis | ⏳ | __/8 | |
| Visibility Dashboard | ⏳ | __/7 | |
| Agent Negotiation | ⏳ | __/10 | |
| Global Optimization | ⏳ | __/7 | |
| Integration | ⏳ | __/3 | |
| Error Handling | ⏳ | __/3 | |
| Performance | ⏳ | __/3 | |

**Total Tests**: 49 individual tests
**Tests Passed**: ____ / 49
**Pass Rate**: _____%

---

## Completion Checklist

- [ ] All 5 features tested individually
- [ ] Integration scenarios tested
- [ ] Error handling verified
- [ ] Performance acceptable
- [ ] No critical bugs found
- [ ] Browser compatibility confirmed
- [ ] Console errors documented
- [ ] Test results documented
- [ ] Screenshots captured (optional)
- [ ] Bug reports filed (if any)

---

## Next Steps After Testing

### If All Tests Pass ✅
1. Mark Sprint 4 as Production Ready
2. Update documentation with test results
3. Plan user training/onboarding
4. Begin Sprint 5 planning

### If Issues Found ❌
1. Prioritize bugs (Critical → Low)
2. Fix critical and high-priority bugs
3. Retest affected features
4. Repeat until all tests pass

---

**Testing Started**: __________
**Testing Completed**: __________
**Tester Name**: __________
**Overall Result**: ⏳ PENDING
