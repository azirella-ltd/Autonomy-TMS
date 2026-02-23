/**
 * Edge Agent API Service
 *
 * API client for PicoClaw fleet management, OpenClaw gateway management,
 * signal ingestion, channel configuration, and security audit.
 */

import { api } from './api';

// ============================================================================
// PicoClaw Fleet Management
// ============================================================================

export const picoClawApi = {
  /** Get fleet summary (total instances, healthy, warning, critical) */
  getFleetSummary: () => api.get('/api/v1/edge-agents/picoclaw/fleet/summary'),

  /** Get all PicoClaw instances with status */
  getFleetInstances: (params = {}) =>
    api.get('/api/v1/edge-agents/picoclaw/fleet/instances', { params }),

  /** Get single PicoClaw instance details */
  getInstance: (siteKey) =>
    api.get(`/api/v1/edge-agents/picoclaw/fleet/instances/${siteKey}`),

  /** Register a new PicoClaw instance */
  registerInstance: (data) =>
    api.post('/api/v1/edge-agents/picoclaw/fleet/instances', data),

  /** Update PicoClaw instance configuration */
  updateInstance: (siteKey, data) =>
    api.put(`/api/v1/edge-agents/picoclaw/fleet/instances/${siteKey}`, data),

  /** Remove PicoClaw instance */
  removeInstance: (siteKey) =>
    api.delete(`/api/v1/edge-agents/picoclaw/fleet/instances/${siteKey}`),

  /** Get heartbeat history for a site */
  getHeartbeats: (siteKey, params = {}) =>
    api.get(`/api/v1/edge-agents/picoclaw/fleet/instances/${siteKey}/heartbeats`, { params }),

  /** Get CDC alerts for a site */
  getAlerts: (siteKey, params = {}) =>
    api.get(`/api/v1/edge-agents/picoclaw/fleet/instances/${siteKey}/alerts`, { params }),

  /** Get fleet-wide alerts */
  getFleetAlerts: (params = {}) =>
    api.get('/api/v1/edge-agents/picoclaw/fleet/alerts', { params }),

  /** Acknowledge an alert */
  acknowledgeAlert: (alertId) =>
    api.post(`/api/v1/edge-agents/picoclaw/fleet/alerts/${alertId}/acknowledge`),

  /** Force send digest for a site */
  forceSendDigest: (siteKey) =>
    api.post(`/api/v1/edge-agents/picoclaw/fleet/instances/${siteKey}/digest`),

  /** Get service account info */
  getServiceAccounts: () =>
    api.get('/api/v1/edge-agents/picoclaw/service-accounts'),

  /** Create service account */
  createServiceAccount: (data) =>
    api.post('/api/v1/edge-agents/picoclaw/service-accounts', data),

  /** Rotate service account token */
  rotateToken: (accountId) =>
    api.post(`/api/v1/edge-agents/picoclaw/service-accounts/${accountId}/rotate`),

  /** Revoke service account */
  revokeServiceAccount: (accountId) =>
    api.delete(`/api/v1/edge-agents/picoclaw/service-accounts/${accountId}`),
};

// ============================================================================
// OpenClaw Gateway Management
// ============================================================================

