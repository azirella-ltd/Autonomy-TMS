/**
 * TMS Capabilities Client Adapter
 *
 * Implements the @autonomy/ui-core CapabilitiesClient interface against
 * the TMS backend's /api/capabilities/me endpoint. Used by
 * <CapabilitiesProvider client={tmsCapabilitiesClient}> to drive
 * useCapabilities() hook in shared components.
 */
import { api } from './api';

export const tmsCapabilitiesClient = {
  /**
   * Fetch the current user's capability list from TMS backend.
   * Returns an array of capability strings (e.g., ['view_decision_stream',
   * 'manage_freight_procurement_worklist', ...]).
   */
  fetchCapabilities: async () => {
    try {
      const { data } = await api.get('/capabilities/me');
      return data?.capabilities || [];
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('[TMS] Failed to fetch capabilities:', err);
      return [];
    }
  },
};

export default tmsCapabilitiesClient;
