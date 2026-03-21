# Knowledge Graphs in Supply Chain Planning: Analysis for Autonomy

**Date**: 2026-03-17
**Status**: Internal Analysis

---

## 1. Executive Summary

This document analyzes whether adopting a formal knowledge graph (KG) — as described in Hedden (2026), the academic KG+GNN literature, and recent industry moves by Blue Yonder/RelationalAI — would materially improve the Autonomy platform.

**Bottom line: Autonomy's existing architecture already captures the core value that knowledge graphs provide in supply chain contexts, but through different (and arguably more appropriate) mechanisms. A formal RDF/OWL knowledge graph would add infrastructure complexity without proportional benefit. However, three specific KG *concepts* — not KG *technology* — are worth incorporating.**

| What KGs promise | How Autonomy already delivers it | Gap? |
|---|---|---|
| Structured entity relationships | 35 AWS SC entities in PostgreSQL with FK relationships | No |
| Network topology reasoning | 4-master-type DAG with typed edges (transportation_lane) | No |
| Multi-hop graph inference | 3-tier GNN (GraphSAGE weekly, tGNN daily, Site tGNN hourly) | No |
| Semantic enrichment from external sources | SAP integration, email signal ingestion, synthetic data wizard | Partial |
| Ontology-driven inference | Deterministic engine + TRM hive + HiveSignalBus | No |
| Feature derivation from graph structure | GNN embeddings, node centrality, attention weights | No |
| Agent-accessible structured context | AgentContextExplainer, decision_reasoning, RAG memory | No |
| Declarative business rules | SKILL.md heuristic files, inv_policy types, sourcing_rules | Partial |

---

## 2. The Hedden Article: What It Actually Demonstrates

Steve Hedden's "Using a Knowledge Graph to Generate Predictive Models" (Towards AI, March 2026) presents a 4-layer architecture applied to Oscar prediction:

1. **Data Foundation** — Formal OWL ontology + RDF instance data (366K triples)
2. **Inferences** — Ontology reasoning expands to 522K triples (e.g., inverse relationships derived automatically)
3. **Enrichment** — External API expansion via identifiers (TMDB, OMDb, Wikidata) grows graph to 625K triples
4. **Predictive Models** — Feature extraction from graph (92-96 candidate features) feeds constrained logistic regression

The key insight: *"Structure + identifiers = connectivity."* Once an ontology defines classes, properties, and inverse relationships, populating it with instance data automatically creates an interconnected graph without manual wiring.

### Applicability to Supply Chain

The Oscar domain is a **static, categorical prediction problem** — will nominee X win category Y? Supply chain planning is a **dynamic, sequential decision problem** under uncertainty. The ontology-first approach works beautifully for the former; it's a poor fit for the latter:

- Oscar predictions use ~96 static features derived from graph structure. Supply chain decisions use **time-varying state** (inventory levels, pipeline shipments, demand signals) that changes every period.
- Hedden's graph is built once and queried. In supply chain, the graph **evolves** — new orders arrive, shipments move, suppliers go offline.
- Hedden uses constrained logistic regression. Autonomy uses **recursive neural networks** (TRMs) with reinforcement learning, conformal prediction, and causal inference.
- The "enrichment" layer (pulling from external APIs) maps loosely to Autonomy's email signal ingestion and SAP data extraction — but these are transactional, not encyclopedic.

The article is an excellent demonstration of semantic data architecture for static prediction. The transferable principle is the separation of ontology (structure of meaning) from instance data (populated entities) — not the specific RDF/OWL/SPARQL technology stack.

---

## 3. Industry Landscape: Who Uses Knowledge Graphs in Supply Chain

### 3.1 Blue Yonder + RelationalAI + Snowflake (2024-2025)

The most significant industry development. At ICON 2025 (May 2025), Blue Yonder announced a supply chain knowledge graph built with RelationalAI inside Snowflake:

- **20x code reduction**: Replaced thousands of lines of imperative business logic with declarative rules
- **Semantic layer**: Records business relationships and processes in human-readable form
- **Scale**: 10 billion ML workloads/day on Snowflake
- **New AI agents**: Paired with autonomous SC decision agents

**Analysis**: Blue Yonder's KG replaces *imperative business logic* with *declarative rules*. Autonomy's equivalent is the `SKILL.md` heuristic files and `inv_policy` type system. The 20x code reduction is compelling, but BY's legacy codebase (acquired from JDA Software, 30+ years of code) had far more imperative logic to replace. Autonomy was built from scratch with a cleaner separation of concerns.

