# Supply Chain Planning (SCP) Knowledge Map

## Purpose

Comprehensive catalog of authoritative resources for teaching the LLM all levels of Supply Chain Planning — from Supply Network Design through Execution (excluding detailed production scheduling). Organized by SCP domain with source attribution, access type, and RAG ingestion priority.

---

## Coverage Scope

| Level | Domain | Included |
|-------|--------|----------|
| Strategic | Supply Network Design | Yes |
| Strategic | S&OP / Integrated Business Planning | Yes |
| Tactical | Demand Planning & Forecasting | Yes |
| Tactical | Supply Planning | Yes |
| Tactical | Master Production Scheduling (MPS) | Yes |
| Tactical | Material Requirements Planning (MRP) | Yes |
| Tactical | Inventory Optimization / Safety Stock | Yes |
| Tactical | Distribution Requirements Planning (DRP) | Yes |
| Operational | ATP / CTP / AATP (Order Promising) | Yes |
| Operational | Order Management & Execution | Yes |
| Operational | Detailed Production Scheduling | **Excluded** |

---

## 1. Professional Bodies & Certifications

### 1.1 ASCM (Association for Supply Chain Management)

**The definitive authority on SCP body of knowledge.**

| Resource | URL | Access | SCP Domains | RAG Priority |
|----------|-----|--------|-------------|--------------|
| ASCM Home | https://www.ascm.org/ | Free | All | Reference |
| CPIM Certification (Planning & Inventory) | https://www.ascm.org/learning-development/certifications-credentials/cpim/ | Paid (~$1,200-1,500/part) | MPS, MRP, S&OP, Inventory, DRP, ATP/CTP | **HIGH** |
| CSCP Certification (Supply Chain Professional) | https://www.ascm.org/learning-development/certifications-credentials/cscp/ | Paid (~$1,800-2,200) | Network Design, S&OP, Demand, Supply, Inventory | HIGH |
| CLTD Certification (Logistics & Distribution) | https://www.ascm.org/learning-development/certifications-credentials/cltd/ | Paid (~$1,500-1,800) | DRP, Order Mgmt, Distribution | Medium |
| ASCM Dictionary (17th Ed) | https://www.ascm.org/learning-development/certifications-credentials/ | Membership (~$200/yr) | All (5,000+ terms) | **HIGH** |
| SCOR Digital Standard | https://scor.ascm.org/ | Free (basic) / Paid (full) | All (process framework) | **HIGH** |
| ASCM Insights / Blog | https://www.ascm.org/ascm-insights/ | Free | Various | Medium |
| ASCM Webinars | https://www.ascm.org/learning-development/ | Free + Paid | Various | Low |

**CPIM Part 1 — Supply Chain Foundations** covers:
- Basics of Supply Chain Management (concepts, demand mgmt fundamentals, MRP/MPS overview)
- Demand Management (forecasting techniques, error measurement: MAD, MAPE, tracking signal)
- Transformation of Demand into Supply (MPS logic, RCCP, MRP logic, BOM explosion, lot sizing)
- Supply (purchasing, supplier management, distribution, logistics)

**CPIM Part 2 — Supply Chain Planning and Execution** covers:
- Module 1 (SMR): S&OP process, aggregate planning, resource planning, production strategies
- Module 2 (MPR): MPS development, planning BOM, ATP/CTP, RCCP, demand management
- Module 3 (DSP): MRP mechanics, lot sizing (EOQ/POQ/LFL/PPB), safety stock, DRP, CRP
- Module 4 (ECO): Priority control, scheduling, PAC, supplier scheduling, order management
- Module 5: Lean, Theory of Constraints, Six Sigma

**CSCP — 8 Modules** covers:
- Supply Chains; Demand Management & Forecasting; Global Supply Chain Networks
- Sourcing Products & Services; Internal Operations & Inventory
- Forward & Reverse Logistics; Supply Chain Relationships; Supply Chain Risk
- Optimization, Sustainability & Technology

### 1.2 SCOR Digital Standard (SCOR DS)

