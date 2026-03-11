# RAG Ingestion Checklist

Actionable checklist for populating the Knowledge Base with SCP resources.

---

## Infrastructure

The RAG stack runs on **Acer-Nitro.local**. Three Docker containers must be running:

| Container | Port | Purpose |
|-----------|------|---------|
| `autonomy-vllm` | 8001 | Chat inference (Qwen3-8B-AWQ, GPU) |
| `autonomy-embeddings` | 11434 | Embedding service (nomic-embed-text via Ollama, CPU) |
| `autonomy-kb-db` | 5432 | pgvector database (`autonomy_kb`) |

```bash
# Check containers are running (on Acer-Nitro.local)
docker ps --filter name=autonomy

# Health checks
curl http://localhost:11434/api/tags      # Ollama models list
curl http://localhost:8001/v1/models      # vLLM models list
```

---

## How to Add Documents

### Option A — Browser UI (Tenant Admins)

Navigate to `/admin/knowledge-base` while logged in as a tenant admin.

- **Documents tab**: Upload files one at a time (PDF, DOCX, TXT, MD, CSV)
- **URL Sources tab**: Paste any public URL — HTML pages and direct PDF/DOCX links are both supported

Note: Some sites (ASCM, Gartner) block automated access and will return an HTTP error. Download manually and upload as a file instead.

### Option B — Drop Folder (Platform Admin, batch)

Place files in `data/rag_intake/<category>/` on Acer-Nitro.local and run:

```bash
# From the Autonomy project root on Acer-Nitro.local
python scripts/ingest_rag.py --intake-only
```

Available category subdirectories:
`mps_mrp`, `inventory_optimization`, `demand_planning`, `supply_planning`, `sop_ibp`, `capacity_planning`, `atp_ctp`, `network_design`, `order_execution`, `stochastic_planning`, `decision_framework`, `ai_planning`, `ai_ml`, `analyst_reports`, `strategy`, `internal_docs`, `general`

### Option C — URL Sources YAML (Platform Admin, batch)

Add entries to `data/rag_sources.yaml` and run:

```bash
python scripts/ingest_rag.py --sources-only
```

YAML format:
```yaml
sources:
  - type: url
    url: https://example.com/whitepaper.pdf
    category: analyst_reports
    title: "Example Whitepaper"
    tags: [example, tag]
  # Also supports: type: gdrive (needs GDRIVE_API_KEY env var)
  #                type: sharepoint (needs SHAREPOINT_TENANT_ID/CLIENT_ID/CLIENT_SECRET)
```

### Full batch run

```bash
# Processes docs/ + data/rag_intake/ + data/rag_sources.yaml
python scripts/ingest_rag.py

# Dry run — show what would be ingested without writing to DB
python scripts/ingest_rag.py --dry-run
```

Already-indexed documents are skipped. Failed/pending records are deleted and retried on each run.

---

## Step 1: Ingest Existing Local Documents (38 PDFs)

All files in `docs/Knowledge/` — use the batch ingest script (preferred) or upload individually via the UI.

```bash
# Batch ingest from docs/ (run on Acer-Nitro.local)
python scripts/ingest_rag.py

# Or upload individually via browser:
# Admin → Knowledge Base → Documents tab → Choose File
```

