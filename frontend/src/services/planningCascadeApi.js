/**
 * Planning Cascade API Service
 *
 * Covers all 5 cascade layers:
 * S&OP → MRS → Supply Agent → Allocation Agent → Execution
 *
 * Supports both FULL and INPUT modes for modular selling.
 */
import { api } from './api';

const BASE = '/planning-cascade';

// =============================================================================
// Layer License
// =============================================================================

export const getLayerLicenses = async (groupId) => {
  const res = await api.get(`${BASE}/layer-license/${groupId}`);
  return res.data;
};

export const updateLayerLicense = async (groupId, layer, mode, packageTier = null) => {
  const res = await api.put(`${BASE}/layer-license/${groupId}`, {
    layer,
    mode,
    package_tier: packageTier,
  });
  return res.data;
};

export const setPackageTier = async (groupId, tier, userId = null) => {
  const res = await api.put(
    `${BASE}/layer-license/${groupId}/package/${tier}`,
    null,
    { params: { user_id: userId } }
  );
  return res.data;
};

// =============================================================================
// Policy Envelope (S&OP Layer)
// =============================================================================

export const createPolicyEnvelope = async (data) => {
  const res = await api.post(`${BASE}/policy-envelope`, data);
  return res.data;
};

export const getActivePolicyEnvelope = async (configId, asOfDate = null) => {
  const params = asOfDate ? { as_of_date: asOfDate } : {};
  const res = await api.get(`${BASE}/policy-envelope/active/${configId}`, { params });
  return res.data;
};

export const getPolicyEnvelopeFeedback = async (configId) => {
  const res = await api.get(`${BASE}/policy-envelope/feedback/${configId}`);
  return res.data;
};

// =============================================================================
// Supply Baseline Pack (MRS Layer)
// =============================================================================

export const createSupplyBaselinePack = async (data) => {
  const res = await api.post(`${BASE}/supply-baseline-pack`, data);
  return res.data;
};

export const getSupplyBaselinePack = async (supbpId) => {
  const res = await api.get(`${BASE}/supply-baseline-pack/${supbpId}`);
  return res.data;
};

// =============================================================================
// Supply Commit (Supply Agent Layer)
// =============================================================================

export const generateSupplyCommit = async (supbpId, mode = 'copilot') => {
  const res = await api.post(`${BASE}/supply-commit/${supbpId}`, null, {
    params: { mode },
  });
  return res.data;
};

export const getSupplyCommit = async (commitId) => {
  const res = await api.get(`${BASE}/supply-commit/${commitId}`);
  return res.data;
};

export const reviewSupplyCommit = async (commitId, userId, action, overrideDetails = null) => {
  const res = await api.post(
    `${BASE}/supply-commit/${commitId}/review`,
    { action, override_details: overrideDetails },
    { params: { user_id: userId } }
  );
  return res.data;
};

export const submitSupplyCommit = async (commitId, userId = null) => {
  const res = await api.post(`${BASE}/supply-commit/${commitId}/submit`, null, {
    params: { user_id: userId },
  });
  return res.data;
};

export const askWhySupplyCommit = async (commitId) => {
  const res = await api.get(`${BASE}/supply-commit/${commitId}/ask-why`);
  return res.data;
};

// =============================================================================
// Allocation Commit (Allocation Agent Layer)
// =============================================================================

export const generateAllocationCommit = async (supplyCommitId, mode = 'copilot') => {
  const res = await api.post(`${BASE}/allocation-commit/${supplyCommitId}`, null, {
    params: { mode },
  });
  return res.data;
};

export const getAllocationCommit = async (commitId) => {
  const res = await api.get(`${BASE}/allocation-commit/${commitId}`);
  return res.data;
};

export const reviewAllocationCommit = async (commitId, userId, action, overrideDetails = null) => {
  const res = await api.post(
    `${BASE}/allocation-commit/${commitId}/review`,
    { action, override_details: overrideDetails },
    { params: { user_id: userId } }
  );
  return res.data;
};

export const submitAllocationCommit = async (commitId, userId = null) => {
  const res = await api.post(`${BASE}/allocation-commit/${commitId}/submit`, null, {
    params: { user_id: userId },
  });
  return res.data;
};

export const askWhyAllocationCommit = async (commitId) => {
  const res = await api.get(`${BASE}/allocation-commit/${commitId}/ask-why`);
  return res.data;
};