| Resource | URL | Access | Notes |
|----------|-----|--------|-------|
| SCOR DS Overview | https://www.ascm.org/corporate-solutions/standards-tools/scor-ds/ | Free (basic) | Latest version replaces SCOR 12.0 |
| SCOR DS PDF (Intro) | https://www.ascm.org/globalassets/ascm_website_assets/docs/intro-and-front-matter-scor-digital-standard2.pdf | Free | Intro and front matter |
| SCOR Wikipedia | https://en.wikipedia.org/wiki/Supply_chain_operations_reference | Free | Good overview |
| SCOR DS at DAU | https://www.dau.edu/blogs/updated-scor-digital-standard-scor-ds | Free | US DoD perspective |

**SCOR DS Process Structure** (updated from linear to infinity loop):
- **Plan** → **Source** → **Transform** (was "Make") → **Order** (new, split from Deliver) → **Fulfill** (new, split from Deliver) → **Return** → **Enable**

**SCOR Level 1 Metrics**: Perfect Order Fulfillment, Order Fulfillment Cycle Time, Upside/Downside Flexibility, Total SC Management Cost, Cash-to-Cash Cycle Time, Return on SC Fixed Assets

### 1.3 Other Professional Bodies

| Organization | URL | Focus | Access |
|-------------|-----|-------|--------|
| ISM (Institute for Supply Management) | https://www.ismworld.org/ | Procurement, supply management | Free + Paid |
| CSCMP (Council of SC Mgmt Professionals) | https://cscmp.org/ | End-to-end SC, SCPro certification | Free + Paid |
| IBF (Institute of Business Forecasting) | https://ibf.org/ | Demand planning, CPF certification | Free + Paid |
| Oliver Wight (IBP methodology) | https://www.oliverwight-americas.com/ | S&OP/IBP, Class A Checklist | Paid |
| Demand Driven Institute | https://www.demanddriveninstitute.com/ | DDMRP, DDS&OP | Free + Paid |

---

## 2. Analyst Firms

### 2.1 Gartner

| Resource | URL | Access | Notes |
|----------|-----|--------|-------|
| **2025 Magic Quadrant for SCP Solutions** | https://www.gartner.com/en/documents/5374263 | Paid ($30K+/yr subscription) | See free reprints below |
| Gartner Peer Insights (SCP) | https://www.gartner.com/reviews/market/supply-chain-planning-solutions | **FREE** (registration) | Best free Gartner resource |
| Gartner SC Topics Hub | https://www.gartner.com/en/supply-chain/topics/supply-chain-planning | Partly free | Topic articles |
| Gartner SC Top 25 | https://www.gartner.com/en/supply-chain/research/supply-chain-top-25 | Summary free / Full paid | Annual ranking |

**2025 MQ Leaders**: Kinaxis (11th consecutive year), o9 Solutions, Oracle (3rd consecutive year), RELEX Solutions (first time Leader), OMP (10th consecutive, highest Ability to Execute)

**Free MQ Reprints** (gated with email):
| Vendor | URL |
|--------|-----|
| Kinaxis | https://www.kinaxis.com/en/about-us/gartner-magic-quadrant-supply-chain-planning-solutions |
| o9 Solutions | https://o9solutions.com/resources/gartner |
| Oracle | https://www.oracle.com/news/announcement/oracle-once-again-named-a-leader-in-2025-gartner-magic-quadrant-for-supply-chain-planning-solutions-2025-05-16/ |
| RELEX | https://www.relexsolutions.com/resources/relex-named-a-leader-in-the-2025-gartner-magic-quadrant-for-supply-chain-planning-solutions/ |

**Gartner's 5-Stage SCP Maturity Model**:
1. **React** — Spreadsheet-based, siloed, firefighting
2. **Anticipate** — Basic demand planning, simple S&OP, batch planning
3. **Integrate** — Cross-functional S&OP/IBP, scenario planning, concurrent planning
4. **Collaborate** — Multi-enterprise, demand sensing, probabilistic planning, control towers
5. **Orchestrate** — Autonomous planning, self-healing SC, AI-driven, continuous planning, digital twins

**Gartner's Autonomy Spectrum**: Manual → Decision Support → Decision Augmentation → Decision Automation → **Autonomous Planning**

