/**
 * Planning Pages Index
 *
 * Exports all planning-related components for the cascade:
 * - S&OP Policy Page (modular layer with input/review/feedback)
 * - MPS Candidates Page (modular layer with tradeoff analysis)
 * - Supply Worklist Page (modular layer with worklist/manual input)
 * - Allocation Worklist Page (modular layer with worklist/manual input)
 * - Execution Page (foundation + TRM + feedback signals)
 * - Cascade Dashboard (orchestrator)
 *
 * Legacy Screen components retained for backward compatibility.
 */

// New modular cascade pages (Feb 2026)
export { default as SOPPolicyPage } from './SOPPolicyPage';
export { default as MPSCandidatesPage } from './MPSCandidatesPage';
export { default as SupplyWorklistPage } from './SupplyWorklistPage';
export { default as AllocationWorklistPage } from './AllocationWorklistPage';
export { default as ExecutionPage } from './ExecutionPage';

// Legacy screen components
export { default as SOPPolicyScreen } from './SOPPolicyScreen';
export { default as MPSCandidateScreen } from './MPSCandidateScreen';
export { default as SupplyAgentWorklist } from './SupplyAgentWorklist';
export { default as AllocationAgentWorklist } from './AllocationAgentWorklist';
export { default as CascadeDashboard } from './CascadeDashboard';

// Re-export existing planning pages
export { default as MasterProductionScheduling } from './MasterProductionScheduling';

// Phase 7 TMS pages
export { default as ShipmentMap } from './ShipmentMap';
export { default as P44Dashboard } from './P44Dashboard';
