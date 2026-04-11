/**
 * TMS Decision Stream Client Adapter
 *
 * Wraps the existing decisionStreamApi.js calls to implement the
 * @azirella-ltd/autonomy-frontend DecisionStreamClient interface. The shared
 * Decision Stream components (DecisionStream, DecisionCard, etc.)
 * consume this via <DecisionStreamProvider client={...}>.
 *
 * Method names match the package contract; the bodies delegate to
 * the existing TMS backend endpoints.
 */
import { api } from './api';
import { decisionStreamApi } from './decisionStreamApi';

export const tmsDecisionStreamClient = {
  /**
   * Fetch the current decision digest.
   */
  getDigest: async (opts = {}) => {
    return decisionStreamApi.getDigest(opts.config_id);
  },

  /**
   * Force-refresh and return new digest.
   */
  refresh: async (opts = {}) => {
    return decisionStreamApi.refreshDigest(opts.config_id);
  },

  /**
   * Submit an action on a decision.
   *
   * Maps the @azirella-ltd/autonomy-frontend action enum to the TMS backend payload:
   *   - 'accept'   → { action: 'accept' }
   *   - 'inspect'  → { action: 'inspect' }
   *   - 'modify'   → { action: 'modify', override_*: ... }
   *   - 'cancel'   → { action: 'cancel', override_*: ... }
   *   - 'reject'   → mapped to 'cancel'
   *   - 'override' → mapped to 'modify' (high-level alias)
   */
  actOnDecision: async (decisionId, request) => {
    let action = request.action;
    if (action === 'reject') action = 'cancel';
    if (action === 'override') action = 'modify';

    return decisionStreamApi.actOnDecision({
      decision_id: decisionId,
      action,
      override_reason_code: request.reason_code,
      override_reason_text: request.reason_text,
      override_values: request.override_values || null,
    });
  },

  /**
   * Conversational chat with optional decision context.
   */
  chat: async (message, opts = {}) => {
    return decisionStreamApi.chat({
      message,
      conversation_id: opts.conversation_id,
      config_id: opts.config_id,
      decision_id: opts.decision_id,
    });
  },

  /**
   * Get the agent's reasoning for a specific decision.
   */
  askWhy: async (decisionId, decisionType) => {
    return decisionStreamApi.askWhy(decisionId, decisionType);
  },

  /**
   * Get time-series context for a decision (forecast, inventory, etc.).
   */
  getDecisionTimeSeries: async (context) => {
    return decisionStreamApi.getDecisionTimeSeries(context);
  },

  /**
   * Analyze an override reason and get follow-up questions.
   */
  analyzeOverrideReason: async (params) => {
    return decisionStreamApi.analyzeOverrideReason(params);
  },

  /**
   * Bulk Mark All Inspected — calls the upstream /mark-all-reviewed endpoint.
   */
  markAllReviewed: async (request) => {
    const { data } = await api.post(
      '/decision-stream/mark-all-reviewed',
      { decision_ids: request.decision_ids },
      { params: { config_id: request.config_id } }
    );
    return data;
  },
};

export default tmsDecisionStreamClient;