**Decision Intelligence (2025-2026)**:
| Resource | URL | Access | Notes |
|----------|-----|--------|-------|
| **MQ for Decision Intelligence Platforms** (Jan 2026) | https://www.gartner.com/en/documents/7363830 | Paid | Inaugural MQ. Leaders: SAS, FICO, Aera Technology |
| Critical Capabilities for DIPs (Jan 2026) | https://www.gartner.com/en/documents/7367030 | Paid | 4 use cases: Stewardship, Analysis, Engineering, Science |
| Hype Cycle for SC Planning Technologies 2025 | https://www.gartner.com/en/documents/6706434 | Paid | Decision-centric planning + agentic AI as newest innovations |
| Market Guide for A&DI Platforms in SC (2025) | https://www.gartner.com/en/documents/4478399 | Paid | SC-specific DI market analysis |
| Gartner IT Glossary: Decision Intelligence | https://www.gartner.com/en/information-technology/glossary/decision-intelligence | Free | Core DI definition |
| Gartner Peer Insights (DIPs) | https://www.gartner.com/reviews/market/decision-intelligence-platforms | Free (reg) | Vendor reviews |

**Key DI Statistics**: DI = "transformational" (2025 AI Hype Cycle), 5-20% current penetration, 2-5yr to mainstream. By 2026, 75% of Global 500 apply DI practices. By 2028, 25% of CDAO visions become "decision-centric". By 2030, 50% of SCM solutions use intelligent agents.

**Platform Analysis**: See `docs/Knowledge/Decision_Intelligence_Framework_Guide.md` for full mapping of Gartner DI capabilities to Autonomy/Powell implementation.

### 2.2 Other Analysts

| Resource | URL | Access | Focus |
|----------|-----|--------|-------|
| IDC MarketScape: SCP | https://www.idc.com/ | Paid ($20-50K/yr) | Technology-focused vendor assessment |
| Forrester Wave: SCP Suites | https://www.forrester.com/ | Paid | Composability, adaptive intelligence |
| **McKinsey Operations Insights** | https://www.mckinsey.com/capabilities/operations/our-insights | **FREE** | Autonomous SC, AI, cost reduction |
| McKinsey: Autonomous SC Planning | https://www.mckinsey.com/capabilities/operations/our-insights/autonomous-supply-chain-planning-for-consumer-goods-companies | **FREE** | +4% revenue, -20% inventory, -10% SC costs |
| McKinsey: Gen AI Reshaping SC | https://www.mckinsey.com/capabilities/operations/our-insights/beyond-automation-how-gen-ai-is-reshaping-supply-chains | **FREE** | Gen AI in supply chains |
| **BCG Operations** | https://www.bcg.com/capabilities/operations/supply-chain-management | **FREE** | AI-powered SC, RISE framework |
| **Oliver Wyman SC** | https://www.oliverwyman.com/ | **FREE** | Supply Chain Triangle (Service-Cost-Cash) |

---

## 3. Vendor Documentation (Free)

### 3.1 SAP IBP (Integrated Business Planning)

| Resource | URL | Covers |
|----------|-----|--------|
| SAP IBP Help Portal | https://help.sap.com/docs/SAP_INTEGRATED_BUSINESS_PLANNING | All IBP modules |
| SAP IBP Product Page | https://www.sap.com/products/scm/integrated-business-planning.html | Overview |
| SAP IBP Onboarding | https://support.sap.com/en/product/onboarding-resource-center/ibp.html | Implementation |
| SAP IBP Community | https://pages.community.sap.com/topics/integrated-business-planning | Q&A, articles |
| SAP S/4HANA MRP Docs | https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/latest | MRP Live, MPS, PP |
| openSAP Courses (MOOCs) | https://open.sap.com/ | Free courses on IBP, S/4HANA |
| SAP IBP Best Practices | https://rapid.sap.com/ | Configuration guides |

**Key SAP IBP Concepts**: Time-series planning, order-based planning, MEIO, unified planning model, planning operators, S&OP snapshots, CPI-DS integration

### 3.2 Oracle Cloud SCM

