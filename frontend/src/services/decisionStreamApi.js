/**
 * Decision Stream API Service
 *
 * API client for the Decision Stream LLM-First UI.
 * Supports digest retrieval, decision actions, and conversational chat.
 */

import { api } from './api';

export const decisionStreamApi = {
  /**
   * Get the decision digest: pending decisions, alerts, and LLM synthesis.
   * @param {number} [configId] - Optional supply chain config ID
   */
  getDigest: (configId) =>
    api
      .get('/decision-stream/digest', { params: { config_id: configId } })
      .then((r) => r.data),

  /**
   * Act on a decision (accept/override/reject).
   * @param {Object} data - { decision_id, decision_type, action, override_reason_code?, override_reason_text?, override_values? }
   */
  actOnDecision: (data) =>
    api.post('/decision-stream/action', data).then((r) => r.data),

  /**
   * Force-refresh the digest (invalidates cache and re-synthesizes via LLM).
   * Use this for the refresh button instead of getDigest to bypass the cache.
   * @param {number} [configId] - Optional supply chain config ID
   */
  refreshDigest: (configId) =>
    api
      .post('/decision-stream/refresh', null, { params: { config_id: configId } })
      .then((r) => r.data),

  /**
   * Send a chat message with decision-context injection.
   * @param {Object} data - { message, conversation_id?, config_id? }
   */
  chat: (data) =>
    api.post('/decision-stream/chat', data).then((r) => r.data),

  /**
   * Get pre-computed reasoning for a specific decision.
   * Returns the decision_reasoning captured at decision time (no LLM call).
   * @param {number} decisionId - Decision ID
   * @param {string} decisionType - Decision type (atp, po_creation, rebalancing, etc.)
   */
  askWhy: (decisionId, decisionType) =>
    api
      .get('/decision-stream/ask-why', {
        params: { decision_id: decisionId, decision_type: decisionType },
      })
      .then((r) => r.data),

  /**
   * Get time series context for a decision (forecast, inventory, or lead time).
   * @param {Object} params - { decision_type, product_id, site_id, config_id }
   */
  getDecisionTimeSeries: (params) =>
    api
      .get('/decision-stream/time-series', { params })
      .then((r) => r.data),

  /**
   * Analyze override reason and get context-specific follow-up questions.
   * @param {Object} body - { reason_code, decision_type, product_name, site_name, override_mode }
   */
  analyzeOverrideReason: (body) =>
    api
      .post('/decision-stream/analyze-override-reason', body)
      .then((r) => r.data),
};

export default decisionStreamApi;
