/**
 * @autonomy/ui-core Integration Example
 *
 * This file demonstrates how a TMS worklist page (or the main
 * Decision Stream page) would use the shared @autonomy/ui-core
 * package once Phase 2 of TMS_INDEPENDENCE_PLAN is executed.
 *
 * It is **NOT** wired into the router yet — it serves as a reference
 * for the adoption work. Filename starts with `_` so existing tooling
 * doesn't auto-import it.
 *
 * To activate this example:
 *   1. npm install /home/trevor/autonomy-ui-core (or
 *      npm install github:MilesAheadToo/autonomy-ui-core)
 *   2. Move the registerTMSDecisionTypes() call to App.js (run once at boot)
 *   3. Wrap the app root with the three providers
 *   4. Rename this file to AutonomyUICoreExample.jsx (drop underscore)
 *   5. Add a route for it
 *
 * The actual swap of the existing 11 worklist pages happens in Phase 2.
 */
import React from 'react';
// FROM the new shared package:
import {
  DecisionStreamProvider,
  CapabilitiesProvider,
  DecisionStream,
  useCapabilities,
  registerDecisionTypes,
} from '@autonomy/ui-core';

// TMS-specific:
import { tmsDecisionStreamClient } from '../../services/tmsDecisionStreamClient';
import { tmsCapabilitiesClient } from '../../services/tmsCapabilitiesClient';
import {
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
} from '../../decisionTypes';

// Run once — typically this lives in App.js, not in a page.
// Putting it here for the standalone example.
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

/**
 * Inner component — has access to useCapabilities because it's
 * inside the providers below.
 */
function DecisionStreamExampleInner({ configId }) {
  const { hasCapability, loading } = useCapabilities();

  if (loading) {
    return <div className="p-4 text-muted-foreground">Loading capabilities…</div>;
  }

  return (
    <DecisionStream
      configId={configId}
      title="TMS Decision Stream"
      subtitle="All 11 TMS agent types rendered via @autonomy/ui-core"
      // Override permission gated by TMS capability
      canOverride={hasCapability('manage_decision_stream')}
      // Admin flag controls CDT readiness banner detail
      isAdmin={hasCapability('manage_tenant_users')}
    />
  );
}

/**
 * Top-level page — wires the providers around the inner component.
 *
 * In a real adoption, the providers would live in App.js so they're
 * available to ALL pages, not just this one. Showing them here for
 * a self-contained example.
 */
export default function AutonomyUICoreExample() {
  // In real usage, configId comes from context (e.g., useActiveConfig())
  const configId = 1;

  return (
    <DecisionStreamProvider client={tmsDecisionStreamClient}>
      <CapabilitiesProvider client={tmsCapabilitiesClient}>
        <DecisionStreamExampleInner configId={configId} />
      </CapabilitiesProvider>
    </DecisionStreamProvider>
  );
}
