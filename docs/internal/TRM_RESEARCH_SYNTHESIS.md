# Tiny Recursive Models (TRM): Research Synthesis

**Last Updated**: 2026-02-23

---

## 1. Origin and Context

Tiny Recursive Models (TRM) were introduced by **Alexia Jolicoeur-Martineau** at **Samsung SAIL Montreal** in October 2025, in the paper ["Less is More: Recursive Reasoning with Tiny Networks"](https://arxiv.org/abs/2510.04871). TRM won the **1st Place Paper Award** at the ARC Prize 2025.

TRM is a direct successor to the **Hierarchical Reasoning Model (HRM)**, also from Samsung SAIL ([arxiv:2506.21734](https://arxiv.org/abs/2506.21734)), which used two interdependent recurrent modules inspired by hierarchical brain processing. TRM dramatically simplifies HRM while improving performance on every benchmark.

**Core thesis**: A single tiny 2-layer network, applied recursively, can outperform models with 100,000× more parameters on structured reasoning tasks.

---

## 2. Architecture

### 2.1 Mathematical Formulation

TRM maintains three state variables:
- **x**: Embedded input question (fixed)
- **y**: Current best-guess answer (refined iteratively)
- **z**: Latent "scratchpad" for internal reasoning (refined iteratively)

The recursive process alternates between two operations:

```
For each improvement step (up to K=16 steps):
    For n inner recursion cycles:
        z ← net(x, y, z)       # Latent reasoning update
    y ← net(y, z)               # Answer refinement
```

A single 2-layer network `net` handles both updates. The network is the same — what changes is the input routing.

### 2.2 Network Specifications

| Parameter | Value |
|-----------|-------|
| **Layers** | 2 (transformer or MLP) |
| **Hidden dimension** | 512 |
| **Total parameters** | 7M (attention) / 5M (MLP) |
| **Attention heads** | Multi-head self-attention (attention variant) |
| **Positional encoding** | None (configurable) |
| **H_cycles** (outer reasoning) | 3 |
| **L_cycles** (inner refinement) | 4-6 (task-dependent) |
| **Effective depth** | 42-48 layers (2 layers × 21-24 applications) |

### 2.3 Key Architectural Properties

**Recursion multiplies compute without multiplying parameters**: The same 2-layer block applied 21 times gives 42 effective layers with only 2 layers' worth of unique parameters. This is why TRM generalizes — it cannot memorize a lookup table with 2 layers, so it must learn general rules.

**Full backpropagation through recursion**: Unlike HRM which used the Implicit Function Theorem (IFT) and 1-step gradient approximation, TRM backpropagates through all recursive steps. The training procedure runs T-1 recursion cycles without gradients, then one cycle with full gradient computation.

**No hierarchy**: TRM removes HRM's two-module hierarchy entirely. The "less is more" insight: adding layers decreased generalization due to overfitting, while increasing recursion depth improved performance.

**Post-normalization for stability**: Post-norm (`Norm(h + F(h))`) is essential for recursion stability, bounding hidden state magnitude across recursive updates. Pre-norm (`h + F(Norm(h))`) allows unbounded residual stream growth and causes NaN failures in deep recursion.

### 2.4 Comparison with HRM

| Aspect | HRM | TRM | Improvement |
|--------|-----|-----|-------------|
| Networks | Two (fL, fH) | One | Simpler |
| Layers per network | 4 | 2 | 50% reduction |
| Parameters | 27M | 5-7M | ~75% reduction |
| Gradient method | IFT + 1-step approx | Full backprop | Exact gradients |
| ACT forward passes | 2 per step | 1 per step | 50% reduction |
| Theoretical basis | Fixed-point convergence | Empirical | Fewer assumptions |
| Effective depth | 384 layers | 42-48 layers | Lower but sufficient |

---

## 3. Training

### 3.1 Loss Function

TRM uses a combined loss:
- **Softmax cross-entropy** for answer prediction at each supervision step
- **Binary cross-entropy** for the halting signal (predict when to stop refining)

**Deep supervision**: Loss is computed at each of the K improvement steps, not just the final output. This encourages the model to produce good intermediate answers.

### 3.2 Optimization

| Parameter | Value |
|-----------|-------|
| Optimizer | AdamW |
| β₁, β₂ | 0.9, 0.95 |
| Batch size | 768 (384 for reduced GPU) |
| Hidden size | 512 |
| EMA coefficient | 0.999 |
| Learning rate | 1e-4 |
| Weight decay | 1.0 |
| Training epochs | 50,000 with 5,000-interval evaluation |

### 3.3 Training Compute Requirements

| Task | GPU | Time |
|------|-----|------|
| Sudoku-Extreme | 1× L40S | <20 hours |
| Maze-Hard | 4× L40S (or 1× reduced batch) | <24 hours |
| ARC-AGI-1 | 4× H100 | ~3 days |
| ARC-AGI-2 | 4× H100 | ~3 days |

### 3.4 Data Augmentation

Heavy augmentation is critical:
- **Sudoku**: 1,000 examples × 1,000 augmentations
- **Maze**: 1,000 examples × 8 augmentations
- **ARC**: Dihedral transformations + colour permutations (~880 augmentations per test input)

Augmentation encourages broader solution distributions before single-pass precision improves.

### 3.5 Curriculum-Guided Adaptive Recursion (CGAR)

CGAR ([arxiv:2511.08653](https://arxiv.org/abs/2511.08653)) is a training enhancement that adapts recursion depth during training:

**Progressive Depth Curriculum (PDC)**:
| Stage | Training Progress | Depth (n, T) | Effective Layers |
|-------|------------------|---------------|------------------|
| 1 | 0-30% | (2, 1) | 6 |
| 2 | 30-60% | (4, 2) | 20 |
| 3 | 60-100% | (6, 3) | 42 |

**Hierarchical Supervision Weighting (HSW)**: Applies λ=0.7 exponential decay across supervision steps, concentrating 153× more gradient signal on early steps vs. final steps.

**Results on Sudoku-Extreme**:
- 1.71× training speedup (10.93h → 6.38h)
- 41.4% FLOPs reduction
- Only 0.63% accuracy drop (86.65% → 86.02%)
- 11% fewer inference reasoning steps (5.85 → 5.52)

---

## 4. Benchmark Performance

### 4.1 Primary Results

| Dataset | TRM (7M) | HRM (27M) | DeepSeek-R1 (671B) | o3-mini-high | Gemini 2.5 Pro |
|---------|----------|-----------|---------------------|--------------|----------------|
| Sudoku-Extreme | **87.4%** | 55.0% | 0% | 0% | 0% |
| Maze-Hard | **85.3%** | 74.5% | 0% | 0% | 0% |
| ARC-AGI-1 | **44.6%** | 40.3% | ~21% | ~22% | ~4% |
| ARC-AGI-2 | **7.8%** | 5.0% | — | — | — |

TRM achieves these results with **0.01% of the parameters** of frontier LLMs.

### 4.2 Critical Analysis (Identity Conditioning)

A follow-up study ([arxiv:2512.11847](https://arxiv.org/abs/2512.11847)) found important nuances:

1. **Test-time compute dominance**: 1000-sample voting improves Pass@1 by ~11 percentage points (29.25% → 40.00%). A substantial fraction of reported performance comes from test-time augmentation and majority voting, not pure model capability.

2. **Identity conditioning dependency**: Replacing the correct puzzle ID with a blank or random token yields **0.00% accuracy**. The model has strict functional dependence on task identifiers.

3. **Shallow effective reasoning**: 94.4% of accuracy is achieved at the first recursion step. Performance saturates after step 4, suggesting shallow effective reasoning despite deep supervision.

4. **Synthesis**: TRM's performance arises from "an interaction between efficiency, task-specific conditioning, and aggressive test-time compute, rather than from arbitrarily deep internal reasoning dynamics."

### 4.3 Resource Efficiency

Compared to QLoRA-tuned Llama 3 8B:
- **VRAM**: 2.4 GB vs 6.1 GB
- **Throughput**: 31.3 samples/sec vs 0.24 samples/sec (130× faster)
- **Accuracy**: Substantially higher under comparable training

---

## 5. Extensions and Variants

### 5.1 Mamba-2 Attention Hybrid

[arxiv:2602.12078](https://arxiv.org/abs/2602.12078) (February 2026) replaces Transformer blocks with Mamba-2 + attention hybrid:

**Architecture**: Mamba-2 → Mamba-2 → Attention → MLP pipeline (6.86M parameters, matched to original 6.83M).

**Results on ARC-AGI-1**:
| Metric | TRM-attn (baseline) | TR-mamba2attn | Delta |
|--------|---------------------|---------------|-------|
| Pass@1 | 29.50% | 29.25% | -0.25% |
| Pass@2 | 43.88% | **45.88%** | +2.00% |
| Pass@100 | — | — | +4.75% |

**Key finding**: +27% more unique candidate solutions due to Mamba-2's different solution trajectories during augmentation. The hybrid sacrifices no single-pass quality while dramatically improving ensemble diversity.

### 5.2 Test-Time Adaptation

[arxiv:2511.02886](https://arxiv.org/abs/2511.02886) demonstrates efficient fine-tuning within competition compute budgets:

- **Pre-training**: 700k+ steps, 48h on 4×H100 → 10% on ARC-AGI-2 public eval
- **Competition fine-tuning**: 12,500 steps, 12h on 4×L4 → 6.67% on semi-private eval
- **Insight**: Pre-trained TRM can be efficiently adapted to new task distributions

### 5.3 Recursive Language Models (RLMs)

The broader recursive paradigm is growing rapidly. [arxiv:2512.24601](https://arxiv.org/abs/2512.24601) and [Ouro looped LMs](https://arxiv.org/html/2510.25741v1) establish recursion as a third scaling axis (beyond model size and data). RLMs process inputs 2 orders of magnitude beyond context windows at comparable cost.

---

## 6. Relevance to Autonomy Platform

### 6.1 Architectural Alignment

The Samsung TRM architecture directly validates several design choices in Autonomy's TRM agents:

| Samsung TRM Principle | Autonomy Implementation | Status |
|-----------------------|-------------------------|--------|
| Tiny 2-layer network | 2-layer transformer encoder, 7M params | ✅ Aligned |
| Recursive refinement (3 steps) | 3-step recursive refinement | ✅ Aligned |
| Single network for dual update | SharedStateEncoder → per-task heads | Adapted |
| Deep supervision at each step | Behavioral cloning + RL multi-phase | Adapted |
| Post-norm for stability | Standard transformer post-norm | ✅ Aligned |
| Full backprop through recursion | Standard PyTorch autograd | ✅ Aligned |

### 6.2 Key Differences from Samsung TRM

Autonomy's TRMs are **not** general-purpose puzzle solvers — they are **narrow execution decision agents** constrained by the Powell SDAM framework:

| Dimension | Samsung TRM | Autonomy TRM |
|-----------|-------------|--------------|
| **Task scope** | General reasoning (Sudoku, Maze, ARC) | Narrow execution decisions (ATP, PO, SS, etc.) |
| **Input** | Grid-based puzzle (x) | Supply chain state vector (inventory, backlog, etc.) |
| **Output** | Grid-based answer (y) | Action + continuous quantity |
| **Latent state** | Scratchpad for reasoning (z) | Shared state encoding |
| **Training data** | Puzzle datasets | Engine expert labels + human overrides + outcomes |
| **Training method** | Deep supervision + halting loss | BC warm-start → Offline RL (CQL) → TD learning |
| **Recursion purpose** | Iterative answer refinement | Iterative decision refinement with context |
| **Deployment** | Batch evaluation | Real-time (<10ms per decision) |
| **Identity conditioning** | Task ID embedding (critical dependency) | Site-specific checkpoints (per-site adaptation) |

### 6.3 Insights from Samsung Research Applicable to Autonomy

1. **Recursion > Parameters**: Samsung's finding that 7M params with recursion beats 671B params without recursion validates our choice of tiny models for execution-level decisions. The key is iterative refinement, not model size.

2. **CGAR for training efficiency**: The curriculum-guided adaptive recursion approach could directly improve our TRM training pipeline. Starting with shallow recursion (1 inner cycle) and progressively deepening to 3 cycles during training would reduce training time by ~40% with minimal accuracy loss.

3. **Post-norm is critical**: Samsung confirms that post-normalization (not pre-norm) is essential for recursive stability. Our TRM implementations should verify post-norm placement.

4. **Test-time compute matters**: Samsung showed that majority voting across augmentations dramatically improves accuracy. For production decisions, we could run 3-5 forward passes with perturbed inputs and use median/majority for higher-confidence decisions — essentially a Monte Carlo TRM inference.

5. **Identity conditioning warning**: Samsung's TRM showed 0% accuracy when task IDs were removed. Our per-site checkpoints serve a similar function — the model learns site-specific patterns. This is a feature (not a bug) for supply chain where each site genuinely has different dynamics, but it means site-specific training data is essential.

6. **Shallow effective reasoning**: Samsung found 94.4% of accuracy at step 1, with saturation by step 4. For our 3-step refinement, this suggests most value is in the first refinement step. We could potentially reduce to 2 steps in latency-critical paths (ATP) without significant accuracy loss.

7. **Mamba-2 hybrid for diversity**: The Mamba-2 hybrid generates 27% more diverse candidates. For decisions requiring robustness (safety stock, PO timing), a hybrid architecture could provide better exploration of the decision space.

### 6.4 Potential Improvements Informed by Research

| Improvement | Source | Impact | Effort |
|-------------|--------|--------|--------|
| CGAR training curriculum | arxiv:2511.08653 | ~40% training speedup | Medium |
| Verify post-norm placement | arxiv:2602.12078 | Recursion stability | Low |
| Monte Carlo TRM inference | arxiv:2512.11847 | Higher-confidence decisions | Medium |
| Adaptive halting (early exit) | arxiv:2510.04871 | ~10% faster inference | Medium |
| Mamba-2 hybrid backbone | arxiv:2602.12078 | +27% solution diversity | High |
| Progressive depth during training | arxiv:2511.08653 | Prevent early overfitting | Medium |

---

## 7. The Broader Recursive Paradigm

TRM is part of a larger trend toward recursive computation as a fundamental AI design principle:

### 7.1 The Scaling Argument

Traditional scaling: more parameters → better performance. TRM inverts this:

```
Traditional:  Performance ∝ Parameters
TRM:          Performance ∝ Parameters × Recursion_Steps
```

Recursion trades parameter count for compute time. A 7M model applied 21 times uses similar FLOPs to a single-pass 147M model but generalizes far better because the 7M model cannot memorize — it must learn rules.

### 7.2 Recursive Language Models

The paradigm extends beyond structured puzzles. Recursive Language Models (RLMs) treat long contexts as an external environment, enabling LMs to recursively call themselves over snippets. RLMs process inputs 100× beyond model context windows with comparable quality and cost.

### 7.3 Implications for Supply Chain AI

The recursive paradigm suggests that supply chain decision agents may benefit from:

1. **Recursive replanning**: Instead of one-shot decisions, iteratively refine plans by re-examining constraints
2. **Latent state as working memory**: Maintain a "scratchpad" of intermediate reasoning across decision steps
3. **Compute-optimal deployment**: Choose recursion depth per-decision based on complexity (simple ATP: 1 step, complex multi-source PO: 3+ steps)
4. **Cross-site recursion**: Apply the same tiny model across different sites, with site-specific conditioning (similar to task ID in Samsung's TRM)

---

## 8. Hive Architecture: Multi-Agent Coordination Research

The Autonomy platform's TRM Hive model (11 TRM agents per site coordinating via signals) requires a neural architecture that supports heterogeneous multi-agent coordination. Research across several fields informs the recommended hybrid design. See [TRM_HIVE_ARCHITECTURE.md Section 14](TRM_HIVE_ARCHITECTURE.md) for the full architectural specification.

### 8.1 Stigmergic Multi-Agent RL (S-MADRL)

[S-MADRL](https://arxiv.org/abs/2510.03592) (2025) demonstrates that virtual pheromone-based coordination scales better than explicit messaging: MADDPG and MAPPO collapse beyond 3-4 agents, while S-MADRL scales to 8+ agents. Agents self-organize into asymmetric workload distributions through indirect communication.

**Relevance**: Our UrgencyVector (11 floats, one per TRM type) and HiveSignalBus (typed events with pheromone decay) implement exactly this paradigm. The half-life decay mechanism mirrors pheromone evaporation, preventing stale signals from corrupting coordination.

### 8.2 Heterogeneous Graph Attention (HetNet)

[HetNet](https://arxiv.org/abs/2108.09568) models heterogeneous multi-agent teams (agents with different observation/action spaces) using type-specific attention weights. Results: 200× reduction in communication bandwidth, 5-707% improvement over homogeneous baselines.

**Relevance**: Our 11 TRM types span 5 functional castes (Scouts, Foragers, Nurses, Guards, Builders) with genuinely different inputs and outputs. A heterogeneous GAT layer over the 11 TRM nodes, with caste-to-caste edge types, provides learned inter-TRM coordination at ~2ms per cycle.

### 8.3 PEER (Parameter Efficient Expert Retrieval)

[PEER](https://arxiv.org/abs/2407.04153) (DeepMind, 2024) demonstrates that millions of tiny single-neuron experts outperform fewer large experts via product-key sparse retrieval. The fine-grained MoE scaling law shows higher granularity → better performance.

**Relevance**: Validates our choice of 11 tiny specialized TRM heads (each ~25K params) over a single large model. The principle "many tiny experts > few large experts" aligns with the hive's functional specialization.

### 8.4 Knocking-Heads Attention

[Knocking-Heads](https://arxiv.org/abs/2510.23052) (2025) enables inter-head coordination in multi-head attention via learned cross-head projections that start diagonal (isolated) and gradually develop inter-head communication during training. Zero inference overhead (<1% additional FLOPs).

**Relevance**: Could be applied to the HetGAT layer's attention heads, enabling different attention heads to specialize on different caste-to-caste communication patterns while maintaining coordination.

### 8.5 Recommended Hybrid: Stigmergic-Graph-Recursive

The recommended architecture combines three layers:
1. **Stigmergic** (runtime): UrgencyVector + HiveSignalBus for <1ms indirect coordination
2. **Graph Attention** (per-cycle): HetGAT over 11 TRM nodes for learned type-aware communication (~2ms)
3. **Recursive Refinement** (per-decision): Samsung TRM-style z/y update loop for iterative decision improvement (~3ms)

Total: ~7ms per decision, ~473K parameters. Still tiny, edge-deployable, within the 10ms latency budget.

**Pragmatic start**: Stigmergic layer only (Architecture C) with ~10M training records from digital twin, 5-8 days compute. See [TRM_HIVE_ARCHITECTURE.md](TRM_HIVE_ARCHITECTURE.md) Section 15.11 for training requirements per architecture variant.

### 8.6 Digital Twin as Training Substrate

The critical research insight for hive training: **stigmergic coordination cannot be learned from isolated decision logs**. Multi-head execution traces — where all 11 TRMs run simultaneously against the same site state — are required to generate the signal interaction data that enables emergent coordination.

The platform's simulation stack (SimPy DAG simulator, Beer Game engine, synthetic data generator) functions as a digital twin that produces these coordinated traces without requiring production data. Six-phase pipeline:
1. **Individual BC** (curriculum-generated, 165K records per phase)
2. **Multi-head traces** (coordinated SimPy/Beer Game episodes, 28.6M records)
3. **Site tGNN training** (BC + PPO from coordinated traces, learns cross-TRM causal relationships)
4. **Stochastic stress-testing** (Monte Carlo disruptions, TRMs + Site tGNN active, 17.6M records)
5. **Copilot calibration** (human override patterns, Site tGNN in shadow mode, 4-10K records)
6. **CDC relearning** (production outcome feedback, continuous)

See [TRM_HIVE_ARCHITECTURE.md](TRM_HIVE_ARCHITECTURE.md) Section 15 for the complete pipeline specification.

### 8.7 Multi-Site Coordination: Five-Layer Stack

In production networks (10-200 sites), the coordination challenge extends beyond intra-hive signals to cross-site communication. The architecture uses four layers at increasing scope and latency:

| Layer | Scope | Latency | Mechanism | What Flows |
|---|---|---|---|---|
| **1. Intra-Hive** | Single site | <10ms | UrgencyVector, HiveSignalBus | TRM-to-TRM signals within a site |
| **2. tGNN Inter-Hive** | All sites | Daily | S&OP GraphSAGE + Execution tGNN | Per-site directives, exception forecasts, allocation adjustments |
| **3. AAP Cross-Authority** | Pairwise sites | Seconds-minutes | AuthorizationRequest/Response | Transfers, priority overrides, capacity sharing |
| **4. S&OP Consensus Board** | Enterprise | Weekly | PolicyEnvelope negotiation | Policy parameters θ |

**Key design principle**: TRMs never call across sites. All cross-site information flows through the tGNN directive (passive, daily) or AAP authorization (active, on-demand). This prevents coupling and maintains the <10ms per-decision latency target.

See [TRM_HIVE_ARCHITECTURE.md](TRM_HIVE_ARCHITECTURE.md) Section 16 for the complete multi-site physical architecture.

---

## 9. Source Papers and References

### Primary TRM Research (Samsung SAIL Montreal)

| Paper | ArXiv | Date | Key Contribution |
|-------|-------|------|------------------|
| Less is More: Recursive Reasoning with Tiny Networks | [2510.04871](https://arxiv.org/abs/2510.04871) | Oct 2025 | Original TRM architecture |
| Hierarchical Reasoning Model | [2506.21734](https://arxiv.org/abs/2506.21734) | Jun 2025 | Predecessor (HRM) |
| Test-time Adaptation of Tiny Recursive Models | [2511.02886](https://arxiv.org/abs/2511.02886) | Nov 2025 | Competition fine-tuning |
| TRM on ARC-AGI-1: Inductive Biases, Identity Conditioning | [2512.11847](https://arxiv.org/abs/2512.11847) | Dec 2025 | Critical analysis |
| Tiny Recursive Reasoning with Mamba-2 Attention Hybrid | [2602.12078](https://arxiv.org/abs/2602.12078) | Feb 2026 | Mamba-2 variant |
| Accelerating Training via CGAR | [2511.08653](https://arxiv.org/abs/2511.08653) | Nov 2025 | Curriculum training |

### Code and Implementation

- **GitHub**: [SamsungSAILMontreal/TinyRecursiveModels](https://github.com/SamsungSAILMontreal/TinyRecursiveModels)
- **HuggingFace**: [papers/2510.04871](https://huggingface.co/papers/2510.04871)

### Multi-Agent Coordination (Hive Architecture)

| Paper | ArXiv | Key Contribution |
|-------|-------|------------------|
| S-MADRL: Stigmergic Multi-Agent Deep RL | [2510.03592](https://arxiv.org/abs/2510.03592) | Virtual pheromone coordination, scales to 8+ agents |
| HetNet: Heterogeneous Graph Attention for Multi-Agent | [2108.09568](https://arxiv.org/abs/2108.09568) | Type-aware attention, 200× bandwidth reduction |
| PEER: Mixture of a Million Experts | [2407.04153](https://arxiv.org/abs/2407.04153) | Fine-grained expertise: many tiny > few large |
| Knocking-Heads Attention | [2510.23052](https://arxiv.org/abs/2510.23052) | Zero-overhead inter-head coordination |
| MAPPO: Multi-Agent PPO | [2103.01955](https://arxiv.org/abs/2103.01955) | CTDE training paradigm |
| Agentic LLM Consensus in Supply Chain | [tandfonline:2025](https://www.tandfonline.com/doi/full/10.1080/00207543.2025.2604311) | Multi-agent consensus-seeking for SC |
| HydraLoRA: Asymmetric LoRA for Multi-Task | [2404.19245](https://arxiv.org/abs/2404.19245) | Shared A matrix, per-task B matrices |
| Multi-Task Shared + Task-Specific Encodings | [2505.24281](https://arxiv.org/abs/2505.24281) | Dual-encoder framework |

### Data Volume & Model Scaling (Learning by Watching)

| Paper | Reference | Key Contribution |
|-------|-----------|------------------|
| Stöckl (RANLP 2021): "Watching a Language Model Learning Chess" | [ACL Anthology](https://aclanthology.org/2021.ranlp-1.148/) | Data volume scaling laws for small models: GPT2-small/medium/large trained on 99K/577K/2.2M chess games. Data volume >> model size for structured decision tasks. Standard metrics (perplexity) misleading — domain-specific eval needed. |
| Kaplan et al. (2020): "Scaling Laws for Neural Language Models" | [arxiv:2001.08361](https://arxiv.org/abs/2001.08361) | Power-law relationship between model size, data volume, and compute. Scale model and data together — model size alone doesn't help. |

**Stöckl 2021 findings applied to TRM training:**

1. **Data volume matters more than model size** for structured decision tasks. GPT2-small (124M params) with enough data outperformed GPT2-large (774M params) with insufficient data on chess move legality. For our 7M-param TRMs, this means data volume is the primary lever — not architecture changes.

2. **Standard loss metrics are misleading**. Low training loss did not predict correct game play. The models that appeared to converge (low perplexity) still made illegal moves. **Implication**: We cannot rely on BC loss alone — we need domain-specific evaluation (correct decision rate on held-out states).

3. **Three-tier evaluation is essential**: (a) Memorization — can the model reproduce training data? (b) Generalization — can it handle unseen states from the same distribution? (c) Rule learning — has it internalized the underlying decision rules (tested via adversarial/edge-case states)?

4. **Data volume thresholds for 7M-param models** (extrapolated from Stöckl + Kaplan):
   - <10K samples: Memorization only, no generalization
   - 50K–150K samples: "Medium" regime — rule learning begins
   - 500K+ samples: Robust generalization, handles edge cases

Our Phase 1 BC training now generates 50K samples/sub-phase × 3 sub-phases × 3 signal phases = 450K total BC samples per TRM, placing us solidly in the robust generalization regime. The `StochasticCurriculumWrapper.generate(multiplier=M)` method enables further scaling via independent Monte Carlo draws.

### Related Work (Recursive Models)

- [Recursive Language Models](https://arxiv.org/abs/2512.24601) — Context folding via recursive LM calls
- [Ouro: Scaling Latent Reasoning via Looped Language Models](https://arxiv.org/html/2510.25741v1) — Pre-trained recursive LMs
- [Relaxed Recursive Transformers (Google DeepMind)](https://arxiv.org/abs/2410.20672) — LoRA-based parameter sharing across repeated blocks

### Summaries and Analysis

- [Nature: 'Tiny' AI model beats massive LLMs at logic test](https://www.nature.com/articles/d41586-025-03379-9)
- [MarkTechPost: TRM surpasses DeepSeek-R1, Gemini 2.5 Pro](https://www.marktechpost.com/2025/10/09/tiny-recursive-model-trm-a-tiny-7m-model-that-surpass-deepseek-r1-gemini-2-5-pro-and-o3-mini-at-reasoning-on-both-arg-agi-1-and-arc-agi-2/)
- [LearnOpenCV: TRM Tiny AI Models Outsmarting Giants](https://learnopencv.com/trm-tiny-ai-models-outsmarting-giants-on-complex-puzzles/)
- [deeplearning.ai: TRM Beats Larger Competitors](https://www.deeplearning.ai/the-batch/tiny-recursive-model-beats-larger-competitors-at-games-like-sudoku-and-maze/)
- [SiliconAngle: Samsung creates tiny AI model that shames biggest LLMs](https://siliconangle.com/2025/10/09/samsung-researchers-create-tiny-ai-model-shames-biggest-llms-reasoning-puzzles/)
- [AI Papers Academy: TRM Paper Explained](https://aipapersacademy.com/tiny-recursive-model/)
- [Medium: The End of the Scaling Era](https://machine-learning-made-simple.medium.com/the-end-of-the-scaling-era-how-recursive-reasoning-outperforms-billion-parameter-models-36d7e3274049)
- [Vunda AI: The $500 AI That Just Beat Gemini](https://www.vunda.ai/blog/samsung-trm-tiny-recursive-model)