### 3.2 o9 Solutions — Enterprise Knowledge Graph (EKG)

Core of their "Digital Brain" platform; proprietary "Graph-Cube" in-memory store. Real-time propagation of changes across the enterprise (e.g., consumer sentiment change propagates instantly to connected models). Named Leader in 2025 Gartner MQ for Supply Chain Planning.

**Analysis**: o9's KG is primarily a **data integration layer** for connecting disparate enterprise systems (ERP, TMS, WMS). Autonomy ingests data via SAP integration and the AWS SC data model — the data model *is* our semantic schema, just relational rather than RDF. Per Lokad's review, the actual "graph" capabilities vs. traditional OLAP cubes are not well-documented publicly.

### 3.3 Kinaxis — Cognitive Network Graph

Patented graph powering their concurrent planning; changes propagate through a single model in real time. More of a data propagation infrastructure than a semantic KG in the traditional sense. Cloud services with always-on algorithms, in-memory databases with direct memory references.

**Analysis**: Kinaxis's "graph" is really a **dependency propagation engine** — when one variable changes, dependent variables recompute instantly. Autonomy's equivalent is the HiveSignalBus (reactive signal propagation) + Site tGNN (learned cross-TRM coordination). The Kinaxis approach is deterministic; Autonomy's is learned.

### 3.4 SAP — Supply Chain Orchestration (H1 2026)

New product using a **network knowledge graph** for detecting risks (tariffs, weather, supplier disruptions). N-tier insights extending beyond traditional boundaries; built on SAP Business Network. SAP HANA Cloud also introduced a separate Knowledge Graph Engine for business context.

**Analysis**: SAP's KG focuses on **multi-tier visibility** across the SAP Business Network (millions of connected companies). Relevant if Autonomy customers need cross-enterprise visibility, but our current focus is single-enterprise planning.

### 3.5 Palantir — Foundry Ontology

Domain-agnostic ontology as "digital twin" of the organization; now backbone for enterprise AI agents (AIP). Lowe's uses Palantir + NVIDIA for continuous global SC optimization. Community has noted gap between Palantir's "ontology" (object model) and "true knowledge graph capabilities" (semantic reasoning, inference).

**Analysis**: Palantir's "ontology" is really a flexible object model with relationships — closer to Autonomy's SQLAlchemy entity model than to formal RDF/OWL. The marketing uses KG terminology, but the implementation is practical data modeling.

### 3.6 Amazon/AWS and Google Cloud

Amazon Neptune provides managed graph DB with SC use cases (BOM traversal, supplier analysis). However, **AWS Supply Chain itself uses a relational model (35 entities), not native graph** — the same model Autonomy implements.

Google's Supply Chain Twin (launched September 2021) had limited evidence of active development post-2023. Current focus shifted to Vertex AI agent-based solutions.

### 3.7 Graph Database Vendors

Neo4j (product lineage, supplier criticality, Graph Data Science library) and TigerGraph (real-time digital twins, claim scenario analysis reduced from 3 weeks to <1 hour, tariff impact modeling) actively market SC use cases.

---

## 4. Academic Research: KGs + GNNs in Supply Chain

### 4.1 Foundational Papers (2022-2023)

- **Kosasih & Brintrup (2022)** — "Towards Knowledge Graph Reasoning for Supply Chain Risk Management Using GNNs" (IJPR). Pioneered GNN encoders over SC knowledge graphs; achieved transparency up to tier-3 suppliers using KG completion methods.
- **Brockmann et al. (2023)** — "Supply Chain Link Prediction on Uncertain Knowledge Graph" (ACM SIGKDD Explorations). Introduced uncertainty quantification into KG link prediction; **RotatE performed best** for most relation types.
- **arxiv:2305.08506 (2023)** — KG-driven resilience analysis using graph centrality and community detection.

### 4.2 Breakthrough Papers (2024-2025)

- **"Towards Trustworthy AI for Link Prediction in SC KG: A Neurosymbolic Approach"** (IJPR 2024). Neural Bellman-Ford Network (NBFNet) for neurosymbolic link prediction — combining GNN learning with symbolic KG reasoning.
- **SupplyGraph (arxiv:2401.15299, 2024)** — First real-world benchmark for GNN-based SC analytics. 41 products, 684 edges from FMCG company. Benchmarks GAT, GCN, GraphSAGE, HGT across 6 tasks.
- **Wasi et al. (arxiv:2411.08550, 2024)** — Comprehensive survey: GNNs outperform baselines by **10-30% in regression/classification** and **15-40% in anomaly detection**. Heterogeneous graph models outperform homogeneous when multiple relationship types are present.
- **SC-TKGR (Electronics, 2025)** — Temporal KG-based GNN framework modeling behavioral dynamics with time-sensitive graph embeddings.
- **"Enhancing SC Visibility with KGs and LLMs" (IJPR 2025, arxiv:2408.07705)** — KG+LLM for visibility without direct reliance on stakeholder information sharing.
- **"Integrating Graph RAG with LLMs for Supplier Discovery" (ASME JCISE, 2025)** — Transforms unstructured supplier data into harmonized KGs via GraphRAG.
- **"Federated GNN for Privacy-Preserved SC Data Sharing" (Applied Soft Computing, 2024)** — Federated GNN training across SC partners without raw data exchange.

