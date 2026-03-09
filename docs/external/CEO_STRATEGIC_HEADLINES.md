![Azirella](../Azirella_Logo.jpg)

> **STRICTLY CONFIDENTIAL AND PROPRIETARY**
> Copyright © 2026 Azirella Ltd. All rights reserved worldwide.
> Unauthorized access, use, reproduction, or distribution of this document or any portion thereof is strictly prohibited and may result in severe civil and criminal penalties.

# Autonomy: Strategic Headlines

**Document Type**: Amazon 6-Pager Executive Brief
**Version**: 1.0
**Date**: January 29, 2026
**Prepared for**: CEO / Board Review

---

## Introduction

Autonomy is an enterprise supply chain planning platform that combines AWS Supply Chain data model compliance with AI-powered decision automation and simulation-based validation. The platform, now branded "Autonomy," represents a new approach to supply chain planning: continuous autonomous planning that acknowledges uncertainty, validates AI before deployment, and costs 90% less than legacy alternatives.

This document summarizes our strategic position, the decisions we face, and the path forward. After completing a comprehensive architectural refactoring, we have transitioned from a technical buildout phase to a customer acquisition phase. The core question is no longer "can we build this?" but "can we prove it works for real customers?"

---

## Part 1: The Problem We Solve

The enterprise planning software market generates $15B annually, dominated by Kinaxis RapidResponse, SAP IBP, and OMP Plus. These systems cost $100K-$500K per user per year, require 12-18 month implementations costing $2-5M+ in consulting fees, and fail 40-60% of the time. Meanwhile, 60% of mid-market companies still rely on Excel for supply chain planning.

The pain points are consistent across our target market. Legacy systems are prohibitively expensive for mid-market companies with $100M-$1B in revenue. Configuration takes months and adapts poorly to changing business conditions. AI recommendations operate as black boxes, building distrust rather than confidence. And deterministic planning—the industry standard—ignores the uncertainty that supply chain professionals face daily.

Our hypothesis is that mid-market manufacturers are underserved by these legacy systems and are receptive to three value propositions: lower-cost alternatives with comparable functionality, AI that can be validated before production deployment, and probabilistic planning that acknowledges uncertainty rather than pretending it doesn't exist.

We assign medium confidence to this hypothesis. The pain points are real and documented, but we lack direct customer validation that our specific approach addresses them better than competitors or the status quo.

---

## Part 2: Our Strategic Approach

We compete on three differentiated axes where legacy systems are weakest.

**Trust through validation, not faith.** Legacy systems ask customers to trust black-box AI recommendations from day one. We enable customers to validate AI agents in a simulation environment before production deployment. When humans compete against AI in supply chain simulations—using the same engine as production—they see exactly how the AI performs under stress. Trust is earned, not assumed.

**Probabilistic outcomes, not point estimates.** Legacy systems produce deterministic plans with single-point forecasts, then add safety stock as a buffer against reality. We model uncertainty explicitly using 20 distribution types for operational variables, Monte Carlo simulation with 1,000+ scenarios, and conformal prediction for formal guarantees. Customers see likelihood distributions for KPIs: "85% chance service level exceeds 95%" rather than "projected service level: 97%."

**Radical cost reduction.** Our target price is $10K per user per year—a 90% reduction from Kinaxis at $250K+. This opens the mid-market segment that legacy vendors have priced out of sophisticated planning tools.

These three axes support our vision of continuous autonomous planning: AI agents that monitor conditions in real-time, generate plans probabilistically, explain their reasoning, and adapt without waiting for monthly planning cycles. The architecture to support this—event-driven triggers, plan versioning, agent orchestration with guardrails, and human-in-the-loop approval workflows—is now complete.

---

## Part 3: Current State and Capabilities

The platform has reached technical maturity. We have achieved 100% compliance with the AWS Supply Chain data model and approximately 88% feature parity with AWS Supply Chain capabilities. Order Management is 95% complete, analytics and visibility are 85% complete, and demand planning viewing is complete (adjustment UI remains at 60%).