| Resource | URL | Covers |
|----------|-----|--------|
| Oracle SCM Cloud Index | https://docs.oracle.com/en/cloud/saas/supply-chain-management/index.html | All modules |
| Oracle Supply Planning | https://docs.oracle.com/en/cloud/saas/supply-chain-management/faspp/ | MRP, supply planning |
| Oracle Demand Management | https://docs.oracle.com/en/cloud/saas/supply-chain-management/fadmd/ | Demand forecasting |
| Oracle Inventory Management | https://docs.oracle.com/en/cloud/saas/supply-chain-management/faimd/ | Inventory |
| Oracle Global Order Promising | https://docs.oracle.com/en/cloud/saas/supply-chain-management/fagop/ | ATP, CTP, PTP |
| Oracle Planning Central | https://docs.oracle.com/en/cloud/saas/supply-chain-management/fapcc/ | Unified workbench |
| Oracle S&OP Cloud | https://docs.oracle.com/en/cloud/saas/supply-chain-management/fasop/ | S&OP process |
| Oracle SCM Blog | https://blogs.oracle.com/scm/ | Thought leadership |
| Oracle CTP (legacy MRP) | https://docs.oracle.com/cd/A60725_05/html/comnls/us/mrp/atp02.htm | CTP mechanics |

### 3.3 Kinaxis RapidResponse

| Resource | URL | Covers |
|----------|-----|--------|
| Kinaxis Resources | https://www.kinaxis.com/en/resources | Whitepapers, webinars (gated) |
| Kinaxis Blog | https://www.kinaxis.com/en/blog | Thought leadership |
| Kinaxis Community | https://community.kinaxis.com/ | Knowledge base |
| Kinaxis YouTube | https://www.youtube.com/@Kinaxis | Demos, webinars |

**Key Kinaxis Concepts**: Concurrent planning, RapidResponse workbench, technique library, control tower

### 3.4 Blue Yonder / DDMRP

| Resource | URL | Covers |
|----------|-----|--------|
| Blue Yonder Resources | https://blueyonder.com/resources | Whitepapers (gated) |
| Blue Yonder Blog | https://blueyonder.com/blog | Thought leadership |
| **Demand Driven Institute** | https://www.demanddriveninstitute.com/ | DDMRP methodology |
| DDI: DDMRP Overview | https://www.demanddriveninstitute.com/ddmrp | Core DDMRP concepts |
| DDI: DDOM | https://www.demanddriveninstitute.com/ddom | Demand Driven Operating Model |
| DDI: DDS&OP | https://www.demanddriveninstitute.com/ddsop | Demand Driven S&OP |
| DDI: Certifications | https://www.demanddriveninstitute.com/certification | DDPP, DDDP, DDOP |
| Patrick Rigoni DDMRP Blog | https://www.yourddmrpexpert.com/ | Practitioner insights |

### 3.5 o9 Solutions

| Resource | URL | Covers |
|----------|-----|--------|
| o9 Knowledge Hub | https://o9solutions.com/knowledge-hub/ | AI planning, IBP |
| o9 Blog | https://o9solutions.com/blog/ | Thought leadership |
| o9: What is MEIO? | https://o9solutions.com/articles/what-is-multi-echelon-inventory-optimization-meio | MEIO explainer |

### 3.6 AWS Supply Chain

| Resource | URL | Covers |
|----------|-----|--------|
| AWS SC Features | https://aws.amazon.com/aws-supply-chain/features/ | All capabilities |
| AWS SC Resources | https://aws.amazon.com/aws-supply-chain/resources/ | Guides, demos |
| AWS SC Documentation | https://docs.aws.amazon.com/aws-supply-chain/ | Technical docs |
| AWS SC Data Model | https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/data-model.html | 35 entities (canonical) |
| AWS SC API Reference | https://docs.aws.amazon.com/aws-supply-chain/latest/APIReference/ | REST API |

### 3.7 Other Vendors

| Resource | URL | Focus |
|----------|-----|-------|
| Coupa Supply Chain Design | https://www.coupa.com/products/supply-chain-design | Network design, digital twin |
| ToolsGroup (MEIO) | https://www.toolsgroup.com/resources/ | MEIO, service-driven planning |
| ToolsGroup MEIO Guide | https://www.toolsgroup.com/blog/multi-echelon-inventory-optimization-toolsgroup-guide/ | MEIO best practices |
| RELEX Solutions | https://www.relexsolutions.com/resources/ | Retail/CPG planning |
| LLamasoft MEIO Formulation | https://help.llama.ai/release/native/modeling/modeling-topics/Multi_Echelon_Safety_Stock_Optimization_Formulation.htm | MEIO math |

---

## 4. Academic Resources

