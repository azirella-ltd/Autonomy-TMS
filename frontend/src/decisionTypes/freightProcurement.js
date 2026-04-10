/**
 * Freight Procurement Agent — Carrier waterfall tendering.
 *
 * Phase: ACQUIRE
 */
import { Gavel } from 'lucide-react';

export const freightProcurementType = {
  id: 'freight_procurement',
  label: 'Freight Procurement Agent',
  icon: Gavel,
  phase: 'ACQUIRE',
  editableFields: [
    { key: 'carrier_id', label: 'Carrier', type: 'text' },
    { key: 'rate_override', label: 'Rate Override ($)', type: 'number' },
    {
      key: 'action',
      label: 'Action',
      type: 'select',
      options: ['tender', 'defer', 'spot', 'broker'],
    },
  ],
  description: 'Carrier waterfall tendering with rate optimization',
};