Our AI agent system offers three approaches for different use cases. TRM (Tiny Recursive Model) is a 7M-parameter transformer that delivers sub-10ms inference for high-frequency decisions. GNN (Graph Neural Network) uses 128M parameters with temporal message passing for demand prediction. LLM agents leverage GPT-4 for multi-agent orchestration with natural language explainability. In simulations, these agents demonstrate 20-35% cost reduction versus naive ordering policies.

The stochastic planning framework is complete, including Monte Carlo simulation, variance reduction techniques, and a probabilistic balanced scorecard covering financial, customer, operational, and strategic metrics. The simulation module—originally the core product as "The Beer Game"—now serves as a validation and training tool within the broader Autonomy platform.

The architectural refactoring that repositioned us from "Beer Game with planning features" to "AWS SC platform with AI and simulation" has been completed. Navigation now prioritizes Planning, Execution, and AI Agents, with Simulation as a supporting capability. The UI displays Autonomy branding throughout.

---

## Part 4: The Uncomfortable Truths

Before discussing strategy, we must acknowledge the constraints we operate under.

**Our AI claims are unvalidated in production.** The "20-35% cost reduction" figure appears in our materials, but it derives entirely from Beer Game simulations, not real supply chains with real data. Until we prove this on customer networks, it remains a hypothesis. Sales teams must qualify this claim or risk credibility damage.

**We have zero reference customers.** Enterprise buyers require references. Without them, we are limited to visionaries willing to take risk (rare), free pilots to prove value (expensive for us), or low-price deals to reduce buyer risk (margin compression). Sales cycles will be long until we secure 2-3 referenceable customers.

**LLM agents carry operational risk.** At scale, OpenAI API costs could reach $10K+ monthly. API outages would impact customers. Model changes could alter agent behavior unexpectedly. We must build fallback mechanisms and cost controls before enterprise deployment.

These truths shape our go-to-market approach. We cannot sell enterprise contracts on unvalidated claims. We must prove performance before scaling.

---

## Part 5: Strategic Decisions and Path Forward

**Market positioning.** We have chosen to position as an "AI Planning Copilot for Mid-Market" rather than attempting to compete directly as an enterprise AWS SC alternative. The platform is technically ready for enterprise positioning, but market validation with mid-market customers reduces risk. We will expand to enterprise positioning after securing 3-5 reference customers.

Our beachhead market is mid-market discrete manufacturers with $100M-$500M revenue currently using Excel or basic ERP planning modules. These companies are underserved by Kinaxis and SAP (too expensive), feel acute pain from manual processes, are willing to try new approaches (not locked into 10-year contracts), and can become references for larger deals.

**AI agent strategy.** We will prioritize LLM agents for initial customers because explainability is critical for building trust. Early adopters need to understand why AI made decisions; LLM agents provide natural language explanations. TRM agents will be positioned for scale and cost optimization after trust is established.

**Pricing structure.** We propose three tiers: Starter (free) provides simulation and basic analytics to drive awareness. Professional ($2,500/month) includes LLM agents, custom configurations, and data export. Enterprise ($10,000/month) adds SSO, multi-tenancy, audit logs, and 24/7 support. Add-on services include GNN training ($5,000 setup + $500/month compute) and custom agent development ($15,000 per agent).

**Go-to-market phases.** Phase 1 (Q1 2026): Secure 3 reference customers with documented ROI through free 90-day pilots. Success criteria: 3 customers with >10% cost reduction or >5% service level improvement. Phase 2 (Q2 2026): Public launch with case studies, press coverage, and conference presence. Success criteria: 10 qualified leads per month, 2-3 closed deals. Phase 3 (Q3-Q4 2026): Scale with 2 account executives, 2-3 SI partners, and expansion to adjacent segments. Success criteria: 10 enterprise customers, $1M ARR.

---

## Part 6: Financials, Risks, and Success Metrics

