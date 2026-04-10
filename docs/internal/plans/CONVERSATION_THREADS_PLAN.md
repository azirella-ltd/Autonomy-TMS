# Conversation Threads Plan

**Created:** 2026-04-10
**Last updated:** 2026-04-10
**Status:** v0.5 shipped on ui-core (`adca0c2`) and TMS (`4c20c8ca`); SCP-side migration in progress on msi-stealth in parallel
**Goal:** Promote `InlineComments` to `@autonomy/ui-core` as `Conversation`, surface it across TMS-native entities, and extend it to support human ↔ agent dialog with Azirella as the default agent participant.

---

## Why this plan exists

The TMS repo (and the SCP repo it was forked from) both ship a fully-built threaded discussion widget — `InlineComments` — that sits on four legacy pages (PurchaseOrders, TransferOrders, Recommendations, Invoices) and is **invisible everywhere else**. The component, the backend `comments` table, and the polymorphic `(entity_type, entity_id)` schema were all built speculatively and never product-driven into the rest of either app.

At the same time, AIIO surfaces a structured Inspect → Override-with-reason flow on every Decision Stream card, but there is no place for the **conversation** that *precedes* an override:

- "Why are we routing this through Memphis?" — a question from one human to another, or from a human to an agent
- "Driver running 30 min late, can we hold the dock slot?" — coordination between planner, broker, and dock agent
- "Customer asked us to expedite — what does it cost to switch to air?" — a what-if discussion before any action is taken

Today these conversations happen in Slack and email, vanish from the system of record, and never feed the agent's training data. The widget that *should* host them already exists.

This plan promotes the widget to the shared package, surfaces it widely, and extends it so that agents — invoked via @mention — become first-class participants in the same threads humans use.

---

## Scope decisions (what's IN and what's OUT)

### IN scope

- **Human ↔ human** threaded discussion attached to any entity
- **Human ↔ agent** dialog initiated by an `@<agent>` mention from a human
- **Azirella as the universal agent participant** — `@Azirella` is the canonical entry point for asking the system anything; per-TRM mentions are available for users who know exactly which agent they want
- **Persistent, queryable, append-only audit trail** of every exchange tied to an entity
- **Reuse of existing infrastructure** — `Comment` SQLAlchemy model, `/comments` endpoint, existing TRM `askWhy`/`chat` methods

### OUT of scope (deferred or rejected)

- ❌ **Agent ↔ agent conversations.** Different shape, different volume, different latency. Cross-TRM coordination stays in the existing Hive signal bus. If a future need emerges to *narrate* coordination loops to humans, that becomes a separate widget reading from a different substrate.
- ❌ **Proactive agent posting.** Agents only reply when a human pulls them in. No `narrate()` helper, no signal-bus-to-comments bridge. This is the constraint that keeps volume manageable.
- ❌ **Real-time websocket push for comments.** Pull-after-post is fine; humans tolerate 2-5 seconds. Can be added later if needed.
- ❌ **Replacement of the override-with-reason dialog.** Override is the binding decision moment with a structured reason code that feeds the replay buffer. Conversation threads are the *journey* to the override, not the override itself.
- ❌ **Replacement of Azirella's voice/wake-word panel.** Azirella stays a global, voice-capable assistant. Comment threads are entity-scoped. Both shapes coexist; @Azirella in a thread invokes the same backend Azirella that the floating panel invokes.

---

## Design principles

1. **Humans and agents are peers in one thread.** No special "agent reply" panel. Agents post into the same comments table with the same shape. Visual treatment (icon, badge, tinted border) makes the distinction scannable.
2. **Agents only respond.** No autonomous narration. The volume of the comments table grows with human conversation pace, not agent decision pace.
3. **Reuse the Comment table.** No schema rewrite. The `(entity_type, entity_id, parent_id)` polymorphic shape already supports everything we need. Authorship is solved with synthetic users (one row per agent).
4. **Override-with-reason is canonical; conversation is context.** If a user overrides a decision after a 5-message Q&A in the thread, the override row is the binding signal. The thread is queryable context the replay buffer can join against later.
5. **Ship value in increments.** v0.5 promotes and surfaces. v0.6 expands surface area. v0.7 adds agents. Each increment is independently valuable; v0.7 is optional.

