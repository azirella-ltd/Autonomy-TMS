# WorkspaceShell Adoption Plan

**Created:** 2026-04-10
**Status:** Option A complete (banner-only edits in both apps); Option B pending
**Goal:** Both Autonomy SCP and Autonomy TMS render their entire app chrome via `@autonomy/ui-core`'s `WorkspaceShell` component, with all app-specific behavior injected via slots.

---

## Where we are today

### Option A — Banner alignment (DONE)

Both `TopNavbar.jsx` files in TMS and SCP have been surgically updated
to match the visual design of `@autonomy/ui-core`'s `TopAppBar.tsx`:

- **TMS commit:** `e67d9e62` — TMS banner: align with @autonomy/ui-core TopAppBar layout (v0.2)
- **SCP commit:** `6805e848` — SCP banner: align with @autonomy/ui-core TopAppBar layout (v0.2) (on `adopt-autonomy-ui-core` branch)

What changed in both files:
- Logo bumped from `h-7` to `h-9`
- Brand text "Autonomy <suffix>" rendered next to the logo
  - "Autonomy" semibold
  - Suffix ("TMS" or "SCP") muted accent
  - Both `text-base` — same size as the centered "Config:" line
- Active config moved to a centered slot in the flex-1 middle column
- Three explicit columns: LEFT (logo+brand) → CENTER (config) → RIGHT (actions)

This is a **drop-in visual fix** with no behavior changes. The existing
TopNavbar still owns Azirella, voice input, user menu, notifications,
help button, system admin context switching, sidebar toggle, and tenant
logo display.

### What's still hand-rolled per app

Each app has its own ~966-line `TopNavbar.jsx` containing:

- Azirella voice input bar (portalled into the header)
- Voice state animations (LISTENING, PROCESSING, SPEAKING)
- Voice assistant clarification flow + popup
- "Hey Azirella" wake-word handler
- User menu with logout, profile, settings, MFA
- Tenant logo display
- System admin context switcher (`/system` → org list)
- Help button + notifications button
- Mobile/responsive sidebar handling

Each app also has its own ~479-line `WorkspaceShell.jsx` containing:

- Multi-tab system (`useTabStore`, `TabPane`, `NewTabPalette`)
- Provisioning banner
- Azirella floating avatar (bottom-right)
- Azirella panel + resize handle
- Tab content caching for background tabs

None of this is in `@autonomy/ui-core` yet. **Option B** is the work
to promote it.

---

## Option B — Full WorkspaceShell adoption

### Goal

Replace each app's hand-rolled `TopNavbar.jsx` + `WorkspaceShell.jsx`
with the package's `WorkspaceShell` component. App-specific behavior
becomes injectable slots/props.

### What needs to be promoted to the package

#### Tier 1 — Probably needed in both apps, low complexity

| Feature | Current location | Target package home |
|---|---|---|
| **TabBar** (multi-tab strip) | `TabBar.jsx` (124 lines) | `src/components/shell/TabBar.tsx` |
| **TabPane** (DOM-preserving wrapper) | `TabPane.jsx` | `src/components/shell/TabPane.tsx` |
| **NewTabPalette** (Ctrl+T command palette) | `NewTabPalette.jsx` | `src/components/shell/NewTabPalette.tsx` |
| **useTabStore** (Zustand) | `stores/useTabStore.js` | `src/stores/useTabStore.ts` |
| **Help button** | inline in TopNavbar | slot prop on TopAppBar |
| **Notifications button + dot** | inline in TopNavbar | slot prop on TopAppBar |
| **User menu dropdown** | inline in TopNavbar | optional `<UserMenu>` component or slot |

#### Tier 2 — Azirella (decision: shared or per-app?)

The Azirella voice/chat feature is significant. Two paths:

**Path 1 — Promote Azirella to the package**

| Feature | Current | Target |
|---|---|---|
| `AzirellaAvatar` | local component | `src/components/azirella/AzirellaAvatar.tsx` |
| `AzirellaPanel` (right-side chat) | local | `src/components/azirella/AzirellaPanel.tsx` |
| `AzirellaPopup` (clarification modal) | local | `src/components/azirella/AzirellaPopup.tsx` |
| Voice input bar (portalled) | inline in TopNavbar | `src/components/azirella/AzirellaInputBar.tsx` |
| `useVoiceAssistant` hook | local | `src/hooks/useVoiceAssistant.ts` |
| Voice state coloring | inline | exported constants |