**Financial projections.** We target 10 enterprise customers by end of Year 1 with average contracts of $100K annually. Conservative projections show 5 customers and $500K ARR; base case shows 10 customers and $1M ARR; optimistic projections reach 20 customers and $2M ARR. We assign low confidence to these projections given no historical data.

Monthly fixed costs total approximately $120K-$130K (engineering $80K, infrastructure $5K, OpenAI API $2K-$10K, sales/marketing $20K, G&A $15K). Break-even requires approximately 12-15 customers at Professional tier. Required runway to profitability is 18-24 months ($2.2M-$2.9M).

**Risk assessment.** Technical risks include AI agent underperformance in production (medium probability, high impact—mitigated by pilot programs) and LLM API costs exceeding budget (medium probability, medium impact—mitigated by TRM fallback). Market risks include legacy vendors cutting prices (medium probability, high impact—mitigated by focusing on AI differentiation rather than price alone) and long enterprise sales cycles (high probability, medium impact—mitigated by starting with mid-market). Execution risks include engineering bandwidth constraints (high probability, high impact—mitigated by prioritizing customer-facing features) and lack of reference customers (high probability, high impact—mitigated by offering free pilots).

**Success metrics.** At 90 days: 3 pilot customers signed, 2 pilots in production, AI agent performance validated with at least 1 customer. At 6 months: 5 paying customers, $300K ARR, 2 published case studies, NPS >40. At 12 months: 10 paying customers, $1M ARR, gross margin >70%, customer churn <20%.

---

## Conclusion

Autonomy has a strong technical foundation: 100% AWS SC compliance, working AI agents, complete stochastic framework, and a clear vision of continuous autonomous planning. We have a differentiated approach through simulation-based validation, probabilistic planning, and AI explainability, with a 90% cost advantage over legacy systems.

What we need is customer validation—real-world proof that AI delivers promised results. This is our highest priority. We need 2-3 documented successes for sales credibility and must complete the whole product with implementation playbooks, support organization, and partner ecosystem.

The strategic choice before us follows Rumelt's framework for good strategy: we have a clear diagnosis (legacy systems are expensive and opaque), a guiding policy (continuous autonomous planning with transparent validation), and we are defining coherent actions (pilots, validation, launch).

The risk is premature scaling. Per Moore's Crossing the Chasm framework, success requires dominance in a beachhead before expansion. Our beachhead is mid-market manufacturers frustrated with Excel but priced out of Kinaxis.

**The path to success is not building more features—it's proving the features we have work for real customers.**

---

## Appendix: Capability Summary

| Capability | Status | Confidence |
|------------|--------|------------|
| AWS SC Data Model | 100% | High |
| Demand Planning (view) | Complete | High |
| Supply Planning (MRP) | Complete | High |
| Order Management | 95% | High |
| AI Agent - TRM | Functional | Medium |
| AI Agent - GNN | Functional | Medium |
| AI Agent - LLM | Functional | Medium |
| Stochastic Planning | Complete | Medium |
| Event-Driven Planning | Complete | High |
| Approval Workflows | Complete | High |
| Simulation Module | Complete | High |
| UI Rebranding | Complete | High |

---

*This document synthesizes EXECUTIVE_SUMMARY.md, CONTINUOUS_PLANNING_BUSINESS_GUIDE.md, AWS_SC_100_PERCENT_COMPLETE.md, and related materials using frameworks from Good Strategy Bad Strategy (Rumelt) and Crossing the Chasm (Moore).*

---


---

![Azirella](../Azirella_Logo.jpg)

> **Copyright © 2026 Azirella Ltd. All rights reserved worldwide.**
> This document and all information contained herein are the exclusive confidential and proprietary property of Azirella Ltd, 27, 25 Martiou St., #105, 2408 Engomi, Nicosia, Cyprus. No part of this document may be reproduced, stored in a retrieval system, transmitted, distributed, or disclosed in any form or by any means — electronic, mechanical, photocopying, recording, or otherwise — without the prior express written consent of Azirella Ltd. Any unauthorized use constitutes a violation of applicable intellectual property laws and may be subject to legal action.