### 4.1 MIT OpenCourseWare (FREE)

| Course | URL | Covers |
|--------|-----|--------|
| **15.762J Supply Chain Planning** | https://ocw.mit.edu/courses/15-762j-supply-chain-planning-spring-2011/ | Risk pooling, inventory placement, collaboration, information sharing |
| 15.762J Resources (Downloads) | https://ocw.mit.edu/courses/15-762j-supply-chain-planning-spring-2011/download/ | Lecture notes, assignments |
| **ESD.273J Logistics & SC Management** | https://ocw.mit.edu/courses/esd-273j-logistics-and-supply-chain-management-fall-2009/ | Vehicle routing, lot sizing, multi-echelon inventory, bullwhip effect, pricing |
| 15.772J D-Lab: Supply Chains | https://ocw.mit.edu/courses/15-772j-d-lab-supply-chains-fall-2014/ | Demand estimation, capacity planning, inventory, coordination |
| 15.763J Manufacturing System & SC Design | https://ocw.mit.edu/courses/15-763j-manufacturing-system-and-supply-chain-design-spring-2005/ | System design decisions |
| MIT SC Course List | https://ocw.mit.edu/course-lists/transportation-logistics-and-supply-chains/ | Full index |

### 4.2 Other Academic Sources

| Resource | URL | Covers |
|----------|-----|--------|
| ETH Zurich OPESS: ATP/CTP | https://opess.ethz.ch/course/section-5-3/5-3-5-available-to-promise-atp-and-capable-to-promise-ctp/ | ATP, CTP concepts |
| CMU: MEIO Overview (PDF) | https://egon.cheme.cmu.edu/ewo/docs/SnyderEWO_081113.pdf | Multi-echelon overview |
| Polimi: MEIO Safety Stock (PDF) | https://www.politesi.polimi.it/retrieve/a81cb05c-f5c3-616b-e053-1605fe0a889a/2018_10_Ratti.pdf | Guaranteed service model |
| arXiv: MEIO Extensions | https://arxiv.org/abs/2306.10961 | MEIO for pharma SCs |
| CiteSeerX: AATP Model (PDF) | https://citeseerx.ist.psu.edu/document?repid=rep1&type=pdf&doi=b69ee7c4f6a00e5f868746ca74b34e5cb8f3f4ee | AATP based on CTP |

### 4.3 Key Textbooks

| Book | Authors | Covers | Access |
|------|---------|--------|--------|
| **Manufacturing Planning & Control for SC Mgmt** (CPIM Reference, 3rd Ed) | Jacobs, Berry, Whybark, Vollmann | MPS, MRP, S&OP, capacity, execution | Paid (~$80) |
| **Supply Chain Management: Strategy, Planning, Operation** (8th Ed) | Chopra & Meindl (Pearson) | Full SCP curriculum | Paid (~$120) |
| **Foundations of Inventory Management** | Zipkin | Inventory theory, stochastic models | Paid (~$100) |
| **Factory Physics** (3rd Ed) | Hopp & Spearman | Manufacturing science, WIP, flow | Paid (~$120) |
| **Demand Driven Material Requirements Planning** | Ptak & Smith | DDMRP methodology | Paid (~$60) |
| **The Transition from S&OP to IBP** | Palmatier & Crum | S&OP → IBP evolution | Paid (~$40) |
| **Oliver Wight ABCD Checklist** | Oliver Wight | Operational excellence assessment | Paid (~$30) |
| **Fundamentals of Supply Chain Theory** (2nd Ed) | Snyder & Shen | Academic SC theory, ML, optimization | Paid (~$80) |

### 4.4 Quantitative / Probabilistic Resources (FREE)

| Resource | URL | Covers |
|----------|-----|--------|
| **Lokad Learn** | https://www.lokad.com/learn/ | Quantitative SC lectures (video) |
| Lokad: Probabilistic Forecasting | https://www.lokad.com/probabilistic-forecasting-in-supply-chain/ | Probabilistic vs point forecasts |
| Lokad: Intro to Quantitative SC | https://www.lokad.com/introduction-to-quantitative-supply-chain/ | Foundation concepts |
| Lokad: Technology | https://www.lokad.com/technology/ | Differentiable programming for SC |
| Lokad: Envision Workshop #4 | https://www.lokad.com/blog/2024/7/1/demand-forecasting-through-envision/ | Demand forecasting practical |