| Status | File | Category |
|--------|------|----------|
| [ ] | `01_MPS_Material_Requirements_Planning_Academic.pdf` | mps_mrp |
| [ ] | `02_Systems2win_MPS_Guide.pdf` | mps_mrp |
| [ ] | `03_ERP_Information_MPS_Guide.pdf` | mps_mrp |
| [ ] | `04_Kinaxis_Master_Production_Scheduling.pdf` | mps_mrp |
| [ ] | `06_Kinaxis_Capacity_Planning_Constraints.pdf` | capacity_planning |
| [ ] | `08_Kinaxis_Inventory_Planning_Optimization.pdf` | inventory_optimization |
| [ ] | `10_OMP_5_Planning_Strategies.pdf` | planning_strategy |
| [ ] | `11_OMP_Supply_Chain_Suite_Overview.pdf` | planning_strategy |
| [ ] | `14_Stanford_Stochastic_Programming_Solutions.pdf` | stochastic_planning |
| [ ] | `16_Safety_Stock_Planning_Supply_Chain.pdf` | inventory_optimization |
| [ ] | `17_MIT_Strategic_Safety_Stock_Placement.pdf` | inventory_optimization |
| [ ] | `18_MIT_Inventory_Optimization_Simulation.pdf` | inventory_optimization |
| [ ] | `19_Vandeput_Inventory_Optimization.pdf` | inventory_optimization |
| [ ] | `20_Inventory_Management_Stochastic_Demand.pdf` | inventory_optimization |
| [ ] | `21_Stochastic_Programming_Global_Supply_Chain.pdf` | stochastic_planning |
| [ ] | `Powell-SDAM-Nov242022_final_w_frontcover.pdf` | decision_framework |
| [ ] | `Powell - Application to Supply Chain Planning.pdf` | decision_framework |
| [ ] | `Powell Approach.pdf` | decision_framework |
| [ ] | `Powell Approach - Condensed.pdf` | decision_framework |
| [ ] | `Powell - RL and SO.pdf` | decision_framework |
| [ ] | `Powell - RL and SO Book.pdf` | decision_framework |
| [ ] | `Powell - Optimal Learning.pdf` | decision_framework |
| [ ] | `Powell - How to teach optimization.pdf` | decision_framework |
| [ ] | `Strategic Synthesis_ Agentic UX for Demand & Supply Planners.pdf` | ai_planning |
| [ ] | `AUTONOMY 1 PAGE COMPANY STRATEGY MEMO .pdf` | strategy |
| [ ] | `Conformal Prediction and Stochastic Programming Integration Guide.pdf` | stochastic_planning |
| [ ] | `Distributor Prototype using Powel Approach.pdf` | decision_framework |
| [ ] | `GNNs in SC Analytics and Optimization.pdf` | ai_ml |
| [ ] | `Graph_Neural_Network_for_Daily_Supply_Chain_Proble.pdf` | ai_ml |
| [ ] | `Learning Production for SCs using GNNs.pdf` | ai_ml |
| [ ] | `Less is More with TRM.pdf` | ai_ml |
| [ ] | `Risk-based-Planning-and-Scheduling-Why-Variation-Matters.pdf` | stochastic_planning |
| [ ] | `Simio-Risk-Based-Planning-And-Scheduling-RPS-Business-Benefits.pdf` | stochastic_planning |
| [ ] | `Simio_AI_Whitepaper_2025-1.pdf` | ai_ml |

---

## Step 2: Download Free Resources (Gap Filling)

### S&OP / IBP (HIGH priority gap)

| Status | Resource | URL | Category |
|--------|----------|-----|----------|
| [ ] | Oliver Wight S&OP/IBP Checklist | https://www.supplychainbrain.com/ext/resources/secure_download/KellysFiles/WhitePapersAndBenchMarkReports/OliverWight/sales-operations-planning-ibp-checklist-correll-palmatier.pdf | sop_ibp |
| [ ] | Oliver Wight IBP Execution Paper | https://www.oliverwight-americas.com/wp-content/uploads/2020/04/WP_EffectiveExecutionITP.pdf | sop_ibp |

### ATP / CTP / AATP (HIGH priority gap)

| Status | Resource | URL | Category |
|--------|----------|-----|----------|
| [ ] | AATP Model Based on CTP (PDF) | https://citeseerx.ist.psu.edu/document?repid=rep1&type=pdf&doi=b69ee7c4f6a00e5f868746ca74b34e5cb8f3f4ee | atp_ctp |
| [ ] | ETH Zurich ATP/CTP Course Page | https://opess.ethz.ch/course/section-5-3/5-3-5-available-to-promise-atp-and-capable-to-promise-ctp/ | atp_ctp |

### MEIO / Inventory Optimization

| Status | Resource | URL | Category |
|--------|----------|-----|----------|
| [ ] | CMU MEIO Overview (PDF) | https://egon.cheme.cmu.edu/ewo/docs/SnyderEWO_081113.pdf | inventory_optimization |
| [ ] | arXiv MEIO Extensions (PDF) | https://arxiv.org/pdf/2306.10961 | inventory_optimization |
| [ ] | Polimi MEIO Thesis (PDF) | https://www.politesi.polimi.it/retrieve/a81cb05c-f5c3-616b-e053-1605fe0a889a/2018_10_Ratti.pdf | inventory_optimization |
| [ ] | LLamasoft MEIO Formulation | https://help.llama.ai/release/native/modeling/modeling-topics/Multi_Echelon_Safety_Stock_Optimization_Formulation.htm | inventory_optimization |

### SCOR Framework