export const openClawApi = {
  /** Get gateway status (running, version, channels connected) */
  getGatewayStatus: () => api.get('/api/v1/edge-agents/openclaw/gateway/status'),

  /** Get gateway configuration */
  getGatewayConfig: () => api.get('/api/v1/edge-agents/openclaw/gateway/config'),

  /** Update gateway configuration */
  updateGatewayConfig: (data) =>
    api.put('/api/v1/edge-agents/openclaw/gateway/config', data),

  /** Test gateway connectivity */
  testGateway: () => api.post('/api/v1/edge-agents/openclaw/gateway/test'),

  /** Get installed skills */
  getSkills: () => api.get('/api/v1/edge-agents/openclaw/skills'),

  /** Enable/disable a skill */
  toggleSkill: (skillId, enabled) =>
    api.put(`/api/v1/edge-agents/openclaw/skills/${skillId}`, { enabled }),

  /** Test a skill */
  testSkill: (skillId, testInput) =>
    api.post(`/api/v1/edge-agents/openclaw/skills/${skillId}/test`, { input: testInput }),

  /** Get channel connections */
  getChannels: () => api.get('/api/v1/edge-agents/openclaw/channels'),

  /** Update channel configuration */
  updateChannel: (channelId, data) =>
    api.put(`/api/v1/edge-agents/openclaw/channels/${channelId}`, data),

  /** Test channel connectivity */
  testChannel: (channelId) =>
    api.post(`/api/v1/edge-agents/openclaw/channels/${channelId}/test`),

  /** Get session activity log */
  getSessionLog: (params = {}) =>
    api.get('/api/v1/edge-agents/openclaw/sessions', { params }),

  /** Get LLM service status */
  getLLMStatus: () => api.get('/api/v1/edge-agents/openclaw/llm/status'),

  /** Update LLM configuration */
  updateLLMConfig: (data) =>
    api.put('/api/v1/edge-agents/openclaw/llm/config', data),
};

// ============================================================================
// Signal Ingestion
// ============================================================================

export const signalApi = {
  /** Get signal ingestion dashboard summary */
  getDashboard: (params = {}) =>
    api.get('/api/v1/signals/dashboard', { params }),

  /** Get recent signals */
  getSignals: (params = {}) =>
    api.get('/api/v1/signals/list', { params }),

  /** Get pending signals for review */
  getPendingSignals: (params = {}) =>
    api.get('/api/v1/signals/pending', { params }),

  /** Approve a signal */
  approveSignal: (signalId, override = {}) =>
    api.post(`/api/v1/signals/${signalId}/approve`, override),

  /** Reject a signal */
  rejectSignal: (signalId, reason) =>
    api.post(`/api/v1/signals/${signalId}/reject`, { reason }),

  /** Get signal details with confidence breakdown */
  getSignalDetails: (signalId) =>
    api.get(`/api/v1/signals/${signalId}`),

  /** Get correlated signal groups */
  getCorrelations: (params = {}) =>
    api.get('/api/v1/signals/correlations', { params }),

  /** Get forecast adjustment history from signals */
  getAdjustmentHistory: (params = {}) =>
    api.get('/api/v1/signals/adjustments', { params }),

  /** Revert a forecast adjustment */
  revertAdjustment: (adjustmentId) =>
    api.post(`/api/v1/signals/adjustments/${adjustmentId}/revert`),

  /** Get channel source configuration */
  getChannelSources: () =>
    api.get('/api/v1/signals/channel-sources'),

  /** Update channel source mapping */
  updateChannelSource: (channelId, data) =>
    api.put(`/api/v1/signals/channel-sources/${channelId}`, data),

  /** Get rate limiting status */
  getRateLimits: () =>
    api.get('/api/v1/signals/rate-limits'),

  /** Get source reliability metrics */
  getSourceReliability: () =>
    api.get('/api/v1/signals/source-reliability'),

  /** Update source reliability weight */
  updateSourceReliability: (source, weight) =>
    api.put(`/api/v1/signals/source-reliability/${source}`, { weight }),
};

// ============================================================================
// Security & Audit
// ============================================================================

export const securityApi = {
  /** Get security audit summary */
  getAuditSummary: () =>
    api.get('/api/v1/edge-agents/security/audit'),

  /** Get CVE status for installed versions */
  getCVEStatus: () =>
    api.get('/api/v1/edge-agents/security/cves'),

  /** Get pre-deployment checklist status */
  getChecklist: () =>
    api.get('/api/v1/edge-agents/security/checklist'),

  /** Update checklist item */
  updateChecklistItem: (itemId, checked) =>
    api.put(`/api/v1/edge-agents/security/checklist/${itemId}`, { checked }),

  /** Get integration health status */
  getIntegrationHealth: () =>
    api.get('/api/v1/edge-agents/security/integration-health'),

  /** Get activity log */
  getActivityLog: (params = {}) =>
    api.get('/api/v1/edge-agents/security/activity-log', { params }),

  /** Get prompt injection stats */
  getInjectionStats: () =>
    api.get('/api/v1/edge-agents/security/injection-stats'),
};
