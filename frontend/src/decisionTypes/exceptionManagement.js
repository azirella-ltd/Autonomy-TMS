/**
 * Exception Management Agent — Delay/damage/refusal/customs resolution.
 *
 * Phase: ASSESS
 */
import { ShieldAlert } from 'lucide-react';

export const exceptionManagementType = {
  id: 'exception_management',
  label: 'Exception Mgmt Agent',
  icon: ShieldAlert,
  phase: 'ASSESS',
  editableFields: [
    {
      key: 'resolution_action',
      label: 'Resolution',
      type: 'select',
      options: ['retender', 'reroute', 'partial_deliver', 'escalate', 'write_off'],
    },
    { key: 'cost_authorization', label: 'Cost Authorization ($)', type: 'number' },
  ],
  description: 'Resolves delays, damage, refusals, temperature excursions, customs holds',
};