---

## Architecture

### Author identity — synthetic users

The `comments.author_id` column FKs to `users`. To support agent authors *without* a schema migration, we create one synthetic user row per agent type at provisioning time:

| `users.email` | `users.full_name` | `users.role` | `users.is_agent` |
|---|---|---|---|
| `azirella@autonomy.tms` | Azirella | agent | `true` |
| `capacity_promise@autonomy.tms` | Capacity Promise Agent | agent | `true` |
| `freight_procurement@autonomy.tms` | Freight Procurement Agent | agent | `true` |
| `dock_scheduling@autonomy.tms` | Dock Scheduling Agent | agent | `true` |
| `exception_management@autonomy.tms` | Exception Management Agent | agent | `true` |
| ... | ... | agent | `true` |

The frontend keys off `is_agent` to render visual treatment. The mention autocomplete returns these alongside human users with a discriminator.

**Why not a discriminator column on `comments.author_type`?** Cleaner long-term, but every comment query and the backend response shape would need updating. Synthetic users avoid that work and produce a working system in v0.7. We can refactor to a discriminator later if a real reason emerges (e.g. an agent identity model that predates the user model, or wanting agents to live in a separate table for IAM reasons).

### The agent-mention bridge (v0.7)

When a comment is created and contains an `@<agent>` mention, a new backend hook fires:

```
POST /comments
  ↓
parse content for @-mentions
  ↓
for each mention pointing at an agent user (is_agent=true):
  ↓
  invoke AgentBridgeService.respond_to_mention(
    agent_user_id,
    thread_root_id,
    entity_type,
    entity_id,
    prior_comments,
    mentioning_user
  )
  ↓
AgentBridgeService:
  - looks up which TRM the agent_user_id corresponds to
    (Azirella → general dispatcher; specific TRM → that TRM)
  - calls existing `askWhy()` or `chat()` with thread context
  - posts the agent's response as a new Comment row
    with author_id = agent_user_id, parent_id = thread_root_id
  - notifies the mentioning user (existing notification path)
```

This is the **only new backend code** in v0.7. The TRM services already have `askWhy` and `chat` methods. The bridge just routes from "comment with mention" → "TRM call" → "comment posted as response."

### `@Azirella` as the universal participant

For users who don't know which TRM owns a question, `@Azirella` is the universal entry point. The Azirella backend already knows how to dispatch to any TRM. In a thread, `@Azirella why is this routed through Memphis?` invokes the same dispatcher logic that the voice bar invokes — the only difference is that the response is posted as a comment in the thread instead of streamed back as voice.

This avoids building a new "agent dispatcher" service. Azirella is the dispatcher.

Per-TRM mentions (`@DockSchedulingAgent`) remain available for users who want to target a specific agent. Power users will use them; novice users will use `@Azirella`.

### What happens to "Ask Why"

Today, Decision Stream cards have an "Ask Why" button that calls a stateless `askWhy(decisionId, decisionType)` endpoint and returns a one-shot reasoning blob with no follow-up support and no persistence.

In v0.7, every powell decision gets an auto-generated thread with the agent's initial reasoning posted as the first comment at decision time. "Ask Why" becomes "open the conversation thread on this decision" — the user sees the agent's reasoning, can ask follow-ups, and other humans can join. The whole exchange is preserved.

The stateless `askWhy` endpoint stays for now (backwards compat) but gets superseded.

---

## Phased delivery

### v0.5 — Promote and rename

**Goal:** `InlineComments` becomes `Conversation` in `@autonomy/ui-core`. Both products consume it. Existing 4 SC-legacy pages migrate to the package version. No new functionality.

**Work in `autonomy-ui-core` repo:**