// =============================================================================
// Cascade Orchestration
// =============================================================================

export const runCascade = async (data) => {
  const res = await api.post(`${BASE}/cascade/run`, data);
  return res.data;
};

export const getCascadeStatus = async (configId) => {
  const res = await api.get(`${BASE}/cascade/status/${configId}`);
  return res.data;
};

// =============================================================================
// Feed-Back Signals
// =============================================================================

export const getFeedbackSignals = async (configId, { fedBackTo, acknowledged, limit } = {}) => {
  const params = {};
  if (fedBackTo) params.fed_back_to = fedBackTo;
  if (acknowledged !== undefined) params.acknowledged = acknowledged;
  if (limit) params.limit = limit;
  const res = await api.get(`${BASE}/feedback-signals/${configId}`, { params });
  return res.data;
};

export const createFeedbackSignal = async (data) => {
  const res = await api.post(`${BASE}/feedback-signal`, data);
  return res.data;
};

export const applyFeedbackSignal = async (signalId, userId = null) => {
  const res = await api.post(`${BASE}/feedback-signals/${signalId}/apply`, null, {
    params: { user_id: userId },
  });
  return res.data;
};

// =============================================================================
// Lineage
// =============================================================================

export const getArtifactLineage = async (artifactType, artifactId) => {
  const res = await api.get(`${BASE}/lineage/${artifactType}/${artifactId}`);
  return res.data;
};

// =============================================================================
// Metrics
// =============================================================================

export const getAgentMetrics = async (configId, agentType, limit = 10) => {
  const res = await api.get(`${BASE}/metrics/${configId}/${agentType}`, {
    params: { limit },
  });
  return res.data;
};

// =============================================================================
// Worklist
// =============================================================================

export const getSupplyWorklist = async (configId, status = null) => {
  const params = status ? { status } : {};
  const res = await api.get(`${BASE}/worklist/supply/${configId}`, { params });
  return res.data;
};

export const getAllocationWorklist = async (configId, status = null) => {
  const params = status ? { status } : {};
  const res = await api.get(`${BASE}/worklist/allocation/${configId}`, { params });
  return res.data;
};

// =============================================================================
// TRM Decisions (Execution Layer)
// =============================================================================

export const getTRMDecisions = async (configId, filters = {}) => {
  const { trm_type, ...params } = filters;
  const path = trm_type
    ? `${BASE}/trm-decisions/${configId}/${trm_type}`
    : `${BASE}/trm-decisions/${configId}`;
  const res = await api.get(path, { params });
  return res.data;
};

export const submitTRMAction = async (payload) => {
  const res = await api.post(`${BASE}/trm-decisions/action`, payload);
  return res.data;
};

// =============================================================================
// Powell Allocation Timeline
// =============================================================================

export const getAllocationTimeline = async (configId, productId, locationId, daysPast = 5, daysFuture = 9) => {
  const res = await api.get(`/powell/allocations/${configId}/timeline`, {
    params: { product_id: productId, location_id: locationId, days_past: daysPast, days_future: daysFuture },
  });
  return res.data;
};

export const submitAllocationOverrides = async (configId, productId, locationId, overrides, reason = null) => {
  const res = await api.post(`/powell/allocations/${configId}/bulk-override`, {
    product_id: productId,
    location_id: locationId,
    overrides,
    reason,
  });
  return res.data;
};

// =============================================================================
// Context-Aware Explainability (Ask Why)
// =============================================================================

/**
 * Get context-aware explanation for a TRM decision.
 * Returns authority, guardrails, attribution, counterfactuals.
 */
export const askWhyTRMDecision = async (decisionId, level = 'NORMAL') => {
  const res = await api.get(`${BASE}/trm-decision/${decisionId}/ask-why`, {
    params: { level },
  });
  return res.data;
};

/**
 * Get context-aware explanation for a GNN node's output.
 * Returns neighbor attention, input saliency, and agent context.
 */
export const askWhyGNNNode = async (configId, nodeId, modelType = 'sop', level = 'NORMAL') => {
  const res = await api.get(`${BASE}/gnn-analysis/${configId}/node/${nodeId}/ask-why`, {
    params: { model_type: modelType, level },
  });
  return res.data;
};