The Azirella **backend client** (analyze, stream, directives) becomes
another injectable interface like `DecisionStreamClient` — each app
implements it against its own backend. The UI components are
domain-agnostic.

**Pros:** Both apps share the AI assistant UX. Brand consistency.
**Cons:** Big component (~600 lines across 3 files). Tight coupling
with app's chat/directive backend. Risk of premature abstraction if
the two apps end up wanting different Azirella behavior.

**Path 2 — Keep Azirella per-app, expose a generic `centerSlot`**

Each app injects whatever it wants into `<TopAppBar centerSlot={...}>`.
TMS injects its Azirella input bar; SCP injects its own. The package
doesn't know about Azirella at all.

**Pros:** Maximum flexibility. No shared package dependency on the
voice assistant. Apps can experiment independently.
**Cons:** Code duplication (~600 lines in each app). Visual drift risk.

**Recommendation:** Path 2 for now. Promote Azirella to the package
in v0.4 once we see how both apps actually use it.

#### Tier 3 — Provisioning banner (TMS-specific?)

The provisioning banner shows a "system is provisioning…" notice when
the backend is mid-warm-start. Currently TMS-only (since SCP is
already provisioned). Likely stays in TMS.

If SCP also wants a similar banner pattern, the package could expose
`<WorkspaceShell globalBanner={<ProvisioningBanner />}>` — which is
already supported in v0.2.

---

## Phased migration

### Phase B1 — Promote tab system to the package
**Estimated effort:** ~2 days

1. Port `TabBar.jsx` → `src/components/shell/TabBar.tsx`
2. Port `TabPane.jsx` → `src/components/shell/TabPane.tsx`
3. Port `NewTabPalette.jsx` → `src/components/shell/NewTabPalette.tsx`
4. Port `useTabStore.js` → `src/stores/useTabStore.ts`
5. Add `<WorkspaceShell tabs>` mode that wraps content in TabPanes
6. Update TMS `WorkspaceShell.jsx` to use the package's TabBar instead
   of the local one (incremental — keep the rest of the local file)
7. Same for SCP
8. Tag `@autonomy/ui-core` v0.3.0

### Phase B2 — Promote user menu, help, notifications
**Estimated effort:** ~1 day

1. Port the user menu dropdown to the package as `<UserMenu>` component
2. Accept `menuItems` prop for app-specific links
3. Accept `user` prop with name, avatar, tenant_logo
4. Accept `onLogout`, `onSwitchTenant` callbacks
5. Add `<TopAppBar actions={<><HelpButton /> <NotificationsButton /> <UserMenu /></>} />`
6. Update both apps to use the new actions
7. Delete the old hand-rolled actions code from each app's TopNavbar

### Phase B3 — Replace local TopNavbar with package WorkspaceShell
**Estimated effort:** ~1 day per app

1. In TMS, replace the use of `<TopNavbar />` in `WorkspaceShell.jsx`
   with `<WorkspaceShell productSuffix="TMS" actions={...} centerSlot={...} />`
2. Delete the local `TopNavbar.jsx` (or shrink it to just the Azirella
   bits if Azirella stays per-app)
3. Same for SCP
4. Visually validate both apps still look identical to before

### Phase B4 — Optional: promote Azirella to the package
**Estimated effort:** ~3-5 days (only if we decide on Path 1 above)

---

## What "done" looks like

After all of Option B:

- **TMS `App.js`** has a single `<WorkspaceShell productSuffix="TMS" ...>`
  wrapping its routes. No local `TopNavbar.jsx` or `WorkspaceShell.jsx`
  in the TMS repo — all chrome comes from the package.
- **SCP `App.js`** likewise has `<WorkspaceShell productSuffix="SCP" ...>`.
  Both repos lose ~1500 lines of duplicated chrome code each.
- A future banner change (e.g., "make the brand text bigger again")
  is one edit in `@autonomy/ui-core` and both apps inherit it.
- A future tab pattern change is also one edit.
- New products (executive console, demo console) get the same chrome
  for free by installing the package.

---

## Tracking

| Phase | Status | Owner | Started | Completed |
|---|---|---|---|---|
| Option A — Banner alignment | DONE | Claude/Trevor | 2026-04-10 | 2026-04-10 |
| Option B Phase B1 — Tab system | Not started | TBD | — | — |
| Option B Phase B2 — User menu/actions | Not started | TBD | — | — |
| Option B Phase B3 — Replace TopNavbar | Not started | TBD | — | — |
| Option B Phase B4 — Azirella (optional) | Not started | TBD | — | — |