| Status | Resource | URL | Category |
|--------|----------|-----|----------|
| [ ] | SCOR DS Intro PDF | https://www.ascm.org/globalassets/ascm_website_assets/docs/intro-and-front-matter-scor-digital-standard2.pdf | scor_framework |

### MIT OpenCourseWare

| Status | Resource | URL | Category |
|--------|----------|-----|----------|
| [ ] | MIT 15.762J SC Planning (all materials) | https://ocw.mit.edu/courses/15-762j-supply-chain-planning-spring-2011/download/ | academic_planning |
| [ ] | MIT ESD.273J Logistics & SC Mgmt | https://ocw.mit.edu/courses/esd-273j-logistics-and-supply-chain-management-fall-2009/ | academic_planning |

### Analyst Reports (Free Reprints)

| Status | Resource | URL | Category |
|--------|----------|-----|----------|
| [ ] | Gartner 2025 MQ Reprint (Kinaxis) | https://www.kinaxis.com/en/about-us/gartner-magic-quadrant-supply-chain-planning-solutions | analyst_reports |
| [ ] | Gartner 2025 MQ Reprint (o9) | https://o9solutions.com/resources/gartner | analyst_reports |
| [ ] | McKinsey: Autonomous SC Planning | https://www.mckinsey.com/capabilities/operations/our-insights/autonomous-supply-chain-planning-for-consumer-goods-companies | analyst_reports |
| [ ] | McKinsey: Gen AI Reshaping SC | https://www.mckinsey.com/capabilities/operations/our-insights/beyond-automation-how-gen-ai-is-reshaping-supply-chains | analyst_reports |

---

## Step 3: Paid Resources (Subscription Required)

| Resource | Cost | URL | Value for RAG |
|----------|------|-----|---------------|
| ASCM Membership (Dictionary + SCOR) | ~$200/yr | https://www.ascm.org/ | 5,000+ SCP terms, SCOR DS access |
| CPIM Learning System (most valuable) | ~$2,400-3,000 | https://www.ascm.org/learning-development/certifications-credentials/cpim/ | Complete SCP body of knowledge |
| "Manufacturing Planning & Control" book | ~$80 | https://www.accessengineeringlibrary.com/content/book/9781265138516 | CPIM reference textbook |
| "Supply Chain Management" (Chopra) | ~$120 | https://www.pearson.com/en-us/subject-catalog/p/supply-chain-management-strategy-planning-and-operation/P200000012829/9780135350294 | Academic SCP textbook |
| "Demand Driven MRP" (Ptak & Smith) | ~$60 | ISBN 978-0831136284 | DDMRP methodology |
| Gartner Subscription | ~$30K+/yr | https://www.gartner.com/ | Full MQ, Hype Cycle, research |

---

## Step 4: OneDrive Private Research

1. Navigate to: `https://1drv.ms/f/c/23a396028c0b7068/IgBocAuMApajIIAjSZQBAAAAATdEOgDqyy6cf0qgAn4knjs?e=CTyzI0`
2. Download all documents locally
3. Upload via Knowledge Base UI or place in `docs/Knowledge/`
4. Categorize each document appropriately

---

## Document Categories for Knowledge Base

Use these categories when uploading to maintain consistent organization:

| Category | Description |
|----------|-------------|
| `sop_ibp` | Sales & Operations Planning, Integrated Business Planning |
| `demand_planning` | Forecasting, demand sensing, CPFR |
| `supply_planning` | Net requirements, sourcing, supply balancing |
| `mps_mrp` | Master Production Scheduling, Material Requirements Planning |
| `inventory_optimization` | Safety stock, MEIO, inventory policies |
| `atp_ctp` | Available-to-Promise, Capable-to-Promise, AATP |
| `network_design` | Supply chain network optimization, facility location |
| `drp_distribution` | Distribution Requirements Planning |
| `order_execution` | Order management, exception handling, fulfillment |
| `scor_framework` | SCOR Digital Standard, process reference |
| `decision_framework` | Powell SDAM, policy classes, VFA/CFA |
| `ai_planning` | Agentic operating model, autonomous planning, agent architecture |
| `ai_ml` | GNN, TRM, reinforcement learning |
| `stochastic_planning` | Probabilistic planning, Monte Carlo, distributions |
| `analyst_reports` | Gartner, IDC, Forrester, McKinsey, BCG |
| `strategy` | Business strategy, positioning |
| `planning_strategy` | Planning methodologies, vendor approaches |
| `academic_planning` | University courses, textbooks, research papers |
| `existing_research` | Private research from OneDrive |

---

*Last updated: 2026-03-11*