---

## 5. Resources Already in Project

### 5.1 docs/Knowledge/ (38 documents)

| File | Domain | Type |
|------|--------|------|
| `01_MPS_Material_Requirements_Planning_Academic.pdf` | MPS, MRP | Academic |
| `02_Systems2win_MPS_Guide.pdf` | MPS | Practitioner |
| `03_ERP_Information_MPS_Guide.pdf` | MPS | Practitioner |
| `04_Kinaxis_Master_Production_Scheduling.pdf` | MPS | Vendor |
| `06_Kinaxis_Capacity_Planning_Constraints.pdf` | Capacity | Vendor |
| `08_Kinaxis_Inventory_Planning_Optimization.pdf` | Inventory | Vendor |
| `10_OMP_5_Planning_Strategies.pdf` | Planning strategies | Vendor |
| `11_OMP_Supply_Chain_Suite_Overview.pdf` | All | Vendor |
| `14_Stanford_Stochastic_Programming_Solutions.pdf` | Stochastic | Academic |
| `16_Safety_Stock_Planning_Supply_Chain.pdf` | Inventory | Practitioner |
| `17_MIT_Strategic_Safety_Stock_Placement.pdf` | Inventory (MEIO) | Academic |
| `18_MIT_Inventory_Optimization_Simulation.pdf` | Inventory | Academic |
| `19_Vandeput_Inventory_Optimization.pdf` | Inventory | Academic |
| `20_Inventory_Management_Stochastic_Demand.pdf` | Inventory | Academic |
| `21_Stochastic_Programming_Global_Supply_Chain.pdf` | Stochastic | Academic |
| `Powell-SDAM-Nov242022_final_w_frontcover.pdf` | Decision framework | Academic |
| `Powell - Application to Supply Chain Planning.pdf` | Decision framework | Platform |
| `Powell Approach.pdf` / `Powell Approach - Condensed.pdf` | Decision framework | Platform |
| `Powell - RL and SO.pdf` / `Powell - RL and SO Book.pdf` | RL/Optimization | Academic |
| `Powell - Optimal Learning.pdf` | Exploration | Academic |
| `Powell - How to teach optimization.pdf` | Pedagogy | Academic |
| `Strategic Synthesis_ Agentic UX for Demand & Supply Planners.pdf` | UX Framework | Platform |
| `AUTONOMY 1 PAGE COMPANY STRATEGY MEMO .pdf` | Strategy | Platform |
| `Conformal Prediction and Stochastic Programming Integration Guide.pdf` | Stochastic | Platform |
| `Distributor Prototype using Powel Approach.pdf` | Decision framework | Platform |
| `GNNs in SC Analytics and Optimization.pdf` | AI/ML | Academic |
| `Graph_Neural_Network_for_Daily_Supply_Chain_Proble.pdf` | AI/ML | Academic |
| `Learning Production for SCs using GNNs.pdf` | AI/ML | Academic |
| `Less is More with TRM.pdf` | AI/ML (TRM) | Academic |
| `Risk-based-Planning-and-Scheduling-*.pdf` (2 files) | Stochastic | Vendor |
| `Simio_AI_Whitepaper_2025-1.pdf` | AI/Simulation | Vendor |

### 5.2 docs/The_Beer_Game/ (8 documents)

Beer Game simulation resources — already cataloged in CLAUDE.md.

---

## 6. Gap Analysis

### What You Have (Strong Coverage)

| Domain | Coverage | Key Sources |
|--------|----------|-------------|
| MPS | Strong | 4 Kinaxis/academic docs + platform code |
| Inventory / Safety Stock | Strong | 5 academic papers + MIT MEIO |
| Stochastic Programming | Strong | Stanford, 3 academic papers, conformal guide |
| AI/ML in SC | Strong | GNN papers, TRM, Powell SDAM (8 docs) |
| Agentic Operating Model / UX | Strong | 4 platform strategy docs |
| Decision Framework (Powell) | **Excellent** | 8 Powell docs covering all 4 policy classes |

### What You Need (Gaps to Fill)

