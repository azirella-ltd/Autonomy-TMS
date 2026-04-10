# autonomy-ui-core Package Design

**Status:** Draft for review
**Purpose:** Define the structure, contracts, and conventions of the shared `@autonomy/ui-core` npm package that both Autonomy SCP and Autonomy TMS will consume.

This document is the **design contract** — once approved, the package gets created in a separate repo (`MilesAheadToo/autonomy-ui-core`) and developed there.

---

## Package overview

| Field | Value |
|-------|-------|
| Name | `@autonomy/ui-core` |
| Repository | `github:MilesAheadToo/autonomy-ui-core` |
| Version | `0.1.0` (initial) |
| License | (Same as parent products) |
| Build | `tsc` (TypeScript) → `dist/` ESM + CJS |
| Tests | Vitest + React Testing Library |
| Storybook | Yes — for component preview and design review |

**Peer dependencies** (consumers must provide):
- `react@>=18`
- `react-dom@>=18`
- `react-router-dom@>=6`
- `lucide-react@>=0.300`
- `tailwindcss@>=3.4`

**Direct dependencies** (bundled):
- `clsx`, `tailwind-merge` (for `cn()` utility)
- `zustand` (for tab/nav stores)
- `react-markdown` (for digest rendering)

---

## File tree

```
autonomy-ui-core/
├── package.json
├── tsconfig.json
├── tailwind.config.js              ← exported preset for consumers
├── vite.config.ts                  ← Storybook + build config
├── README.md
├── CHANGELOG.md
│
├── src/
│   ├── index.ts                    ← public exports
│   │
│   ├── components/
│   │   ├── decision-stream/
│   │   │   ├── DecisionStream.tsx          ← top-level inbox container
│   │   │   ├── DecisionCard.tsx            ← individual decision card
│   │   │   ├── DecisionCard.types.ts
│   │   │   ├── DigestMessage.tsx           ← LLM-synthesized summary
│   │   │   ├── AlertBanner.tsx             ← top alert strip
│   │   │   ├── CDTReadinessBanner.tsx
│   │   │   ├── ChatDataBlock.tsx           ← inline chat data
│   │   │   ├── AskWhyPanel.tsx             ← "why did you decide that"
│   │   │   ├── OverrideDialog.tsx          ← override flow modal
│   │   │   ├── DecisionStatusBadge.tsx
│   │   │   ├── ReasonCodeSelector.tsx
│   │   │   └── index.ts
│   │   │
│   │   ├── common/
│   │   │   ├── Card.tsx
│   │   │   ├── Button.tsx
│   │   │   ├── Badge.tsx
│   │   │   ├── Input.tsx
│   │   │   ├── Select.tsx
│   │   │   ├── Modal.tsx
│   │   │   ├── Alert.tsx
│   │   │   ├── Spinner.tsx
│   │   │   ├── Skeleton.tsx
│   │   │   ├── Table.tsx
│   │   │   ├── Tabs.tsx
│   │   │   ├── Tooltip.tsx
│   │   │   ├── Toast.tsx
│   │   │   ├── Progress.tsx
│   │   │   ├── Accordion.tsx
│   │   │   └── index.ts
│   │   │
│   │   ├── navigation/
│   │   │   ├── TwoTierNav.tsx              ← main app nav
│   │   │   ├── CategoryBar.tsx             ← top-level categories
│   │   │   ├── PageBar.tsx                 ← page-level nav
│   │   │   ├── NavigationProvider.tsx      ← context for nav config injection
│   │   │   └── index.ts
│   │   │
│   │   ├── workspace/
│   │   │   ├── WorkspaceShell.tsx          ← VS Code-style tabbed workspace
│   │   │   ├── TabBar.tsx
│   │   │   ├── TabPane.tsx                 ← preserves DOM state
│   │   │   ├── NewTabPalette.tsx           ← Ctrl+T command palette
│   │   │   └── index.ts
│   │   │
│   │   ├── azirella/
│   │   │   ├── AzirellaAvatar.tsx          ← animated avatar
│   │   │   ├── AzirellaPanel.tsx           ← right-side chat panel
│   │   │   ├── AzirellaPopup.tsx
│   │   │   └── index.ts
│   │   │
│   │   ├── metrics/
│   │   │   ├── GartnerMetricCard.tsx       ← KPI card with trend
│   │   │   ├── CompositeMetricCard.tsx     ← multi-component KPI
│   │   │   ├── Sparkline.tsx
│   │   │   ├── HierarchyFilterBar.tsx
│   │   │   └── index.ts
│   │   │
│   │   └── charts/
│   │       ├── SankeyDiagram.tsx           ← generic flow diagram (data-driven nodes)
│   │       ├── RoleTimeSeries.tsx
│   │       └── index.ts
│   │
│   ├── hooks/
│   │   ├── useCapabilities.ts              ← RBAC hook
│   │   ├── useDecisionStream.ts            ← Decision Stream API hook
│   │   ├── useTabStore.ts                  ← Zustand tab state
│   │   ├── useVoiceAssistant.ts            ← Web Speech API
│   │   ├── useToast.ts
│   │   └── index.ts
│   │
│   ├── registries/
│   │   ├── decisionTypeRegistry.ts         ← THE key extension point
│   │   ├── iconRegistry.ts                 ← optional icon overrides
│   │   ├── reasonCodeRegistry.ts           ← per-app override reason codes
│   │   ├── statusRegistry.ts               ← per-app status colors/labels
│   │   └── index.ts
│   │
│   ├── contexts/
│   │   ├── DecisionStreamContext.tsx       ← backend client injection
│   │   ├── CapabilitiesContext.tsx         ← user capabilities injection
│   │   ├── ThemeContext.tsx                ← color tokens injection
│   │   └── index.ts
│   │
│   ├── theme/
│   │   ├── tailwind-preset.js              ← shared Tailwind config preset
│   │   ├── tokens.ts                       ← color/spacing tokens
│   │   └── index.ts
│   │
│   ├── lib/
│   │   ├── utils/
│   │   │   ├── cn.ts                       ← className merger
│   │   │   ├── formatters.ts               ← currency, date, percent
│   │   │   └── time.ts
│   │   └── index.ts
│   │
│   └── types/
│       ├── decision.ts                     ← Decision, DecisionStatus, DecisionUrgency
│       ├── client.ts                       ← DecisionStreamClient interface
│       ├── navigation.ts                   ← NavigationConfig interface
│       └── index.ts
│
└── stories/                                ← Storybook stories
    ├── DecisionStream.stories.tsx
    ├── DecisionCard.stories.tsx
    ├── TwoTierNav.stories.tsx
    └── ...
```