### 4.3 Key Research Trends

1. Static-to-temporal KGs (time-stamped triples)
2. Visibility-to-prediction shift (from "what exists?" to "what will happen?")
3. Neurosymbolic hybrid approaches (GNN learning + symbolic KG reasoning)
4. Privacy-preserving federated learning over distributed KGs
5. LLM-powered automated KG construction from unstructured data

### 4.4 Best Architectures for SC (from research)

| Architecture | Best For | Autonomy Equivalent |
|---|---|---|
| HGT (Heterogeneous Graph Transformer) | Full network modeling | S&OP GraphSAGE |
| R-GCN / CompGCN | KG completion / link prediction | Not implemented (not needed) |
| NBFNet (Neural Bellman-Ford Network) | Trustworthy link prediction | Not implemented |
| GATv2 + GRU | Dynamic state tracking | Site tGNN (already using this) |
| RotatE / ComplEx | KG embedding for link prediction | Not applicable |

---

## 5. Standards and Ontologies

- **ASCM SCOR Digital Standard (2025)**: 6 process types, 250+ metrics. Process taxonomy but no formal OWL axioms.
- **SCONTO**: Modular OWL DL ontology from INGAR/INTEC; formally describes SC processes based on SCOR at multiple abstraction levels.
- **IOF Supply Chain Ontology (NIST)**: Built on Basic Formal Ontology (BFO); open source on GitHub. Definitions from GS1 and APICS standards.
- **GS1**: GTIN (product IDs), GLN (location IDs), EPCIS (event-based visibility) map naturally to KG triples.
- **UN/CEFACT**: Core Component Library provides reusable semantic components for international trade.

**Critical gap**: No unified supply chain ontology exists. SCONTO, IOF, SCOR, GS1 cover overlapping but different aspects. Most enterprises use proprietary data models — including AWS SC's 35-entity model that Autonomy implements.

---

## 6. The Fundamental Mismatch: Why KGs Are Not the Right Foundation for Decision Intelligence

### Knowledge Graphs are for Knowledge Representation
- Static relationships, categorical facts, ontological hierarchies
- Answers questions like: "Which suppliers provide component X?" "What is the BOM for product Y?"
- Query-time reasoning over stored facts

### Autonomy is for Sequential Decision-Making Under Uncertainty
- Dynamic state that evolves every period (Powell Sₜ → Sₜ₊₁)
- Makes decisions like: "How much should site Z order this period?" "Should we expedite this MO?"
- Training-time learning of optimal policies, not query-time reasoning

The Powell SDAM framework makes this explicit:
- **State (Sₜ)** = Physical (Rₜ) + Information (Iₜ) + Belief (Bₜ). Temporal and dynamic — not a graph of static facts.
- **Policy (π)** = A learned mapping from state to decision. This is what TRMs do. KGs don't produce policies.
- **Exogenous information (Wₜ₊₁)** = Demand shocks, supplier disruptions. Stochastic — KGs model what *is*, not what *might happen*.

**The most significant gap identified by research**: No major KG platform connects graph representation to stochastic optimization or sequential decision-making. KGs excel at representing state (Sₜ) but do not address policy optimization (X^π) or objective functions. This is where the Powell framework is truly novel — and where formal KG technology adds nothing.

### The GNN *Is* the Knowledge Graph

This is the central insight: **Autonomy's 3-tier GNN architecture performs the same function as a knowledge graph, but with learned representations instead of explicit triples.**

| KG Capability | GNN Equivalent in Autonomy |
|---|---|
| Entity relationships | Adjacency matrix from DAG topology |
| Multi-hop traversal | Message passing across GNN layers |
| Relationship inference | Attention weights learn relationship importance |
| Feature enrichment | Node features from all 35 AWS SC entity tables |
| Temporal reasoning | GRU layers in tGNN and Site tGNN |
| Anomaly detection | CDC monitor + conformal prediction |
| Causal reasoning | Site tGNN causal edges + counterfactual computation |