| Domain | Gap | Recommended Sources | Priority |
|--------|-----|---------------------|----------|
| **S&OP / IBP** | No dedicated S&OP methodology doc | Oliver Wight IBP materials, CPIM Part 2 SMR, Kinaxis S&OP whitepaper | **HIGH** |
| **Demand Planning** | No forecasting methods doc | CPIM Part 1 demand chapter, Lokad probabilistic forecasting, IBF resources | **HIGH** |
| **MRP Logic** | Limited to MPS docs | CPIM Part 2 DSP module, SAP S/4HANA MRP docs, DDMRP book | **HIGH** |
| **Supply Planning** | Covered by Powell but no standalone doc | SAP IBP for Supply docs, Oracle Supply Planning docs | HIGH |
| **Network Design** | No network optimization doc | CSCP Module 1, Coupa/LLamasoft resources | Medium |
| **DRP** | No distribution planning doc | CPIM Part 2 DSP DRP section, CLTD materials | Medium |
| **ATP/CTP/AATP** | Platform code exists but no reference doc | Oracle GOP docs, ETH Zurich OPESS, AATP paper | **HIGH** |
| **SCOR Framework** | No SCOR process reference | SCOR DS (free tier), ASCM membership | Medium |
| **DDMRP** | Not covered at all | Demand Driven Institute, Ptak & Smith book | Medium |
| **Order Execution** | Partially covered by TRM docs | CPIM Part 2 ECO module, SCOR Deliver/Order/Fulfill | Medium |
| **ASCM Dictionary** | No standardized terminology reference | ASCM Dictionary (membership) | HIGH |
| **Gartner Frameworks** | No analyst perspective | Free MQ reprints from vendors | Medium |

---

## 7. Recommended Acquisition Plan

### Phase 1: Free Downloads (Immediate)

| Action | Source | Domain |
|--------|--------|--------|
| Download MIT OCW 15.762J materials | https://ocw.mit.edu/courses/15-762j-supply-chain-planning-spring-2011/download/ | SC Planning |
| Download MIT OCW ESD.273J materials | https://ocw.mit.edu/courses/esd-273j-logistics-and-supply-chain-management-fall-2009/ | Logistics, MEIO |
| Download SCOR DS Intro PDF | https://www.ascm.org/globalassets/ascm_website_assets/docs/intro-and-front-matter-scor-digital-standard2.pdf | SCOR framework |
| Download CMU MEIO Overview PDF | https://egon.cheme.cmu.edu/ewo/docs/SnyderEWO_081113.pdf | Inventory optimization |
| Download arXiv MEIO paper | https://arxiv.org/abs/2306.10961 | MEIO |
| Download CiteSeerX AATP paper | https://citeseerx.ist.psu.edu/document?repid=rep1&type=pdf&doi=b69ee7c4f6a00e5f868746ca74b34e5cb8f3f4ee | ATP/AATP |
| Download Polimi MEIO thesis | https://www.politesi.polimi.it/retrieve/a81cb05c-f5c3-616b-e053-1605fe0a889a/2018_10_Ratti.pdf | MEIO safety stock |
| Get Gartner 2025 MQ reprint (Kinaxis) | https://www.kinaxis.com/en/about-us/gartner-magic-quadrant-supply-chain-planning-solutions | Analyst framework |
| Get Gartner 2025 MQ reprint (o9) | https://o9solutions.com/resources/gartner | Analyst framework |
| Read McKinsey autonomous planning | https://www.mckinsey.com/capabilities/operations/our-insights/autonomous-supply-chain-planning-for-consumer-goods-companies | AI planning |
| Browse Lokad Learn lectures | https://www.lokad.com/learn/ | Probabilistic SC |
| Get Oliver Wight S&OP/IBP checklist | https://www.supplychainbrain.com/ext/resources/secure_download/KellysFiles/WhitePapersAndBenchMarkReports/OliverWight/sales-operations-planning-ibp-checklist-correll-palmatier.pdf | S&OP/IBP |
| Get Oliver Wight execution paper | https://www.oliverwight-americas.com/wp-content/uploads/2020/04/WP_EffectiveExecutionITP.pdf | IBP execution |

### Phase 2: Paid Subscriptions (Recommended)

