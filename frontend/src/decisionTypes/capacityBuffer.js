/**
 * Capacity Buffer Agent — Reserve carrier capacity above forecast.
 *
 * Phase: ASSESS
 */
import { BarChart3 } from 'lucide-react';

export const capacityBufferType = {
  id: 'capacity_buffer',
  label: 'Capacity Buffer Agent',
  icon: BarChart3,
  phase: 'ASSESS',
  editableFields: [
    { key: 'buffer_loads', label: 'Buffer Loads', type: 'number' },
    {
      key: 'buffer_policy',
      label: 'Buffer Policy',
      type: 'select',
      options: ['fixed', 'pct_forecast', 'conformal'],
    },
  ],
  description: 'Reserve carrier capacity for surge and spot premiums',
};