---

## Public exports (`src/index.ts`)

```typescript
// Components
export * from './components/decision-stream';
export * from './components/common';
export * from './components/navigation';
export * from './components/workspace';
export * from './components/azirella';
export * from './components/metrics';
export * from './components/charts';

// Hooks
export * from './hooks';

// Registries (the extension points)
export * from './registries';

// Contexts (for client/config injection)
export * from './contexts';

// Theme
export { default as autonomyTailwindPreset } from './theme/tailwind-preset';
export * from './theme/tokens';

// Utilities
export * from './lib/utils/cn';
export * from './lib/utils/formatters';

// Types
export * from './types';
```

---

## Core contracts

### 1. Decision Type Registry

**This is the critical extension point.** Apps register their decision types at boot; shared components consume the registry to render correctly.

```typescript
// src/registries/decisionTypeRegistry.ts

export interface EditableField {
  key: string;
  label: string;
  type: 'number' | 'text' | 'date' | 'select' | 'textarea';
  options?: string[] | { value: string; label: string }[];
  helperText?: string;
  inputProps?: Record<string, any>;
}

export interface DecisionTypeConfig {
  /** Unique identifier — matches backend decision_type value */
  id: string;

  /** Human-readable label shown in UI */
  label: string;

  /** Lucide React icon component */
  icon: React.ComponentType<{ className?: string; size?: number }>;

  /** Optional decision-cycle phase grouping */
  phase?: 'SENSE' | 'ASSESS' | 'ACQUIRE' | 'PROTECT' | 'BUILD' | 'REFLECT';

  /** Color hint for badges/cards */
  color?: 'primary' | 'success' | 'warning' | 'danger' | 'info';

  /** Fields the user can override in the override dialog */
  editableFields: EditableField[];

  /** Optional custom context renderer (e.g., carrier waterfall, ETA chart) */
  renderContext?: (decision: Decision) => React.ReactNode;

  /** Optional custom summary renderer for the decision card body */
  renderSummary?: (decision: Decision) => React.ReactNode;

  /** Override reason codes specific to this decision type (overrides app default) */
  reasonCodes?: { value: string; label: string }[];
}

const registry = new Map<string, DecisionTypeConfig>();

export function registerDecisionType(config: DecisionTypeConfig): void {
  if (registry.has(config.id)) {
    console.warn(`[autonomy-ui-core] Decision type "${config.id}" is already registered. Overwriting.`);
  }
  registry.set(config.id, config);
}

export function registerDecisionTypes(configs: DecisionTypeConfig[]): void {
  configs.forEach(registerDecisionType);
}

export function getDecisionType(id: string): DecisionTypeConfig | undefined {
  return registry.get(id);
}

export function getAllDecisionTypes(): DecisionTypeConfig[] {
  return Array.from(registry.values());
}

export function getDecisionTypesByPhase(phase: string): DecisionTypeConfig[] {
  return getAllDecisionTypes().filter((t) => t.phase === phase);
}

export function clearDecisionTypeRegistry(): void {
  registry.clear();
}
```

