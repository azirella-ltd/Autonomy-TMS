# Powell Framework Dashboard Demo

**Autonomy Platform - AI-as-Labor Operating Model**

*Demo Duration: 5-7 minutes*

---

## Executive Summary

This demo showcases Autonomy's **Powell Framework Dashboards** - role-based views aligned to the AI-as-Labor operating model. The system supports three persona-based landing pages:

| Role | Landing Page | Focus |
|------|--------------|-------|
| **SC_VP** | Executive Dashboard | Strategic performance metrics, ROI |
| **SOP_DIRECTOR** | S&OP Worklist | Tactical worklist, agent recommendations |
| **MPS_MANAGER** | Agent Decisions | Operational execution monitoring |

**Key Value Propositions:**
1. AI agents own decisions by default (AI-as-Labor)
2. Humans override with reasoning captured (governance)
3. Agent Performance Score measures AI vs baseline
4. Human Override Rate measures automation adoption
5. Override reasons feed back for continuous learning (RLHF)

---

## Demo Setup

### Option A: Terminal Preview (No Server Required)
```bash
cd backend
pip install rich  # if not installed
python scripts/demo_powell_dashboards.py
```

### Option B: Full UI Demo (Recommended)
```bash
# Start the full stack
make up

# Seed demo data
docker compose exec backend python scripts/seed_dot_foods_demo.py

# Or seed from the demo script
python scripts/demo_powell_dashboards.py --seed
```

**URL:** http://localhost:8088

### Demo Login Credentials

| User | Email | Password | Access |
|------|-------|----------|--------|
| **Demo (All Roles)** | demo@distdemo.com | Autonomy@2025 | All dashboards |
| SC_VP | scvp@distdemo.com | Autonomy@2025 | Executive Dashboard only |
| SOP_DIRECTOR | sopdir@distdemo.com | Autonomy@2025 | S&OP Worklist only |
| MPS_MANAGER | mpsmanager@distdemo.com | Autonomy@2025 | Agent Decisions only |

**Recommendation:** Use `demo@distdemo.com` for demos to avoid login/logout.

---

## Demo Flow

### Act 1: Login & Overview (30 sec)

**Action:** Login as demo@distdemo.com

**Talking Points:**

> "I'm logging in as a demo user that has access to all Powell Framework dashboards. In production, users would have role-specific access based on their capabilities."

> "Notice I land on the Executive Dashboard automatically. The system detects that I have the `view_executive_dashboard` capability and routes me to the appropriate dashboard."

> "This demo user has ALL Powell capabilities combined, so I can navigate between all dashboards without logging out."

---

### Act 2: Executive Dashboard (1.5 min)

**URL:** /executive-dashboard

**Show:** KPI Cards

| Metric | Value | Meaning |
|--------|-------|---------|
| **Agent Score** | +42 | Agent Performance Score - agent decisions are 42 points better than baseline |
| **Override Rate** | 22% | Human Override Rate - 22% of decisions overridden by humans |
| **Touchless Rate** | 65% | 65% executed without any human intervention |
| **Override Ratio** | 22% | 22% of decisions overridden by humans |

**Talking Points:**

> "This is the Executive Dashboard - the strategic view for VP-level users."

> "The key metric is the Agent Performance Score. It measures how well the AI agent is performing compared to a baseline. A positive score means the agent is adding value."

> "The Human Override Rate shows what percentage of decisions humans are overriding. 22% means planners trust the AI for most decisions."

> "The Touchless Rate is the holy grail - 65% of decisions execute without ANY human touch. That's real automation."

---

### Act 3: S&OP Worklist (2 min)

**Navigate:** Click "S&OP Worklist" in navigation

**URL:** /sop-worklist

**Show:** Worklist Items

| ID | Type | Agent Recommendation | Confidence | Status |
|----|------|---------------------|------------|--------|
| WL-001 | Safety Stock | Increase to 2.5 weeks | 87% | Pending |
| WL-002 | Expedite | Rush order recommended | 92% | Pending |
| WL-003 | Allocation | +15% strategic reserve | 78% | Pending |

**Talking Points:**

> "The S&OP Worklist is where tactical planners spend their time. It's a prioritized list of exceptions that need human attention."

> "Notice each item shows the agent's recommendation and a confidence score. High confidence items might just need a quick approval."

**Action:** Click "Ask Why" on WL-001

**Show:** Agent Reasoning Modal

> "Here's the key differentiator - Ask Why. The agent doesn't just give you a recommendation, it EXPLAINS why."

> "You can see the evidence: specific orders that had stockouts, demand variance data, lead time changes. The agent shows its work."

> "The confidence score tells you how reliable this recommendation is. 87% is pretty high - the agent is confident in this one."

**Action:** Click "Override" to show override capture

> "If I disagree, I click Override. Notice I have to provide a reason. This is governance - we track WHY humans override the AI."

