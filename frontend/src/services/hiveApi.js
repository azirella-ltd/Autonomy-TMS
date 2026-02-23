/**
 * Hive API Service
 *
 * Client methods for hive health, scenarios, and authorization endpoints.
 */

import { api } from './api';

const hiveApi = {
  // ---- Hive Health & Status -----------------------------------------------

  /** Get hive status for a site (urgency vector, signal bus, etc.) */
  getHiveStatus: (siteKey) =>
    api.get(`/api/v1/site-agent/hive/status/${siteKey}`),

  /** Get decision cycle phase info for a site */
  getDecisionCycle: (siteKey) =>
    api.get(`/api/v1/site-agent/hive/decision-cycle/${siteKey}`),

  /** Run a decision cycle */
  runDecisionCycle: (siteKey) =>
    api.post(`/api/v1/site-agent/hive/decision-cycle/${siteKey}/run`),

  /** Get hive health metrics */
  getHiveHealth: (siteKey) =>
    api.get(`/api/v1/site-agent/hive/health/${siteKey}`),

  // ---- Planning Scenarios -------------------------------------------------

  /** Create a scenario branch */
  createBranch: (parentId, variableDeltas) =>
    api.post('/api/v1/scenarios/branch', { parent_id: parentId, variable_deltas: variableDeltas }),

  /** Evaluate a scenario (run what-if) */
  evaluateScenario: (scenarioId) =>
    api.post(`/api/v1/scenarios/${scenarioId}/evaluate`),

  /** Promote a scenario (approve + prune siblings) */
  promoteScenario: (scenarioId) =>
    api.post(`/api/v1/scenarios/${scenarioId}/promote`),

  /** Get scenario tree */
  getScenarioTree: (rootId) =>
    api.get(`/api/v1/scenarios/${rootId}/tree`),

  /** Compare scenarios side-by-side */
  compareScenarios: (ids) =>
    api.get(`/api/v1/scenarios/compare`, { params: { ids: ids.join(',') } }),

  // ---- Authorization Protocol ---------------------------------------------

  /** Get all authorization threads */
  getAuthThreads: () =>
    api.get('/api/v1/authorization-protocol/threads'),

  /** Get a single authorization thread */
  getAuthThread: (threadId) =>
    api.get(`/api/v1/authorization-protocol/threads/${threadId}`),

  /** Submit an authorization request */
  submitAuthRequest: (body) =>
    api.post('/api/v1/authorization-protocol/threads', body),

  /** Respond to an authorization thread */
  respondToThread: (threadId, body) =>
    api.post(`/api/v1/authorization-protocol/threads/${threadId}/respond`, body),

  /** Resolve an authorization thread (human) */
  resolveThread: (threadId, body) =>
    api.post(`/api/v1/authorization-protocol/threads/${threadId}/resolve`, body),

  /** Escalate an authorization thread */
  escalateThread: (threadId) =>
    api.post(`/api/v1/authorization-protocol/threads/${threadId}/escalate`),

  /** Get authority map */
  getAuthorityMap: () =>
    api.get('/api/v1/authorization-protocol/authority-map'),

  /** Get authorization stats */
  getAuthStats: () =>
    api.get('/api/v1/authorization-protocol/stats'),

  /** Check SLA timeouts */
  checkSLATimeouts: () =>
    api.post('/api/v1/authorization-protocol/sla-check'),
};

export default hiveApi;