1. Add `Conversation` type contracts in `src/types/conversation.ts`:
   - `Conversation` (the comment shape)
   - `ConversationAuthor` (with `is_agent` flag)
   - `ConversationsClient` interface (list / create / update / delete / pin / listMentionableUsers)
   - `CommentType` enum

2. Add `ConversationsProvider` + `useConversationsClient()` hook in `src/contexts/ConversationsContext.tsx` (mirror of `DecisionStreamContext`).

3. Port `InlineComments.jsx` → `Conversation.tsx`:
   - Replace direct `api.*` calls with `client.*` calls
   - Replace `formatDistanceToNow` from `date-fns` with a tiny inline relative-time formatter (avoid the new dep)
   - Replace local common imports (`./index`) with ui-core's existing common primitives (Card, Button, Badge, Alert, Spinner, Input, etc.)
   - Add basic TypeScript types (component is currently untyped JSX)
   - Drop the imports we don't yet have (Textarea, Select, Label, IconButton) and substitute equivalents from the existing common primitives or inline minimal versions

4. Export `Conversation`, `ConversationsProvider`, `useConversationsClient`, types from `src/index.ts`

5. Build, bump to `v0.5.0`, commit, push

**Work in `Autonomy-TMS` repo:**

6. Write `frontend/src/services/tmsConversationsClient.js` adapter — implements `ConversationsClient` against the existing `/comments` and `/users` endpoints

7. Wrap `index.js` providers with `<ConversationsProvider client={tmsConversationsClient}>`

8. Update the 4 SC-legacy pages (PurchaseOrders, TransferOrders, Recommendations, Invoices) to import `Conversation` from `@autonomy/ui-core` instead of the local `InlineComments`

9. Verify `npm run build` is clean for the swapped files

10. Commit

**Work in `Autonomy` (SCP) repo:**

11. Same migration on the same 4 pages. Separate PR. Out of scope for this session.

**Defer to v0.6:** deletion of local `InlineComments.jsx` and `components/decision-stream/` from TMS — those are blocked on the `pages/DecisionStream.jsx` migration which we're handling as a separate workstream.

---

### v0.6 — Surface widely (humans only)

**Goal:** Wire `<Conversation>` into the top TMS-native entities. Still humans-only — no agent participation yet.

**TMS surfaces (in priority order):**

1. **Decision Stream cards** — embed in the card detail/expanded view. Replaces nothing yet (the existing "Ask Why" stays). This is the highest-leverage surface because every agent decision becomes commentable.
2. **Exception detail** (in [pages/planning/ExceptionDashboard.jsx](frontend/src/pages/planning/ExceptionDashboard.jsx)) — every exception generates multi-party human coordination. This is where the widget earns its keep.
3. **Shipment detail** (in the shipment tracking views) — daily collaboration on individual moves.
4. **Load detail** (in [pages/planning/LoadBoard.jsx](frontend/src/pages/planning/LoadBoard.jsx)) — load planner ↔ ops coordination.

**SCP surfaces** (separate workstream): demand plans, supply plans, production orders, MO/TO execution. The model docstring already names them.

**Validation:** before shipping v0.6, validate placement and UX with a real planner (or product judgment). Don't wire it into a surface that won't get used.

---

### v0.7 — Human ↔ agent (Azirella + per-TRM)

**Goal:** Agents become first-class participants. Humans `@Azirella` in any thread to get a contextual answer. Per-TRM mentions work for power users.

**Backend work (TMS):**