### 2. Decision Stream Client

```typescript
// src/types/client.ts

export interface DigestResponse {
  decisions: Decision[];
  summary?: string;             // LLM-synthesized digest text
  alerts?: Alert[];
  timestamp: string;
}

export interface ActDecisionRequest {
  action: 'accept' | 'override' | 'reject' | 'inspect';
  reason_code?: string;
  reason_text?: string;
  override_values?: Record<string, any>;
}

export interface DecisionStreamClient {
  getDigest(opts?: { config_id?: number; level?: string }): Promise<DigestResponse>;
  refresh(): Promise<DigestResponse>;
  actOnDecision(decisionId: number, request: ActDecisionRequest): Promise<void>;
  chat(message: string, history?: ChatMessage[]): Promise<ChatResponse>;
  askWhy(decisionId: number): Promise<AskWhyResponse>;
  getDecisionTimeSeries(decisionId: number): Promise<TimeSeriesResponse>;
}
```

### 3. Decision Stream Provider

```typescript
// src/contexts/DecisionStreamContext.tsx

import { createContext, useContext } from 'react';
import type { DecisionStreamClient } from '../types/client';

const DecisionStreamContext = createContext<DecisionStreamClient | null>(null);

export function DecisionStreamProvider({
  client,
  children
}: {
  client: DecisionStreamClient;
  children: React.ReactNode;
}) {
  return (
    <DecisionStreamContext.Provider value={client}>
      {children}
    </DecisionStreamContext.Provider>
  );
}

export function useDecisionStreamClient(): DecisionStreamClient {
  const client = useContext(DecisionStreamContext);
  if (!client) {
    throw new Error('useDecisionStreamClient must be used within DecisionStreamProvider');
  }
  return client;
}
```

### 4. Capabilities Provider

```typescript
// src/contexts/CapabilitiesContext.tsx

export interface CapabilitiesProvider {
  capabilities: string[];
  loading: boolean;
  hasCapability: (cap: string) => boolean;
  hasAnyCapability: (caps: string[]) => boolean;
  hasAllCapabilities: (caps: string[]) => boolean;
}

// Apps inject their own implementation (TMS uses its own /api/capabilities/me,
// SCP uses its own, executive console aggregates).
export const CapabilitiesContext = createContext<CapabilitiesProvider | null>(null);

export function useCapabilities(): CapabilitiesProvider {
  const ctx = useContext(CapabilitiesContext);
  if (!ctx) throw new Error('useCapabilities requires CapabilitiesProvider');
  return ctx;
}
```

### 5. Navigation Configuration

```typescript
// src/types/navigation.ts

export interface NavItem {
  label: string;
  path?: string | null;
  icon?: React.ComponentType;
  requiredCapability?: string;
  description?: string;
  isSectionHeader?: boolean;
  children?: NavItem[];
}

export interface NavSection {
  section: string;
  sectionIcon?: React.ComponentType;
  divider?: boolean;
  adminOnly?: boolean;
  items: NavItem[];
}

export type NavigationConfig = NavSection[];
```

Apps inject their own `NavigationConfig` via `<NavigationProvider config={tmsNavConfig}>`.

---

## Example: TMS app integration

```typescript
// Autonomy-TMS/frontend/src/decisionTypes/freightProcurement.ts
import { Gavel } from 'lucide-react';
import type { DecisionTypeConfig } from '@autonomy/ui-core';
import { CarrierWaterfallPanel } from '../components/CarrierWaterfallPanel';

export const freightProcurementType: DecisionTypeConfig = {
  id: 'freight_procurement',
  label: 'Freight Procurement Agent',
  icon: Gavel,
  phase: 'ACQUIRE',
  editableFields: [
    { key: 'carrier_id', label: 'Carrier', type: 'text' },
    { key: 'rate_override', label: 'Rate Override ($)', type: 'number' },
    { key: 'action', label: 'Action', type: 'select',
      options: ['tender', 'defer', 'spot', 'broker'] },
  ],
  renderContext: (decision) => <CarrierWaterfallPanel decision={decision} />,
};
```