> "These override reasons become training data. The system learns from human expertise."

---

### Act 4: Agent Performance (1 min)

**Navigate:** Click "Agent Performance" in navigation

**URL:** /agent-performance

**Show:** Performance Breakdown by Category

| Decision Type | Agent Score | User Score | Override Rate |
|---------------|------------|------------|---------------|
| Safety Stock | +48 | +35 | 18% |
| Order Quantity | +52 | +41 | 15% |
| Expedite | +28 | +45 | 42% |
| Allocation | +55 | +38 | 12% |

**Talking Points:**

> "Agent Performance shows detailed analysis - agent vs human performance by decision type."

> "Look at Safety Stock - the agent scores +48, humans score +35. The agent is outperforming on this category."

> "But look at Expedite - humans score +45, agent only +28. Human expertise is still valuable here."

> "This tells us: give the agent more autonomy on Safety Stock, keep humans in the loop for Expedites."

---

### Act 5: Summary & Key Takeaways (1 min)

**Talking Points:**

> "To summarize the Powell Framework approach:"

> "ONE - AI-as-Labor. Agents own decisions by default. Humans override, not approve."

> "TWO - Transparency. Ask Why shows agent reasoning with evidence."

> "THREE - Governance. Override reasons captured for audit and learning."

> "FOUR - Measurement. Agent Performance Scores and Override Rates prove AI value over time."

> "FIVE - Continuous Improvement. Human overrides train better agents."

---

## Key Metrics Reference

### Agent Performance Score

| Score | Meaning |
|-------|---------|
| +50 to +100 | Excellent - agent significantly outperforms baseline |
| +20 to +49 | Good - agent adds measurable value |
| 0 to +19 | Neutral - on par with baseline |
| -1 to -50 | Poor - agent underperforms, needs training |
| -51 to -100 | Critical - immediate attention required |

### Human Override Rate

| Range | Meaning |
|-------|---------|
| 0-10% | Fully autonomous - minimal human oversight |
| 11-30% | High trust - occasional overrides |
| 31-50% | Moderate - regular human review |
| 51-70% | Low trust - frequent overrides |
| 71-100% | Pilot mode - humans override most decisions |

---

## Q&A Talking Points

**Q: What's the difference between Agent Performance Score and Override Rate?**
> "Agent Performance Score measures decision QUALITY - how good are the decisions. Override Rate measures ADOPTION - how much humans trust the AI. You can have a high Agent Score but high Override Rate if humans don't trust it yet."

**Q: How do override reasons improve the AI?**
> "Every override with a reason becomes a training example. If users consistently override a certain pattern with similar reasons, the system learns to adjust. It's like RLHF for enterprise planning."

**Q: Can we track individual planner performance?**
> "Yes - we measure User Score alongside Agent Score. If a planner consistently makes better decisions than the agent, that expertise gets captured in the feedback loop."

**Q: What happens when Override Rate is high?**
> "High Override Rate means humans are overriding a lot. Either the agent needs more training, or we need to identify specific decision types where humans add value. The Agent Performance breakdown helps diagnose this."

---

## Recording Tips

1. **Terminal Preview First**: Run the terminal demo to familiarize yourself
2. **Browser Full Screen**: Use full-screen browser for clean recording
3. **Slow Mouse Movements**: Move deliberately for viewers to follow
4. **Pause on Modals**: Let Ask Why modal display for 3-4 seconds
5. **Narrate Actions**: Say what you're clicking before clicking

## Command Reference

```bash
# Terminal preview (with pauses)
python scripts/demo_powell_dashboards.py

# Video recording mode (3-second delays)
python scripts/demo_powell_dashboards.py --no-pause

# Seed data and run
python scripts/demo_powell_dashboards.py --seed

# Custom delay (5 seconds)
python scripts/demo_powell_dashboards.py --no-pause --delay 5
```

---

## Technical Reference

### Routes
- `/executive-dashboard` - SC_VP landing (requires `view_executive_dashboard`)
- `/sop-worklist` - SOP_DIRECTOR landing (requires `view_sop_worklist`)
- `/agent-performance` - Detailed analysis (requires `view_executive_dashboard`)
- `/insights/actions` - MPS_MANAGER landing (requires `view_agent_decisions`)

### Capabilities
- `view_executive_dashboard` - SC_VP strategic view
- `view_sop_worklist` - SOP_DIRECTOR tactical worklist
- `view_agent_decisions` - MPS_MANAGER operational view

### Files
- Frontend Pages: `frontend/src/pages/ExecutiveDashboard.jsx`, `SOPWorklistPage.jsx`
- Navigation: `frontend/src/config/navigationConfig.js`
- Capabilities: `backend/app/core/capabilities.py`
- Demo Seed: `backend/scripts/seed_dot_foods_demo.py`
