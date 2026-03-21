# Azirella Assistant — UX Engagement Paradigm

## Design Principles

Azirella follows the **Claude Code / Cowork engagement model** adapted for supply chain planners:

1. **Show your work** — never a bare spinner. Show what Azirella is doing at each step.
2. **Coach, don't interrogate** — when information is missing, rewrite the user's prompt with colored placeholders instead of asking form-like questions.
3. **Use the DAG** — every clarification option comes from the tenant's actual supply chain topology. Never guess or hallucinate options.
4. **Respect authority boundaries** — Azirella answers any question but only executes actions within the user's role scope.
5. **Progressive disclosure** — show the most important information first, let users drill deeper.

---

## Pattern 1: Prompt Rewrite Preview (IMPLEMENTED)

When the user types a directive (not a question), Azirella:

1. **Parses** the intent and identifies missing fields
2. **Rewrites** the prompt with enriched context and placeholders
3. **Displays** the enriched version with color coding:
   - **White text**: the user's original words (unchanged)
   - **Purple text**: context Azirella added (product names resolved, sites identified)
   - **Red ? (large, bold, pulsing)**: information Azirella needs from the user
4. **Waits** for the user to fill in the `?` marks and submit, or edit as text

```
User types: "increase safety stock for frozen"

Azirella shows:
┌────────────────────────────────────────────────────────────┐
│ Azirella understood this as:                                │
│                                                             │
│ increase safety stock for Frozen Proteins [FROZEN/FRZ_PROTEIN] │
│ at ? by ? because ?                                         │
│                                                             │
│ Your words    Added context    ?  Needs your input           │
│                                                             │
│ ▸ Edit as text                                              │
│                                                             │
│ Replace the ? marks, then submit        [Cancel] [Submit]   │
└────────────────────────────────────────────────────────────┘
```

The `?` markers are:
- **Red** (#ef4444)
- **Extra large** (text-xl, ~20px vs 14px body text)
- **Bold** (font-black, 900 weight)
- **Pulsing** (subtle CSS animation to draw attention)

### Implementation
- Frontend: `AzirellaPopup.jsx` — enrichedDisplay renderer splits rephrased prompt into segments
- Backend: `directive_service.py` — the `/directives/analyze` endpoint returns `rephrased_prompt` with `?` placeholders for missing fields

---

## Pattern 2: Progressive Step Summary (PLANNED)

For multi-step operations (provisioning, supply plan generation, strategy evaluation), Azirella streams progress as action cards:

```
Azirella: Executing your strategy...

  ✓ Priority raised to P1 — ATP re-consumption allocates 320 units     (0.3s)
  ⟳ Creating production order at Plant 1 US — 80 units of C900 BIKE... (running)
  ○ Expediting Frame-900 PO — awaiting procurement agent authorization  (queued)
```

Each step shows:
- Status icon: ✓ complete, ⟳ running, ○ queued
- One-line description of the action
- One-line result summary when complete
- Duration

### Technical approach
- Backend sends SSE (Server-Sent Events) for each step
- Frontend renders action cards that fill in as events arrive
- Collapsed view: single progress bar with step count
- Expanded view: full step list with results

---

## Pattern 3: Ghost Text Completion (PLANNED)

As the user types in the Azirella input, show dimmed template text completing their partial input:

```
User typing: "increase safe"
Ghost text:   "increase safety stock for [product] at [site] by [amount]"
```

The ghost text comes from a static template registry (not LLM-generated, for speed):

| Prefix | Template |
|--------|----------|
| `increase` | `increase [metric] for [product] at [site] by [amount]` |
| `decrease` | `decrease [metric] for [product] at [site] by [amount]` |
| `what is` | `what is the [metric] for [product] at [site]?` |
| `show me` | `show me [metric] trends for [product] over [period]` |
| `compare` | `compare [metric] between [site A] and [site B]` |
| `bigmart` | `Bigmart just called — they need [quantity] of [product] delivered to [location] in [timeframe]` |

Ghost text is accepted with Tab, ignored by continuing to type.

### Technical approach
- Frontend: custom input component with overlay span for ghost text
- Template registry: static JSON, no API call
- Match: prefix matching with fuzzy tolerance

---

## Pattern 4: Conversational Clarification (IMPLEMENTED, ENHANCED)

When fields are missing, Azirella uses the DAG topology to offer valid options:

```
User: "What's the revenue for the SW region?"

Azirella: "I can show you revenue for the Southwest region.
          Do you want all product categories, or a specific one?
          Your product categories are: Beverages, Dry Goods,
          Frozen Desserts, Frozen Proteins, Refrigerated Dairy."
```

If the user gives an invalid value:
```
User: "Moon"

Azirella: "I don't recognise 'Moon' as a region.
          The regions in your network are:
          NW (Seattle/Portland), SW (Los Angeles/San Diego),
          Central, NE, SE."
```

### Technical approach
- Backend: `_get_dag_topology()` loads sites, products, regions from the SC config
- Injected into the LLM system prompt as `=== SUPPLY CHAIN TOPOLOGY ===`
- LLM instructed to use ONLY these options for clarification

---

## Pattern 5: Related Prompts / Follow-ups (PLANNED)

After answering a question or completing a directive, Azirella suggests 2-3 contextual follow-up actions as clickable chips:

```
Azirella: "The current OTIF for Frozen Proteins is 94.2%,
          up 1.6pp from last week."

  [What's driving the improvement?]
  [Show trend over last 8 weeks]
  [Compare across regions]
```

Clicking a chip populates the input and auto-submits.

### Technical approach
- Backend: LLM response includes a `follow_ups` array in the response JSON
- Frontend: render as horizontal scrollable chip row below the answer
- Chips are pre-formatted prompts with context already injected

---

## Pattern 6: Confidence Badges on Responses (PLANNED)

Every Azirella response about data includes a confidence indicator:

```
Azirella: "The demand forecast for Orange Juice next week is 1,240 units."
          [P50 forecast | 90% interval: 980–1,520 | Source: LightGBM + conformal]
```

This surfaces the conformal prediction intervals directly in the conversational response, building trust through transparency.

---

## Role-Scoped Responses

The LLM system prompt includes:
- User's role title and scope (from `ROLE_DESCRIPTIONS`)
- What they CAN and CANNOT do
- Instruction to refuse actions outside scope with a helpful redirect

Example:
```
User (Executive): "Create a PO for 500 widgets"

Azirella: "As a Supply Chain Executive, I can help you understand
          the procurement position for widgets. Currently there are
          3 active POs totaling 1,200 units.

          To create a new PO, your MPS Manager or Procurement team
          would need to action that. Would you like me to summarize
          the current procurement status instead?"
```

---

## Voice Integration

- **Demo mode**: Browser Web Speech API (functional but basic)
- **Production mode**: Enterprise voice services (higher accuracy, multi-language)
- **Voice responses**: Same content as text, but Azirella only speaks if the user initiated via voice
- **Voice coaching**: Azirella reads the clarification options aloud, pauses for response

---

## Implementation Status

| Pattern | Status | Files |
|---------|--------|-------|
| Prompt Rewrite Preview | **Implemented** | `AzirellaPopup.jsx` |
| DAG Topology Clarification | **Implemented** | `decision_stream_service.py` |
| Role-Scoped Responses | **Implemented** | `decision_stream_service.py` |
| Progressive Step Summary | Planned | SSE infrastructure exists |
| Ghost Text Completion | Planned | Frontend only |
| Related Prompts | Planned | Backend + Frontend |
| Confidence Badges | Planned | Conformal data exists |