```typescript
// Autonomy-TMS/frontend/src/decisionTypes/index.ts
import { registerDecisionTypes } from '@autonomy/ui-core';
import { capacityPromiseType } from './capacityPromise';
import { shipmentTrackingType } from './shipmentTracking';
import { demandSensingType } from './demandSensing';
import { capacityBufferType } from './capacityBuffer';
import { exceptionManagementType } from './exceptionManagement';
import { freightProcurementType } from './freightProcurement';
import { brokerRoutingType } from './brokerRouting';
import { dockSchedulingType } from './dockScheduling';
import { loadBuildType } from './loadBuild';
import { intermodalTransferType } from './intermodalTransfer';
import { equipmentRepositionType } from './equipmentReposition';

export function registerTMSDecisionTypes(): void {
  registerDecisionTypes([
    capacityPromiseType,
    shipmentTrackingType,
    demandSensingType,
    capacityBufferType,
    exceptionManagementType,
    freightProcurementType,
    brokerRoutingType,
    dockSchedulingType,
    loadBuildType,
    intermodalTransferType,
    equipmentRepositionType,
  ]);
}
```

```typescript
// Autonomy-TMS/frontend/src/services/tmsDecisionStreamClient.ts
import type { DecisionStreamClient } from '@autonomy/ui-core';
import { api } from './api';

export const tmsDecisionStreamClient: DecisionStreamClient = {
  getDigest: async (opts) => {
    const { data } = await api.get('/decision-stream/digest', { params: opts });
    return data;
  },
  refresh: async () => {
    const { data } = await api.post('/decision-stream/refresh');
    return data;
  },
  actOnDecision: async (decisionId, request) => {
    await api.post('/decision-stream/action', { decision_id: decisionId, ...request });
  },
  chat: async (message, history) => {
    const { data } = await api.post('/decision-stream/chat', { message, history });
    return data;
  },
  askWhy: async (decisionId) => {
    const { data } = await api.get(`/decision-stream/${decisionId}/why`);
    return data;
  },
  getDecisionTimeSeries: async (decisionId) => {
    const { data } = await api.get(`/decision-stream/${decisionId}/timeseries`);
    return data;
  },
};
```

```tsx
// Autonomy-TMS/frontend/src/App.tsx
import {
  DecisionStreamProvider,
  CapabilitiesContext,
  NavigationProvider,
} from '@autonomy/ui-core';
import { registerTMSDecisionTypes } from './decisionTypes';
import { tmsDecisionStreamClient } from './services/tmsDecisionStreamClient';
import { tmsCapabilities } from './services/tmsCapabilities';
import { tmsNavConfig } from './config/tmsNavConfig';

// Register at module load — happens once at app startup
registerTMSDecisionTypes();

export function App() {
  return (
    <DecisionStreamProvider client={tmsDecisionStreamClient}>
      <CapabilitiesContext.Provider value={tmsCapabilities}>
        <NavigationProvider config={tmsNavConfig}>
          <Routes>{/* TMS-specific pages */}</Routes>
        </NavigationProvider>
      </CapabilitiesContext.Provider>
    </DecisionStreamProvider>
  );
}
```

```tsx
// Autonomy-TMS/frontend/src/pages/planning/CapacityPromiseWorklistPage.tsx
import {
  DecisionStream,
  Card,
  Button,
  useCapabilities,
} from '@autonomy/ui-core';

export function CapacityPromiseWorklistPage() {
  const { hasCapability } = useCapabilities();
  // The DecisionStream component looks up the 'capacity_promise' type from
  // the registry and renders the right columns, override fields, and context.
  return (
    <DecisionStream
      filterByType="capacity_promise"
      title="Capacity Promise Worklist"
      canManage={hasCapability('manage_capacity_promise_worklist')}
    />
  );
}
```

---

## What stays out of `autonomy-ui-core`

- **Domain-specific pages** (LoadBoard, Carrier Management, S&OP, MRP) — these belong to each app
- **API service modules** — each app has its own backend client
- **Domain icons / colors / labels** — passed via the registry
- **Authentication flow** — each app handles its own login/MFA against its own backend
- **Tenant management** — app-specific
- **Backend services** (Powell, conformal, governance) — separate optional `autonomy-scp-core` Python package

---

## Open questions for review

1. **TypeScript or JavaScript?** Current TMS frontend is JS. The shared package is more maintainable in TS. Consumers can still write JS.
2. **Tailwind preset bundling** — should we publish the Tailwind config as a preset, or document the required tokens?
3. **Storybook hosting** — GitHub Pages? Chromatic? Internal only?
4. **Versioning strategy** — semver with breaking changes in major versions? Or 0.x until first prod use?
5. **Test coverage target** — 80%? Component snapshot tests?
6. **Should `autonomy-ui-core` include the Azirella backend client too?** Voice/chat is a feature, but the LLM endpoint is app-specific.

---

## Next steps (after this design is approved)

1. Create `MilesAheadToo/autonomy-ui-core` repo with this skeleton
2. Build out the registries and contexts first (the contracts)
3. Port `DecisionCard`, `DecisionStream`, `OverrideDialog` from current TMS code, stripping domain knowledge
4. Port common components
5. Add Storybook
6. Tag `v0.1.0`
7. TMS adopts via Phase 2 of TMS_INDEPENDENCE_PLAN