1. **Provisioning script update** — at customer provisioning time, create the synthetic agent user rows: one for `azirella@autonomy.tms`, one per TRM type. Mark `is_agent=true` (add the column if it doesn't exist). Single alembic migration adds the column; idempotent.

2. **Agent bridge service** — `app/services/agent_mention_bridge.py`. Single function:
   ```
   respond_to_mention(agent_user_id, thread_root_id, entity_type, entity_id, prior_comments, mentioning_user) -> Comment
   ```
   Looks up which TRM (or Azirella) corresponds to the agent_user_id, calls the existing `askWhy`/`chat` service with thread context, posts the response as a new Comment row.

3. **`/comments` POST hook** — when a new comment is created, parse for `@<agent>` mentions and invoke the bridge for each. Background task; the POST returns immediately and the agent comments appear shortly after via the existing comment-list pull.

4. **`/users` endpoint update** — return `is_agent` flag so the frontend can render agents distinctly in mention autocomplete.

**Frontend work (in `@autonomy/ui-core`):**

5. **Visual treatment for agent comments:**
   - If `comment.author.is_agent`, render the avatar as a colored circle with a robot/zap icon (lucide `Bot`) instead of an initial
   - Add an "Agent" badge next to the name
   - Render `comment.author_confidence` inline if present (small chip: "confidence 0.87")
   - Subtle border tint on agent comments

6. **Mention autocomplete** distinguishes agents — agents in their own section of the dropdown with a robot icon, sorted to the top so users discover them.

7. **Optimistic agent placeholder** — when a user submits a comment with an agent mention, show a "🤖 Agent is thinking..." placeholder until the agent's response arrives.

8. **Permission rules** — humans cannot edit/delete/pin agent comments. Agents cannot pin themselves. Already partially handled via the `isAuthor` check; just extend it.

**Validation:**

- Wire the first agent-mention into Decision Stream cards (highest signal-to-noise — every decision has an agent that owns it)
- Pilot with one TRM (probably CapacityPromise or DockScheduling) before exposing all 11
- Confirm that override-with-reason still feels like the canonical action and the conversation feels like context

---

## File-level deliverables — v0.5

### `autonomy-ui-core` repo

```
src/
├── types/
│   └── conversation.ts                    [NEW]
├── contexts/
│   ├── ConversationsContext.tsx           [NEW]
│   └── index.ts                           [UPDATE: export Conversations]
├── components/
│   └── conversation/                      [NEW directory]
│       ├── Conversation.tsx               [NEW — port of InlineComments]
│       ├── CommentItem.tsx                [NEW — extracted subcomponent]
│       ├── CommentForm.tsx                [NEW — extracted subcomponent]
│       └── index.ts                       [NEW]
├── lib/
│   └── utils/
│       └── relativeTime.ts                [NEW — replaces date-fns]
└── index.ts                               [UPDATE: export conversation]
```

`package.json`: bump to `v0.5.0`. No new runtime deps (we replace `date-fns` with the inline formatter).

### `Autonomy-TMS` repo

```
frontend/src/
├── services/
│   └── tmsConversationsClient.js          [NEW]
├── index.js                               [UPDATE: wrap with ConversationsProvider]
└── pages/planning/
    ├── PurchaseOrders.jsx                 [UPDATE: import from @autonomy/ui-core]
    ├── TransferOrders.jsx                 [UPDATE]
    ├── Recommendations.jsx                [UPDATE]
    └── Invoices.jsx                       [UPDATE]
```

The local `frontend/src/components/common/InlineComments.jsx` is **not deleted** in v0.5 — left in place to avoid breaking anything we missed. Deletion happens in a cleanup commit after both apps are migrated.

---

## Open questions (decisions deferred)

1. **Where do per-TRM mentions live in the autocomplete?** Top-level alongside humans, or under an "Agents" subsection? Probably subsection — discoverable but not noisy.

2. **Should agent comments support markdown?** Today human comments are plain text (with optional `content_html`). Agent responses from `askWhy`/`chat` often want bullet points and emphasis. Either render markdown for all comments, or only for agent comments. Deferred to v0.7 implementation.

3. **Does the conversation thread scroll independently of the entity detail page, or render inline?** Affects whether a long thread pushes the rest of the detail page off-screen. Probably needs a max-height + internal scroll. Deferred to v0.6 implementation.

4. **Soft delete for agent comments?** Agents can't delete their own comments today (no UI). But should an admin be able to retract an agent comment that's wrong? Probably yes — but record the retraction in a way that's visible (struck through, not invisible). Deferred to v0.7.

5. **Notification routing for agent responses.** When `@Azirella` is mentioned and Azirella replies, who gets notified? The original mentioner, or everyone subscribed to the thread? Use the existing notification system but confirm the routing rules. Deferred to v0.7.

---

## Risks

1. **Channel conflict with override-with-reason.** If users start having their override discussions in the conversation thread instead of the override dialog, the structured override signal weakens. Mitigation: enforce the rule via UX — the conversation widget in v0.6+ links explicitly to the override dialog, framed as "When you've decided, click Override to record your decision."

2. **Surfacing without product validation.** It's tempting to wire `<Conversation>` into every detail page in v0.6. Resist that — pick the 3-4 highest-leverage surfaces, validate they're used, then expand. A widget that's everywhere but used nowhere is worse than a widget on a few pages where it's loved.

3. **Agent comment quality.** TRM `askWhy`/`chat` outputs were not designed to be read in a comment thread next to human messages. They may be too long, too technical, or too repetitive. v0.7 should include a pass on the prompt formatting so agent comments read like a colleague's response, not a stack trace.

4. **`is_agent` column on `users`.** This is the one schema change in v0.7. Risk: breaking existing user queries. Mitigation: default `false`, no backfill needed, the column is purely additive.

---

## Tracking

| Phase | Status | Where | Commit / Notes |
|---|---|---|---|
| v0.5 Promote `InlineComments` → `Conversation` (ui-core) | **DONE** | acer-nitro | `MilesAheadToo/autonomy-ui-core@adca0c2` (v0.5.0) |
| v0.5 TMS adapter + provider + 4-page migration | **DONE** | acer-nitro | `Autonomy-TMS@4c20c8ca` |
| v0.5 SCP adapter + provider + 4-page migration | **In progress** | msi-stealth | Running in parallel session — `scpConversationsClient` + index.js + 4 pages being changed there |
| v0.6 Wire into TMS-native surfaces (Exception, Shipment, Load, DS card) | Not started | TBD | — |
| v0.6 Wire into SCP-native surfaces (demand/supply plans, prod orders) | Not started | TBD | — |
| v0.7 Synthetic agent users + bridge service (TMS backend) | Not started | TBD | — |
| v0.7 Visual treatment + mention autocomplete (ui-core) | Partially shipped in v0.5 — `is_agent` rendering, `Bot` icon, blue treatment, "Agent" badge, confidence chip already in `Conversation.tsx` | acer-nitro | `MilesAheadToo/autonomy-ui-core@adca0c2` |
| v0.7 First wire-up: Decision Stream cards + CapacityPromise pilot | Not started | TBD | — |

### Per-product machine split (2026-04-10)

The work is split by **product**, not by phase:

- **acer-nitro** = **TMS station.** Single-repo focus on `Autonomy-TMS` + `autonomy-ui-core` releases. Landed `@autonomy/ui-core` v0.4 (`filterByType`) and v0.5 (`Conversation`), all 11 TMS worklist swaps, and the TMS-side Conversation adoption. Phase 2.5, v0.6 surfacing into TMS-native entities, and v0.7 TMS backend work all continue here.
- **msi-stealth** = **multi-repo primary workspace.** SCP development, the `Autonomy` → `Autonomy-SCP` rename, future workspace meta-repo setup. The SCP-side Conversation v0.5 migration (`scpConversationsClient`, provider wiring, the same 4 SC-legacy pages) is in flight here. Treat msi-stealth as authoritative for the SCP repo and for the rename.

**The narrow rule:** acer-nitro does not touch the SCP repo locally. That's the only restriction. TMS development on acer-nitro proceeds normally and does not block on msi-stealth.

**After the rename settles on msi-stealth:** acer-nitro pulls in `Autonomy-TMS`, optionally clones the renamed SCP repo as a read-only reference, ignores the workspace meta-repo entirely.