| Resource | Cost | Value |
|----------|------|-------|
| ASCM Individual Membership | ~$200/yr | Dictionary access, SCOR DS, webinars, discounts |
| CPIM Learning System (Part 1 + 2) | ~$2,400-3,000 total | **Most comprehensive SCP knowledge base** |
| "Manufacturing Planning & Control" textbook | ~$80 | CPIM reference, covers all tactical planning |
| "Demand Driven MRP" (Ptak & Smith) | ~$60 | DDMRP methodology |
| "Supply Chain Management" (Chopra & Meindl) | ~$120 | Academic SCP textbook |

### Phase 3: OneDrive Private Research

Your private research at the OneDrive link requires manual download — the link returned 403 when accessed programmatically. To ingest:
1. Download files from OneDrive to your local machine
2. Place in `docs/Knowledge/` directory
3. Upload through the Knowledge Base UI at `/admin/knowledge-base`
4. Or batch-ingest via the API: `POST /api/v1/knowledge-base/documents`

---

## 8. RAG Ingestion Recommendations

### Ingestion Priority by Domain

| Priority | Domain | Documents to Ingest |
|----------|--------|---------------------|
| P1 | Existing docs/Knowledge/ PDFs | All 38 existing PDFs (batch upload) |
| P1 | S&OP/IBP gap | Oliver Wight checklist PDF, Kinaxis S&OP whitepaper |
| P1 | ATP/CTP/AATP gap | Oracle GOP docs, AATP paper, ETH Zurich content |
| P1 | MRP Logic gap | SAP S/4HANA MRP docs (web scrape to PDF) |
| P2 | MIT OCW materials | Lecture notes and assignments from 15.762J |
| P2 | MEIO papers | CMU overview, arXiv extensions, Polimi thesis |
| P2 | Demand Planning gap | Lokad resources (save as PDF) |
| P2 | SCOR framework | SCOR DS intro PDF |
| P3 | Vendor whitepapers | Kinaxis resources (gated downloads) |
| P3 | Analyst reports | Gartner MQ reprints |
| P3 | McKinsey/BCG reports | Save articles as PDF |
| P3 | OneDrive research | Manual download and upload |

### Chunking Recommendations for SCP Documents

| Document Type | Recommended Chunk Size | Overlap | Rationale |
|---------------|----------------------|---------|-----------|
| Academic papers (PDF) | 1024 chars | 200 | Dense, self-contained sections |
| Vendor documentation | 1500 chars | 300 | Longer context needed for procedures |
| Textbook chapters | 1024 chars | 200 | Standard academic format |
| Platform docs (MD) | 800 chars | 150 | Already structured with headers |
| Glossary/Dictionary | 512 chars | 50 | Short, independent entries |

---

## 9. Mapping to Autonomy Platform

| SCP Domain | Platform Implementation | Key Files | RAG Context Needed |
|-----------|------------------------|-----------|-------------------|
| Network Design | `supply_chain_config_service.py`, DAG model | Config API, SC entities | Network optimization theory |
| S&OP/IBP | S&OP GraphSAGE, Consensus Board (planned) | `powell/` services | S&OP process, IBP maturity |
| Demand Planning | `demand_processor.py`, `ForecastAdjustmentTRM` | AWS SC planning services | Forecasting methods, demand sensing |
| Supply Planning | `net_requirements_calculator.py`, Powell planner | AWS SC planning services | Netting logic, sourcing rules |
| MPS | `MasterProductionScheduling.jsx`, MPS endpoints | Planning pages, API | MPS logic, time fences, planning BOM |
| MRP | `net_requirements_calculator.py`, BOM explosion | AWS SC planning services | MRP mechanics, lot sizing |
| Inventory | `inventory_target_calculator.py`, 4 policy types | AWS SC planning services | Safety stock methods, MEIO |
| DRP | `InventoryRebalancingTRM` | Powell services | DRP logic, push/pull |
| ATP/CTP/AATP | `ATPExecutorTRM`, priority consumption | Powell services | ATP calculation, AATP consumption |
| Order Execution | `OrderTrackingTRM`, `POCreationTRM` | Powell services | Exception management, PO logic |
| AI Agents | TRM Hive, GNN, LLM agents | Powell services, models | Agent architecture, training |

---

*Last updated: 2026-02-23*
*Compiled for RAG knowledge base ingestion targeting Qwen 3 8B via vLLM with pgvector*
