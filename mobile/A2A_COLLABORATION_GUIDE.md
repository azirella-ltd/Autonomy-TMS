# A2A Collaboration Guide

**Agent-to-Agent (A2A) Real-time Collaboration**

Complete user guide for chatting with AI agents during gameplay.

---

## Table of Contents

1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Chat Interface](#chat-interface)
4. [Agent Suggestions](#agent-suggestions)
5. [Message Types](#message-types)
6. [Best Practices](#best-practices)
7. [Troubleshooting](#troubleshooting)

---

## Introduction

### What is A2A Collaboration?

A2A (Agent-to-Agent) Collaboration enables real-time chat between human players and AI agents during gameplay. Get instant suggestions, ask questions, and make better supply chain decisions with AI assistance.

### Key Features

- 💬 **Real-time Chat** - Instant messaging with AI agents
- 💡 **Smart Suggestions** - AI-powered order recommendations
- 📊 **Context-Aware Advice** - Suggestions based on current game state
- 🎯 **Confidence Levels** - Know how confident the AI is
- 📈 **Performance Insights** - Understand supply chain metrics

---

## Getting Started

### Opening Chat

1. **Navigate to Game Detail Screen**
   - Open any active game
   - View game status and progress

2. **Tap the Chat FAB**
   - Look for the floating 💬 button in bottom-right
   - Badge shows unread message count
   - Tap to open full-screen chat

3. **Start Chatting**
   - Type your message in the input box
   - Press Send or hit Enter
   - Agent responds in real-time

### First Conversation

**Example 1: Request a Suggestion**
```
You: "What should I order this round?"

🤖 Wholesaler Agent: "I recommend ordering 45 units."

[Suggestion Card appears]
- Order: 45 units
- Confidence: 85%
- Rationale: Recent demand trending up, low inventory...
[Accept] [Decline]
```

**Example 2: Ask a Question**
```
You: "Why is my backlog increasing?"

🤖 Wholesaler Agent: "Your backlog is increasing because:
- Recent demand spike from 30 to 48 units
- Current orders only delivering 35 units
- Inventory depleted to 12 units
- I recommend increasing your order to 50 units"
```

---

## Chat Interface

### Main Components

```
┌─────────────────────────────────┐
│ [🤖] [💡] Messages         [✕]  │  ← Header
├─────────────────────────────────┤
│ ┌─ Suggestion ─────────────┐   │
│ │ 🤖 Order: 45 units        │   │  ← Suggestion Panel
│ │ Confidence: 85%           │   │
│ │ [Accept] [Decline]        │   │
│ └───────────────────────────┘   │
├─────────────────────────────────┤
│                                 │
│ Today                           │  ← Date Separator
│                                 │
│ 🤖 Wholesaler:                  │
│ "I recommend 45 units..."       │  ← Agent Message
│                                 │
│ You:                            │
│ "Why 45 instead of 40?"         │  ← Your Message
│                                 │
│ 🤖 Wholesaler is typing...      │  ← Typing Indicator
│                                 │
├─────────────────────────────────┤
│ [Type a message...       Send]  │  ← Input
└─────────────────────────────────┘
```

### Header Icons

| Icon | Function |
|------|----------|
| 🤖 | Request agent suggestion |
| 💡 | Toggle suggestion panel |
| ✕ | Close chat |

### Message Types

**Agent Messages** (Left side, gray bubble)
- Agent emoji (🏪 🏭 🚛 🏗️)
- Agent name
- Message content
- Timestamp
- Metadata (for suggestions/analysis)

**Your Messages** (Right side, blue bubble)
- "You" label
- Message content
- Timestamp
- Delivery status (⏳ ✓ ✓✓)

### Status Indicators

| Symbol | Meaning |
|--------|---------|
| ⏳ | Message sending |
| ✓ | Message delivered |
| ✓✓ | Message read by agent |

---

## Agent Suggestions

### What are Suggestions?

AI agents provide order quantity recommendations based on:
- Current inventory levels
- Current backlog
- Recent demand patterns
- Forecasted future demand
- Supply chain position

### Suggestion Card

```
┌─────────────────────────────────┐
│ 🤖 Wholesaler Agent Suggestion  │
├─────────────────────────────────┤
│ Recommended Order: 45 units     │
│                                 │
│ Confidence: ████████░░ 85%      │
│                                 │
│ Rationale:                      │
│ • Recent demand trending up     │
│ • Low current inventory (50)    │
│ • Avoid backlog increase        │
│ • GNN forecast: 48 units        │
│                                 │
│ Context:                        │
│ • Current Inventory: 50         │
│ • Current Backlog: 10           │
│ • Avg Recent Demand: 42         │
│ • Forecast Demand: 48           │
│                                 │
│ [Accept Suggestion] [Decline]   │
└─────────────────────────────────┘
```

### Confidence Levels

| Color | Range | Interpretation |
|-------|-------|----------------|
| 🟢 Green | 80-100% | High confidence - strongly recommended |
| 🟠 Orange | 60-79% | Medium confidence - consider carefully |
| 🔴 Red | 0-59% | Low confidence - use with caution |

### Accepting Suggestions

**When to Accept:**
- ✅ High confidence (80%+)
- ✅ Rationale makes sense
- ✅ Context aligns with your strategy
- ✅ Agent has been accurate previously

**When to Decline:**
- ❌ Low confidence (<60%)
- ❌ Rationale doesn't match your strategy
- ❌ You have better information
- ❌ Testing a different approach

### Requesting Suggestions

1. **Tap 🤖 Icon** in chat header
2. **Wait for Response** (2-3 seconds)
3. **Review Suggestion Card**
4. **Accept or Decline**

Agents use:
- Current game state
- Historical patterns
- ML forecasting models
- Supply chain optimization algorithms

---

## Message Types

### 1. Text Messages

Simple conversational messages.

**Example:**
```
You: "How's the supply chain looking?"

🤖 Wholesaler: "Overall stable. Inventory healthy
at 65 units. Demand consistent around 40 units
per round."
```

### 2. Suggestions

Order recommendations with confidence and rationale.

**Example:**
```
🤖 Wholesaler Suggestion:
Order: 45 units
Confidence: 85%

💡 Rationale:
Recent demand trending up. Your current inventory
of 50 units won't cover the forecasted demand of
48 units plus safety stock.
```

### 3. Questions

Ask agents specific questions about the game.

**Common Questions:**
- "What should I order?"
- "Why is my backlog high?"
- "What's causing the demand spike?"
- "How's my performance?"
- "What happens if I order 50 units?"

### 4. Analysis

Agent-provided insights and metrics.

**Example:**
```
🤖 Wholesaler Analysis:
📊 Bullwhip Ratio: 1.8 (improving)
📈 Service Level: 92%
💰 Total Cost: $3,450
🎯 Safety Stock: Adequate

Your performance is strong this game!
```

---

## Best Practices

### Communication Tips

**DO:**
- ✅ Be specific with questions
- ✅ Ask for rationale
- ✅ Request suggestions early in round
- ✅ Share your strategy with agents
- ✅ Ask "what if" questions

**DON'T:**
- ❌ Ignore high-confidence suggestions
- ❌ Ask too many questions at once
- ❌ Rely blindly on suggestions
- ❌ Dismiss agent advice without review

### Strategy Integration

**1. Pre-Round Planning**
```
You: "What should I order this round?"
Agent: [Provides suggestion]
You: [Review context and accept/decline]
```

**2. Mid-Game Adjustments**
```
You: "My backlog is growing. What should I do?"
Agent: "Increase order to 55 units. Your current
order of 40 isn't covering demand of 48."
```

**3. Performance Review**
```
You: "How am I doing compared to optimal?"
Agent: "Your service level is 89%, 3% below target.
Consider maintaining higher safety stock."
```

### When to Trust Agents

**High Trust Scenarios:**
- 🟢 Confidence >80%
- 🟢 Stable demand patterns
- 🟢 Agent performance history good
- 🟢 Rationale aligns with data

**Low Trust Scenarios:**
- 🔴 Confidence <60%
- 🔴 Volatile demand patterns
- 🔴 Agent made recent errors
- 🔴 Rationale unclear

---

## Troubleshooting

### Messages Not Sending

**Symptoms:**
- Message stuck with ⏳ status
- No agent response

**Solutions:**
1. Check internet connection
2. Close and reopen chat
3. Restart app
4. Check server status

### Agent Not Responding

**Symptoms:**
- No typing indicator
- No response after 10+ seconds

**Solutions:**
1. Tap 🤖 to request suggestion again
2. Ask a different question
3. Check if agent is online
4. Report issue to support

### Suggestions Not Appearing

**Symptoms:**
- Request sent but no suggestion card
- Empty suggestion panel

**Solutions:**
1. Wait 3-5 seconds for processing
2. Request again
3. Check game is active
4. Refresh game state

### Chat Performance Slow

**Symptoms:**
- Laggy scrolling
- Slow message delivery
- UI freezes

**Solutions:**
1. Close other apps
2. Clear chat history (100+ messages)
3. Restart app
4. Update to latest version

---

## Advanced Features

### Multi-Agent Coordination

Chat with multiple agents simultaneously:

```
You: "Everyone, what do you think about ordering 50?"

🏪 Retailer: "50 is too high for me, I'd do 40"
🏭 Wholesaler: "50 works for me, demand is rising"
🚛 Distributor: "I agree with 50, safety stock needed"
```

Agents can:
- See each other's messages
- Coordinate recommendations
- Reach consensus
- Highlight disagreements

### What-If Analysis

Ask hypothetical questions:

```
You: "What if I order 50 instead of 40?"

🤖 Agent: "Ordering 50 vs 40:
+ Inventory increases by 10
+ Backlog reduced by 8
+ Service level improves to 95%
- Holding cost increases by $150
Overall: Recommended if demand stays high"
```

### Historical Context

Agents remember:
- Previous suggestions
- Your acceptance rate
- Past performance
- Strategy preferences

```
You: "What did you suggest last round?"

🤖 Agent: "Last round I suggested 42 units
(confidence 78%). You ordered 45 instead.
Actual demand was 44, so your decision was good!"
```

---

## FAQ

### How many agents can I chat with?
All AI agents in your supply chain (typically 3-4).

### Do agents see my messages to other agents?
Yes, in broadcast mode. Direct messages are private.

### Can I chat with other human players?
Not yet - A2A is currently agent-only.

### Are chat histories saved?
Yes, full chat history is saved per game.

### Can I delete messages?
Not currently supported.

### How does the AI generate suggestions?
Combination of ML forecasting, game state analysis, and optimization algorithms.

### Is there a message limit?
500 characters per message, unlimited messages.

### Can I use chat offline?
Messages queue while offline and send when reconnected.

---

## Keyboard Shortcuts

### iOS
- **Send Message**: Return key
- **New Line**: Shift + Return
- **Close Chat**: Swipe down

### Android
- **Send Message**: Enter key
- **New Line**: Shift + Enter
- **Close Chat**: Back button

---

## Privacy & Data

### What's Stored?
- Chat messages
- Agent suggestions
- Acceptance/decline history
- Performance metrics

### What's NOT Stored?
- Personal information
- Messages to other players
- Voice or video

### Who Can See My Chats?
- Only you and AI agents in your game
- System administrators (for support)
- No other players

---

## Tips for Success

### 🎯 Getting Better Suggestions
1. Request early in the round
2. Provide context in messages
3. Accept/decline with rationale
4. Build trust with agents

### 📈 Improving Performance
1. Review suggestion rationale
2. Understand confidence levels
3. Track acceptance rate
4. Learn from agent explanations

### 🤝 Effective Collaboration
1. Ask clarifying questions
2. Share your strategy
3. Explain your decisions
4. Request analysis regularly

---

## Support

### Need Help?
- 📧 Email: support@beergame.com
- 💬 In-app chat: Settings → Support
- 📚 Docs: docs.beergame.com/a2a

### Report Issues
1. Tap ⚙️ in chat header
2. Select "Report Issue"
3. Describe the problem
4. Submit with screenshots

---

**A2A Collaboration Guide v1.0**
**Last Updated**: 2026-01-14

---

*Make smarter decisions with AI assistance!* 🤖💡✨