The GNN approach is strictly more powerful because:
1. It **learns** which relationships matter (attention weights) vs. requiring manual ontology engineering
2. It handles **temporal dynamics** natively (GRU state) vs. requiring separate temporal reasoning
3. It produces **continuous embeddings** for downstream ML vs. discrete triples
4. It **scales** to the number of edges, not the number of inferred triples

---

## 7. What We Should Actually Take from the KG Literature

Rather than adopting KG technology, three KG *concepts* merit attention:

### 7.1 Declarative Business Rules (from Blue Yonder/RelationalAI)

Blue Yonder's 20x code reduction comes from expressing business logic as declarative rules rather than imperative code. Autonomy has the beginnings of this:

- `SKILL.md` files encode heuristic rules per TRM type
- `inv_policy` types define parameterized inventory policies
- `sourcing_rules` declare multi-sourcing with priorities

**Opportunity**: Extend the declarative approach to more decision logic. Instead of imperative Python in TRM services, express more rules in a structured, human-readable format that both LLMs and TRMs can consume. This is a **rule engine** pattern, not a knowledge graph.

**Priority**: Low. Current SKILL.md approach works. Revisit if rule complexity grows beyond 11 TRM types.

### 7.2 Semantic Layer for LLM Agents (from Hedden + o9)

The strongest argument for a KG in supply chain is as a **semantic layer between LLMs and operational data**. When an LLM needs to answer "why did OTIF drop at the Northeast DC?", it needs to traverse relationships: DC → orders → shipments → suppliers → disruptions.

Autonomy's current approach:
- `AgentContextExplainer` provides pre-computed context for TRM decisions
- `decision_reasoning.py` generates human-readable explanations
- RAG decision memory retrieves similar past decisions

**Opportunity**: Build a lightweight **semantic index** — not an RDF triple store, but a structured metadata layer that maps entity relationships for LLM consumption. This could be a JSON-LD-like representation of the AWS SC entity graph, refreshed periodically, that Claude Skills and the "Azirella" system use as grounding context. No new database needed — just a materialized view of entity relationships.

**Priority**: Medium. Would improve LLM response quality for complex cross-entity queries.

### 7.3 External Identifier Registry (from Hedden's Layer 3)

Hedden's most transferable insight is **enrichment via external identifiers**. Each entity in the graph has external IDs (IMDB, TMDB, Wikidata) that act as expansion points for pulling additional data.

Autonomy already has this for some entities:
- `TradingPartner` with external supplier IDs
- `email_signals` linking domain → TradingPartner
- SAP integration mapping SAP material/plant codes to AWS SC entities

**Opportunity**: Formalize the **external identifier** pattern. Each `Site`, `Product`, and `TradingPartner` should carry an `external_identifiers` JSON field linking to external systems (SAP material number, GTIN/UPC, D-U-N-S number, LEI code). When an LLM or agent needs enrichment data, it knows where to look.

**Priority**: Medium. Useful for SAP integration and multi-system deployments.

---

## 8. Competitor Positioning

### "Blue Yonder Has a Knowledge Graph — Shouldn't We?"

Blue Yonder's KG serves a different purpose than what Autonomy needs:
- BY uses KG to **unify 30 years of legacy code** into a declarative layer. Autonomy was built clean.
- BY's KG is a **data integration layer** for Snowflake. Autonomy's data is already in a unified schema.
- BY processes 10B ML workloads/day — their KG helps *organize* this at scale. Autonomy's TRM Hive *coordinates* decisions at the site level, a fundamentally different problem.

### Marketing Counter-Narrative

If competitors market KG capabilities:

> *"Knowledge graphs organize what you know. Our GNN architecture learns what matters. Every week, our S&OP GraphSAGE discovers which supply chain relationships are driving risk and opportunity — not from manually engineered ontologies, but from the data itself. Combined with conformal prediction for uncertainty quantification and causal AI for decision attribution, Autonomy doesn't just model your supply chain — it learns to manage it."*

The research validates this framing: **no KG platform connects knowledge representation to sequential decision optimization under uncertainty**. This is Autonomy's unique positioning.

---

## 9. Known KG Limitations (from Research)

