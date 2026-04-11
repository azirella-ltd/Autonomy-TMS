/**
 * TMS Decision Type Registrations
 *
 * Registers all 11 TMS TRM decision types with @azirella-ltd/autonomy-frontend's
 * decisionTypeRegistry. Call `registerTMSDecisionTypes()` once at app
 * boot (in App.js, before rendering routes).
 *
 * Coverage by phase:
 *   SENSE   — capacity_promise, shipment_tracking, demand_sensing
 *   ASSESS  — capacity_buffer, exception_management
 *   ACQUIRE — freight_procurement, broker_routing
 *   PROTECT — dock_scheduling
 *   BUILD   — load_build, intermodal_transfer
 *   REFLECT — equipment_reposition
 */

import { registerDecisionTypes } from '@azirella-ltd/autonomy-frontend';

// SENSE phase
import { capacityPromiseType } from './capacityPromise';
import { shipmentTrackingType } from './shipmentTracking';
import { demandSensingType } from './demandSensing';

// ASSESS phase
import { capacityBufferType } from './capacityBuffer';
import { exceptionManagementType } from './exceptionManagement';

// ACQUIRE phase
import { freightProcurementType } from './freightProcurement';
import { brokerRoutingType } from './brokerRouting';

// PROTECT phase
import { dockSchedulingType } from './dockScheduling';

// BUILD phase
import { loadBuildType } from './loadBuild';
import { intermodalTransferType } from './intermodalTransfer';

// REFLECT phase
import { equipmentRepositionType } from './equipmentReposition';

/**
 * Register all 11 TMS decision types with the @azirella-ltd/autonomy-frontend registry.
 * Idempotent — safe to call multiple times.
 *
 * Verify registration by calling getRegisteredDecisionTypeCount() — should
 * return 11 immediately after this call.
 */
export function registerTMSDecisionTypes() {
  registerDecisionTypes([
    // SENSE
    capacityPromiseType,
    shipmentTrackingType,
    demandSensingType,
    // ASSESS
    capacityBufferType,
    exceptionManagementType,
    // ACQUIRE
    freightProcurementType,
    brokerRoutingType,
    // PROTECT
    dockSchedulingType,
    // BUILD
    loadBuildType,
    intermodalTransferType,
    // REFLECT
    equipmentRepositionType,
  ]);
}

// Re-export individual types for direct import if needed
export {
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
};