1. **Data quality**: KGs are only as good as their data; integrating inconsistent ERP data introduces errors that propagate through inference
2. **Scalability**: Real enterprise SC may have millions of nodes; GNN training struggles beyond ~1M nodes without sampling
3. **Trust/data sharing paradox**: Multi-tier visibility requires companies to share data they are reluctant to disclose
4. **Expertise gap**: Few organizations have ontologists who understand both RDF/OWL and supply chain planning
5. **Visibility vs. decision-making gap**: Most KG implementations answer "what exists?" not "what should we do?"
6. **Vendor lock-in**: o9's Graph-Cube, Kinaxis's Cognitive Graph, BY's RelationalAI/Snowflake dependency are all proprietary and non-interoperable
7. **Overhead vs. value**: For mid-market supply chains (10-200 sites, 100-10K products), PostgreSQL with proper indexes handles the graph sizes where KG overhead is not justified

---

## 10. Recommendation Summary

### Do Not Implement
- RDF/OWL ontology or SPARQL endpoint
- Graph database (Neo4j, Neptune, etc.)
- Formal KG inference engine

### Consider Implementing (Medium Priority)
1. **Semantic Context Service** — JSON-LD-like entity relationship index for LLM grounding
2. **External Identifier Registry** — Standardized `external_identifiers` field on Site/Product/TradingPartner
3. **Declarative Rule Expansion** — Continue extending SKILL.md pattern if rule complexity grows

### Already Have (No Action Needed)
- Graph-based reasoning (3-tier GNN)
- Entity relationship model (AWS SC 35 entities)
- Network topology analysis (DAG + GraphSAGE)
- Temporal graph dynamics (GATv2 + GRU)
- Agent-accessible knowledge (RAG memory, decision reasoning, context explainer)
- External data enrichment (SAP integration, email signals)

---

## 11. References

### Source PDF
- Hedden, S. (2026). "Using a Knowledge Graph to Generate Predictive Models for the Oscars." Towards AI. [Link](https://pub.towardsai.net/using-a-knowledge-graph-to-build-a-predictive-model-for-the-oscars-8203bc11d906)

### Academic Papers
- Wasi, A.T. et al. (2024). "GNNs in SC Analytics and Optimization." arxiv:2411.08550.
- Kosasih, E.E. & Brintrup, A. (2022). "Towards KG Reasoning for SC Risk Management Using GNNs." IJPR.
- Brockmann et al. (2023). "Supply Chain Link Prediction on Uncertain Knowledge Graph." ACM SIGKDD Explorations.
- "Towards Trustworthy AI for Link Prediction in SC KG." IJPR 2024.
- SupplyGraph (arxiv:2401.15299, 2024). First SC benchmark for GNN analytics.
- "Enhancing SC Visibility with KGs and LLMs." IJPR 2025 (arxiv:2408.07705).
- "A KG Perspective on Supply Chain Resilience." arxiv:2305.08506 (2023).
- "SCONTO: A Modular Ontology for Supply Chain Representation." OpenReview.
- IOF Supply Chain Ontology, ASU Semantic Computing Lab / NIST.

### Industry
- [Blue Yonder + RelationalAI + Snowflake SC Knowledge Graph](https://www.businesswire.com/news/home/20250505924588/en/Blue-Yonder-Transforms-Supply-Chain-Management-With-New-AI-Agents-and-Supply-Chain-Knowledge-Graph-at-ICON-2025) (ICON 2025).
- [o9 Solutions: KGs and Supply Chain Complexity](https://o9solutions.com/articles/how-knowledge-graphs-help-mitigate-increasing-supply-chain-complexity/).
- [BCG: Using Digital Twins to Manage Complex SCs](https://www.bcg.com/publications/2024/using-digital-twins-to-manage-complex-supply-chains) (2024).
- [Gartner: Top SC Technology Trends for 2025](https://www.gartner.com/en/newsroom/press-releases/2025-03-18-gartner-identifies-top-supply-chain-technology-trends-for-2025).
- [McKinsey: Digital Twins for End-to-End SC Growth](https://www.mckinsey.com/capabilities/quantumblack/our-insights/digital-twins-the-key-to-unlocking-end-to-end-supply-chain-growth).
- ASCM SCOR Digital Standard (2025).
- [RelationalAI KG Coprocessor on Snowflake](https://relational.ai/resources/rai-debuts-ka-coprocessor-as-snowflake-native-app).

### Platform Architecture
- DAG Logic: `docs/internal/DAG_Logic.md`
- AWS SC Entity Model: `backend/app/models/sc_entities.py` (35 entities)
- Site tGNN: `backend/app/models/gnn/site_tgnn.py` (11 TRM nodes, 22 causal edges)
- S&OP GraphSAGE: Network structure analysis, risk scoring
- Powell SDAM Framework: `POWELL_APPROACH.md`
